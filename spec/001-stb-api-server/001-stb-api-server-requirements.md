# Spec: STB API Server (001)

## Objective

Turn the protocol documentation in `docs/` into a deployable HTTP server that abstracts all Ministra/Stalker Portal STB complexity behind clean REST endpoints. Any language or service can consume the API via standard HTTP — no STB protocol knowledge required by the caller.

A companion Python library (`stb_reader`) implements the STB protocol and is the engine that powers the server. The server is a thin FastAPI wrapper around it.

**Users:** Developers building home automation, media frontends, or scripts that need to query channels, browse VOD, or obtain playable stream URLs from an STB portal.

**Success looks like:** A developer can `docker run` the server, hit `GET /live-tv/channels`, and get a clean JSON list of channels — then point a media player at `GET /live-tv/channels/{id}/stream` and have it play immediately.

---

## User Stories

- As a developer, I want to list all live TV channels (optionally filtered by genre) so that I can build a channel guide.
- As a developer, I want a stream endpoint that redirects directly to a playable URL so that I can pass the endpoint URL to a media player without extra steps.
- As a developer, I want to browse VOD categories and content so that I can build a VOD library UI.
- As a developer, I want series season/episode navigation so that I can drill into a show's episodes and stream one.
- As a developer, I want the server to handle STB authentication transparently so that I never deal with tokens, cookies, or device headers.

---

## Functional Requirements

- **FR-1:** Server authenticates with the STB portal on startup (handshake + get_profile) and stores the session token in memory.
- **FR-2:** Server auto-re-authenticates silently when a request fails with an auth error.
- **FR-3:** `GET /live-tv/genres` returns a list of channel genre objects.
- **FR-4:** `GET /live-tv/channels` returns a paginated list of channels, accepting optional query params: `genre_id`, `page` (1-indexed), `sort` (`number`|`name`|`fav`), `hd` (bool), `fav` (bool).
- **FR-5:** `GET /live-tv/channels/{channel_id}/stream` resolves the channel's stream command and returns HTTP 302 to the playable URL.
- **FR-6:** `GET /vod/categories` returns a list of VOD category objects.
- **FR-7:** `GET /vod/content` returns a paginated list of VOD content, accepting optional query params: `category_id`, `page` (1-indexed), `sort` (`added`|`popular`|`rating`|`name`), `fav` (bool).
- **FR-8:** `GET /vod/content/{content_id}/seasons` returns the list of seasons for a series.
- **FR-9:** `GET /vod/content/{content_id}/seasons/{season_id}/episodes` returns the episode list for a season.
- **FR-10:** `GET /vod/content/{content_id}/stream` resolves and redirects (302) to the stream URL for a movie.
- **FR-11:** `GET /vod/episodes/{episode_id}/stream` resolves and redirects (302) to the stream URL for a series episode.
- **FR-12:** `GET /health` returns `{"status": "ok"}` when the server is running and authenticated.
- **FR-13:** Stream URLs prefixed with `ffmpeg ` are stripped to a bare URL before redirecting.
- **FR-14:** Pagination is always 1-indexed in the REST API, regardless of underlying STB protocol quirks.
- **FR-15:** All list responses use a consistent envelope: `{"data": [...], "page": 1, "total": 500, "per_page": 14}`.

---

## Non-Functional Requirements

- **NFR-1:** Each endpoint must respond in under 3 seconds under normal network conditions.
- **NFR-2:** Server configuration is entirely via environment variables (no config files required).
- **NFR-3:** The core `stb_reader` library has no FastAPI dependency — it is usable standalone.
- **NFR-4:** The server exposes no authentication of its own (intended for trusted internal networks).
- **NFR-5:** The server must run as a single process with no external database or cache dependency.

---

## Out of Scope

- PVR / DVR recording support
- Favourites write operations (add/remove fav)
- Parental control / PIN unlock flows
- EPG (Electronic Programme Guide) data
- Multi-portal / multi-tenant support
- HTTPS termination (delegate to a reverse proxy)
- Server-side auth (API keys, OAuth)
- Playlist (M3U) export endpoints

---

## Assumptions

- Python 3.11+ is acceptable as the runtime.
- The STB portal is reachable from the server's network.
- A single MAC address / device identity is used for the session.
- The STB token does not expire during normal operation but may need refresh on server restart.
- `ffmpeg`-wrapped URLs are the only non-standard stream format needing cleanup (HLS and direct HTTP work as-is).

---

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Language | Python 3.11+ | Ecosystem fit, existing STB tooling is Python |
| HTTP server | FastAPI + Uvicorn | Fast, typed, auto-docs |
| STB HTTP client | `requests` (sync) | Simple; server runs sync workers |
| Data models | Python `dataclasses` | Lightweight, no extra deps |
| Packaging | `pyproject.toml` (Hatchling) | Modern Python packaging |
| Container | Docker (single image) | One-command deployment |
| Tests | `pytest` + `responses` (mock HTTP) | Standard, well-supported |

---

## Commands

