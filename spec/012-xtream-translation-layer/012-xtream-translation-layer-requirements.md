# Spec 012: Xtream Codes Translation Layer

## Objective

Expose an Xtream Codes API on top of the existing STB reader so that any
Xtream-compatible IPTV client (TiviMate, IPTV Smarters, GSE Player, VLC, Kodi,
etc.) can point at this server and work natively — without any knowledge of the
Stalker/Ministra portal underneath.

**User:** An operator who has a Stalker portal and wants to use it with modern
Xtream-compatible IPTV players, without running a separate proxy service.

**Success:** A fresh TiviMate or IPTV Smarters install can be pointed at
`http://<server>:<port>` with configured username/password and successfully
browse live TV, VOD, and series; resolve stream URLs; and play content.

---

## Assumptions

1. Single-tenant: one configured username/password maps to the single STB portal
   already configured in the server. No user database.
2. Stalker channel/content IDs are always numeric strings castable to int.
3. Episode streams can be resolved via `/media/{episode_id}.mpg` (same pattern
   as VOD movies — consistent with how `vod.get_stream_url_by_content_id` works).
4. No new Python package dependencies beyond what is already in `pyproject.toml`.
5. EPG: Stalker portals typically don't expose XMLTV-format EPG, so an empty
   stub is the correct scope for this iteration.
6. The existing `strm_proxy_streams` config flag governs whether stream delivery
   proxies or redirects — Xtream routes follow the same rule.
7. All categories (VOD + series share the same source) are returned for both
   `get_vod_categories` and `get_series_categories`.

---

## User Stories

- As an IPTV client user, I want to enter my server URL, username, and password
  in my player and see all live TV channels organized by genre.
- As an IPTV client user, I want to browse and play VOD movies from my portal
  through my Xtream-compatible player.
- As an IPTV client user, I want to browse series, navigate seasons and episodes,
  and play any episode through my Xtream-compatible player.
- As an operator, I want to configure the Xtream credentials independently of
  the STB portal MAC/serial so I can share them safely.

---

## Functional Requirements

### Authentication

- **FR-1:** The server accepts `XTREAM_USERNAME` and `XTREAM_PASSWORD` as
  environment variables (defaults: `"admin"` / `"password"`).
- **FR-2:** Every Xtream endpoint validates the supplied `username` and
  `password` parameters against these configured values. Mismatched credentials
  return a response indicating authentication failure (HTTP 403 for API
  endpoints; `{"user_info": {"auth": 0}}` for `/player_api.php` with no action
  is also acceptable per Xtream convention — use HTTP 403 for clarity).
- **FR-3:** Auth check is case-sensitive.

### Player API — Login / Server Info

- **FR-4:** `GET /player_api.php?username=X&password=Y` (no `action`) returns a
  JSON object with `user_info` and `server_info` fields. `user_info.auth` is `1`
  for valid credentials.
- **FR-5:** `POST /player_api.php` with the same query params works identically
  to GET (some clients POST).
- **FR-6:** An unknown `action` value returns `[]`.

### Player API — Live TV

- **FR-7:** `action=get_live_categories` returns an array of objects:
  `[{"category_id": "<str>", "category_name": "<str>", "parent_id": 0}]`
  sourced from `client.live_tv.get_genres()`.
- **FR-8:** `action=get_live_streams` returns all live channels as a flat array.
  Optional `category_id` query parameter filters by genre. Each item includes:
  `num`, `name`, `stream_type="live"`, `stream_id` (int), `stream_icon`,
  `epg_channel_id`, `added`, `category_id`, `custom_sid`, `tv_archive`,
  `direct_source`, `tv_archive_duration`.
- **FR-9:** All pages of the Stalker channel list are collected before returning.

### Player API — VOD

- **FR-10:** `action=get_vod_categories` returns the same category shape as
  FR-7, sourced from `client.vod.get_categories()`.
- **FR-11:** `action=get_vod_streams` returns all non-series VOD content
  (`is_series=False`) as a flat array. Optional `category_id` filter. Each item:
  `num`, `name`, `stream_type="movie"`, `stream_id` (int), `stream_icon`,
  `rating`, `rating_5based`, `added`, `category_id`, `container_extension="mp4"`,
  `custom_sid`, `direct_source`.
- **FR-12:** `action=get_vod_info&vod_id=N` returns a single object with `info`
  and `movie_data` subobjects for the matching content item. Returns `{}` if not
  found.

### Player API — Series

- **FR-13:** `action=get_series_categories` returns the same list as
  `get_vod_categories` (same source, same shape).
- **FR-14:** `action=get_series` returns all series (`is_series=True`) as a flat
  array. Optional `category_id` filter. Each item: `num`, `name`,
  `series_id` (int), `cover`, `plot`, `cast`, `director`, `genre`, `releaseDate`,
  `last_modified`, `rating`, `rating_5based`, `backdrop_path`, `youtube_trailer`,
  `episode_run_time`, `category_id`.
