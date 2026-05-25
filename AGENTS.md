# AGENTS.md

## Build & Setup

```
Install library:    uv pip install -e .
Install test deps:  uv pip install -e ".[test]"
Run tests:          uv run pytest tests/ -v
Run with coverage:  uv run pytest --cov=stb_reader tests/
Build distribution: uv build
Check package:      uv run twine check dist/*
```

## Project Structure

```
stb_reader/        Sole importable package
  __init__.py      Public API: STBClient, all models, all exceptions
  client.py        STBClient entry point
  auth.py          handshake(), get_profile()
  live_tv.py       ITVService — genres, channels, stream URLs
  vod.py           VODService — categories, content, seasons, episodes, streams
  models.py        Dataclasses: Genre, Channel, Category, Content, Season, Episode, EpisodeFile, PagedResult
  _http.py         STBSession (requests wrapper with STB headers and auto-reauth)
  exceptions.py    STBError, AuthError, StreamError, NotFoundError

tests/             pytest suite; all HTTP mocked via `responses` library
docs/protocol/     STB protocol reference (authentication, live-tv, vod-series)
docs/guide/        User-facing guides (cli.md)
spec/              Spec-driven feature specs (NNN-slug/{requirements,plan,implement}.md)

.github/
  workflows/
    publish.yml    Publishes to PyPI on v* tag push (requires PYPI_TOKEN secret)

pyproject.toml     Package metadata and hatchling build config
README.md          Installation and quick-start documentation
LICENSE            MIT licence
```

## Public API

```python
from stb_reader import STBClient

client = STBClient(base_url="http://portal.example.com", mac="00:1A:79:XX:XX:XX")
client.authenticate()

# Live TV
genres   = client.live_tv.get_genres()
channels = client.live_tv.get_channels(genre_id="*", page=1)
url      = client.live_tv.get_stream_url(channels.items[0].cmd)

# VOD
cats     = client.vod.get_categories()
content  = client.vod.get_content(category_id="*", page=1)
seasons  = client.vod.get_seasons(series_id="123")
episodes = client.vod.get_episodes(series_id="123", season_id=seasons.items[0].id)
url      = client.vod.get_stream_url_by_first_file("123", seasons.items[0].id, episodes.items[0].id)
```

All models and exceptions are importable directly from `stb_reader`:
`Genre`, `Channel`, `Category`, `Content`, `Season`, `Episode`, `EpisodeFile`, `PagedResult`,
`STBError`, `AuthError`, `StreamError`, `NotFoundError`

## Code Style

- Python 3.11+; snake_case everywhere
- Dataclasses for all domain models (`stb_reader/models.py`)
- Full type hints on every function signature
- No Pydantic, no async in `stb_reader/`

## Testing

- Mock all HTTP with `responses` library — never make real network calls in tests
- Target: 90%+ coverage on `stb_reader/`
- Run `uv run pytest tests/ -v` before every commit
- No test file may import from `server.*`

## Publishing

Releases publish to PyPI automatically when a `v*` tag is pushed:

```bash
git tag v0.2.0
git push origin v0.2.0
```

The `PYPI_TOKEN` secret must be configured in the GitHub repository settings.

## Boundaries

- **Always:** typed signatures, run pytest before commits, run `uv build` to verify packaging
- **Ask first:** new runtime dependencies, changing the public `__init__.py` API, adding new STBClient methods
- **Never:** real HTTP calls in tests, credentials in source, async in `stb_reader/` core

## Documentation

- `docs/protocol/` contains protocol-level reference for the Ministra/Stalker STB API
- `docs/guide/` contains user-facing guides (CLI, library usage)
- Update the relevant `docs/protocol/` file when changing protocol behavior
- Update this file (`AGENTS.md`) when adding commands, models, or boundaries
