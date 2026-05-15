# 012 — Xtream Codes Translation Layer: Plan

## Overview

Add a set of HTTP routes to the existing FastAPI server that implement the **Xtream Codes API** wire format. Any Xtream-compatible IPTV client (TiviMate, IPTV Smarters, GSE Player, VLC, etc.) can point at this server and work natively — with the server translating requests to Stalker portal calls under the hood.

No new Python dependencies. Only the existing `stb_reader/` library and FastAPI patterns already in use.

---

## Xtream Codes API Surface

### Endpoint map

| Xtream URL | Method | Purpose |
|---|---|---|
| `/player_api.php` | GET/POST | Auth + server info (no `action`) or any action below |
| `/player_api.php?action=get_live_categories` | GET | Live TV genre list |
| `/player_api.php?action=get_live_streams` | GET | All channels (optionally `&category_id=N`) |
| `/player_api.php?action=get_vod_categories` | GET | VOD movie categories |
| `/player_api.php?action=get_vod_streams` | GET | All VOD movies (optionally `&category_id=N`) |
| `/player_api.php?action=get_vod_info&vod_id=N` | GET | Single VOD movie detail |
| `/player_api.php?action=get_series_categories` | GET | Series categories |
| `/player_api.php?action=get_series` | GET | All series (optionally `&category_id=N`) |
| `/player_api.php?action=get_series_info&series_id=N` | GET | Series detail (seasons + episodes) |
| `/{username}/{password}/{stream_id}` | GET | Live stream delivery |
| `/{username}/{password}/{stream_id}.{ext}` | GET | Live stream delivery (with extension) |
| `/movie/{username}/{password}/{vod_id}.{ext}` | GET | VOD stream delivery |
| `/series/{username}/{password}/{episode_id}.{ext}` | GET | Series episode stream delivery |
| `/get.php` | GET | M3U playlist (live channels) |
| `/xmltv.php` | GET | EPG — empty XMLTV stub |

All `player_api.php` requests pass `username` and `password` as query params.

---

## Key Design Decisions

### 1. Authentication — single-tenant

The STB reader is configured for one portal (one MAC/token). We add two new config vars:

```
XTREAM_USERNAME=admin
XTREAM_PASSWORD=secret
```

Any request with matching credentials passes. Wrong credentials → `{"user_info": {"auth": 0}}`. This is simpler than a user database and matches the single-tenant nature of the existing server.

**Implementation:** a small `_check_auth(username, password, settings)` helper that raises `HTTPException(403)` if credentials don't match.

### 2. Pagination — collect all pages

Xtream clients expect a single flat JSON array for list endpoints (`get_live_streams`, `get_vod_streams`, `get_series`). The Stalker portal paginates.

**Implementation:** a `_collect_all_pages(fn, **kwargs)` helper that calls the paginating function repeatedly until all items are fetched:

```python
def _collect_all_pages(fn, **kwargs):
    items, page = [], 1
    while True:
        result = fn(**kwargs, page=page)
        items.extend(result.items)
        if not result.items or page * result.per_page >= result.total:
            break
        page += 1
    return items
```

### 3. ID mapping — direct cast

Stalker IDs are numeric strings (`"12345"`). Xtream uses integers (`12345`). Cast directly:
- Stalker ID → Xtream: `int(stalker_id)` (safe; all Stalker IDs are numeric)
- Xtream ID → Stalker: `str(xtream_id)`

No ID table needed.

### 4. Stream URL resolution — per type

| Stream type | Xtream route | Stalker resolution |
|---|---|---|
| Live | `/{u}/{p}/{stream_id}` | `client.live_tv.get_stream_url(channel.cmd)` after finding channel by ID |
| VOD | `/movie/{u}/{p}/{vod_id}.{ext}` | `client.vod.get_stream_url(f"/media/{vod_id}.mpg")` |
| Episode | `/series/{u}/{p}/{episode_id}.{ext}` | `client.vod.get_stream_url(f"/media/{episode_id}.mpg")` |

For live channels, we need to find the channel's `cmd` by scanning pages (same as the existing `get_stream_url_by_id`). For VOD and episodes, we construct the cmd directly using the `/media/{id}.mpg` pattern — this is already validated by `vod.get_stream_url_by_content_id`.

Stream delivery reuses the existing `stream_response()` helper from `server/routes/_helpers.py`, respecting `strm_proxy_streams` config.

### 5. VOD vs Series categories

Stalker's `get_categories()` returns a single list with no series/movie flag. We return the **same category list** for both `get_vod_categories` and `get_series_categories`. Content is filtered by `is_series` flag at the content level.