```
# Install library only
pip install -e .

# Install with server extras
pip install -e ".[server]"

# Run server (development)
uvicorn server.main:app --reload

# Run server (production)
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Run tests
pytest

# Run tests with coverage
pytest --cov=stb_reader --cov-report=term-missing

# Docker build
docker build -t stb-reader .

# Docker run
docker run -e STB_PORTAL_URL=http://portal.example.com \
           -e STB_MAC=00:1A:79:XX:XX:XX \
           -p 8000:8000 stb-reader
```

---

## Project Structure

```
stb-reader/
├── stb_reader/               # Core library (pip-installable, no FastAPI dep)
│   ├── __init__.py           # Exports STBClient
│   ├── client.py             # STBClient: entry point, holds session + services
│   ├── _http.py              # Low-level requests.Session wrapper
│   ├── auth.py               # handshake(), get_profile()
│   ├── live_tv.py            # ITVService: genres, channels, stream links
│   ├── vod.py                # VODService: categories, content, seasons, episodes, stream links
│   ├── models.py             # Dataclasses: Genre, Channel, Category, Content, Season, Episode, PagedResult
│   └── exceptions.py         # STBError, AuthError, StreamError
├── server/
│   ├── main.py               # FastAPI app + lifespan (auth on startup)
│   ├── config.py             # Settings via env vars (Pydantic BaseSettings)
│   └── routes/
│       ├── __init__.py
│       ├── live_tv.py        # /live-tv/* route handlers
│       └── vod.py            # /vod/* route handlers
├── tests/
│   ├── conftest.py           # Shared fixtures (mock STB session)
│   ├── test_auth.py
│   ├── test_live_tv.py
│   └── test_vod.py
├── spec/
│   └── 001-stb-api-server/
│       └── 001-stb-api-server-requirements.md  ← this file
├── docs/                     # Existing protocol docs (unchanged)
├── pyproject.toml
├── Dockerfile
└── CLAUDE.md
```

---

## Code Style

```python
# stb_reader/live_tv.py — representative style
from dataclasses import dataclass
from stb_reader._http import STBSession
from stb_reader.models import Genre, Channel, PagedResult
from stb_reader.exceptions import StreamError

@dataclass
class ITVService:
    _session: STBSession

    def get_genres(self) -> list[Genre]:
        data = self._session.get(type="itv", action="get_genres")
        return [Genre(id=g["id"], title=g["title"], alias=g["alias"], censored=bool(g["censored"])) for g in data]

    def get_channels(self, genre_id: str = "*", page: int = 1, sort: str = "number") -> PagedResult[Channel]:
        raw = self._session.get(type="itv", action="get_ordered_list", genre=genre_id, p=page - 1, sortby=sort)
        channels = [_parse_channel(c) for c in raw["data"]]
        return PagedResult(items=channels, total=int(raw["total_items"]), page=page, per_page=int(raw["max_page_items"]))

    def get_stream_url(self, cmd: str) -> str:
        result = self._session.get(type="itv", action="create_link", cmd=cmd)
        if result.get("error"):
            raise StreamError(result["error"])
        url = result["cmd"]
        return url.removeprefix("ffmpeg ")
```

**Conventions:**
- Snake_case for all names; classes are PascalCase
- No global state; services receive a session via constructor
- Type hints on all public methods
- Dataclasses for models (no Pydantic in the library layer)
- Pydantic only in `server/` (FastAPI response models)
- No comments except for non-obvious WHY explanations

---

## Testing Strategy

- **Framework:** `pytest`
- **Mock library:** `responses` (intercepts `requests` calls)
- **Test location:** `tests/` at repo root; one file per library module
- **Coverage target:** 90%+ on `stb_reader/`; server routes covered by integration-style tests using FastAPI's `TestClient`
- **Test levels:**
  - Unit: each service method tested with mocked HTTP responses
  - Integration: FastAPI routes tested end-to-end via `TestClient` (still mocked at HTTP layer)
  - No real STB portal required in CI

---

## Boundaries

- **Always:** Run `pytest` before committing; use typed function signatures; validate env vars at startup and fail fast with a clear error message
- **Ask first:** Adding new Python dependencies; changing the REST URL structure; adding server-side auth
- **Never:** Make real HTTP calls in tests; commit credentials or MAC addresses; add async to the library layer (keep it sync/requests)

---

## Success Criteria

- SC-1: `GET /health` returns `200 {"status": "ok"}` when `STB_PORTAL_URL` and `STB_MAC` are set and the portal is reachable.
- SC-2: `GET /live-tv/channels` returns a JSON list of channels with `id`, `name`, `number`, `logo`, `hd` fields.
- SC-3: `GET /live-tv/channels/{id}/stream` responds with HTTP 302 and a `Location` header containing a URL that a media player can open.
- SC-4: `GET /vod/content/{id}/seasons` returns a non-empty list for a known series `content_id`.
- SC-5: `pytest` passes with no failures and ≥90% coverage on `stb_reader/`.
- SC-6: `docker build` completes without errors and `docker run` starts the server on port 8000.
- SC-7: The `stb_reader` library can be imported and `STBClient` instantiated without installing FastAPI.
