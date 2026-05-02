# Spec 006: Portal Content Sync

## Objective

Walk the Stalker portal and store all VOD content (movies + series) in the local SQLite database so users can search/browse offline and create library entries with just a `content_id` — no body required.

Currently `POST /library/add/{content_id}` requires the caller to supply `name`, `year`, and `is_series` in the request body. This forces the client to know portal details that the server already has (or can fetch). This spec adds a background sync that populates a `portal_content` table, and wires the library add endpoint to that table so the body is no longer needed.

## User Stories

- As a user, I want to trigger a full portal sync so that all VOD titles are cached locally.
- As a user, I want to search cached portal content by keyword so that I can find content to add to my library.
- As a user, I want to `POST /library/add/{content_id}` with no body so that I don't have to look up metadata separately.
- As a user, I want to see sync progress/status so that I know when the cache is ready.
- As a user, I want the sync to run automatically on a schedule so that new portal content appears without manual intervention.

## Functional Requirements

- **FR-1** A `portal_content` table stores every VOD item synced from the portal: `content_id`, `name`, `cmd`, `screenshot_uri`, `genres` (JSON array as TEXT), `year`, `description`, `rating`, `duration`, `is_series`, `fav`, `for_rent`, `lock`, `portal_raw` (full JSON blob), `synced_at` (ISO 8601 UTC).
- **FR-2** A `portal_categories` table stores all portal categories: `category_id`, `title`, `alias`, `synced_at`.
- **FR-3** A `portal_content_category` join table links content to categories: `(content_id, category_id)` composite primary key.
- **FR-4** An FTS5 virtual table `portal_content_fts` indexes `content_id` (UNINDEXED), `name`, and `description` for full-text search.
- **FR-5** A `portal_sync_state` singleton table (enforced by `CHECK (id = 1)`) tracks: `last_sync_started_at`, `last_sync_finished_at`, `last_sync_status` (`idle` | `running` | `success` | `failed`), `content_count`, `error_message`.
- **FR-6** `POST /portal/sync` triggers a full portal sync (background task). Returns `202 Accepted` immediately. Returns `409 Conflict` if a sync is already running.
- **FR-7** `GET /portal/sync/status` returns current sync state from `portal_sync_state`.
- **FR-8** `GET /portal/search?query=<string>` returns paginated portal content matching the query in name or description. Supports optional `page` (default 1), `page_size` (default 50, max 200), `is_series` filter (0 or 1). Returns `503` if portal content table is empty (never synced).
- **FR-9** `GET /portal/content/{content_id}` returns a single item from `portal_content`. Returns `404` if not found.
- **FR-10** `POST /library/add/{content_id}` accepts **no request body**. The server looks up `name`, `year`, `is_series` from `portal_content`. Returns `404` if `content_id` is not found in `portal_content`.
- **FR-11** The sync strategy fetches all categories first (one request), then fetches all content using `category_id="*"` pagination (N page requests). A second pass associates content to categories via per-category fetch using already-known page counts to avoid re-fetching all content again. Sequential requests only — no concurrency.
- **FR-12** A configurable delay of `portal_sync_request_delay_ms` (default 250 ms, min 0) is inserted between each portal HTTP request during sync.
- **FR-13** A configurable `portal_sync_interval_hours` (default 24, 0 = disabled) controls the background re-sync schedule. On startup, if `portal_content` is empty a sync runs immediately regardless of interval.
- **FR-14** Sync uses upsert (`INSERT OR REPLACE`) so re-running is idempotent. Rows not seen in the latest sync are NOT deleted (content removed from portal stays in cache).
- **FR-15** A configurable `portal_sync_max_pages` (default 0 = unlimited) caps the number of content pages fetched during sync. When set to a positive integer, the sync stops after that many pages (for testing/development without a full sync).
- **FR-16** Sync emits structured log lines at key points: sync started, each category fetched, each content page fetched (with page number and cumulative count), sync finished (with total count and duration), and each skipped page error.

## Non-Functional Requirements

- **NFR-1** `GET /portal/search` responds in < 300 ms for a cache of up to 100,000 items.
- **NFR-2** No new Python package dependencies (uses stdlib `sqlite3`, `asyncio`, `threading`, `time`, `json`, `logging`).
- **NFR-3** Portal requests during sync are sequential with a configurable delay; no concurrent portal calls from sync.
- **NFR-4** Sync runs in `asyncio.to_thread` so it never blocks the event loop.
- **NFR-5** All DB write operations are protected by a `threading.Lock` shared across library and portal tables.
- **NFR-6** If the portal returns an error on a page fetch during sync, that page is skipped with a `WARNING` log; the sync continues and finishes with status `success` (partial). If authentication fails, the sync is aborted with status `failed`.

## Out of Scope

