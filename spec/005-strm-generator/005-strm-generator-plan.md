# Plan: .strm Generator — Stalker Portal VOD Library Sync

## Component Overview

Three new files, two modified files, one updated docker-compose:

```
server/db.py              ← new: SQLite schema + CRUD
server/sync.py            ← new: portal walking, .strm writing, name-change rename
server/routes/library.py  ← new: /library endpoints
server/config.py          ← modified: 4 new settings
server/main.py            ← modified: mount router, init DB, start background task
docker-compose.yml        ← modified: add Jellyfin service + shared volume
.env.example              ← modified: document new env vars
```

Test files mirror the source:

```
tests/test_library_db.py      ← unit tests for server/db.py
tests/test_library_sync.py    ← unit tests for server/sync.py (portal mocked)
tests/test_library_routes.py  ← integration tests for /library routes
```

---

## Dependency Order

Each phase depends on the one before it. Phases 1–3 can be developed and tested in
isolation before any route or wiring work begins.

```
Phase 1: Config
    ↓
Phase 2: DB layer (server/db.py)
    ↓
Phase 3: Sync logic (server/sync.py)
    ↓
Phase 4: Routes (server/routes/library.py)
    ↓
Phase 5: main.py wiring + background task
    ↓
Phase 6: Docker + .env.example
    ↓
Phase 7: Docs
```

---

## Phase 1 — Config

**Files:** `server/config.py`, `.env.example`

Add four settings (FR-17):

```python
strm_output_dir: str          # required — validated non-empty at startup (A-5)
strm_server_base_url: str     # required — validated non-empty at startup (A-5)
strm_db_path: str = "./library.db"
strm_sync_interval_hours: int = 6
```

`.env.example` additions:

```
# Library / .strm generator
STRM_OUTPUT_DIR=/library
STRM_SERVER_BASE_URL=http://stb-reader:8000
STRM_DB_PATH=./library.db
STRM_SYNC_INTERVAL_HOURS=6
```

No tests needed for config itself — validation is covered by the startup test in Phase 5.

---

## Phase 2 — DB Layer (`server/db.py`)

**Files:** `server/db.py`, `tests/test_library_db.py`

### Schema

```sql
CREATE TABLE IF NOT EXISTS library_items (
    content_id     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    year           TEXT NOT NULL,
    is_series      INTEGER NOT NULL,
    added_at       TEXT NOT NULL,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS strm_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id  TEXT NOT NULL REFERENCES library_items(content_id),
    season_id   TEXT,
    episode_id  TEXT,
    file_id     TEXT NOT NULL,
    strm_path   TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);
```

### Public functions

```python
def init_db(path: str) -> sqlite3.Connection
def add_library_item(db, content_id, name, year, is_series) -> None   # raises IntegrityError on duplicate
def get_library_items(db) -> list[dict]                                # includes strm_count per item
def get_library_item(db, content_id) -> dict | None
def delete_library_item(db, content_id) -> list[str]                  # returns list of strm_paths to delete
def add_strm_file(db, content_id, season_id, episode_id, file_id, strm_path) -> None
def get_strm_files(db, content_id) -> list[dict]
def episode_exists(db, content_id, season_id, episode_id) -> bool     # FR-15: skip if already in DB
def update_library_item_name(db, content_id, name, year) -> None      # FR-18
def update_strm_path(db, old_path, new_path) -> None                  # FR-18
def set_last_synced(db, content_id) -> None
```

`delete_library_item` returns the `strm_path` list so the caller can remove files from
disk before or after the DB delete (sync.py handles the file deletion).

### Tests (`tests/test_library_db.py`)

- `init_db` creates both tables
- `add_library_item` round-trips correctly
- Duplicate `content_id` raises `sqlite3.IntegrityError`
- `get_library_items` returns `strm_count` = number of `strm_files` rows
- `delete_library_item` returns paths and cascades rows
- `episode_exists` returns True only after `add_strm_file`

---

## Phase 3 — Sync Logic (`server/sync.py`)

**Files:** `server/sync.py`, `tests/test_library_sync.py`

This is the heaviest phase. All portal calls go through the existing `VODService`
(already on `request.app.state.client.vod`).

### Helper functions

