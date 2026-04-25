# Tasks: STB API Server (001)

Tasks are ordered by dependency. Each must pass its verification step before the next begins.

---

- [ ] **Task 1: Package scaffold**
  - Acceptance: `pyproject.toml` defines the `stb_reader` package with `requests` as a runtime dep and `fastapi`, `uvicorn[standard]`, `pydantic-settings` under `[project.optional-dependencies] server`. Python `>=3.11` constraint set.
  - Verify: `pip install -e .` succeeds with no errors; `pip install -e ".[server]"` succeeds; `python -c "import stb_reader"` works (empty package is fine at this stage).
  - Files: `pyproject.toml`, `stb_reader/__init__.py`

---

- [ ] **Task 2: Exceptions and models**
  - Acceptance: `STBError`, `AuthError`, `StreamError` are defined and form a hierarchy (`AuthError` and `StreamError` both subclass `STBError`). All eight dataclasses (`Genre`, `Channel`, `Category`, `Content`, `Season`, `Episode`, `PagedResult`) are importable with the correct fields and types as specified in the plan.
  - Verify: `python -c "from stb_reader.models import Genre, Channel, Category, Content, Season, Episode, PagedResult; from stb_reader.exceptions import STBError, AuthError, StreamError"` exits 0.
  - Files: `stb_reader/exceptions.py`, `stb_reader/models.py`

---

- [ ] **Task 3: HTTP session wrapper**
  - Acceptance: `STBSession.get(type, action, **params)` builds the correct URL (`{base_url}/stalker_portal/c/portal.php`), sends all required headers (`Authorization: Bearer {token}`, `User-Agent`, `X-User-Agent`, `Cookie` with mac/lang/timezone/PHPSESSID), includes `JsHttpRequest=1-xml` in the query string, and unwraps the `{"js": ...}` envelope. Non-2xx responses raise `STBError`.
  - Verify: `pytest tests/test_http.py` — tests cover: correct URL construction, all headers present, `js` unwrapping, `STBError` on 4xx/5xx.
  - Files: `stb_reader/_http.py`, `tests/conftest.py`, `tests/test_http.py`

---

- [ ] **Task 4: Auth module and STBClient**
  - Acceptance: `handshake(session)` calls `type=stb, action=handshake`, extracts the `token` from the response, sets `session.token`, and returns the token string. `get_profile(session)` calls `type=stb, action=get_profile` and returns the raw dict. `STBClient.__post_init__` constructs an `STBSession` and attaches `live_tv` and `vod` service stubs. `STBClient.authenticate()` calls `handshake` then `get_profile` in order.
  - Verify: `pytest tests/test_auth.py` — tests cover: token extracted and set on session, `authenticate()` makes two requests in correct order, `AuthError` raised when handshake response has no token.
  - Files: `stb_reader/auth.py`, `stb_reader/client.py`, `stb_reader/__init__.py`, `tests/test_auth.py`

---

- [ ] **Task 5: ITVService — Live TV**
  - Acceptance:
    - `get_genres()` calls `itv/get_genres` and returns `list[Genre]`.
    - `get_channels(genre_id, page, sort, hd, fav)` calls `itv/get_ordered_list` with `p = page - 1` (0-indexed translation) and returns `PagedResult[Channel]`.
    - `get_stream_url(cmd)` calls `itv/create_link`, raises `StreamError` if `error` field is non-empty, strips `ffmpeg ` and `auto ` prefixes from the returned URL.
    - `get_stream_url_by_id(channel_id)` paginates `get_channels()` until a channel with matching `id` is found, then calls `get_stream_url`; raises `STBError("channel not found")` if exhausted.
  - Verify: `pytest tests/test_live_tv.py` — tests cover: genre list parsing, channel pagination with correct 0-index translation, `ffmpeg `+`auto ` prefix stripping, `StreamError` on error field, `channel_id` not found case.
  - Files: `stb_reader/live_tv.py`, `tests/test_live_tv.py`

---