- **FR-15:** `action=get_series_info&series_id=N` returns an object with:
  - `info`: series metadata
  - `episodes`: dict keyed by season number string (e.g. `"1"`, `"2"`), each
    value a list of episode objects with `id`, `episode_num`, `title`,
    `container_extension`, `info`, `custom_sid`, `added`, `season`,
    `direct_source`.
  - `seasons`: list of season objects with `air_date`, `episode_count`, `id`,
    `name`, `overview`, `season_number`, `cover`, `cover_big`.
- **FR-16:** Season number key in the `episodes` dict is parsed from the season
  name (e.g. `"Season 1"` → `"1"`); falls back to the 1-based loop index if
  parsing fails.

### Stream Delivery

- **FR-17:** `GET /{username}/{password}/{stream_id}` and
  `GET /{username}/{password}/{stream_id}.{ext}` resolve and deliver the live
  channel stream for the given `stream_id` (Stalker channel ID as int → str).
- **FR-18:** `GET /movie/{username}/{password}/{vod_id}.{ext}` resolves and
  delivers the VOD stream via `client.vod.get_stream_url_by_content_id(str(vod_id))`.
- **FR-19:** `GET /series/{username}/{password}/{episode_id}.{ext}` resolves and
  delivers the episode stream via the same content-id mechanism
  (`client.vod.get_stream_url_by_content_id(str(episode_id))`).
- **FR-20:** Stream delivery reuses the existing `stream_response()` helper:
  HTTP 302 redirect when `strm_proxy_streams=false`; full proxy when `true`.
- **FR-21:** Stream routes respect the same error handling as existing stream
  routes: 404 for NotFoundError, 502 for StreamError/STBError.

### M3U Playlist

- **FR-22:** `GET /get.php?username=X&password=Y&type=m3u_plus` (and `type=m3u`)
  returns an M3U8+ playlist of all live channels as `text/plain`.
- **FR-23:** Each entry uses `#EXTINF:-1 tvg-id="" tvg-name="{name}" tvg-logo="{logo}" group-title="{genre_name}",{name}` followed by the stream URL `{base_url}/{username}/{password}/{stream_id}.m3u8`.
- **FR-24:** Genre name in `group-title` is resolved by fetching genres once and
  building an id→name map.

### EPG

- **FR-25:** `GET /xmltv.php?username=X&password=Y` returns a minimal valid
  XMLTV document (empty `<tv>` element) with `Content-Type: application/xml`.

### Route Registration

- **FR-26:** The Xtream router is registered in `main.py` after all existing
  routers and before the static file mount. This ensures the catch-all live
  stream route `/{username}/{password}/{stream_id}` does not shadow `/health`,
  `/live-tv/*`, `/vod/*`, `/library/*`, `/proxy`, `/player_api.php`, `/get.php`,
  `/xmltv.php`.

---

## Non-Functional Requirements

- **NFR-1:** No new runtime dependencies. Only packages already listed in
  `pyproject.toml` may be used.
- **NFR-2:** The existing `/health` and all existing routes continue to work
  after the xtream router is added.
- **NFR-3:** All Xtream API responses use `application/json` (FastAPI default)
  except `/get.php` (`text/plain`) and `/xmltv.php` (`application/xml`).
- **NFR-4:** Tests follow the existing pattern: `responses` library mocks for
  STB portal HTTP, `MagicMock` for `STBClient`, `FastAPI TestClient`.

---

## Out of Scope

- EPG data: `/xmltv.php` returns an empty stub; no Stalker EPG mapping.
- `get_short_epg` and `get_simple_data_table` actions: return `[]`.
- Catchup / timeshift API.
- Panel / admin API.
- Multi-user / user database: single configured username/password only.
- Response caching for Xtream endpoints.
- HDHomeRun emulation.
- VOD in M3U playlist (`/get.php` covers live channels only).

---

## Tech Stack

- Python 3.11+, FastAPI, Uvicorn
- `stb_reader/` library (existing): `ITVService`, `VODService`, `STBClient`
- `server/routes/_helpers.py`: `stream_response()`, `_proxy_url()`
- `server/config.py`: Pydantic Settings
- pytest + responses + FastAPI TestClient (existing test stack)

---

## Commands

```
# Run all tests
pytest

# Run only Xtream tests
pytest tests/test_xtream.py -v

# Run with coverage
pytest --cov=server --cov=stb_reader --cov-report=term-missing

# Lint (if configured)
ruff check .

# Start dev server
uvicorn server.main:app --reload
```

---

## Project Structure

```
server/
  config.py              ← Add xtream_username, xtream_password
  main.py                ← Include xtream router (after existing, before static)
  routes/
    xtream.py            ← New: all Xtream Codes routes
    _helpers.py          ← Existing: stream_response(), _proxy_url() (unchanged)

tests/
  test_xtream.py         ← New: all Xtream route tests
  conftest.py            ← Existing (unchanged)

spec/012-xtream-translation-layer/
  012-xtream-translation-layer-plan.md
  012-xtream-translation-layer-requirements.md  ← this file
```

