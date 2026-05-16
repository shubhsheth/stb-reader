# 012 — Convert stb-reader to a pure Python library

## Goal

Remove the `server/` FastAPI app entirely and ship `stb_reader` as a standalone,
pip-installable library. Users call simple methods on `STBClient` to get data from
an STB portal; no database, no web server, no Docker required.

---

## Current state

| Area | Files |
|------|-------|
| Library | `stb_reader/__init__.py`, `client.py`, `_http.py`, `auth.py`, `live_tv.py`, `vod.py`, `models.py`, `exceptions.py` |
| Server (to remove) | `server/` (main, config, db, sync, vod_sync, routes/*, static/) |
| Tests — keep | `tests/test_auth.py`, `tests/test_http.py`, `tests/test_live_tv.py` |
| Tests — mixed | `tests/test_vod.py` — top-level functions test `VODService`; `TestVodSync` / `TestVodSearch` classes test server routes |
| Tests — remove | `tests/test_server.py`, `tests/test_library_routes.py`, `tests/test_library_db.py`, `tests/test_vod_sync.py`, `tests/test_library_sync.py` |
| Infra (to remove) | `Dockerfile`, `docker-compose.yml`, `.env.example`, `.dockerignore` |

---

## Dependency questions (resolved)

| Question | Answer |
|----------|--------|
| Does any library code import from `server/`? | No — `server/` imports from `stb_reader`, never the reverse |
| Does `test_vod.py` mix library and server tests? | Yes — `TestVodSync` and `TestVodSearch` use `server.db`; pure-library tests are at module level |
| Will removing `server/` break any library test? | Only if the test imports from `server.*`; confirmed only in the classes above |

---

## Tasks

### Task 1 — Strip server package and infra files  
**Scope: XS** (delete only, no code changes)  
**Files:** `server/` (entire directory), `Dockerfile`, `docker-compose.yml`, `.env.example`, `.dockerignore`

Acceptance criteria:
- `server/` directory no longer exists
- Infra files removed
- `git status` shows only deletions

Verify: `ls server/ 2>&1` → "No such file or directory"

---

### Task 2 — Remove server-only tests and clean up mixed test file  
**Scope: S** (delete files, edit one file)  
**Files:**
- Delete: `tests/test_server.py`, `tests/test_library_routes.py`, `tests/test_library_db.py`, `tests/test_vod_sync.py`, `tests/test_library_sync.py`
- Edit: `tests/test_vod.py` — remove `TestVodSync`, `TestVodSearch`, `vod_client` fixture, and the `from server.*` imports

Acceptance criteria:
- No `tests/test_server.py` etc.
- `tests/test_vod.py` contains only `VODService` unit tests
- No `import` from `server.*` anywhere in `tests/`

Verify: `grep -r "from server" tests/` → no output

---

### Task 3 — Update `pyproject.toml` to be a pure library  
**Scope: XS** (one file)  
**File:** `pyproject.toml`

Changes:
- Remove `[project.optional-dependencies]` `server` group (fastapi, uvicorn, pydantic-settings, httpx[http2], cachetools)
- Keep `test` group as-is (pytest, responses, httpx, pytest-cov)
- Keep `requests` as the only runtime dependency

Acceptance criteria:
- `uv pip install .` installs only `requests`
- `uv pip install ".[test]"` adds test deps only

Verify: `grep -E "fastapi|uvicorn|pydantic-settings|cachetools" pyproject.toml` → no output

---

### Task 4 — Expand `__init__.py` public API  
**Scope: XS** (one file)  
**File:** `stb_reader/__init__.py`

Export all user-facing symbols so `from stb_reader import STBClient, Channel, Genre, ...` works without knowing internal modules:
- `STBClient`
- All models: `Genre`, `Channel`, `Category`, `Content`, `Season`, `Episode`, `EpisodeFile`, `PagedResult`
- All exceptions: `STBError`, `AuthError`, `StreamError`, `NotFoundError`

Acceptance criteria:
- `python -c "from stb_reader import STBClient, Genre, Channel, Category, Content, Season, Episode, EpisodeFile, PagedResult, STBError, AuthError, StreamError, NotFoundError"` exits 0

Verify: run the command above

---

### Task 5 — Add PyPI packaging metadata  
**Scope: S** (one file, one new file)  
**Files:** `pyproject.toml`, `README.md` (new)

Add the metadata PyPI requires:
- `[project]` fields: `description`, `license`, `authors`, `keywords`, `classifiers`, `urls` (Homepage, Repository)
- `[project.urls]` section
- Create a `README.md` that becomes the PyPI long description (reference it via `readme = "README.md"` in `[project]`)

README must cover: install instructions (`pip install stb-reader`), quick-start code example showing `STBClient` usage, and a brief description of what the library does.

Acceptance criteria:
- `uv build` produces a `.tar.gz` and `.whl` in `dist/`
- `twine check dist/*` passes with no errors
- PyPI classifiers include Python version and licence

Verify: `uv build && uv run twine check dist/*`

---

### Task 6 — Add GitHub Actions publish workflow  
**Scope: S** (one new file)  
**File:** `.github/workflows/publish.yml`

Trigger: push of a `v*` tag (e.g. `v0.1.0`).

Steps:
1. Checkout
2. Set up Python + uv
3. `uv build`
4. Publish to PyPI using `uv publish` (uses `PYPI_TOKEN` repository secret via `UV_PUBLISH_TOKEN` env var)

Acceptance criteria:
- Workflow file is valid YAML
- Uses `uv publish` (not twine) for publishing
- Only triggers on version tags, not every push

Verify: `python -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml'))"` exits 0

---

### Task 7 — Run full test suite and confirm green  
**Scope: XS** (no code changes, verify only)

```
uv run pytest tests/ -v
```

Acceptance criteria:
- All tests pass (no server-related imports remaining)
- No import errors

---

## Dependency order

```
Task 1 (delete server/)
    ↓
Task 2 (clean tests — server must be gone first so we can grep cleanly)
    ↓
Task 3 (pyproject.toml — strip server deps)
Task 4 (public API — expand __init__.py)
    ↓
Task 5 (PyPI metadata — depends on Task 3 having clean pyproject.toml)
Task 6 (GitHub Actions — independent of library changes)
    ↓
Task 7 (verify — must run after all changes)
```

Tasks 3 and 4 can be done in parallel after Task 2.  
Tasks 5 and 6 can be done in parallel after Task 3.

---

## Out of scope

- Adding new library methods not already present
- Async support