### 6. EPG

Return a minimal valid XMLTV document. Most Xtream clients will function without EPG data; this avoids the complexity of mapping STB EPG (if any) to XMLTV format.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE tv SYSTEM "xmltv.dtd">
<tv generator-info-name="stb-reader"></tv>
```

### 7. `get_series_info` — N+1 requests

This is the most expensive action. For a series with S seasons, it requires:
- 1 call to `get_seasons(series_id)`
- S calls to `get_episodes(series_id, season_id)` — one per season

For typical series (5–10 seasons), this is 6–11 sequential Stalker requests. Acceptable for an on-demand lookup. No caching needed in initial implementation.

---

## Response Shapes

### Login response (`/player_api.php` no action)

```json
{
  "user_info": {
    "username": "admin",
    "password": "secret",
    "message": "",
    "auth": 1,
    "status": "Active",
    "exp_date": null,
    "is_trial": "0",
    "active_cons": "0",
    "created_at": "0",
    "max_connections": "1",
    "allowed_output_formats": ["m3u8", "ts", "rtmp"]
  },
  "server_info": {
    "url": "http://server:8000",
    "port": "8000",
    "https_port": "443",
    "server_protocol": "http",
    "rtmp_port": "1935",
    "timezone": "Europe/London",
    "timestamp_now": 1234567890,
    "time_now": "2024-01-01 12:00:00",
    "process": true
  }
}
```

### `get_live_categories`

```json
[{"category_id": "1", "category_name": "Sports", "parent_id": 0}]
```

### `get_live_streams`

```json
[{
  "num": 1,
  "name": "CNN HD",
  "stream_type": "live",
  "stream_id": 12345,
  "stream_icon": "http://...",
  "epg_channel_id": "",
  "added": "0",
  "category_id": "1",
  "custom_sid": "",
  "tv_archive": 0,
  "direct_source": "",
  "tv_archive_duration": 0
}]
```

### `get_vod_categories` / `get_series_categories`

```json
[{"category_id": "1", "category_name": "Action", "parent_id": 0}]
```

### `get_vod_streams`

```json
[{
  "num": 1,
  "name": "Movie Title",
  "stream_type": "movie",
  "stream_id": 12345,
  "stream_icon": "http://...",
  "rating": "7.5",
  "rating_5based": 3.75,
  "added": "0",
  "category_id": "1",
  "container_extension": "mp4",
  "custom_sid": "",
  "direct_source": ""
}]
```

### `get_vod_info`

```json
{
  "info": {
    "name": "Movie Title",
    "cover_big": "http://...",
    "movie_image": "http://...",
    "releasedate": "2024",
    "episode_run_time": "120",
    "description": "...",
    "plot": "...",
    "genre": "Action",
    "rating": "7.5",
    "duration_secs": 7200,
    "duration": "2:00:00"
  },
  "movie_data": {
    "stream_id": 12345,
    "name": "Movie Title",
    "added": "0",
    "category_id": "1",
    "container_extension": "mp4",
    "custom_sid": "",
    "direct_source": ""
  }
}
```

### `get_series`

```json
[{
  "num": 1,
  "name": "Show Title",
  "series_id": 12345,
  "cover": "http://...",
  "plot": "...",
  "cast": "",
  "director": "",
  "genre": "",
  "releaseDate": "2024",
  "last_modified": "0",
  "rating": "8.0",
  "rating_5based": 4.0,
  "backdrop_path": [],
  "youtube_trailer": "",
  "episode_run_time": "",
  "category_id": "1"
}]
```

### `get_series_info`

```json
{
  "info": {
    "name": "Show Title",
    "cover": "http://...",
    "plot": "",
    "cast": "",
    "director": "",
    "genre": "",
    "releaseDate": "2024",
    "last_modified": "0",
    "rating": "",
    "rating_5based": 0,
    "backdrop_path": [],
    "youtube_trailer": "",
    "episode_run_time": "",
    "category_id": "1"
  },
  "episodes": {
    "1": [{
      "id": "56789",
      "episode_num": 1,
      "title": "Pilot",
      "container_extension": "mp4",
      "info": {"duration_secs": 0, "duration": "", "movie_image": "", "plot": "", "releaseDate": ""},
      "custom_sid": "",
      "added": "0",
      "season": 1,
      "direct_source": ""
    }]
  },
  "seasons": [{
    "air_date": "",
    "episode_count": 10,
    "id": 1,
    "name": "Season 1",
    "overview": "",
    "season_number": 1,
    "cover": "",
    "cover_big": ""
  }]
}
```

### M3U playlist (`/get.php`)

```
#EXTM3U
#EXTINF:-1 tvg-id="" tvg-name="CNN HD" tvg-logo="http://..." group-title="News",CNN HD
http://server:8000/admin/secret/12345.m3u8
```

---

## File Plan

| File | Change | Size |
|---|---|---|
| `server/config.py` | Add `xtream_username`, `xtream_password` fields | XS |
| `server/routes/xtream.py` | New file: all Xtream routes + helpers | L |
| `server/main.py` | Include xtream router before static mount | XS |
| `tests/test_xtream.py` | New file: tests for all Xtream endpoints | L |

---

## Task Breakdown

### Task 1 — Config (XS)
**File:** `server/config.py`

Add:
```python
xtream_username: str = "admin"
xtream_password: str = "password"
```

**Verify:** `Settings()` with env vars `XTREAM_USERNAME=x XTREAM_PASSWORD=y` works.

---

### Task 2 — `server/routes/xtream.py`: auth + login + server info (S)

- `_check_auth(u, p, settings)` → raises `HTTPException(403)` on mismatch
- `_login_response(settings, request)` → builds the login/server info JSON
- `GET/POST /player_api.php` with no `action` → return login response
- `GET/POST /player_api.php?action=<unknown>` → return `[]`

**Verify:** `GET /player_api.php?username=admin&password=password` → 200 with `user_info.auth=1`
**Verify:** `GET /player_api.php?username=wrong&password=wrong` → 403

---

### Task 3 — Live TV actions (S)

In `server/routes/xtream.py`:

- `action=get_live_categories` → `client.live_tv.get_genres()` → map to `[{category_id, category_name, parent_id}]`
- `action=get_live_streams` (optional `category_id`) → `_collect_all_pages(client.live_tv.get_channels, genre_id=cat or "*")` → map to stream list

**Stalker → Xtream channel mapping:**
- `num`: loop index (1-based)
- `stream_id`: `int(ch.id)`
- `name`: `ch.name`
- `stream_icon`: `ch.logo`
- `category_id`: `ch.genre_id`
- `epg_channel_id`, `added`, `custom_sid`, `tv_archive*`, `direct_source`: safe defaults

**Verify:** `action=get_live_categories` → list of dicts with `category_id` string
**Verify:** `action=get_live_streams&category_id=1` → filtered channel list

---

### Task 4 — VOD actions (S)

- `action=get_vod_categories` → `client.vod.get_categories()` → category list (all, not filtered by is_series)
- `action=get_vod_streams` (optional `category_id`) → `_collect_all_pages(client.vod.get_content, category_id=...)` filtered to `not c.is_series`
- `action=get_vod_info&vod_id=N` → scan content pages to find by id → build vod_info response

**Verify:** `action=get_vod_streams` → list of movies only (is_series=False)
**Verify:** `action=get_vod_info&vod_id=123` → single item with `info` + `movie_data`

---

### Task 5 — Series actions (S)

- `action=get_series_categories` → same as `get_vod_categories` (same source)
- `action=get_series` (optional `category_id`) → `_collect_all_pages(...)` filtered to `c.is_series`
- `action=get_series_info&series_id=N` → `get_seasons(str(N))` + for each season `get_episodes(str(N), season_id)` → build nested episodes dict + seasons list

**Seasons key in `episodes` dict:** use the season's natural number (parse from `season.name` like "Season 1" → `"1"`), fall back to loop index.

**Episode ID in response:** `int(episode.id)` — used by client to construct stream URL.

**Verify:** `action=get_series_info&series_id=N` → has `info`, `episodes` (dict keyed by season number), `seasons` list

---

### Task 6 — Stream URL endpoints (M)

Three new route patterns in `server/routes/xtream.py`:

```python
@router.get("/{username}/{password}/{stream_id}")
@router.get("/{username}/{password}/{stream_id}.{ext}")
async def live_stream(username, password, stream_id: int, ext: str = "m3u8", request, settings, client):
    _check_auth(username, password, settings)
    return await stream_response(settings, request,
        client.live_tv.get_stream_url_by_id, str(stream_id))

