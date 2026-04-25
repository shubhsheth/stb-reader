# Plan: STB API Server (001)

## Component Map & Dependency Order

```
exceptions.py ──┐
models.py ──────┤
                ▼
              _http.py
                │
          ┌─────┴─────┐
          ▼           ▼
        auth.py    live_tv.py   vod.py
          │           │           │
          └─────┬─────┘           │
                ▼                 │
            client.py ────────────┘
                │
          ┌─────┴──────────────┐
          ▼                    ▼
    server/config.py    tests/conftest.py
          │                    │
    server/main.py        test_*.py files
          │
    routes/live_tv.py
    routes/vod.py
          │
       Dockerfile
```

No cycles. Build order is strictly bottom-up.

---

## Implementation Phases

### Phase A — Package Scaffold
Files: `pyproject.toml`

Defines the package, Python version constraint, runtime deps (`requests`), and optional `[server]` extras (`fastapi`, `uvicorn`, `pydantic-settings`). This gates everything else.

**Checkpoint:** `pip install -e .` succeeds; `pip install -e ".[server]"` succeeds.

---

### Phase B — Domain Foundation
Files: `stb_reader/exceptions.py`, `stb_reader/models.py`, `stb_reader/_http.py`

**`exceptions.py`** — Three classes:
- `STBError(Exception)` — base
- `AuthError(STBError)` — handshake/token failures
- `StreamError(STBError)` — create_link errors (e.g. `nothing_to_play`)

**`models.py`** — Pure dataclasses (no methods, no validation):
```
Genre(id, title, alias, censored: bool)
Channel(id, number, name, cmd, logo, genre_id, hd: bool, censored: bool)
Category(id, title, alias, censored: bool)
Content(id, name, cmd, screenshot_uri, genres, year, description, rating, duration, is_series: bool, fav: bool)
Season(id, name, video_id)
Episode(id, name, series_number, cmd)
PagedResult(items: list, total: int, page: int, per_page: int)
```

**`_http.py`** — `STBSession` wraps `requests.Session`:
- Constructor args: `base_url`, `mac`, `serial`, `lang`, `timezone`
- Stores token (initially `""`)
- `get(type, action, **params) -> dict` method:
  1. Builds URL: `{base_url}/stalker_portal/c/portal.php`
  2. Merges fixed params (`JsHttpRequest=1-xml`, `type`, `action`) with `**params`
  3. Sets headers: `Authorization: Bearer {token}`, `User-Agent`, `X-User-Agent`, `Cookie`
  4. Makes GET request; raises `STBError` on non-2xx
  5. Unwraps and returns `response.json()["js"]`

**Checkpoint:** `from stb_reader._http import STBSession` works; unit test verifies header injection and `js` unwrapping with a mocked response.

---

### Phase C — Auth
Files: `stb_reader/auth.py`, `stb_reader/client.py`, `stb_reader/__init__.py`

**`auth.py`** — two functions (not methods, easier to test):
- `handshake(session: STBSession) -> str` — returns token; sets `session.token`
- `get_profile(session: STBSession) -> dict` — returns raw profile dict

**`client.py`** — `STBClient`:
```python
@dataclass
class STBClient:
    base_url: str
    mac: str
    serial: str = "000000000000"
    lang: str = "en"
    timezone: str = "Europe/London"
    _session: STBSession = field(init=False)
    live_tv: ITVService = field(init=False)
    vod: VODService = field(init=False)

    def __post_init__(self):
        self._session = STBSession(self.base_url, self.mac, self.serial, self.lang, self.timezone)
        self.live_tv = ITVService(self._session)
        self.vod = VODService(self._session)

    def authenticate(self) -> None:
        handshake(self._session)
        get_profile(self._session)
```

**`__init__.py`** — exports `STBClient` only.

**Checkpoint:** `from stb_reader import STBClient; c = STBClient("http://x", "00:00:00:00:00:00"); c.authenticate()` works (mocked).

---

### Phase D — Services
Files: `stb_reader/live_tv.py`, `stb_reader/vod.py`

**`ITVService`:**
| Method | STB call | Notes |
|--------|----------|-------|
| `get_genres()` | `itv/get_genres` | Returns `list[Genre]` |
| `get_channels(genre_id, page, sort, hd, fav)` | `itv/get_ordered_list` | Translates `page` → `p = page - 1` (0-indexed) |
| `get_stream_url(channel: Channel)` | `itv/create_link` | Strips `ffmpeg ` prefix; raises `StreamError` on error field |

