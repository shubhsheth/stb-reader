# Plan: Search VOD Endpoint (002)

## Component Dependency Graph

```
sqlite3 (stdlib)
    └── server/vod_cache.py  (VODCache)
            └── server/sync.py  (sync_vod_cache)
                    └── server/main.py  (lifespan: create cache, sync, background task)
                            └── server/routes/vod.py  (GET /vod/content, GET /vod/search)
server/config.py  (vod_cache_db_path, vod_cache_sync_interval)  ← used by main.py
```

No changes propagate into `stb_reader/`; everything is additive within `server/`.

## SQLite Schema (version 1)

```sql
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS content (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    cmd             TEXT,
    screenshot_uri  TEXT,
    genres          TEXT,
    year            TEXT,
    description     TEXT,
    rating          TEXT,
    duration        TEXT,
    is_series       INTEGER DEFAULT 0,
    fav             INTEGER DEFAULT 0,
    for_rent        INTEGER DEFAULT 0,
    lock            INTEGER DEFAULT 0,
    portal_raw      TEXT,
    cached_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS content_category (
    content_id  TEXT NOT NULL,
    category_id TEXT NOT NULL,
    PRIMARY KEY (content_id, category_id)
);

-- Reserved for future lazy caching of seasons
CREATE TABLE IF NOT EXISTS seasons (
    id        TEXT NOT NULL,
    series_id TEXT NOT NULL,
    name      TEXT,
    video_id  TEXT,
    portal_raw TEXT,
    cached_at  REAL NOT NULL,
    PRIMARY KEY (id, series_id)
);

-- Reserved for future lazy caching of episodes
CREATE TABLE IF NOT EXISTS episodes (
    id            TEXT NOT NULL,
    series_id     TEXT NOT NULL,
    season_id     TEXT NOT NULL,
    name          TEXT,
    series_number TEXT,
    cmd           TEXT,
    portal_raw    TEXT,
    cached_at     REAL NOT NULL,
    PRIMARY KEY (id, series_id, season_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
    content_id UNINDEXED,
    name,
    description
);
```

Migration runner: on `VODCache.__init__`, read `schema_version.version`; if the
table or row is absent, create all tables and insert `version=1`. Future
migrations will be applied as numbered SQL patches when version < target.

## Sort Mapping

| `sort` param | SQL clause |
|---|---|
| `name` | `ORDER BY name COLLATE NOCASE` |
| `rating` | `ORDER BY CAST(rating AS REAL) DESC` |
| `added` / anything else | `ORDER BY rowid DESC` |

## Sync Strategy

`sync_vod_cache(client, cache)` in `server/sync.py`:

1. `cache.clear()` — delete all rows from `content`, `content_category`,
   `content_fts`; leave `seasons`/`episodes` untouched.
2. Fetch categories: `client.vod.get_categories()`.
3. For each category: paginate `client.vod._s.get("vod", "get_ordered_list", category=cat.id, p=page, sortby="added")` directly on the raw session to retain `for_rent`/`lock` fields; call `cache.upsert_batch(items_mapped, raw_rows, cat.id)` per page.
4. Paginate `client.vod._s.get("vod", "get_ordered_list", category="*", ...)` to catch uncategorized content; upsert with `category_id="*"`.

Accessing `client.vod._s` (the private `STBSession`) is intentional and
contained within the server sync layer — it avoids changing `stb_reader/vod.py`.

## Background Task in `server/main.py`

```python
async def _cache_refresh_loop(client, cache, interval):
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(sync_vod_cache, client, cache)
```

`sync_vod_cache` is synchronous (uses `requests`); `asyncio.to_thread` keeps
it off the event loop thread.

## Implementation Phases

| Phase | Work | Checkpoint |
|---|---|---|
| A | `server/config.py` additions | `Settings()` accepts new env vars |
| B | `server/vod_cache.py` — `VODCache` class | `pytest tests/test_vod_cache.py` passes |
| C | `server/sync.py` — `sync_vod_cache` | Sync runs against a mocked session |
| D | `server/main.py` — lifespan wiring | Server starts; cache file created |
| E | `server/routes/vod.py` — update + new route | All route tests pass |
| F | `tests/test_server.py` — new test cases | Full suite green |

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| FTS5 not compiled into SQLite | Catch `OperationalError` on virtual table creation; log a warning and fall back to `LIKE '%query%'` search |
| Large catalog makes initial sync slow | Sync runs in background thread; server is responsive immediately; `/vod/search` returns 503 until ready |
| Portal rate-limits per-category pagination | Sync is a startup/scheduled job; no per-request portal calls once cache is warm |
| `vod_cache.db` left behind in tests | Use `:memory:` DB in all `test_vod_cache.py` tests |