@router.get("/movie/{username}/{password}/{vod_id}.{ext}")
async def vod_stream(username, password, vod_id: int, ext: str, request, settings, client):
    _check_auth(username, password, settings)
    return await stream_response(settings, request,
        client.vod.get_stream_url_by_content_id, str(vod_id))

@router.get("/series/{username}/{password}/{episode_id}.{ext}")
async def series_stream(username, password, episode_id: int, ext: str, request, settings, client):
    _check_auth(username, password, settings)
    return await stream_response(settings, request,
        client.vod.get_stream_url_by_content_id, str(episode_id))
```

**Note on route ordering:** The live stream route `/{username}/{password}/{stream_id}` is very generic and will match many paths. It must be registered **after** more specific prefixes (`/movie/`, `/series/`, `/player_api.php`, `/get.php`, `/xmltv.php`, `/proxy`, `/health`). The xtream router must be mounted **last** in `main.py`.

**Verify:** `GET /{u}/{p}/12345` resolves live channel and returns 302 or proxied stream
**Verify:** `GET /movie/{u}/{p}/12345.mp4` resolves VOD and returns 302 or proxied stream

---

### Task 7 — M3U playlist (S)

`GET /get.php?username=X&password=Y&type=m3u_plus&output=ts`

- Auth check
- Collect all channels via `_collect_all_pages`
- Build M3U8+ text:
  ```
  #EXTM3U
  #EXTINF:-1 tvg-id="" tvg-name="{name}" tvg-logo="{logo}" group-title="{genre}",{name}
  {base_url}/{username}/{password}/{stream_id}.m3u8
  ```
- Return as `text/plain` (some clients want `application/x-mpegurl`)

**Genre name lookup:** we have `genre_id` on channel; fetch genres once to build an id→name map.

**Verify:** `GET /get.php?username=admin&password=password&type=m3u_plus` → text starting with `#EXTM3U`

