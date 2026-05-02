# Spec 006: Portal Content Sync

## Objective

Walk the Stalker portal and store all VOD content (movies + series) in the local SQLite database so users can search/browse offline and create library entries with just a `content_id` — no body required.

Currently `POST /library/add/{content_id}` requires the caller to supply `name`, `year`, and `is_series` in the request body. This forces the client to know portal details that the server already has (or can fetch). This spec adds a background sync that populates `portal_content`, consolidates the `library_items` table into it, and wires library management to use the single table.

## User Stories

- As a user, I want to trigger a full portal sync so that all VOD titles are cached locally.
- As a user, I want to search cached portal content by keyword so that I can find content to add to my library.
- As a user, I want to `POST /library/add/{content_id}` with no body so that I don't have to look up metadata separately.
- As a user, I want to see sync progress/status so that I know when the cache is ready.
- As a user, I want the sync to run automatically on a schedule so that new portal content appears without manual intervention.

## Functional Requirements

### Database Schema

- **FR-1** A single `vod_content` table replaces the former `library_items` table and stores every VOD item synced from the portal. Columns: `content_id` (PK), `name`, `cmd`, `screenshot_uri`, `genres` (JSON array as TEXT), `year`, `description`, `rating`, `duration`, `is_series` (0/1), `fav`, `for_rent`, `lock`, `portal_raw` (full JSON blob), `synced_at` (ISO 8601 UTC), `in_library` (INTEGER DEFAULT 0), `added_at` (TEXT, NULL when not in library), `last_synced_at` (TEXT, NULL until first library sync).
- **FR-2** A `vod_categories` table stores all portal categories: `category_id` (PK), `title`, `alias`, `synced_at`.
- **FR-3** A `vod_content_category` join table links content to categories: `(content_id, category_id)` composite primary key, `content_id` references `vod_content`.
- **FR-4** An FTS5 virtual table `vod_content_fts` indexes `content_id` (UNINDEXED), `name`, and `description`.
- **FR-5** A `vod_sync_state` singleton table (enforced by `CHECK (id = 1)`) tracks: `last_sync_started_at`, `last_sync_finished_at`, `last_sync_status` (`idle` | `running` | `success` | `failed`), `content_count`, `error_message`.
- **FR-6** The `strm_files` table retains its existing schema; its `content_id` FK references `vod_content` instead of the former `library_items`.

### Sync Endpoints

- **FR-7** `POST /vod/sync` triggers a full portal sync (background task). Returns `202 Accepted` immediately. Returns `409 Conflict` if a sync is already running.
- **FR-8** `GET /vod/sync/status` returns current sync state from `vod_sync_state`.

### Search Endpoint

- **FR-9** `GET /vod/search?query=<string>` returns paginated `vod_content` rows matching the query in name or description via FTS5. Supports optional `page` (default 1), `page_size` (default 50, max 200), `is_series` filter (0 or 1). Returns `503` if `vod_content` is empty (never synced).

### Library Endpoints (modified)

- **FR-10** `POST /library/add/{content_id}` accepts no request body. Sets `in_library=1` and `added_at=now()` on the matching `vod_content` row. Returns `404` if `content_id` is not in `vod_content`. Returns `409` if already in library.
- **FR-11** `GET /library` returns all `vod_content` rows where `in_library=1`, each including `strm_count` (subquery count from `strm_files`).
- **FR-12** `DELETE /library/{content_id}` sets `in_library=0`, clears `added_at` and `last_synced_at`, deletes all `strm_files` rows, and deletes the corresponding `.strm` files from disk. Returns `404` if not in library.
- **FR-13** `POST /library/sync/{content_id}` and `POST /library/sync` continue to work as before; `set_last_synced` updates `last_synced_at` on `vod_content`.

### Sync Strategy

