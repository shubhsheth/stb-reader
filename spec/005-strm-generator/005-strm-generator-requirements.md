# Spec: .strm Generator — Stalker Portal VOD Library Sync

## Objective

Build a library management layer on top of the existing `stb-reader` proxy. Users add movies
or series to a persistent library; the system generates Jellyfin/Emby-compatible `.strm` files
on disk that point back to the proxy server for stream resolution. When new episodes appear on
the portal, a sync operation generates new `.strm` files without duplicating existing ones.

Users are home-media operators running Jellyfin or Emby who want their portal VOD content to
appear as a native library (with metadata, posters, and episode tracking) rather than a flat
IPTV channel list.

Success looks like: add a series, run sync, open Jellyfin — the show appears with seasons,
episode thumbnails, and descriptions pulled from TMDB/TVDb, and episodes play via the proxy.

---

## User Stories

- As a user, I want to add content to my library by ID so that the system automatically
  determines whether it is a movie or series and generates the right `.strm` files.
- As a user, I want to sync a series so that new episodes added to the portal since my last
  sync get new `.strm` files automatically.
- As a user, I want the library to sync on a schedule so that new episodes appear without
  manual intervention.
- As a user, I want to remove content from my library so that the `.strm` files and DB records
  are cleaned up.
- As a user, I want to list my library so that I can see what has been added and when it was
  last synced.

---

## Functional Requirements

- FR-1: `POST /library/add/{content_id}` fetches the content record from the portal, inspects
  `is_series`, and branches accordingly:
  - If movie (`is_series=false`): writes one `.strm` file to disk.
  - If series (`is_series=true`): walks the portal tree (seasons → episodes → files) and writes
    one `.strm` file per episode.
  Returns HTTP 201 with the created library item and a count of `.strm` files written.
  Returns HTTP 409 if the content is already in the library.
- FR-3: `GET /library` returns a JSON array of all library items, each including `content_id`,
  `name`, `year`, `is_series`, `added_at`, `last_synced_at`, and `strm_count`.
- FR-4: `DELETE /library/{content_id}` removes the library item and all associated `.strm`
  files from disk and from the DB. Returns HTTP 204. Returns HTTP 404 if not in the library.
- FR-5: `POST /library/sync/{content_id}` re-walks the portal tree for a series and creates
  `.strm` files for any episodes not already represented in the DB. Also detects name/year
  changes (see FR-18). Returns HTTP 200 with a count of new files created. Is a no-op
  (returns 0) for movies. Returns HTTP 404 if not in the library.
- FR-6: `POST /library/sync` runs FR-5 logic for every series in the library. Returns HTTP 200
  with a per-item summary of new files created.
- FR-18: During sync, the portal content record is re-fetched. If `name` or `year` differs
  from the value stored in `library_items`, all `.strm` files for that content are moved to
  the new path on disk, all `strm_path` values in `strm_files` are updated, and
  `library_items.name` / `library_items.year` are updated. Old (now-empty) directories are
  removed.
- FR-7: `.strm` file content for a movie is a single line:
  `{server_base_url}/vod/content/{content_id}/stream`
- FR-8: `.strm` file content for an episode file is a single line:
  `{server_base_url}/vod/content/{content_id}/seasons/{season_id}/episodes/{episode_id}/files/{file_id}/stream`
- FR-9: File path on disk for a movie follows Jellyfin naming:
  `{output_dir}/Movies/{sanitized_name} ({year})/{sanitized_name} ({year}).strm`
- FR-10: File path on disk for an episode follows Jellyfin naming:
  `{output_dir}/TV/{sanitized_name} ({year})/Season {season_num:02d}/{sanitized_name} ({year}) - S{season_num:02d}E{episode_num:02d} - {sanitized_episode_name}.strm`
- FR-11: Filename sanitisation replaces `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` with `-`.
- FR-12: Season number is parsed from the season `name` field (e.g. `"Season 2"` → `2`). If
  parsing fails, fall back to the season's 1-based position in the list returned by the portal.
- FR-13: Episode number comes from the episode's `series_number` field (cast to int). If zero
  or absent, fall back to the episode's 1-based position in its season list.
- FR-14: The portal returns exactly one file per episode. That file's `file_id` and `cmd` are
  used directly. No `.strm` file is created for the episode if the portal returns zero files.
