# Tasks: Category Content Folders (010)

## Phase 1 — Path functions

- [ ] Task: Add `category_folder` param to `movie_strm_path` and `episode_strm_path`
  - Acceptance:
    - `movie_strm_path(output_dir, name, year, category_folder=None)`:
      - `category_folder=None` → `Path(output_dir) / "Movies" / folder / f"{folder}.strm"` (unchanged)
      - `category_folder="Action"` → `Path(output_dir) / "Action" / "Movies" / folder / f"{folder}.strm"`
    - `episode_strm_path(…, category_folder=None)`:
      - `category_folder=None` → `Path(output_dir) / "TV" / …` (unchanged)
      - `category_folder="Drama"` → `Path(output_dir) / "Drama" / "TV" / …`
    - All existing call sites (no `category_folder` arg) produce identical paths.
  - Verify: new parametrized tests in `test_library_sync.py` asserting exact `Path` values for
    both `None` and non-`None` `category_folder`; `pytest tests/test_library_sync.py -q` exits 0
  - Files: `server/sync.py`, `tests/test_library_sync.py`
  - Size: XS

---

## Phase 2 — Sync helpers

- [ ] Task: Thread `category_folder` through sync helpers
  - Acceptance: The following functions each gain `category_folder: str | None = None`
    (default `None`):
    - `_write_series_strm_files` — passes `category_folder` to `episode_strm_path`
    - `add_content` — passes `category_folder` to `_write_series_strm_files` and `movie_strm_path`
    - `sync_item` — passes `category_folder` to `_write_series_strm_files`
    - `add_or_sync_content` — passes `category_folder` to `add_content` and `sync_item`
  - All existing callers without `category_folder` continue to work identically.
  - Verify: new tests in `test_library_sync.py`:
    1. `add_content(…, category_folder="Action")` for a movie → `.strm` file is under `…/Action/Movies/…`
    2. Same for a series episode → file under `…/Action/TV/…`
    3. `add_content(…)` with no category arg → file under `…/Movies/…` (unchanged)
    - `pytest tests/test_library_sync.py -q` exits 0
  - Files: `server/sync.py`, `tests/test_library_sync.py`
  - Size: S

---

## Phase 3 — DB helper

- [ ] Task: Add `remove_category_strm_files` DB helper
  - Acceptance: `remove_category_strm_files(db, content_ids: list[str], path_prefix: str) -> list[str]`
    - Deletes `strm_files` rows for the given `content_ids` whose `strm_path` starts with
      `path_prefix + os.sep` (trailing separator prevents partial folder name matches).
    - Returns the list of deleted `strm_path` values for disk cleanup.
    - Rows for the same `content_ids` whose paths do NOT start with the prefix are untouched.
  - Verify: new tests in `test_library_db.py`:
    1. Insert rows under `{prefix}/Movies/…` and `Movies/…`; assert only the prefixed rows
       are returned and deleted.
    2. Partial name match (prefix `Action` vs folder `Action-Comedy`) — assert no false positives.
    - `pytest tests/test_library_db.py -q` exits 0
  - Files: `server/db.py`, `tests/test_library_db.py`
  - Size: XS

---

## Phase 4 — Routes

- [ ] Task: Update category add route to pass category folder
  - Acceptance: `POST /library/category/{category_id}` in `server/routes/library.py`:
    - Computes `folder = sanitize(cat["title"])` using the existing `sanitize` import from
      `server.sync`.
    - Passes `category_folder=folder` to every `add_or_sync_content` call in the fan-out task.
    - All other behaviour (202 response, background task, `add_category_to_library` call)
      is unchanged.
  - Verify: new test in `test_library_routes.py` — POST a category, assert written `.strm`
    files land under `{output_dir}/{sanitized_title}/Movies/…`; `pytest tests/ -q` exits 0
  - Files: `server/routes/library.py`, `tests/test_library_routes.py`
  - Size: XS

- [ ] Task: Update category delete route to use scoped removal
  - Acceptance: `DELETE /library/category/{category_id}` in `server/routes/library.py`:
    - Replaces the current `delete_content(db, content_id)` fan-out with:
      1. Compute `prefix = str(Path(settings.strm_output_dir) / sanitize(cat["title"]))`.
      2. Get `content_ids = get_content_ids_for_category(db, category_id)`.
      3. Call `remove_category_strm_files(db, content_ids, prefix)` → get `paths`.
      4. Delete those paths from disk (same `Path.unlink` + parent `rmdir` pattern as `delete_content`).
      5. For each `content_id` in `content_ids`: if `get_strm_files(db, content_id)` is now
         empty, call `remove_from_library(db, content_id)`.
    - Calls `remove_category_from_library(db, category_id)` as before.
    - Content with remaining strm files in other contexts stays `in_library = 1`.
  - Verify: new tests in `test_library_routes.py`:
    1. DELETE category → only files under the category prefix are removed from disk and DB.
    2. Content whose only strm files were in the deleted category → `in_library = 0`.
    3. Content that also has a single-add strm file → remains `in_library = 1` and its
       non-category file is still present on disk.
    - `pytest tests/ -q` exits 0
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
    - The file layout section documents both path forms:
      - Single add: `{STRM_OUTPUT_DIR}/Movies/{Name} ({Year})/` and `TV/…`
      - Category sync: `{STRM_OUTPUT_DIR}/{CategoryName}/Movies/…` and `{CategoryName}/TV/…`
    - Notes that content already in the library is skipped by category sync.
    - Notes that `DELETE /library/category/{id}` removes only files placed under that
      category's subfolder; single-add files are unaffected.
    - No stale information remains.
  - Verify: read the file; confirm both path formats are present
  - Files: `docs/library.md`
  - Size: XS
