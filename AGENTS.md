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
  main.py     App factory and lifespan
  config.py   Environment variable settings
  routes/     live_tv.py, vod.py

tests/        pytest suite; all HTTP is mocked via `responses` library
docs/         STB protocol reference (authentication, live-tv, vod-series)
spec/         Spec-driven feature specs (NNN-slug/{requirements,plan,implement}.md)
```

## REST API Endpoints

```
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
