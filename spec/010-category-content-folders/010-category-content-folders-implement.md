# Tasks: Category Content Folders (010)

## Phase 1 — DB layer

- [ ] Task: DB migration — add `category_id` column to `strm_files`
  - Acceptance: `MIGRATIONS` in `server/db.py` has a new `_add_col` entry appended:
    `_add_col("strm_files", "category_id", "TEXT")`. Existing rows default to `NULL`.
    `PRAGMA user_version` increments correctly.
  - Verify: `pytest tests/test_library_db.py -q` passes (existing migration tests catch
    incorrect version bumps)
  - Files: `server/db.py`
  - Size: XS

- [ ] Task: Update `add_strm_file` to accept and store `category_id`
  - Acceptance: `add_strm_file(db, content_id, season_id, episode_id, file_id, strm_path,
    category_id=None)` stores `category_id` in the new column. All existing call sites in
    `server/sync.py` continue to work without modification (default `None`).
  - Verify: new test in `test_library_db.py` — call with `category_id="cat1"`, query back the
    row, assert `category_id == "cat1"`; call without it, assert `category_id IS NULL`
  - Files: `server/db.py`, `tests/test_library_db.py`
  - Size: XS

- [ ] Task: Add `get_strm_paths_for_category` and `remove_category_strm_files` DB helpers
  - Acceptance:
    - `get_strm_paths_for_category(db, category_id) -> list[str]` returns `strm_path` values
      for all rows where `strm_files.category_id = ?`.
    - `remove_category_strm_files(db, category_id) -> list[str]` deletes those rows and
      returns their `strm_path` values (for disk cleanup). Rows with `NULL` or a different
      `category_id` are not touched.
  - Verify: new tests in `test_library_db.py`:
    - Insert rows with `category_id="cat1"` and `category_id=NULL`; assert only `cat1` rows
      are returned/deleted.
  - Files: `server/db.py`, `tests/test_library_db.py`
  - Size: XS

- [ ] Verify Phase 1
  - Acceptance: `pytest tests/test_library_db.py -q` exits 0
  - Verify: run the command
  - Files: none

---

## Phase 2 — Path functions

- [ ] Task: Add `category_folder` param to `movie_strm_path` and `episode_strm_path`
  - Acceptance:
    - `movie_strm_path(output_dir, name, year, category_folder=None)`:
      - `category_folder=None` → `Path(output_dir) / "Movies" / folder / f"{folder}.strm"` (unchanged)
      - `category_folder="Action"` → `Path(output_dir) / "Action" / "Movies" / folder / f"{folder}.strm"`
    - `episode_strm_path(output_dir, name, year, season_num, ep_num, ep_name, category_folder=None)`:
      - `category_folder=None` → `Path(output_dir) / "TV" / …` (unchanged)
      - `category_folder="Drama"` → `Path(output_dir) / "Drama" / "TV" / …`
    - All existing call sites (no `category_folder` arg) continue to produce identical paths.
  - Verify: new parametrized tests in `test_library_sync.py` asserting exact `Path` values for
    both `None` and non-`None` `category_folder`
  - Files: `server/sync.py`, `tests/test_library_sync.py`
  - Size: XS

- [ ] Verify Phase 2
  - Acceptance: `pytest tests/test_library_sync.py -q` exits 0
  - Verify: run the command
  - Files: none

---

## Phase 3 — Sync helpers

- [ ] Task: Thread `category_folder` and `category_id` through sync helpers
  - Acceptance: The following functions each gain `category_folder: str | None = None` and
    `category_id: str | None = None` (both default `None`):
    - `_write_series_strm_files` — passes `category_folder` to `episode_strm_path` and
      `category_id` to `add_strm_file`
    - `add_content` — passes both to `_write_series_strm_files`; passes `category_folder` to
      `movie_strm_path` and `category_id` to `add_strm_file` for movies
    - `add_or_sync_content` — passes both to `add_content` and `sync_item`
    - `sync_item` — passes both to `_write_series_strm_files`
  - All existing callers that pass no `category_folder`/`category_id` continue to work
    identically (root folder behaviour preserved via defaults).
  - Verify: new tests in `test_library_sync.py`:
    1. `add_content(..., category_folder="Action", category_id="cat1")` for a movie → `.strm`
       file is under `…/Action/Movies/…`; `strm_files` row has `category_id="cat1"`
    2. Same for a series episode — file under `…/Action/TV/…`
    3. `add_content(...)` with no category args → file under `…/Movies/…` (unchanged)
  - Files: `server/sync.py`, `tests/test_library_sync.py`
  - Size: S

- [ ] Verify Phase 3
  - Acceptance: `pytest tests/test_library_sync.py -q` exits 0
  - Verify: run the command
  - Files: none

---

## Phase 4 — Routes

- [ ] Task: Update category add route to pass category context
  - Acceptance: `POST /library/category/{category_id}` in `server/routes/library.py`:
    - Looks up the category row via `get_category(db, category_id)`.
    - Computes `folder = sanitize(cat["title"])` (import `sanitize` from `server.sync`).
    - Passes `category_folder=folder` and `category_id=category_id` to every
      `add_or_sync_content` call in the fan-out task.
    - All other behaviour (202 response, background task, `add_category_to_library` call) is
      unchanged.
  - Verify: new test in `test_library_routes.py` — POST a category, assert written `.strm`
    files land under `{output_dir}/{sanitized_title}/Movies/…`
  - Files: `server/routes/library.py`, `tests/test_library_routes.py`
  - Size: XS

- [ ] Task: Update category delete route to use scoped removal
  - Acceptance: `DELETE /library/category/{category_id}` in `server/routes/library.py`:
    - Replaces the current `delete_content(db, content_id)` fan-out with:
      1. Call `remove_category_strm_files(db, category_id)` → get paths.
      2. Delete those paths from disk (same `Path.unlink` + parent `rmdir` pattern as `delete_content`).
      3. For each `content_id` that was in this category (from `get_content_ids_for_category`):
         if `get_strm_files(db, content_id)` is now empty, call `remove_from_library(db, content_id)`.
    - Calls `remove_category_from_library(db, category_id)` as before.
    - Content with remaining strm files in other contexts stays `in_library = 1`.
  - Verify: new tests in `test_library_routes.py`:
    1. DELETE category → only that category's `.strm` files are removed from disk and DB.
    2. Content whose only strm files were in the deleted category → `in_library = 0`.
    3. Content that also had a single-add strm file (category_id NULL) → remains `in_library = 1`
       and its non-category file is still present.
  - Files: `server/routes/library.py`, `tests/test_library_routes.py`
  - Size: S

- [ ] Verify Phase 4
  - Acceptance: `pytest tests/ -q` exits 0 (full suite, no regressions)
  - Verify: run the command
  - Files: none

---

## Phase 5 — Docs

- [ ] Task: Update `docs/library.md`
  - Acceptance:
    - The file layout section shows both the single-add path (`Movies/…`, `TV/…`) and the
      category-sync path (`{CategoryName}/Movies/…`, `{CategoryName}/TV/…`).
    - Notes that content already in the library is skipped by category sync.
    - Notes that `DELETE /library/category/{id}` removes only that category's files.
    - No stale information remains.
  - Verify: read the file; confirm both path formats are documented
  - Files: `docs/library.md`
  - Size: XS
