# Implementation Tasks: .strm Generator — Stalker Portal VOD Library Sync

Tasks are ordered by dependency. Complete each task and run `pytest tests/` before
starting the next. Each task touches at most 3–4 files.

---

- [ ] **Task 1: Config settings**
  - Add four fields to `server/config.py`:
    ```python
    strm_output_dir: str          # required
    strm_server_base_url: str     # required
    strm_db_path: str = "./library.db"
    strm_sync_interval_hours: int = 6
    ```
  - Update `.env.example` with the new vars and inline comments for the three
    `STRM_SERVER_BASE_URL` options (Docker service name / LAN IP / reverse proxy).
  - Acceptance: `Settings()` loads the four fields from env; missing `strm_output_dir`
    or `strm_server_base_url` raises `ValidationError`.
  - Verify: `pytest tests/` passes (no regressions; config validation covered by
    existing `test_missing_required_env_raises` pattern in `tests/test_server.py`).
  - Files: `server/config.py`, `.env.example`

---

- [ ] **Task 2: DB layer**
  - Create `server/db.py` with the two-table schema and all CRUD functions:
    - `init_db(path: str) -> sqlite3.Connection` — creates tables if not present;
      uses `check_same_thread=False`.
    - `add_library_item(db, content_id, name, year, is_series) -> None`
    - `get_library_items(db) -> list[dict]` — each item includes `strm_count`
      (subquery: `SELECT count(*) FROM strm_files WHERE content_id = ?`).
    - `get_library_item(db, content_id) -> dict | None`
    - `delete_library_item(db, content_id) -> list[str]` — deletes rows from both
      tables, returns the list of `strm_path` values to unlink from disk.
    - `add_strm_file(db, content_id, season_id, episode_id, file_id, strm_path) -> None`
    - `get_strm_files(db, content_id) -> list[dict]`
    - `episode_exists(db, content_id, season_id, episode_id) -> bool` (FR-15)
    - `set_last_synced(db, content_id) -> None`
  - Create `tests/test_library_db.py`:
    - Use `tmp_path` fixture for the db file path.
    - `init_db` creates both tables.
    - `add_library_item` round-trips: inserted row is returned by `get_library_item`.
    - Duplicate `content_id` raises `sqlite3.IntegrityError`.
    - `get_library_items` returns `strm_count = 0` before any files, `strm_count = 2`
      after two `add_strm_file` calls.
    - `delete_library_item` returns the `strm_path` list and removes both table rows.
    - `episode_exists` returns `False` before insert, `True` after `add_strm_file`.
  - Acceptance: all `test_library_db.py` tests pass.
  - Verify: `pytest tests/test_library_db.py -v`
  - Files: `server/db.py`, `tests/test_library_db.py`

---

- [ ] **Task 3: Sync helper functions**
  - Create `server/sync.py` with the pure helper functions:
    - `sanitize(name: str) -> str` — replaces `/ \ : * ? " < > |` with `-` (FR-11).
    - `parse_season_num(season_name: str, fallback: int) -> int` — extracts first
      `\d+` match from `season_name`; returns `fallback` if none found (FR-12).
    - `movie_strm_path(output_dir: str, name: str, year: str) -> Path` — builds
      `{output_dir}/Movies/{sanitized} ({year})/{sanitized} ({year}).strm` (FR-9).
    - `episode_strm_path(output_dir, name, year, season_num, ep_num, ep_name) -> Path`
      — builds `{output_dir}/TV/{name} ({year})/Season {NN}/{name} ({year}) - SnnEnn - {ep_name}.strm` (FR-10).
    - `write_strm(path: Path, url: str) -> None` — `path.parent.mkdir(parents=True,
      exist_ok=True)`, `path.write_text(url + "\n")` (FR-7, FR-8).
  - Add helper tests to `tests/test_library_sync.py`:
    - `sanitize` replaces all forbidden characters, leaves safe names unchanged.
    - `parse_season_num("Season 2", 1)` returns `2`.
    - `parse_season_num("Special", 3)` returns `3` (fallback).
    - `movie_strm_path` produces the correct nested path.
    - `episode_strm_path` produces correct `S01E02` zero-padded path.
    - `write_strm` creates parent dirs and file content equals `url + "\n"`.
  - Acceptance: all `test_library_sync.py` tests pass.
  - Verify: `pytest tests/test_library_sync.py -v`
  - Files: `server/sync.py`, `tests/test_library_sync.py`

---