---

## Code Style

Follow the existing patterns in `server/routes/live_tv.py` and `server/routes/vod.py`:

```python
# server/routes/xtream.py
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, PlainTextResponse
from stb_reader.models import Genre, Channel, Category, Content

router = APIRouter(tags=["xtream"])


def _check_auth(username: str, password: str, settings) -> None:
    if username != settings.xtream_username or password != settings.xtream_password:
        raise HTTPException(status_code=403, detail="Invalid credentials")


def _collect_all_pages(fn, **kwargs) -> list:
    items, page = [], 1
    while True:
        result = fn(**kwargs, page=page)
        items.extend(result.items)
        if not result.items or page * result.per_page >= result.total:
            break
        page += 1
    return items


@router.get("/player_api.php")
@router.post("/player_api.php")
async def player_api(
    username: str = Query(...),
    password: str = Query(...),
    action: str | None = Query(default=None),
    ...
    request: Request = None,
):
    _check_auth(username, password, request.app.state.settings)
    ...
```

- Access `client`, `settings` via `request.app.state.*`
- Return plain `dict` / `list` — FastAPI serialises to JSON
- Reuse `stream_response()` from `._helpers` for all stream delivery
- Keep route file flat — no sub-classes, no abstraction layers

---

## Testing Strategy

- **Framework:** pytest
- **Test file:** `tests/test_xtream.py`
- **Pattern:** match `tests/test_server.py` — `MagicMock` for `STBClient`,
  `patch.dict("os.environ", ENV_VARS)`, `FastAPI TestClient`, no real HTTP
- **ENV_VARS** in test file must include `XTREAM_USERNAME` and `XTREAM_PASSWORD`

**Coverage targets:**

| Area | Tests required |
|---|---|
| Auth | valid creds → 200; invalid → 403 |
| Login response | `user_info.auth == 1`; has `server_info` |
| `get_live_categories` | correct shape; maps genre fields |
| `get_live_streams` | all channels returned; `category_id` filter passed through |
| `get_vod_categories` | correct shape |
| `get_vod_streams` | only non-series items; `stream_type == "movie"` |
| `get_vod_info` | `info` + `movie_data` present; unknown id returns `{}` |
| `get_series_categories` | same list as vod categories |
| `get_series` | only series items; `series_id` is int |
| `get_series_info` | `episodes` dict keyed by season number; `seasons` list present |
| Live stream route | calls `get_stream_url_by_id`; returns 302 (redirect mode) |
| VOD stream route | calls `get_stream_url_by_content_id`; returns 302 |
| Series stream route | calls `get_stream_url_by_content_id`; returns 302 |
| M3U playlist | response starts with `#EXTM3U`; channel entries present |
| XMLTV stub | 200; `Content-Type: application/xml`; valid XML |
| Unknown action | returns `[]` |

---

## Boundaries

**Always:**
- Run `pytest` before declaring a task done
- Validate credentials on every Xtream endpoint
- Collect all Stalker pages before returning a flat list
- Register the xtream router after all other routers in `main.py`

**Ask first:**
- Changing `pyproject.toml` dependencies
- Modifying `server/routes/_helpers.py` (shared with existing routes)
- Any change to `stb_reader/` core library
- Adding DB schema changes

**Never:**
- Return real stream URLs in JSON responses (only in stream delivery routes via redirect/proxy)
- Skip auth validation on any Xtream endpoint
- Add caching without a spec update

---

## Success Criteria

1. `pytest tests/test_xtream.py` passes with all tests green.
2. `pytest` (full suite) passes — no regressions on existing routes.
3. `GET /player_api.php?username=admin&password=password` returns JSON with
   `user_info.auth == 1` and a `server_info` block.
4. `GET /player_api.php?username=wrong&password=wrong&action=get_live_categories`
   returns HTTP 403.
5. `GET /player_api.php?username=admin&password=password&action=get_live_streams`
   returns a JSON array where every item has `stream_id` (integer) and
   `stream_type == "live"`.
6. `GET /player_api.php?username=admin&password=password&action=get_series_info&series_id=N`
   returns an object with `episodes` (dict keyed by season number string) and
   `seasons` (list).
7. `GET /get.php?username=admin&password=password&type=m3u_plus` returns a
   response whose body starts with `#EXTM3U`.
8. `GET /xmltv.php?username=admin&password=password` returns HTTP 200 with
   `Content-Type: application/xml` and a body containing `<tv`.
9. `GET /health` still returns `{"status": "ok"}` after the xtream router is
   added (no route shadowing).
10. `GET /{username}/{password}/{stream_id}` does not match `/health` or
    `/player_api.php` paths (route ordering is correct).

---

## Open Questions

None. All requirements are drawn from the approved plan.
