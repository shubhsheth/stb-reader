# Spec: Convert stb-reader to a pure Python library with PyPI publishing

## Objective

`stb-reader` currently ships as a FastAPI application bundled with a pure-Python client library (`stb_reader/`). The goal is to strip the application layer entirely and ship only the library — a lightweight, pip-installable package that lets Python developers retrieve live-TV and VOD data from an STB portal with simple method calls. Publishing to PyPI makes the library discoverable and installable without cloning the repository.

**User:** A Python developer who wants to talk to a Ministra/Stalker STB portal from their own script or application.

**Success looks like:** `pip install stb-reader`, two lines of code, data flowing.

---

## User Stories

- As a Python developer, I want to `pip install stb-reader` so that I can use the library without cloning the repo.
- As a Python developer, I want to import `STBClient` and call `.authenticate()`, `.live_tv.get_channels()`, `.vod.get_content()`, etc. so that I can retrieve portal data with minimal boilerplate.
- As a maintainer, I want a GitHub Actions workflow that publishes a new release to PyPI when I push a `v*` tag so that releases are automated and consistent.
- As a maintainer, I want no `server/` code in the library package so that users don't get FastAPI as a transitive dependency.

---

## Functional Requirements

- **FR-1:** The `stb_reader` package is the sole importable artifact; `server/` and all its dependencies are removed.
- **FR-2:** `from stb_reader import STBClient` works after `pip install stb-reader`.
- **FR-3:** All public models (`Genre`, `Channel`, `Category`, `Content`, `Season`, `Episode`, `EpisodeFile`, `PagedResult`) and exceptions (`STBError`, `AuthError`, `StreamError`, `NotFoundError`) are importable directly from `stb_reader`.
- **FR-4:** The only runtime dependency is `requests`.
- **FR-5:** `pyproject.toml` contains the full PyPI metadata: name, version, description, license, authors, Python version constraint, classifiers, and project URLs.
- **FR-6:** A `README.md` exists at the repo root describing installation and a minimal working example.
- **FR-7:** A GitHub Actions workflow publishes the package to PyPI when a `v*` tag is pushed, using `uv publish` and the `PYPI_TOKEN` repository secret (via `UV_PUBLISH_TOKEN`).
- **FR-8:** All existing library unit tests pass after the server is removed.

---

## Non-Functional Requirements

- **NFR-1:** `uv build` completes without warnings.
- **NFR-2:** `twine check dist/*` (or equivalent) reports no errors before publish.
- **NFR-3:** The package installs cleanly into a fresh virtualenv with only `requests` as a dependency.
- **NFR-4:** No test imports anything from `server.*`.

---

## Out of Scope

- Adding new `STBClient` methods or changing the existing library API.
- Async support.
- Publishing to TestPyPI as a separate step.
- A CHANGELOG or versioning automation beyond the tag-triggered workflow.
- Updating the `docs/` protocol reference files.

---

## Assumptions

- Package name on PyPI will be `stb-reader` (matching the existing `pyproject.toml` `name`).
- License is MIT (no existing LICENSE file; one will be created).
- Authors field will use the GitHub username `shubhsheth` as a placeholder; maintainer can update before first publish.
- The `PYPI_TOKEN` secret is already configured (or will be configured) on the GitHub repository — the workflow only wires it up.
- `uv` is available in the CI environment (ubuntu-latest + `astral-sh/setup-uv`).

---

## Tech Stack

- Python 3.11+
- `requests` (sole runtime dep)
- `uv` for build and publish (`uv build`, `uv publish`)
- `hatchling` build backend (already in use)
- GitHub Actions for CI/CD

---

## Commands

```
Install library (editable):  uv pip install -e .
Install test deps:           uv pip install -e ".[test]"
Run tests:                   uv run pytest tests/ -v
Run with coverage:           uv run pytest --cov=stb_reader tests/
Build distribution:          uv build
Check package:               uv run twine check dist/*
Publish (manual):            UV_PUBLISH_TOKEN=<token> uv publish
```

---

## Project Structure (after)

```
stb_reader/        Sole importable package
  __init__.py      Exports STBClient, all models, all exceptions
  client.py        STBClient entry point
  auth.py          handshake(), get_profile()
  live_tv.py       ITVService — genres, channels, stream URLs
  vod.py           VODService — categories, content, seasons, episodes, streams
  models.py        Dataclasses: Genre, Channel, Category, Content, Season, Episode, EpisodeFile, PagedResult
  _http.py         STBSession (requests wrapper)
  exceptions.py    STBError, AuthError, StreamError, NotFoundError

tests/             pytest suite — library tests only, all HTTP mocked
  conftest.py
  test_auth.py
  test_http.py
  test_live_tv.py
  test_vod.py      VODService tests only (server-route tests removed)

.github/
  workflows/
    publish.yml    Publish to PyPI on v* tag push

spec/              Spec-driven feature docs
docs/              STB protocol reference

pyproject.toml     Library metadata + hatchling build config
README.md          Installation + quick-start example
LICENSE            MIT licence text
```

**Removed entirely:** `server/`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.dockerignore`

---

## Code Style

Follows existing conventions — no changes to library internals:

```python
# stb_reader/__init__.py  — full public surface
from .client import STBClient
from .models import Genre, Channel, Category, Content, Season, Episode, EpisodeFile, PagedResult
from .exceptions import STBError, AuthError, StreamError, NotFoundError

__all__ = [
    "STBClient",
    "Genre", "Channel", "Category", "Content",
    "Season", "Episode", "EpisodeFile", "PagedResult",
    "STBError", "AuthError", "StreamError", "NotFoundError",
]
```

- Python 3.11+, snake_case, full type hints
- Dataclasses for all domain models
- No Pydantic, no async in `stb_reader/`

---

## Testing Strategy

- **Framework:** pytest + `responses` library (mock all HTTP)
- **Location:** `tests/` alongside source
- **Coverage target:** 90%+ on `stb_reader/`
- **Levels:** unit tests only (no integration tests without a real portal)
- **Rule:** zero imports from `server.*` in any test file

---

## Boundaries

- **Always:** run `pytest` before committing; keep type hints on all public signatures; run `uv build` to verify packaging
- **Ask first:** changing the public `__init__.py` API beyond what is specified here; adding any new runtime dependency
- **Never:** commit real credentials or tokens; import `server.*` from library or library tests; skip failing tests

---

## Success Criteria

1. `pip install stb-reader` in a clean virtualenv succeeds with `requests` as the only dependency.
2. The following one-liner executes without `ImportError`:
   ```python
   from stb_reader import STBClient, Genre, Channel, Category, Content, Season, Episode, EpisodeFile, PagedResult, STBError, AuthError, StreamError, NotFoundError
   ```
3. `uv run pytest tests/ -v` — all tests pass, zero failures.
4. `uv build && uv run twine check dist/*` — no errors or warnings.
5. No file under `tests/` imports from `server.*`.
6. `.github/workflows/publish.yml` exists and is valid YAML with a `v*` tag trigger.
7. `README.md` exists and includes both installation instructions and a code example.
8. `server/` directory does not exist.
