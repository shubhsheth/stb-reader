# Spec 006: Portal Content Sync

## Objective

Walk the Stalker portal and store all VOD content (movies + series) in the local SQLite database so users can search/browse offline and create library entries with just a `content_id` — no lookup body required.

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
- **FR-5** A `portal_sync_state` singleton table tracks: `last_sync_started_at`, `last_sync_finished_at`, `last_sync_status` (`idle` | `running` | `success` | `failed`), `content_count`, `error_message`.
- **FR-6** `POST /portal/sync` triggers a full portal sync (background task). Returns `202 Accepted` immediately. Returns `409 Conflict` if a sync is already running.
- **FR-7** `GET /portal/sync/status` returns current sync state from `portal_sync_state`.
- **FR-8** `GET /portal/search?query=<string>` returns paginated portal content matching the query in name or description. Supports optional `page` (default 1), `page_size` (default 50, max 200), `is_series` filter (0 or 1). Returns `503` if portal content table is empty (never synced).
- **FR-9** `GET /portal/content/{content_id}` returns a single item from `portal_content`. Returns `404` if not found.
- **FR-10** `POST /library/add/{content_id}` body becomes fully optional. When body is omitted (or any field is missing), the server looks up `name`, `year`, `is_series` from `portal_content`. Returns `404` if content_id not found in `portal_content` and not in request body. Body fields still accepted to override DB values (backward-compatible).
- **FR-11** The sync strategy fetches all categories first (one request), then fetches all content using `category_id="*"` pagination (N page requests). A second pass associates content to categories via per-category fetch using already-known page counts to avoid re-fetching data. Sequential requests only — no concurrency.
- **FR-12** A configurable delay of `portal_sync_request_delay_ms` (default 500 ms, min 0) is inserted between each portal HTTP request during sync.
- **FR-13** A configurable `portal_sync_interval_hours` (default 24, 0 = disabled) controls the background re-sync schedule. On startup, if `portal_content` is empty a sync runs immediately regardless of interval.
- **FR-14** Sync uses upsert (INSERT OR REPLACE) so re-running is idempotent. Rows not seen in the latest sync are NOT deleted (content removed from portal stays in cache).
- **FR-15** The schema is versioned via a `db_schema_version` table. Existing `library_items` and `strm_files` tables are preserved; new tables are added via migration from version 1 → 2.

## Non-Functional Requirements

- **NFR-1** `GET /portal/search` responds in < 300 ms for a cache of up to 100,000 items.
- **NFR-2** No new Python package dependencies (uses stdlib `sqlite3`, `asyncio`, `threading`).
- **NFR-3** Portal requests during sync are sequential with a delay; no concurrent portal calls from sync.
- **NFR-4** Sync runs in `asyncio.to_thread` so it never blocks the event loop.
- **NFR-5** The `db_lock` (`threading.Lock`) protects all write operations across the combined library + portal tables.
- **NFR-6** If the portal returns an error on a page fetch during sync, that page is skipped with a warning log; the sync continues and finishes with status `success` (partial). If authentication fails, the sync is aborted with status `failed`.

## Out of Scope

- Live TV channel caching.
- Series season/episode metadata caching (only top-level Content items are synced here).
- Removing content from cache when it disappears from the portal.
- Search within the `/vod/content` endpoint (spec 002 approach via separate `vod_cache.db` is superseded by this spec).
- Web UI or frontend for browsing.

## Assumptions

- `strm_data_dir` is already configured and is the directory for the single shared SQLite file (`library.db`).
- The portal `category_id="*"` parameter returns all content across all categories (current behaviour of `VODService.get_content`).
- Genres field from the portal is already a string; if it's a list it will be JSON-encoded before storage.
- `portal_raw` stores the raw dict from the portal response serialised as JSON; this is a best-effort field.

## Tech Stack

Python 3.11+, FastAPI, `sqlite3` (stdlib), `asyncio`, `threading`, Pydantic, pytest + responses

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
  db.py              (MODIFIED) - add portal_content schema + CRUD + migration
  portal_sync.py     (NEW)      - portal walking + rate-limited fetch loop
  routes/portal.py   (NEW)      - /portal/sync, /portal/sync/status, /portal/search, /portal/content/{id}
  routes/library.py  (MODIFIED) - make add body optional, lookup from portal_content
  config.py          (MODIFIED) - 2 new settings: portal_sync_interval_hours, portal_sync_request_delay_ms
  main.py            (MODIFIED) - run DB migration, mount portal router, startup sync task

tests/
  test_portal_sync.py    (NEW) - unit tests for sync logic + rate limiting
  test_portal_routes.py  (NEW) - integration tests for /portal/* endpoints
  test_library_routes.py (MODIFIED) - test bodyless add endpoint
```

## Code Style

```python
# server/db.py — migration runner style
_MIGRATIONS: dict[int, str] = {
    2: """
        CREATE TABLE IF NOT EXISTS portal_content ( ... );
        CREATE VIRTUAL TABLE IF NOT EXISTS portal_content_fts USING fts5( ... );
        ...
        INSERT OR IGNORE INTO db_schema_version (version) VALUES (2);
    """,
}

def migrate(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS db_schema_version (version INTEGER PRIMARY KEY)")
    db.execute("INSERT OR IGNORE INTO db_schema_version (version) VALUES (1)")
    current = db.execute("SELECT MAX(version) FROM db_schema_version").fetchone()[0]
    for version in sorted(v for v in _MIGRATIONS if v > current):
        db.executescript(_MIGRATIONS[version])
    db.commit()
```

Type hints on all functions. No classes for single-use modules. `asyncio.to_thread` wraps blocking sync work.

## Testing Strategy

- Framework: pytest + responses (HTTP mocking), httpx (FastAPI TestClient)
- `test_portal_sync.py`: mock `VODService`, assert page iteration, rate-limit calls, upsert behaviour, partial failure handling
- `test_portal_routes.py`: TestClient, in-memory DB, assert 202/409/503/404 responses, search pagination
- `test_library_routes.py`: add test cases for bodyless `POST /library/add/{content_id}` — portal_content populated vs empty
- Coverage: new modules at ≥ 90%

## Boundaries

- **Always:** run tests before committing; keep portal requests sequential during sync.
- **Ask first:** adding any new Python dependency; changing `strm_files` or `library_items` columns.
- **Never:** delete rows from `portal_content` during sync; block the event loop with sync I/O; run concurrent portal requests.

## Success Criteria

- SC-1: After `POST /portal/sync` completes, `GET /portal/sync/status` returns `status: success` and `content_count > 0`.
- SC-2: `GET /portal/search?query=action` returns paginated results that match portal content loaded into `portal_content`.
- SC-3: `POST /library/add/{content_id}` with no body and a known content_id succeeds with 201 using data from `portal_content`.
- SC-4: `POST /library/add/{content_id}` with no body and an unknown content_id returns 404.
- SC-5: Running two concurrent `POST /portal/sync` calls returns 202 for the first and 409 for the second.
- SC-6: A portal page fetch error during sync is skipped; sync still finishes with status `success`.
- SC-7: DB migration runs on startup; existing `library_items` and `strm_files` data is intact after migration.
- SC-8: No real network calls are made in any test (all portal HTTP is mocked).
- SC-9: The delay between portal requests during sync matches `portal_sync_request_delay_ms` (verified by mock call timing or call-count assertions).

## Open Questions

None — requirements are complete.