- [ ] **Task 4: Sync core functions**
  - Add core functions to `server/sync.py`:
    - `add_content(db, vod, output_dir, server_base, content_id, name, year, is_series) -> int`
      — inserts `library_item`, dispatches to movie path or `_write_series_strm_files`;
      raises `sqlite3.IntegrityError` on duplicate (FR-1).
    - `_write_series_strm_files(db, vod, output_dir, server_base, content_id, name, year) -> int`
      — walks `get_seasons → get_episodes → get_episode_files`; skips episodes already
      in DB (`episode_exists`); skips episodes with zero files; uses `files[0]` (FR-2,
      FR-13, FR-14, FR-15).
    - `sync_item(db, vod, output_dir, server_base, content_id) -> int` — no-op for
      movies; calls `_write_series_strm_files` with stored name/year; calls
      `set_last_synced` (FR-5).
    - `sync_all(db, vod, output_dir, server_base) -> list[dict]` — iterates series in
      `get_library_items`, calls `sync_item` for each, returns
      `[{"content_id": ..., "new_files": n}, ...]` (FR-6).
    - `delete_content(db, content_id) -> None` — calls `delete_library_item` to get
      paths, unlinks each file with `missing_ok=True`, removes now-empty parent dirs (FR-4).
  - Extend `tests/test_library_sync.py` with core tests. Use `tmp_path` for
    `output_dir`; use an in-memory SQLite db (`init_db(":memory:")`); mock the `vod`
    object with `MagicMock` returning fixture `Season`, `Episode`, `EpisodeFile` objects:
    - `add_content` movie: one `.strm` file written at correct path, content equals proxy URL.
    - `add_content` series (2 seasons × 2 episodes): four `.strm` files, all at correct
      `SxxExx` paths.
    - Duplicate `add_content` raises `sqlite3.IntegrityError`.
    - Episode with zero files is skipped — no `.strm` written, no DB row (FR-14).
    - `sync_item` on a series with 2 existing + 1 new episode: returns `1`, writes only
      the new file (FR-15).
    - `sync_item` on a movie: returns `0`, no portal calls made.
    - `sync_all` returns correct per-item counts.
    - `delete_content` removes files from disk and DB rows.
  - Acceptance: all `test_library_sync.py` tests pass.
  - Verify: `pytest tests/test_library_sync.py -v`
  - Files: `server/sync.py`, `tests/test_library_sync.py`

---

- [ ] **Task 5: Library routes**
  - Create `server/routes/library.py` with all five endpoints:
    ```
    POST   /library/add/{content_id}    → 201 / 409
    GET    /library                     → 200
    DELETE /library/{content_id}        → 204 / 404
    POST   /library/sync/{content_id}   → 200 / 404
    POST   /library/sync                → 200
    ```
  - Define `AddContentRequest(BaseModel)` with `name: str`, `year: str`,
    `is_series: bool` in the same file.
  - Exception mapping: `sqlite3.IntegrityError` → 409; `NotFoundError` → 404.
  - Routes read `db`, `settings`, and `client.vod` from `request.app.state`.
  - Create `tests/test_library_routes.py`. Add a `library_client` fixture that extends
    the existing `test_client` pattern: patches env with the four `STRM_*` vars
    (using `tmp_path` for `STRM_OUTPUT_DIR` and `STRM_DB_PATH=:memory:`); also patches
    `server.main.init_db` to return an in-memory db. Mock the vod client for portal
    calls as needed.
  - Tests:
    - `POST /library/add/{id}` movie → 201, correct body fields, `.strm` file on disk.
    - `POST /library/add/{id}` series → 201, `strm_count` matches episode count.
    - `POST /library/add/{id}` duplicate → 409.
    - `GET /library` → 200, lists added items with `strm_count`.
    - `DELETE /library/{id}` → 204, file removed from disk.
    - `DELETE /library/{id}` unknown → 404.
    - `POST /library/sync/{id}` → 200, returns `{"new_files": n}`.
    - `POST /library/sync/{id}` unknown → 404.
    - `POST /library/sync` → 200, returns list of per-item results.
  - Acceptance: all `test_library_routes.py` tests pass.
  - Verify: `pytest tests/test_library_routes.py -v`
  - Files: `server/routes/library.py`, `tests/test_library_routes.py`

---

- [ ] **Task 6: main.py wiring and background task**
  - Update `server/main.py` lifespan:
    1. Call `init_db(settings.strm_db_path)`; store on `app.state.db`.
    2. Store `settings` on `app.state.settings`.
    3. Import and mount the library router.
    4. If `settings.strm_sync_interval_hours > 0`, start an `asyncio` background task
       that sleeps for the interval then calls `sync_all` via `asyncio.to_thread`
       (NFR-3). Cancel the task in the `yield` teardown (FR-19).
  - Acceptance: `GET /health` still returns 200; server starts without error when the
    four `STRM_*` env vars are set.
  - Verify: `pytest tests/ -v` — full suite passes with no regressions.
  - Files: `server/main.py`

---

- [ ] **Task 7: .env.example**
  - Add the four `STRM_*` vars with inline comments explaining the three
    `STRM_SERVER_BASE_URL` options as documented in NFR-4.
  - Acceptance: `.env.example` contains all variables from `server/config.py`.
  - Verify: manual review.
  - Files: `.env.example`

---

- [ ] **Task 8: Documentation**
  - Update `AGENTS.md`:
    - New endpoints under a `## Library` section.
    - New env vars with descriptions.
    - Note that `POST /library/add/{content_id}` requires a JSON body.
  - Create `docs/library.md`:
    - Describe the library concept (add → sync → .strm files → Jellyfin).
    - Document all five endpoints with request/response examples.
    - Document the three `STRM_SERVER_BASE_URL` options and when to use each (NFR-4).
    - Document the background sync interval config.
  - Acceptance: `AGENTS.md` has no stale references; `docs/library.md` covers all
    public-facing behaviour.
  - Verify: review both files for accuracy against the implemented endpoints.
  - Files: `AGENTS.md`, `docs/library.md`