- FR-15: The DB records which `file_id` was used per episode; re-running sync skips episodes
  that already have a `strm_files` row, even if the portal now returns different files.
- FR-16: State is persisted in a SQLite database at the path configured by `strm_db_path`.
  Schema is created automatically on server startup if not present.
- FR-17: Four new settings are added to `server/config.py` (all read from `.env`):
  - `strm_output_dir` — root directory for `.strm` files (required)
  - `strm_server_base_url` — base URL used in `.strm` file content; must be reachable by
    whichever party fetches the stream (see NFR-4 for options). Required.
  - `strm_db_path` — path to the SQLite DB file (default: `./library.db`)
  - `strm_sync_interval_hours` — how often the background sync runs in hours (default: `6`;
    set to `0` to disable automatic sync)
- FR-19: On server startup, if `strm_sync_interval_hours > 0`, an `asyncio` background task
  is started that runs the FR-6 sync logic on the configured interval. The task is cancelled
  cleanly during server shutdown via the FastAPI lifespan context.

---

## Non-Functional Requirements

- NFR-1: No new Python runtime dependencies — `sqlite3`, `pathlib`, and `asyncio` are all
  stdlib; background scheduling uses `asyncio.create_task` (no third-party scheduler).
- NFR-2: A full series sync (all pages of all seasons for all episodes) makes the minimum
  number of portal requests — one per page of results, no redundant calls.
- NFR-3: The background sync task does not block the FastAPI event loop; all portal I/O
  inside the task runs in a thread pool via `asyncio.to_thread`.
- NFR-4: `strm_server_base_url` must be set to a URL reachable by whoever fetches the stream.
  Jellyfin's playback behaviour determines who that is:
  - **Transcoding / server-proxied playback:** only the Jellyfin server fetches the URL.
    `http://stb-reader:8000` (Docker service name) works when both containers share a Docker
    network. Recommended starting point.
  - **Direct play:** the client device fetches the URL directly. The Docker service name is
    not resolvable outside Docker; use the host LAN IP instead
    (`http://192.168.1.x:8000`). Works on LAN only — breaks for remote clients.
  - **Remote / production access:** put stb-reader behind a reverse proxy with a public
    hostname (`https://stb.yourdomain.com`). Works for all playback modes and all clients
    including remote. Required upgrade when remote access is needed.

---

## Out of Scope

- Live TV `.strm` generation.
- Quality profile selection (the portal returns exactly one file per episode).
- A web UI — this is API-only.
- Jellyfin library scan notifications after file generation.
- Metadata override files (`.nfo` sidecar files).
- Movie quality variants (the portal does not expose a files list for standalone movies).

---

## Assumptions

- A-1: The portal returns exactly one file per episode; no quality selection is needed.
- A-2: `content_id` uniquely identifies a piece of content on the portal for the lifetime of
  a session and across re-authentications.
- A-3: Name changes on the portal are handled at sync time (FR-18). Files are moved on disk
  to match the new name, consistent with how Radarr/Sonarr handle title changes from TMDB.
- A-4: Output directories are created with `parents=True, exist_ok=True`; no pre-existing
  directory structure is required.
- A-5: `strm_output_dir` and `strm_server_base_url` are validated at startup (non-empty);
  the server refuses to start if either is missing.
- A-6: The default deployment has Jellyfin and stb-reader in the same Docker Compose file on
  the same network, with `STRM_SERVER_BASE_URL=http://stb-reader:8000`. Upgrading to a
  reverse proxy hostname later requires only changing this one env var and re-running sync
  to regenerate `.strm` files with the new URL.

---

## Tech Stack

Python 3.11+, FastAPI, `sqlite3` (stdlib), `pathlib` (stdlib), `asyncio` (stdlib),
`requests`, `pydantic-settings`, `pytest` + `responses` + `httpx`.

---

## Commands

```
Test:  pytest tests/
Dev:   uvicorn server.main:app --reload
```

---

## Project Structure

```
server/
  db.py              → SQLite schema, connection factory, CRUD functions
  sync.py            → portal-walking logic: walk_series(), write_strm()
  routes/
    live_tv.py       → (unchanged)
    vod.py           → (unchanged)
    library.py       → FastAPI router for /library endpoints
  config.py          → add strm_output_dir, strm_server_base_url, strm_db_path, strm_sync_interval_hours
  main.py            → mount /library router, init DB on startup, start background sync task
tests/
  test_library_db.py     → unit tests for server/db.py CRUD
  test_library_sync.py   → unit tests for server/sync.py with mocked portal calls
  test_library_routes.py → integration tests for server/routes/library.py endpoints
spec/
  005-strm-generator/
    005-strm-generator-requirements.md   ← this file
    005-strm-generator-plan.md
    005-strm-generator-implement.md
```