- [ ] **Task 6: VODService — VOD & Series**
  - Acceptance:
    - `get_categories()` calls `vod/get_categories` and returns `list[Category]`.
    - `get_content(category_id, page, sort, fav)` calls `vod/get_ordered_list` with `p = page` (1-indexed, matches STB) and returns `PagedResult[Content]`.
    - `get_seasons(series_id)` calls `vod/get_ordered_list` with `movie_id=series_id, season_id=0, episode_id=0` and returns `list[Season]`.
    - `get_episodes(series_id, season_id)` calls `vod/get_ordered_list` with `movie_id, season_id, episode_id=0` and returns `list[Episode]`.
    - `get_stream_url(cmd)` calls `vod/create_link`, strips prefixes, raises `StreamError` on error.
    - `get_stream_url_by_content_id(content_id)` and `get_stream_url_by_episode_id(episode_id, series_id)` paginate to find the matching item and resolve the URL.
  - Verify: `pytest tests/test_vod.py` — tests cover: category/content parsing, season and episode list parsing, 1-indexed page passthrough, stream URL resolution, prefix stripping.
  - Files: `stb_reader/vod.py`, `tests/test_vod.py`

---

- [ ] **Task 7: Server config and health endpoint**
  - Acceptance: `Settings` (Pydantic `BaseSettings`) reads `STB_PORTAL_URL`, `STB_MAC`, `STB_SERIAL`, `STB_LANG`, `STB_TIMEZONE`, `PORT` from environment. Missing required vars (`STB_PORTAL_URL`, `STB_MAC`) produce a clear validation error at startup. FastAPI lifespan constructs `STBClient`, calls `authenticate()`, and stores the client on `app.state`. `GET /health` returns `200 {"status": "ok"}`.
  - Verify: `pytest tests/test_server.py::test_health` using `TestClient` with env vars patched; also verify that starting without `STB_PORTAL_URL` raises a validation error (not a silent failure).
  - Files: `server/__init__.py`, `server/config.py`, `server/main.py`, `tests/test_server.py`

---

- [ ] **Task 8: Live TV routes**
  - Acceptance:
    - `GET /live-tv/genres` → `200` with `[{"id": ..., "title": ..., "alias": ..., "censored": ...}, ...]`
    - `GET /live-tv/channels?genre_id=*&page=1&sort=number` → `200` with `{"data": [...], "page": 1, "total": N, "per_page": N}`
    - `GET /live-tv/channels/{channel_id}/stream` → `302` with `Location` header set to the clean stream URL; returns `404` if channel not found, `502` if STB returns a stream error.
  - Verify: `pytest tests/test_server.py::TestLiveTV` — covers all three endpoints including the 302 redirect, 404 not-found, and 502 stream-error cases.
  - Files: `server/routes/__init__.py`, `server/routes/live_tv.py`, `tests/test_server.py` (extend)

---

- [ ] **Task 9: VOD routes**
  - Acceptance:
    - `GET /vod/categories` → `200` with category list.
    - `GET /vod/content?category_id=&page=1&sort=added` → `200` with paged envelope.
    - `GET /vod/content/{content_id}/seasons` → `200` with season list.
    - `GET /vod/content/{content_id}/seasons/{season_id}/episodes` → `200` with episode list.
    - `GET /vod/content/{content_id}/stream` → `302` to stream URL (movie).
    - `GET /vod/episodes/{episode_id}/stream` → `302` to stream URL (episode).
    - All stream routes return `404` for unknown IDs and `502` on STB stream errors.
  - Verify: `pytest tests/test_server.py::TestVOD` — covers all six endpoints including error cases.
  - Files: `server/routes/vod.py`, `tests/test_server.py` (extend)

---

- [ ] **Task 10: Dockerfile and final smoke test**
  - Acceptance: `Dockerfile` uses `python:3.11-slim`, copies `pyproject.toml`, `stb_reader/`, and `server/`, runs `pip install ".[server]"`, exposes port 8000, and sets `CMD` to `uvicorn server.main:app --host 0.0.0.0 --port 8000`. `pytest` full suite passes with ≥90% coverage on `stb_reader/`.
  - Verify:
    1. `docker build -t stb-reader .` exits 0.
    2. `pytest --cov=stb_reader --cov-report=term-missing` shows ≥90% coverage and zero failures.
  - Files: `Dockerfile`
