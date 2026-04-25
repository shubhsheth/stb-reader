# Implementation Tasks: Search VOD Endpoint (002)

## Task A — Extend `server/config.py`

- [ ] Add `vod_cache_db_path: str = "vod_cache.db"` and
  `vod_cache_sync_interval: int = 3600` to `Settings`.
- Acceptance: `Settings(STB_PORTAL_URL="x", STB_MAC="y")` has both fields with
  correct defaults; `VOD_CACHE_DB_PATH` / `VOD_CACHE_SYNC_INTERVAL` env vars
  override them.
- Verify: `python -c "from server.config import Settings; s = Settings(STB_PORTAL_URL='x', STB_MAC='y'); assert s.vod_cache_db_path == 'vod_cache.db'"`
- Files: `server/config.py`

## Task B — Implement `server/vod_cache.py`

- [ ] Create `VODCache` class with:
  - `__init__(db_path)` — opens/creates SQLite, runs migration runner,
    inserts `schema_version=1` if absent.
  - `upsert_batch(items, raw_rows, category_id)` — upsert content rows,
    upsert `content_category` rows, rebuild FTS entries for affected ids.
  - `get_content(category_id, page, sort, fav) -> PagedResult[Content]` —
    paginated query; `category_id="*"` bypasses the join.
  - `search(query, page, sort) -> PagedResult[Content]` — FTS5 MATCH.
  - `is_empty() -> bool`
  - `clear()` — DELETE from `content`, `content_category`, `content_fts`.
- Acceptance: all `tests/test_vod_cache.py` tests pass (see Task F for list).
- Verify: `python -m pytest tests/test_vod_cache.py -v`
- Files: `server/vod_cache.py`

## Task C — Implement `server/sync.py`

- [ ] Create `sync_vod_cache(client, cache)` synchronous function:
  1. `cache.clear()`
  2. Fetch categories via `client.vod.get_categories()`
  3. For each category, paginate raw portal responses via
     `client.vod._s.get("vod", "get_ordered_list", ...)`, map to `Content`
     objects, call `cache.upsert_batch(items, raw_rows, cat.id)`.
  4. Repeat step 3 with `category="*"` for uncategorized content.
- Acceptance: function runs without error when `client.vod._s.get` is mocked to
  return a single-page portal response.
- Verify: unit test in `tests/test_vod_cache.py` (or a small standalone script).
- Files: `server/sync.py`

## Task D — Wire cache into `server/main.py`

- [ ] In the FastAPI lifespan:
  1. Create `VODCache(settings.vod_cache_db_path)`, store as
     `app.state.vod_cache`.
  2. Run `sync_vod_cache(client, app.state.vod_cache)` via
     `asyncio.to_thread(...)` after `client.authenticate()`.
  3. Launch `asyncio.create_task(_cache_refresh_loop(...))` with
     `settings.vod_cache_sync_interval`.
- Acceptance: server starts cleanly; `app.state.vod_cache` is set.
- Verify: existing `test_health` and server fixture still pass.
- Files: `server/main.py`

## Task E — Update `server/routes/vod.py`

- [ ] `GET /vod/content`: read from `request.app.state.vod_cache.get_content(...)`
  when not empty; fall back to `client.vod.get_content(...)` when empty.
- [ ] Add `GET /vod/search`:
  ```python
  @router.get("/search")
  def search_content(request, query: str, category_id="*", page=1, sort="added"):
  ```
  Returns 503 when cache empty, otherwise the standard paginated envelope.
- Acceptance: route handler calls cache methods, not `client.vod.*`, when cache
  is populated.
- Verify: `python -m pytest tests/test_server.py -v`
- Files: `server/routes/vod.py`

## Task F — Tests

- [ ] Create `tests/test_vod_cache.py` with `:memory:` DB fixture:
  - `test_schema_version_is_1_after_init`
  - `test_is_empty_before_upsert`
  - `test_is_not_empty_after_upsert`
  - `test_upsert_and_get_content_pagination`
  - `test_get_content_category_filter`
  - `test_get_content_all_categories`
  - `test_get_content_fav_filter`
  - `test_search_matches_name`
  - `test_search_matches_description`
  - `test_search_no_results`
  - `test_clear_empties_content`
  - `test_for_rent_and_lock_stored_from_raw`
  - `test_portal_raw_is_valid_json`

- [ ] Add to `tests/test_server.py` (`TestVOD` class):
  - `test_get_content_reads_from_cache` — `cache.is_empty()` False →
    `cache.get_content` called, not `client.vod.get_content`
  - `test_get_content_falls_back_to_portal` — `cache.is_empty()` True →
    `client.vod.get_content` called
  - `test_search_returns_envelope` — `GET /vod/search?query=inception` →
    200 with `{data, page, total, per_page}`
  - `test_search_missing_query_422` — `GET /vod/search` → 422
  - `test_search_503_when_cache_empty` — `cache.is_empty()` True → 503

- Acceptance: `python -m pytest tests/ -v` is fully green; no new test file
  touches the filesystem.
- Verify: `python -m pytest tests/ -v --tb=short`
- Files: `tests/test_vod_cache.py`, `tests/test_server.py`

## Task G — Update `AGENTS.md`

- [ ] Update `AGENTS.md` at the repo root to document:
  - Overview of the server and its two main route groups (`/live-tv`, `/vod`)
  - The VOD cache: what it is, where the SQLite file lives, how to configure
    `VOD_CACHE_DB_PATH` and `VOD_CACHE_SYNC_INTERVAL`
  - The new `GET /vod/search?query=<str>` endpoint (params, response shape,
    503-when-empty behaviour)
  - How to run the server and tests
- Acceptance: `AGENTS.md` covers all four bullet points above.
- Verify: manual review of the file.
- Files: `AGENTS.md`