- Live TV channel caching.
- Series season/episode metadata caching (only top-level Content items are synced here).
- Removing portal_content rows when content disappears from the portal.
- Spec 002's separate `vod_cache.db` approach — this spec covers that use case and supersedes it. Spec 002 was never implemented.
- Web UI or frontend for browsing.

## Assumptions

- `strm_data_dir` is already configured and is the directory for the single shared SQLite file (`library.db`).
- The portal `category_id="*"` parameter returns all content across all categories (current behaviour of `VODService.get_content`).
- Genres field from the portal is already a string; if it's a list it will be JSON-encoded before storage.
- `portal_raw` stores the raw dict from the portal response serialised as JSON; this is a best-effort field.

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
  db.py              (MODIFIED) - add portal_content schema + CRUD; simple CREATE IF NOT EXISTS, no versioning
  portal_sync.py     (NEW)      - portal walking + rate-limited fetch loop + structured logging
  routes/portal.py   (NEW)      - /portal/sync, /portal/sync/status, /portal/search, /portal/content/{id}
  routes/library.py  (MODIFIED) - remove body from add endpoint, lookup from portal_content
  config.py          (MODIFIED) - 3 new settings: portal_sync_interval_hours, portal_sync_request_delay_ms, portal_sync_max_pages
  main.py            (MODIFIED) - init portal tables, mount portal router, startup sync task

tests/
  test_portal_sync.py    (NEW) - unit tests for sync logic, rate limiting, max_pages cap, partial failure
  test_portal_routes.py  (NEW) - integration tests for /portal/* endpoints
  test_library_routes.py (MODIFIED) - update add tests: no body, portal_content lookup, 404 when not cached
```

## Code Style

```python
# server/db.py — portal tables added alongside existing tables in init_db
def init_db(path: str) -> sqlite3.Connection:
    ...
    db.executescript("""
        CREATE TABLE IF NOT EXISTS library_items ( ... );
        CREATE TABLE IF NOT EXISTS strm_files ( ... );
        CREATE TABLE IF NOT EXISTS portal_content ( ... );
        CREATE TABLE IF NOT EXISTS portal_categories ( ... );
        CREATE TABLE IF NOT EXISTS portal_content_category ( ... );
        CREATE VIRTUAL TABLE IF NOT EXISTS portal_content_fts USING fts5( ... );
        CREATE TABLE IF NOT EXISTS portal_sync_state (
            id INTEGER PRIMARY KEY CHECK (id = 1), ...
        );
        INSERT OR IGNORE INTO portal_sync_state (id, last_sync_status) VALUES (1, 'idle');
    """)

# server/portal_sync.py — structured log at each key step
import logging, time
log = logging.getLogger(__name__)

def run_sync(db, lock, vod, delay_ms, max_pages):
    log.info("portal_sync.started")
    t0 = time.monotonic()
    ...
    log.info("portal_sync.page", extra={"page": p, "count": n, "cumulative": total})
    ...
    log.info("portal_sync.finished", extra={"count": total, "duration_s": time.monotonic() - t0})
```

Type hints on all functions. No classes for single-use modules. `asyncio.to_thread` wraps blocking sync work.

## Testing Strategy

- Framework: pytest + responses (HTTP mocking), httpx (FastAPI TestClient)
- `test_portal_sync.py`: mock `VODService`, assert page iteration, delay calls (`time.sleep` mock), `max_pages` cap, upsert idempotency, partial page failure handling
- `test_portal_routes.py`: TestClient, in-memory DB fixture, assert 202/409/503/404 responses, search pagination and `is_series` filter
- `test_library_routes.py`: update existing add tests — no body, portal_content populated returns 201, portal_content empty returns 404
- Coverage: new modules at ≥ 90%

## Boundaries

- **Always:** run tests before committing; keep portal requests sequential during sync.
- **Ask first:** adding any new Python dependency; changing `strm_files` or `library_items` columns.
- **Never:** delete rows from `portal_content` during sync; block the event loop with sync I/O; run concurrent portal requests.

## Success Criteria

- SC-1: After `POST /portal/sync` completes, `GET /portal/sync/status` returns `status: success` and `content_count > 0`.
- SC-2: `GET /portal/search?query=action` returns paginated results matching portal content in `portal_content`.
- SC-3: `POST /library/add/{content_id}` with no body and a known content_id returns 201 using data from `portal_content`.
- SC-4: `POST /library/add/{content_id}` with no body and an unknown content_id returns 404.
- SC-5: Two concurrent `POST /portal/sync` calls: first returns 202, second returns 409.
- SC-6: A portal page fetch error during sync is skipped; sync finishes with status `success`.
- SC-7: `portal_sync_max_pages=2` causes sync to stop after 2 content pages regardless of portal total.
- SC-8: Sync log output includes started, per-page, and finished lines with correct counts.
- SC-9: No real network calls are made in any test (all portal HTTP is mocked).
- SC-10: Existing `library_items` and `strm_files` data is intact after `init_db` runs with the new portal tables included.
