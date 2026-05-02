# Plan 006: Portal Content Sync

## Implementation Order

Dependencies flow in one direction: DB schema first, then sync logic, then routes, then wiring. Each phase can be verified independently before the next begins.

```
Phase A: DB schema (db.py)
    ↓
Phase B: Config (config.py)
    ↓
Phase C: Sync engine (vod_sync.py)
    ↓
Phase D: VOD routes — sync + search (routes/vod.py)
    ↓
Phase E: Library routes — rewrite for vod_content (routes/library.py + sync.py)
    ↓
Phase F: Wiring (main.py)
    ↓
Phase G: Tests
```

---

## Phase A — DB Schema (`server/db.py`)

**What changes:**
- `init_db` gets the new `vod_content`, `vod_categories`, `vod_content_category`, `vod_content_fts`, and `vod_sync_state` tables added to its `executescript` block.
- `strm_files` FK comment updated (schema unchanged, FK target is now `vod_content` but SQLite doesn't enforce FKs by default so no structural change needed).
- `library_items` table removed from `executescript`.
- All CRUD functions rewritten for `vod_content`:
  - `add_library_item` → `add_to_library(db, content_id)` — sets `in_library=1`, `added_at=now()`
  - `get_library_items` → reads `WHERE in_library=1`, subquery for `strm_count`
  - `get_library_item` → reads from `vod_content` by content_id
  - `delete_library_item` → sets `in_library=0`, clears `added_at`/`last_synced_at`, returns `strm_paths`
  - `set_last_synced` → updates `last_synced_at` on `vod_content`
  - `episode_exists` — unchanged, still queries `strm_files`
  - `add_strm_file` — unchanged
  - `get_strm_files` — unchanged
- New functions for portal sync:
  - `upsert_vod_content(db, row: dict) -> dict | None` — INSERT OR REPLACE, returns old row if exists (for FR-21 similarity check)
  - `get_vod_content(db, content_id) -> dict | None`
  - `search_vod_content(db, query, page, page_size, is_series) -> tuple[list[dict], int]`
  - `count_vod_content(db) -> int`
  - `get_sync_state(db) -> dict`
  - `set_sync_state(db, **kwargs)` — UPDATE on singleton row
  - `delete_vod_content_rows(db, content_ids: list[str]) -> list[str]` — deletes rows + returns strm_paths

**Key detail — FTS maintenance:** SQLite FTS5 content tables require manual trigger or explicit insert/delete. We'll use a content-less FTS approach: after each `INSERT OR REPLACE` into `vod_content`, do a matching `INSERT OR REPLACE` into `vod_content_fts`. On delete, `DELETE FROM vod_content_fts WHERE content_id = ?`.

**Key detail — upsert preserving library fields:** `INSERT OR REPLACE` on a PK conflict does a delete+insert, which would lose `in_library`/`added_at`/`last_synced_at`. We must use `INSERT INTO vod_content (...) VALUES (...) ON CONFLICT(content_id) DO UPDATE SET name=excluded.name, ..., synced_at=excluded.synced_at` — explicitly NOT updating `in_library`, `added_at`, `last_synced_at`.

**Verify:** `pytest tests/test_library_db.py` (updated) passes.

---

## Phase B — Config (`server/config.py`)

**What changes:** Three new optional settings added to `Settings`:
- `vod_sync_interval_hours: int = 24`
- `vod_sync_request_delay_ms: int = 250`
- `vod_sync_max_pages: int = 0`

Remove `strm_sync_interval_hours` (superseded by `vod_sync_interval_hours`).

**Verify:** `python -c "from server.config import Settings"` with a minimal `.env` succeeds.

---

## Phase C — Sync Engine (`server/vod_sync.py`)

**New file.** Contains one public entry point:

```python
def run_portal_sync(
    db: sqlite3.Connection,
    lock: threading.Lock,
    vod,           # VODService
    output_dir: str,
    delay_ms: int,
    max_pages: int,
) -> None:
```

**Internal flow:**

```
1. Acquire lock → set sync_state: running, started_at=now
2. Fetch all categories (vod.get_categories()) → upsert vod_categories
3. Fetch all content pages (category_id="*"):
   a. page = 1, seen_ids = set()
   b. Loop:
      - sleep(delay_ms / 1000)
      - fetch page via vod._s.get("vod", "get_ordered_list", category=..., page=p)
      - on error: log WARNING, continue to next page
      - for each item: check existing row for FR-21 similarity, upsert vod_content
      - add content_id to seen_ids
      - log vod_sync.page
      - if max_pages > 0 and page >= max_pages: break
      - if page >= total_pages: break
      - page += 1
4. Second pass — category associations (only if max_pages == 0):
   a. For each category, fetch page 1 to get total; paginate
   b. sleep(delay_ms) between each fetch
   c. INSERT OR IGNORE into vod_content_category
5. Stale cleanup (only if max_pages == 0):
   a. stale_ids = all content_ids in vod_content NOT IN seen_ids
   b. For each stale: delete .strm files, delete strm_files rows, delete vod_content row
6. Set sync_state: success, finished_at=now, content_count=len(seen_ids)
7. Release lock
On any unhandled exception: set sync_state: failed, error_message=str(e); re-raise
```

**FR-21 similarity check** inside the per-item upsert:
```python
from difflib import SequenceMatcher
def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# Before upsert: fetch existing row
# If exists and (_similar(old.name, new.name) < 0.75 or _similar(old.year, new.year) < 0.75):
#   delete strm files, strm_files rows, reset in_library=0
```

**`run_portal_sync` is synchronous** — called via `asyncio.to_thread` from the route handler and background task.

**Verify:** `pytest tests/test_vod_sync.py` passes (written in Phase G).

---

## Phase D — VOD Routes (`server/routes/vod.py`)

**Three new endpoints added to existing router:**

```
POST /vod/sync       → trigger run_portal_sync in background task; 202 or 409
GET  /vod/sync/status → return get_sync_state(db)
GET  /vod/search     → search_vod_content(db, query, page, page_size, is_series)
```

**409 guard:** Check `get_sync_state(db)["last_sync_status"] == "running"` before creating the task. Use `app.state.db_lock` (threading.Lock set on app state in main.py).

**503 guard on search:** If `count_vod_content(db) == 0`, return 503.

**Verify:** `pytest tests/test_vod.py` passes (updated).

---

## Phase E — Library Routes + Sync (`server/routes/library.py`, `server/sync.py`)

**`routes/library.py`:**
- `POST /library/add/{content_id}`: remove `AddContentRequest` body entirely. Look up `vod_content` row; 404 if missing, 409 if `in_library=1`. Call `add_to_library(db, content_id)`, then if not is_series write movie `.strm`. Return item + strm_count.
- `GET /library`: unchanged call, now queries `vod_content WHERE in_library=1`.
- `DELETE /library/{content_id}`: call `delete_library_item` (returns paths) + delete files from disk. Already done in `delete_content` in sync.py — keep that helper.
- `POST /library/sync/{content_id}` and `POST /library/sync`: now look up from `vod_content` instead of `library_items`. Logic otherwise unchanged.

**`server/sync.py`:**
- `add_content`: simplified — no longer takes name/year/is_series as params; reads from `vod_content` row. Calls `add_to_library` instead of `add_library_item`.
- `sync_item` / `sync_all` / `delete_content`: update DB calls to use new function names; behaviour unchanged.
- Remove `add_library_item` import.

**Verify:** `pytest tests/test_library_routes.py tests/test_library_db.py` passes (updated).

---

## Phase F — Wiring (`server/main.py`)

**What changes:**
- Import `vod_sync.run_portal_sync` and `threading`.
- Create `db_lock = threading.Lock()` and attach to `app.state.db_lock`.
- Pass `db_lock` into routes via `app.state`.
- On startup: if `count_vod_content(db) == 0`, trigger immediate sync via `asyncio.create_task(asyncio.to_thread(...))`.
- Replace `strm_sync_interval_hours` loop with `vod_sync_interval_hours` loop calling `run_portal_sync`.
- Mount updated routers (no structural change, routers already imported).

**Verify:** `pytest` full suite passes. Server starts with `uvicorn server.main:app`.

---

## Phase G — Tests

**`tests/test_vod_sync.py` (new):** Unit tests with in-memory DB and mocked `VODService`:
- Pages iterate correctly; `seen_ids` accumulates.
- `time.sleep` called with `delay_ms / 1000` between requests.
- `max_pages=2` stops after 2 pages; stale cleanup skipped.
- Page fetch exception is caught; sync finishes with `success`.
- Auth exception sets status `failed`.
- Upsert preserves `in_library=1` across re-sync.
- Stale row (not in new sync): strm file deleted from disk, DB row removed (SC-9).
- Name similarity < 75%: strm deleted, `in_library` reset to 0 (SC-10).

**`tests/test_vod.py` (modified):** Add:
- `POST /vod/sync` → 202; second call → 409 while running.
- `GET /vod/sync/status` returns `idle` initially; `success` after sync.
- `GET /vod/search` → 503 on empty cache.
- `GET /vod/search?query=foo` → results, pagination, `is_series` filter.

**`tests/test_library_routes.py` (modified):**
- `POST /library/add/{content_id}` with no body: 201 when in `vod_content`.
- `POST /library/add/{content_id}` with no body: 404 when not in `vod_content`.
- `DELETE /library/{content_id}`: strm files removed from disk.
- Remove all tests that supplied a request body to add.

**`tests/test_library_db.py` (modified):**
- Update fixtures to use `vod_content` table; test new CRUD functions.
- Verify `in_library` flag toggling, `strm_count` subquery.

**Verify:** `pytest --cov=server` ≥ 90% on new modules.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `INSERT OR REPLACE` wiping library fields | Use `INSERT ... ON CONFLICT DO UPDATE SET` with explicit column list excluding library fields |
| FTS5 getting out of sync with content table | Explicit FTS insert/delete paired with every content upsert/delete |
| Category second pass doubling request count | Only runs on full (unlimited) sync; logged so observable |
| Stale cleanup deleting active content | Keyed on `seen_ids` set built during that sync run; only runs when `max_pages=0` |
| Background sync blocking event loop | Wrapped in `asyncio.to_thread`; lock is threading.Lock not asyncio.Lock |
