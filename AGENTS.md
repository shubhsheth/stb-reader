# AGENTS.md

## Build & Setup

```
Install library:  pip install -e .
Install dev deps: pip install -e ".[dev]"
Run tests:        pytest
Run with coverage: pytest --cov=stb_reader
Start server:     uvicorn server.main:app --reload
Docker build:     docker build -t stb-reader .
Docker run:       docker run -e STB_URL=... -e STB_MAC=... -p 8000:8000 stb-reader
```

## Project Structure

```
stb_reader/   Core pip-installable library; no FastAPI dependency
  client.py   STBClient entry point
  auth.py     handshake(), get_profile()
  live_tv.py  ITVService (genres, channels, stream URLs)
  vod.py      VODService (categories, content, seasons, episodes, streams)
  models.py   Dataclasses: Genre, Channel, Category, VODItem, etc.
  _http.py    Low-level requests.Session wrapper with STB headers
  exceptions.py  STBError, AuthError, StreamError

server/       FastAPI + Uvicorn HTTP layer
  main.py     App factory and lifespan; mounts static/ at /
  config.py   Environment variable settings
  db.py       SQLite schema and CRUD for the library
  sync.py     Portal-walking logic: add_content(), sync_item(), delete_content()
  routes/     live_tv.py, vod.py, library.py
  static/     Frontend assets served at /
    index.html  Single-page search + library management UI

tests/        pytest suite; all HTTP is mocked via `responses` library
docs/         STB protocol reference (authentication, live-tv, vod-series, library)
spec/         Spec-driven feature specs (NNN-slug/{requirements,plan,implement}.md)
```

## Frontend

Single-page UI served at `GET /`. Plain HTML/CSS/JS — no build step, no external dependencies.

- Search VOD content via the search bar (calls `GET /vod/search`)
- Filter by All / Movies / Series
- Add or Remove items from the library with one click
- Paginated results (25 per page)

## REST API Endpoints

```
GET /                                           Web UI (static HTML)
GET /health                                     Health check
GET /live-tv/genres                             List channel genres
GET /live-tv/channels                           Paginated channel list
GET /live-tv/channels/{id}/stream               302 redirect to stream URL
GET /vod/categories                             List VOD categories
GET /vod/content                                            Paginated VOD content
GET /vod/content/{id}/seasons                               Series seasons
GET /vod/content/{id}/seasons/{sid}/episodes                Season episodes
GET /vod/content/{id}/seasons/{sid}/episodes/{eid}/stream   302 redirect to first file stream
GET /vod/content/{id}/seasons/{sid}/episodes/{eid}/files    Episode files (multi-quality)
GET /vod/content/{id}/seasons/{sid}/episodes/{eid}/files/{fid}/stream  302 redirect to file stream
GET /vod/content/{id}/stream                                302 redirect to movie stream
```

## Library Endpoints

```
POST   /library/add/{content_id}    Add content to library; body: {"name": str, "year": str, "is_series": bool}
                                    Returns 201 with item + strm_count, 409 if already present
GET    /library                     List all library items (each includes strm_count)
DELETE /library/{content_id}        Remove item and delete .strm files; 204 on success, 404 if not found
POST   /library/sync/{content_id}   Sync new episodes for a series; returns {"new_files": n}; 404 if not found
POST   /library/sync                Sync all series; returns [{content_id, new_files}, ...]
```

## Library Environment Variables

```
STRM_OUTPUT_DIR          Root directory where .strm files are written (required)
STRM_SERVER_BASE_URL     Base URL embedded in .strm files, reachable by Jellyfin at playback time (required)
STRM_DATA_DIR            Directory for the SQLite library database; DB created at {STRM_DATA_DIR}/data.db (required)
STRM_SYNC_INTERVAL_HOURS Hours between automatic background syncs (default: 6; 0 = disabled)
```

See `docs/library.md` for deployment details including Docker service name vs LAN IP vs reverse proxy.

## Code Style

- Python 3.11+; snake_case everywhere
- Dataclasses for all domain models (`stb_reader/models.py`)
- Full type hints on every function signature
- Pydantic only in the server layer — never in `stb_reader/`
- No async in `stb_reader/`; server layer may use async

## Testing

- Mock all HTTP with `responses` library — never make real network calls in tests
- Integration tests use FastAPI `TestClient`
- Target: 90%+ coverage on `stb_reader/`
- Run `pytest` before every commit

## Boundaries

- **Always:** typed signatures, fail fast on missing env vars, run pytest before commits
- **Ask first:** new third-party dependencies, REST URL shape changes, server-level auth
- **Never:** real HTTP calls in tests, credentials in source, async in `stb_reader/` core

## Documentation

- `docs/` contains protocol-level reference for the Ministra/Stalker STB API
- Update the relevant `docs/` file when adding or changing endpoints or protocol behavior
- Update this file (`AGENTS.md`) when adding commands, endpoints, models, or boundaries