- **FR-14** The sync strategy fetches all categories first (one request), then fetches all content using `category_id="*"` pagination (N page requests). A second pass associates content to categories via per-category fetch. Sequential requests only — no concurrency.
- **FR-15** A configurable delay of `vod_sync_request_delay_ms` (default 250 ms, min 0) is inserted between each portal HTTP request during sync.
- **FR-16** A configurable `vod_sync_interval_hours` (default 24, 0 = disabled) controls the background re-sync schedule. On startup, if `vod_content` is empty a sync runs immediately regardless of interval.
- **FR-17** Sync uses `INSERT OR REPLACE` so re-running is idempotent. `in_library`, `added_at`, and `last_synced_at` are preserved on upsert (not overwritten by sync).
- **FR-18** A configurable `vod_sync_max_pages` (default 0 = unlimited) caps the number of content pages fetched. When positive, sync stops after that many pages (for testing without a full sync). Stale content cleanup (FR-20, FR-21) is skipped when `vod_sync_max_pages > 0` since the sync is intentionally partial.
- **FR-20** After a full unlimited sync completes, any `vod_content` row whose `content_id` was not returned by the portal in that sync run is considered stale. Stale rows have their `.strm` files deleted from disk, their `strm_files` rows deleted, and the `vod_content` row deleted.
- **FR-21** During upsert, if a row already exists in `vod_content` and the incoming `name` or `year` differs from the stored value with a similarity ratio below 75% (using `difflib.SequenceMatcher`), the content is considered to have changed significantly. In this case the old `.strm` files are deleted from disk, `strm_files` rows are deleted, and `in_library` is set to 0 with `added_at` and `last_synced_at` cleared. The `vod_content` row is then updated with the new portal data.
- **FR-19** Sync emits structured log lines at key points: sync started, each category fetched, each content page fetched (page number + cumulative count), sync finished (total count + duration), and each skipped page error.

## Non-Functional Requirements

- **NFR-1** `GET /vod/search` responds in < 300 ms for a cache of up to 100,000 items.
- **NFR-2** No new Python package dependencies (uses stdlib `sqlite3`, `asyncio`, `threading`, `time`, `json`, `logging`).
- **NFR-3** Portal requests during sync are sequential with a configurable delay; no concurrent portal calls.
- **NFR-4** Sync runs in `asyncio.to_thread` so it never blocks the event loop.
- **NFR-5** All DB write operations are protected by a `threading.Lock` shared across all tables.
- **NFR-6** Page fetch errors during sync are skipped with a `WARNING` log; sync finishes with status `success` (partial). Auth failures abort with status `failed`.

## Out of Scope

- Live TV channel caching.
- Series season/episode metadata caching (only top-level Content items are synced here).
- Spec 002's separate `vod_cache.db` approach — this spec supersedes it. Spec 002 was never implemented.
- Web UI or frontend for browsing.

## Assumptions

- `strm_data_dir` is already configured and is the directory for the single shared SQLite file (`library.db`).
- A portal sync must be run before any content can be added to the library (no body fallback).
- The portal `category_id="*"` returns all content across all categories (current behaviour of `VODService.get_content`).
- Genres field from the portal is a string; if it's a list it will be JSON-encoded before storage.
- `portal_raw` stores the raw portal dict serialised as JSON; best-effort field.

## Tech Stack

Python 3.11+, FastAPI, `sqlite3` (stdlib), `asyncio`, `threading`, `time`, `json`, `logging`, Pydantic, pytest + responses

## Commands

```
Build/install:  pip install -e ".[dev]"
Test:           pytest
Test with cov:  pytest --cov=server --cov=stb_reader
Lint:           ruff check . && ruff format --check .
Dev server:     uvicorn server.main:app --reload
```

## Project Structure

```
server/
  db.py              (MODIFIED) - replace library_items with vod_content; add all vod_* tables via CREATE IF NOT EXISTS
  vod_sync.py        (NEW)      - portal walking, rate-limited fetch loop, stale/changed content cleanup, structured logging
  routes/vod.py      (MODIFIED) - add /vod/sync, /vod/sync/status, /vod/search
  routes/library.py  (MODIFIED) - update all CRUD to use vod_content; remove body from add; delete .strm files on remove
  config.py          (MODIFIED) - 3 new settings: vod_sync_interval_hours, vod_sync_request_delay_ms, vod_sync_max_pages
  main.py            (MODIFIED) - init new DB schema, mount updated routers, startup sync task

tests/
  test_vod_sync.py       (NEW)      - sync logic, rate limiting, max_pages cap, partial failure, upsert preserves in_library
  test_vod.py            (MODIFIED) - add tests for /vod/sync, /vod/sync/status, /vod/search
  test_library_routes.py (MODIFIED) - update all tests: no body, portal_content lookup, 404 when not cached
  test_library_db.py     (MODIFIED) - update CRUD tests for portal_content-based schema
```

## DB Tables Summary

| Table | Role |
|---|---|
| `vod_content` | All portal VOD items + library membership (`in_library`, `added_at`, `last_synced_at`) |
| `vod_categories` | Portal category list |
| `vod_content_category` | Content↔category join |
| `vod_content_fts` | FTS5 search index on name + description |
| `vod_sync_state` | Singleton sync status/progress |
| `strm_files` | Generated `.strm` file records (FK → `vod_content`) |