**`VODService`:**
| Method | STB call | Notes |
|--------|----------|-------|
| `get_categories()` | `vod/get_categories` | Returns `list[Category]` |
| `get_content(category_id, page, sort, fav)` | `vod/get_ordered_list` | Page is 1-indexed (matches STB) |
| `get_seasons(series_id)` | `vod/get_ordered_list` | Params: `movie_id=series_id, season_id=0, episode_id=0` |
| `get_episodes(series_id, season_id)` | `vod/get_ordered_list` | Params: `movie_id, season_id, episode_id=0` |
| `get_stream_url(cmd: str)` | `vod/create_link` | Strips `ffmpeg ` prefix; returns `result["cmd"]` (preferred over `result["url"]`) |

**Stream URL cleaning** (shared logic, private function `_clean_url(url: str) -> str`):
- Strips leading `ffmpeg ` prefix
- Strips leading `auto ` prefix (some portal variants)

**Checkpoint:** `pytest tests/test_live_tv.py tests/test_vod.py` all pass.

---

### Phase E — Server
Files: `server/__init__.py`, `server/config.py`, `server/main.py`, `server/routes/__init__.py`, `server/routes/live_tv.py`, `server/routes/vod.py`

**`config.py`** — Pydantic `BaseSettings`:
```
STB_PORTAL_URL   (required)
STB_MAC          (required)
STB_SERIAL       (default: "000000000000")
STB_LANG         (default: "en")
STB_TIMEZONE     (default: "Europe/London")
PORT             (default: 8000)
```
Fail fast with a clear error if required vars are missing.

**`main.py`** — FastAPI app:
- Lifespan context manager: construct `STBClient`, call `authenticate()`, store in `app.state.client`
- Include routers for `/live-tv` and `/vod`
- `GET /health` → `{"status": "ok"}`

**`routes/live_tv.py`:**
```
GET /live-tv/genres                          → list[Genre]
GET /live-tv/channels                        → PagedResult[Channel]  (query: genre_id, page, sort, hd, fav)
GET /live-tv/channels/{channel_id}/stream    → 302 redirect
```
The stream route must first fetch the channel list to get the `cmd` value. Since channels have `id` and `cmd`, the route calls `get_channels()` with `genre_id="*"` and paginates until the channel is found — **or** the client is extended with a `get_channel_by_id` helper that fetches a single page filtered appropriately.

> **Design note:** To avoid full list scan, `get_channels` accepts a `channel_id` lookup shortcut: it fetches page 1 with high `max_page_items` and filters client-side. If not found, it paginates. This is deferred to implementation — the route simply calls `live_tv.get_stream_url_by_id(channel_id)` which encapsulates the logic.

**`routes/vod.py`:**
```
GET /vod/categories                                          → list[Category]
GET /vod/content                                             → PagedResult[Content]
GET /vod/content/{content_id}/seasons                        → list[Season]
GET /vod/content/{content_id}/seasons/{season_id}/episodes   → list[Episode]
GET /vod/content/{content_id}/stream                         → 302 redirect
GET /vod/episodes/{episode_id}/stream                        → 302 redirect
```

VOD stream routes have the same lookup problem. `VODService` will get `get_stream_url_for_content(content_id)` and `get_stream_url_for_episode(episode_id, series_id)` helpers.

**Checkpoint:** `TestClient` integration tests for all routes pass with mocked STB responses.

---

### Phase F — Docker
File: `Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY stb_reader/ stb_reader/
COPY server/ server/
RUN pip install ".[server]"
EXPOSE 8000
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Checkpoint:** `docker build` succeeds; `docker run -e STB_PORTAL_URL=... -e STB_MAC=... -p 8000:8000` starts the server and `curl localhost:8000/health` returns `{"status":"ok"}`.

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Different portal versions return different JSON shapes | Medium | Use `.get(key, default)` everywhere; log unexpected shapes |
| Token expires mid-operation | Low | Catch `AuthError` in route handlers, call `client.authenticate()`, retry once |
| `channel_id` lookup requires paginating all channels | Medium | Add `get_stream_url_by_id` helper with early-exit pagination |
| `ffmpeg`/`auto` URL prefix variants missed | Low | Centralise in `_clean_url()`; easy to extend |
| Server fails to start if STB unreachable | Expected | Lifespan logs clearly and raises so the container exits with non-zero code |

---

## Parallel vs Sequential

- Phases A → B → C → D → E → F must be sequential (hard dependency chain)
- Within Phase D, `routes/live_tv.py` and `routes/vod.py` can be written in parallel
- Within Phase E, `test_live_tv.py` and `test_vod.py` can be written in parallel
- Tests for each service can be written alongside (TDD) or after the service

---

## Verification Checkpoints Summary

| After Phase | Check |
|-------------|-------|
| A | `pip install -e ".[server]"` ✓ |
| B | `from stb_reader._http import STBSession` + unit test ✓ |
| C | `STBClient(...).authenticate()` works with mocked HTTP ✓ |
| D | All service method unit tests pass ✓ |
| E | All route integration tests pass via `TestClient` ✓ |
| F | `docker build && docker run` + `curl /health` ✓ |