---

## Code Style

Match existing conventions (`dataclasses`, `str()` casts, `pathlib.Path`):

```python
# db.py — plain functions, sqlite3 connection passed in or opened via factory
def add_library_item(db: sqlite3.Connection, content_id: str, name: str, year: str, is_series: bool) -> None:
    db.execute(
        "INSERT INTO library_items (content_id, name, year, is_series, added_at) VALUES (?, ?, ?, ?, ?)",
        (content_id, name, year, int(is_series), _now()),
    )
    db.commit()

# sync.py — pure function, returns list of written paths
def write_strm(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(url + "\n")

# server/routes/library.py — thin, delegates to server/db.py + server/sync.py
@router.post("/library/add/{content_id}", status_code=201)
def add_content(content_id: str, request: Request):
    ...
```

SQLite schema:

```sql
CREATE TABLE IF NOT EXISTS library_items (
    content_id     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    year           TEXT NOT NULL,
    is_series      INTEGER NOT NULL,   -- 0=movie, 1=series
    added_at       TEXT NOT NULL,      -- ISO 8601 UTC
    last_synced_at TEXT                -- NULL until first sync
);

CREATE TABLE IF NOT EXISTS strm_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id  TEXT NOT NULL REFERENCES library_items(content_id),
    season_id   TEXT,                  -- NULL for movies
    episode_id  TEXT,                  -- NULL for movies
    file_id     TEXT NOT NULL,
    strm_path   TEXT NOT NULL UNIQUE,  -- absolute path on disk
    created_at  TEXT NOT NULL
);
```

---

## Testing Strategy

Framework: `pytest` with `responses` for portal HTTP mocking, `httpx` for FastAPI test client.
Test locations: `tests/test_library_db.py`, `tests/test_library_sync.py`,
`tests/test_library_routes.py`.

Coverage expectations:
- `db.py`: CRUD happy paths + duplicate insert raises `IntegrityError` (tested directly).
- `sync.py`: movie `.strm` write, series walk (2 seasons × 2 episodes), zero-files episode
  skipped, season number fallback to index, name-change triggers file rename on disk.
- Routes: 201 created, 409 already-exists, 404 not-found, 204 delete, sync returns correct counts.
- Background scheduler: tested by asserting the asyncio task is created and cancelled cleanly
  (no actual sleep in tests — interval is set to 0 or task is cancelled immediately).
- All portal HTTP calls in sync tests are mocked with `responses`; no real portal is contacted.

---

## Boundaries

- **Always:** Run `pytest tests/` before committing; create parent directories before writing
  `.strm` files; sanitise filenames before building paths.
- **Ask first:** Changing existing route URL shapes; altering the SQLite schema after it has
  been defined (may require migration logic).
- **Never:** Write raw portal stream URLs into `.strm` files (always use the proxy URL);
  delete `.strm` files that are not recorded in `strm_files` table; expose `cmd` values in
  any API response or URL path.

---

## Success Criteria

- `POST /library/add/{id}` with a movie content ID returns HTTP 201 and the `.strm` file
  exists at the correct Jellyfin-compatible path containing only the proxy URL.
- `POST /library/add/{id}` with a series content ID returns HTTP 201 and `.strm` files exist
  for every episode, named with correct `SxxExx` convention.
- `GET /library` lists all added items with correct `strm_count`.
- `DELETE /library/{id}` removes the DB record and deletes all `.strm` files from disk.
- `POST /library/sync/{id}` creates `.strm` files for new episodes, does not duplicate
  existing ones, and renames files on disk when the portal name/year has changed.
- `POST /library/sync` applies sync to all series in the library.
- The background task runs the full sync automatically on the configured interval; setting
  `strm_sync_interval_hours=0` disables it.
- Duplicate `POST /library/add/{id}` returns HTTP 409.
- `pytest tests/` passes with no regressions across the full test suite.
- `.strm` filenames contain no characters from the set `/\:*?"<>|`.

---

## Open Questions

None — all design decisions confirmed by the user prior to spec authorship.