## API Surface Summary

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/live-tv/genres` | Live TV genres |
| GET | `/live-tv/channels` | Live TV channels |
| GET | `/live-tv/channels/{id}/stream` | Live TV stream |
| GET | `/vod/categories` | Portal VOD categories (live) |
| GET | `/vod/content` | Paginated VOD content (live) |
| GET | `/vod/content/{id}/seasons` | Series seasons (live) |
| GET | `/vod/content/{id}/seasons/{sid}/episodes` | Episodes (live) |
| GET | `/vod/content/{id}/seasons/{sid}/episodes/{eid}/files` | Episode files (live) |
| GET | `/vod/content/{id}/seasons/{sid}/episodes/{eid}/stream` | Episode stream redirect |
| GET | `/vod/content/{id}/seasons/{sid}/episodes/{eid}/files/{fid}/stream` | Episode file stream |
| GET | `/vod/content/{id}/stream` | Movie stream redirect |
| POST | `/vod/sync` | Trigger full portal content sync |
| GET | `/vod/sync/status` | Sync progress/status |
| GET | `/vod/search` | Search cached portal content |
| POST | `/library/add/{content_id}` | Add content to library (no body) |
| GET | `/library` | List library items |
| DELETE | `/library/{content_id}` | Remove from library |
| POST | `/library/sync/{content_id}` | Sync strm files for one item |
| POST | `/library/sync` | Sync strm files for all items |

## Code Style

```python
# server/db.py — all tables in one init_db call
def init_db(path: str) -> sqlite3.Connection:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS vod_content (
            content_id   TEXT PRIMARY KEY,
            ...
            in_library   INTEGER NOT NULL DEFAULT 0,
            added_at     TEXT,
            last_synced_at TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS vod_content_fts USING fts5(
            content_id UNINDEXED, name, description
        );
        CREATE TABLE IF NOT EXISTS vod_sync_state (
            id INTEGER PRIMARY KEY CHECK (id = 1), ...
        );
        INSERT OR IGNORE INTO vod_sync_state (id, last_sync_status) VALUES (1, 'idle');
        CREATE TABLE IF NOT EXISTS strm_files (
            content_id TEXT NOT NULL REFERENCES vod_content(content_id), ...
        );
    """)

# server/vod_sync.py — structured logging
log = logging.getLogger(__name__)

def run_sync(db, lock, vod, delay_ms, max_pages):
    log.info("vod_sync.started")
    ...
    log.info("vod_sync.page", extra={"page": p, "cumulative": total})
    log.info("vod_sync.finished", extra={"count": total, "duration_s": elapsed})
```

## Testing Strategy

- Framework: pytest + responses (HTTP mocking), httpx (FastAPI TestClient)
- `test_vod_sync.py`: mock `VODService`, assert page iteration, `time.sleep` mock for delay, `max_pages` cap, upsert idempotency, `in_library` preserved across re-sync, stale row deletion (disk + DB), significant name/year change triggers strm cleanup and in_library reset, cleanup skipped on capped sync
- `test_vod.py`: 202/409 for sync trigger, 503 on empty cache search, paginated results, `is_series` filter
- `test_library_routes.py`: no body add returns 201, unknown id returns 404, delete clears `in_library` and removes strm_files rows and `.strm` files from disk
- Coverage: new modules ≥ 90%

## Boundaries

- **Always:** run tests before committing; keep portal requests sequential during sync.
- **Ask first:** adding any new Python dependency; changing `strm_files` columns.
- **Never:** overwrite `in_library`/`added_at` during vod sync; block the event loop with sync I/O; run concurrent portal requests.

## Success Criteria

- SC-1: After `POST /vod/sync` completes, `GET /vod/sync/status` returns `status: success` and `content_count > 0`.
- SC-2: `GET /vod/search?query=action` returns paginated results from `vod_content`.
- SC-3: `POST /library/add/{content_id}` with no body and a known content_id returns 201; `vod_content.in_library` is set to 1.
- SC-4: `POST /library/add/{content_id}` for an unknown content_id returns 404.
- SC-5: Two concurrent `POST /vod/sync` calls: first 202, second 409.
- SC-6: A portal page fetch error during sync is skipped; sync finishes with status `success`.
- SC-7: `vod_sync_max_pages=2` causes sync to stop after 2 content pages; stale cleanup does not run.
- SC-8: Re-running a full sync does not clear `in_library=1` on items already in library.
- SC-9: After a full sync, a `vod_content` row absent from the portal response has its `.strm` files deleted from disk and its DB row removed.
- SC-10: When a re-sync returns the same `content_id` with a name that is < 75% similar to the stored name, `.strm` files are deleted and `in_library` is reset to 0.
- SC-11: `DELETE /library/{content_id}` removes `.strm` files from disk and the `strm_files` rows.
- SC-12: No real network calls in any test.
- SC-13: `GET /library` only returns rows where `in_library=1`.