```python
def sanitize(name: str) -> str
    # FR-11: replace /\:*?"<>| with -

def movie_strm_path(output_dir: str, name: str, year: str) -> Path
    # FR-9: {output_dir}/Movies/{sanitized} ({year})/{sanitized} ({year}).strm

def episode_strm_path(output_dir, name, year, season_num, ep_num, ep_name) -> Path
    # FR-10: {output_dir}/TV/{name} ({year})/Season {NN}/{name} ({year}) - SnnEnn - {ep_name}.strm

def parse_season_num(season_name: str, fallback: int) -> int
    # FR-12: re.search(r'\d+', name) → int, else fallback

def write_strm(path: Path, url: str) -> None
    # creates parents, writes url + newline
```

### Core functions

**`find_content_by_id(vod, content_id) -> Content`**

Pages through `vod.get_content(category_id="*", page=n)` until it finds the item with
matching `id`. Short-circuits as soon as found. Raises `NotFoundError` if exhausted.
Used at add time (FR-1) and sync time (FR-18) to get current name/year from portal.

**`add_content(db, vod, output_dir, server_base, content_id) -> int`** (FR-1)

1. Call `find_content_by_id` to get `name`, `year`, `is_series`
2. `add_library_item(db, ...)` — raises `IntegrityError` if duplicate (caller maps to 409)
3. If movie: build path (FR-9), write `.strm` (FR-7), `add_strm_file(db, ...)`; return 1
4. If series: call `_write_series_strm_files`; return count

**`_write_series_strm_files(db, vod, output_dir, server_base, content_id, name, year) -> int`**

```
for season in vod.get_seasons(content_id):
    season_num = parse_season_num(season.name, fallback=index+1)
    for episode in vod.get_episodes(content_id, season.id):
        if episode_exists(db, content_id, season.id, episode.id):
            continue                          # FR-15: skip already-written
        files = vod.get_episode_files(content_id, season.id, episode.id)
        if not files:
            continue                          # FR-14: skip if portal returns no files
        file = files[0]
        ep_num = int(episode.series_number) or (index+1)   # FR-13
        path = episode_strm_path(output_dir, name, year, season_num, ep_num, episode.name)
        url = f"{server_base}/vod/content/{content_id}/seasons/{season.id}/episodes/{episode.id}/files/{file.id}/stream"
        write_strm(path, url)                 # FR-8
        add_strm_file(db, content_id, season.id, episode.id, file.id, str(path))
        count += 1
return count
```

**`sync_item(db, vod, output_dir, server_base, content_id) -> int`** (FR-5, FR-15, FR-18)

1. Fetch `item = get_library_item(db, content_id)` — caller raises 404 if None
2. Return 0 immediately if `item["is_series"] == 0` (movie no-op)
3. `current = find_content_by_id(vod, content_id)` to get current name/year
4. If name or year changed (FR-18): call `_rename_strm_files(db, item, current)`
5. Call `_write_series_strm_files(...)` with updated name/year; return new count
6. `set_last_synced(db, content_id)`

**`_rename_strm_files(db, old_item, new_content)`** (FR-18)

```
for file_row in get_strm_files(db, content_id):
    old_path = Path(file_row["strm_path"])
    new_path = (rebuild path with new name/year)
    update_strm_path(db, str(old_path), str(new_path))   # DB first
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.rename(new_path)
# remove now-empty old directories
update_library_item_name(db, content_id, new_content.name, new_content.year)
```