---

### Task 8 — XMLTV stub (XS)

`GET /xmltv.php?username=X&password=Y`

- Auth check
- Return static XML:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE tv SYSTEM "xmltv.dtd">
  <tv generator-info-name="stb-reader"></tv>
  ```
- Content-Type: `application/xml`

**Verify:** Returns 200 with valid XML

---

### Task 9 — Wire up in main.py (XS)

In `server/main.py`, import and include the xtream router **before** the static mount but **after** all other routers:

```python
from .routes.xtream import router as xtream_router
app.include_router(xtream_router)
app.mount("/", StaticFiles(...))  # must remain last
```

The xtream router has no prefix — its routes are at root level.

**Verify:** Server starts; `GET /health` still works; `GET /player_api.php?username=admin&password=password` returns user_info

---

### Task 10 — Tests (M)

`tests/test_xtream.py` — follows existing test patterns (mock STB portal responses with `responses` library, use FastAPI `TestClient`):

- Auth: valid creds → 200, invalid → 403
- Login response structure: `user_info.auth == 1`, has `server_info`
- `get_live_categories`: maps to genre list
- `get_live_streams`: returns channels, filtered by category_id
- `get_vod_categories`: category list
- `get_vod_streams`: movies only (is_series=False filtered)
- `get_vod_info`: info + movie_data structure
- `get_series_categories`: category list
- `get_series`: series only (is_series=True filtered)
- `get_series_info`: episodes dict + seasons list
- Live stream route: check redirect or proxy
- VOD stream route: check redirect or proxy
- M3U playlist: starts with `#EXTM3U`, has channel entries
- XMLTV stub: valid XML response

---

## Dependency Order

```
Task 1 (config)
    └─ Task 2 (auth + login)
           ├─ Task 3 (live TV actions)
           ├─ Task 4 (VOD actions)
           ├─ Task 5 (series actions)
           ├─ Task 6 (stream URLs)    ← depends on Task 2 auth helper
           ├─ Task 7 (M3U)
           └─ Task 8 (XMLTV)
Task 9 (wire up) — after Tasks 2–8
Task 10 (tests) — after Task 9
```

---

## What We Are NOT Doing

- **EPG data**: Real EPG from Stalker is not mapped. XMLTV is a stub.
- **Catchup/timeshift**: Not in scope.
- **Panel API** (admin endpoints): Not in scope.
- **User management**: Single-tenant only; one configured username/password.
- **Short EPG / `get_short_epg` / `get_simple_data_table`**: Not in scope (return `[]`).
- **Caching**: No response caching for Xtream endpoints (the existing DB sync covers VOD; live TV is always fresh).
- **HDHomeRun emulation**: Out of scope.

---

## Open Questions / Risks

| Risk | Mitigation |
|---|---|
| `/{u}/{p}/{stream_id}` route catches too many paths | Register xtream router last; all other routes take priority |
| Series episode stream via `/media/{id}.mpg` might not work on all portals | Test with real portal; fallback can be added later |
| Large portals (thousands of channels) slow to respond | Acceptable for now; caching is a follow-up |
| Some Xtream clients send POST to `/player_api.php` with form body instead of query params | Handle both GET and POST; read params from query string (body params are rarely used in practice) |
