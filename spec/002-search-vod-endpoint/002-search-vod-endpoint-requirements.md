# Spec: Search VOD Endpoint

## Objective

Add keyword search to the VOD API and make all VOD content browsing fast by
introducing a SQLite-backed local cache. Currently, `/vod/content` pages through
the live STB portal on every request (slow), and there is no way to search by
title at all. After this change, the server syncs all VOD content into SQLite on
startup and on a configurable schedule; both browse and search are served from
that cache.

Users are developers who query the REST API from home-automation scripts, media
frontends, or CLI tools. Success looks like: `GET /vod/search?query=inception`
returns matching results in under 300 ms after the initial sync, and
`GET /vod/content` is visibly faster than hitting the portal live.

## User Stories

- As a developer, I want to search VOD content by keyword so that I can find a
  title without knowing its category or ID.
- As a developer, I want `/vod/content` to respond quickly so that browsing
  large catalogs is not painfully slow.
- As an operator, I want the cache to refresh automatically so that new portal
  content appears without a server restart.

## Functional Requirements

- FR-1: `GET /vod/search?query=<string>` returns a paginated envelope
  `{"data": [...], "page": N, "total": N, "per_page": N}` of `Content` objects
  whose `name` or `description` matches the query string.
- FR-2: `query` is a required parameter; omitting it returns HTTP 422.
- FR-3: `GET /vod/search` supports optional `category_id`, `page`, and `sort`
  query parameters with the same defaults as `/vod/content`.
- FR-4: `GET /vod/content` is served from the SQLite cache when the cache is
  populated; it falls back to the live portal when the cache is empty.
- FR-5: On server startup, a full sync fetches all VOD content from the portal
  and stores it in SQLite.
- FR-6: A background task re-syncs the cache on a configurable interval
  (default 3600 seconds, controlled by `VOD_CACHE_SYNC_INTERVAL` env var).
- FR-7: The SQLite file path is configurable via `VOD_CACHE_DB_PATH` env var
  (default `vod_cache.db`).
- FR-8: While the cache is empty (sync not yet complete), `GET /vod/search`
  returns HTTP 503 with a descriptive message.
- FR-9: The cache stores category↔content associations so that
  `GET /vod/content?category_id=<id>` returns only content belonging to that
  category.
- FR-10: Portal fields `for_rent` and `lock` are persisted in the cache even
  though they are not currently in the `Content` model.
- FR-11: Each cached row stores a `portal_raw` JSON blob (serialised `Content`
  vars) as a forward-compatibility escape hatch.
- FR-12: The schema is versioned via a `schema_version` table; a migration
  runner in `VODCache.__init__` applies pending SQL patches on startup.

## Non-Functional Requirements

- NFR-1: `/vod/search` and `/vod/content` (cache-served) respond in under 300 ms
  for catalogs up to 50 000 items.
- NFR-2: The cache uses only stdlib `sqlite3`; no new runtime dependencies are
  added to the project.
- NFR-3: The sync runs in a background `asyncio` task and does not block
  in-flight HTTP requests.
- NFR-4: `VODCache` is thread-safe (SQLite writes protected by `threading.Lock`).
- NFR-5: The SQLite file is the only persistent artifact; no external database
  server is required.

## Out of Scope

- Caching seasons and episodes (tables are created in the schema for future use,
  but the seasons/episodes endpoints remain live-portal calls in this iteration).
- Search across episodes or season names.
- User-facing cache invalidation endpoint.
- Fuzzy / phonetic matching (FTS5 MATCH is exact token matching).

## Assumptions

- The server process has write access to the directory where `vod_cache.db` is
  created.
- FTS5 is available in the SQLite build shipped with Python 3.11+ (it is
  included by default in CPython distributions).
- The portal's `get_ordered_list` with `category_id="*"` returns all content
  regardless of category; per-category fetches are used to build the
  category↔content mapping.
- Content items are uniquely identified by `id` across all categories.

## Tech Stack

- Python 3.11+, FastAPI, `sqlite3` (stdlib), `asyncio` (stdlib)
- Existing: `requests`, Pydantic `BaseSettings`, pytest + responses

## Commands

```
Install deps:  pip install -e ".[server]"
Run server:    uvicorn server.main:app --reload
Run tests:     python -m pytest tests/ -v
Lint:          (no linter configured — follow existing code style)
```

## Project Structure

```
server/
├── vod_cache.py   ← NEW: VODCache class (SQLite + FTS5 + migration runner)
├── sync.py        ← NEW: sync_vod_cache() async function
├── config.py      ← add vod_cache_db_path, vod_cache_sync_interval
├── main.py        ← create cache, run initial sync, start background task
└── routes/
    └── vod.py     ← /vod/content reads cache; add /vod/search
tests/
└── test_vod_cache.py  ← NEW: unit tests for VODCache
spec/
└── 002-search-vod-endpoint/
    ├── 002-search-vod-endpoint-requirements.md  ← this file
    ├── 002-search-vod-endpoint-plan.md
    └── 002-search-vod-endpoint-implement.md
```

No changes to `stb_reader/` — all new logic lives in `server/`.

## Code Style

Follow existing patterns exactly. Example route handler:

```python
@router.get("/search")
def search_content(
    request: Request,
    query: str,
    category_id: str = "*",
    page: int = 1,
    sort: str = "added",
):
    cache = request.app.state.vod_cache
    if cache.is_empty():
        raise HTTPException(status_code=503, detail="cache not ready")
    result = cache.search(query=query, page=page, sort=sort)
    return {
        "data": [vars(c) for c in result.items],
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }
```

## Testing Strategy

- Framework: pytest with `responses` for HTTP mocking, `unittest.mock` for
  FastAPI integration tests (see `tests/test_server.py`).
- `tests/test_vod_cache.py` uses a temporary in-memory or tmp-path SQLite DB
  (`:memory:` or `tmp_path` fixture) — no file left behind after tests.
- `tests/test_server.py` mocks `app.state.vod_cache` via `MagicMock`.
- Every new public method on `VODCache` must have at least one test.
- No test should make real network calls.

## Boundaries

- **Always:** Run `pytest tests/ -v` before committing; follow existing
  response-envelope shape `{"data", "page", "total", "per_page"}`.
- **Ask first:** Adding new Python dependencies; changing the `Content`
  dataclass in `stb_reader/models.py`; altering existing endpoint response
  shapes.
- **Never:** Make real HTTP calls from tests; commit `vod_cache.db` to the
  repository; change `stb_reader/` code in this iteration.

## Success Criteria

- `GET /vod/search?query=<term>` returns matching content in the standard
  paginated envelope.
- Omitting `query` returns 422; requesting while cache is empty returns 503.
- `GET /vod/content` returns results from cache (verified by asserting
  `client.vod.get_content` is NOT called when cache is populated).
- `vod_cache.db` is created on server startup and contains content rows after
  sync.
- `python -m pytest tests/ -v` passes with no failures.
- No new runtime dependencies added to `pyproject.toml`.