DB is updated before the filesystem move. If the process crashes mid-rename, the
`strm_path` in the DB points to the new location; on next sync the missing old file
is a no-op (the episode already has a row so it won't be re-added).

**`sync_all(db, vod, output_dir, server_base) -> list[dict]`** (FR-6)

Iterates all series in `get_library_items`, calls `sync_item` for each, returns
`[{"content_id": ..., "new_files": n}, ...]`.

**`delete_content(db, content_id) -> None`** (FR-4)

1. `paths = delete_library_item(db, content_id)` (DB first)
2. For each path: `Path(p).unlink(missing_ok=True)`
3. Remove now-empty parent directories

### Tests (`tests/test_library_sync.py`)

Use `tmp_path` fixture (pytest) for output_dir. Mock portal via `responses` library.

- `sanitize` strips all forbidden characters
- `parse_season_num` extracts digit; falls back to index on non-numeric name
- `movie_strm_path` / `episode_strm_path` produce correct Jellyfin paths
- `add_content` movie: one `.strm` file written with correct proxy URL
- `add_content` series: 2 seasons × 2 episodes → 4 `.strm` files
- Episode with zero files is skipped (FR-14)
- `sync_item` skips already-existing episodes (FR-15)
- `sync_item` detects name change, renames files and dirs (FR-18)
- `sync_all` aggregates counts across series

---

## Phase 4 — Routes (`server/routes/library.py`)

**Files:** `server/routes/library.py`, `tests/test_library_routes.py`

Routes are thin: validate inputs, call sync/db functions, map exceptions to HTTP codes.

```python
router = APIRouter(tags=["library"])

@router.post("/library/add/{content_id}", status_code=201)
@router.get("/library")
@router.delete("/library/{content_id}", status_code=204)
@router.post("/library/sync/{content_id}")
@router.post("/library/sync")
```

Exception mapping:
- `sqlite3.IntegrityError` → HTTP 409
- `NotFoundError` (from stb_reader) → HTTP 404

The `db` connection and `vod` client are accessed via `request.app.state`.

### Tests (`tests/test_library_routes.py`)

Use the existing `TestClient` + `responses` pattern from `tests/test_server.py`.

- `POST /library/add/{id}` movie → 201, `.strm` file exists
- `POST /library/add/{id}` series → 201, correct file count
- `POST /library/add/{id}` duplicate → 409
- `GET /library` → lists items with correct `strm_count`
- `DELETE /library/{id}` → 204, files removed from disk
- `DELETE /library/{id}` unknown → 404
- `POST /library/sync/{id}` → 200, returns new file count
- `POST /library/sync/{id}` unknown → 404
- `POST /library/sync` → 200, per-item summary

---

## Phase 5 — main.py Wiring + Background Task

**Files:** `server/main.py`

Changes to the existing `lifespan` context manager:

```python
@asynccontextmanager
async def lifespan(app):
    settings = Settings()
    # ... existing auth setup ...
    db = init_db(settings.strm_db_path)
    app.state.db = db
    app.state.settings = settings
    from .routes.library import router as library_router
    app.include_router(library_router)

    task = None
    if settings.strm_sync_interval_hours > 0:
        async def _sync_loop():
            while True:
                await asyncio.sleep(settings.strm_sync_interval_hours * 3600)
                await asyncio.to_thread(
                    sync_all, db, app.state.client.vod,
                    settings.strm_output_dir, settings.strm_server_base_url,
                )
        task = asyncio.create_task(_sync_loop())
    yield
    if task:
        task.cancel()
```

The sync runs *after* sleeping, not immediately on startup — avoids a flood of portal
calls every time the server restarts.

---

## Phase 6 — Docker + .env.example

**Files:** `docker-compose.yml`, `.env.example`

`docker-compose.yml`:

```yaml
services:
  stb-reader:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - strm_library:/library
    restart: unless-stopped

  jellyfin:
    image: jellyfin/jellyfin
    volumes:
      - strm_library:/media/library:ro
      - jellyfin_config:/config
      - jellyfin_cache:/cache
    ports:
      - "8096:8096"
    restart: unless-stopped

volumes:
  strm_library:
  jellyfin_config:
  jellyfin_cache:
```

Both services share the `strm_library` volume. stb-reader writes; Jellyfin reads
(`:ro`). Both are on the default Compose network, so `http://stb-reader:8000` resolves
from the Jellyfin container.

---

## Phase 7 — Docs

**Files:** `AGENTS.md`, `docs/library.md`

- `AGENTS.md`: add new endpoints, new env vars, new commands
- `docs/library.md`: new file documenting the library API and deployment options
  (Docker service name / LAN IP / reverse proxy — NFR-4)

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `find_content_by_id` is O(n pages) | Short-circuit on first match; one-time cost at add, infrequent at sync |
| FR-18 rename crash leaves DB/disk inconsistent | DB updated first; on next sync the episode row already exists so it won't be re-added, but the old physical file may be orphaned — acceptable for this iteration |
| Background task fires while manual sync is in flight | Both operate on the same SQLite connection; `episode_exists` check (FR-15) ensures no duplicates regardless of race |
| Portal returns `series_number = "0"` or empty string | FR-13 fallback to 1-based position in episode list |
| Season name not matching `\d+` pattern | FR-12 fallback to 1-based position in season list |
