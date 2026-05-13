# Tasks: Category Library Sync (009)

## Phase 1 — DB helpers + migration

- [ ] Task: Add `vod_categories` migration columns
  - Acceptance: `MIGRATIONS` in `server/db.py` has two new `_add_col` entries appended —
    `("vod_categories", "in_library", "INTEGER NOT NULL DEFAULT 0")` and
    `("vod_categories", "added_at", "TEXT")`. Existing rows default to `0` / `NULL`.
  - Verify: `pytest tests/test_library_db.py::test_init_db_migrates_old_schema -q` passes (migration test already covers the pattern; will also catch if `PRAGMA user_version` is wrong)
  - Files: `server/db.py`

- [ ] Task: Add `get_category` DB helper
  - Acceptance: `get_category(db, category_id)` returns a `dict` for a known category_id and
    `None` for an unknown one. Returned dict includes the new `in_library` and `added_at` fields.
  - Verify: new tests in `test_library_db.py` — known ID returns dict, unknown ID returns None
  - Files: `server/db.py`, `tests/test_library_db.py`

- [ ] Task: Add `get_content_ids_for_category` DB helper
  - Acceptance: `get_content_ids_for_category(db, category_id)` returns a list of `content_id`
    strings for all rows in `vod_content_category` matching that category; empty list when none exist.
  - Verify: new tests — category with 2 linked items returns 2 IDs; unknown category returns `[]`
  - Files: `server/db.py`, `tests/test_library_db.py`

- [ ] Task: Add `add_category_to_library` DB helper
  - Acceptance: sets `in_library = 1` and `added_at` (ISO 8601 UTC) on the category row. A second
    call does not overwrite `added_at` (idempotent via `AND in_library = 0` guard).
  - Verify: new tests — first call sets flags; second call leaves `added_at` unchanged
  - Files: `server/db.py`, `tests/test_library_db.py`

- [ ] Task: Add `remove_category_from_library` DB helper
  - Acceptance: sets `in_library = 0` and `added_at = NULL` on the category row.
  - Verify: new test — call after `add_category_to_library` clears both fields
  - Files: `server/db.py`, `tests/test_library_db.py`

- [ ] Task: Verify Phase 1
  - Acceptance: `pytest tests/test_library_db.py -q` exits 0 with no failures or errors
  - Verify: run the command
  - Files: none

---

## Phase 2 — Sync helper

- [ ] Task: Add `add_or_sync_content` sync helper
  - Acceptance: if `get_library_item` returns `None`, delegates to `add_content` and returns its
    count; otherwise delegates to `sync_item` and returns its count.
  - Verify: two new unit tests in `test_library_sync.py`:
    1. Content not in library → `add_content` is called, strm file is written
    2. Content already in library (series) → `sync_item` is called, new episodes are written
  - Files: `server/sync.py`, `tests/test_library_sync.py`

- [ ] Task: Verify Phase 2
  - Acceptance: `pytest tests/test_library_sync.py -q` exits 0
  - Verify: run the command
  - Files: none

---

## Phase 3 — Routes

- [ ] Task: Replace content endpoints in `library.py`
  - Acceptance:
    - `POST /library/content/{content_id}` returns 202 for known content (in or out of library),
      404 for unknown content
    - `DELETE /library/content/{content_id}` returns 204 and removes strm files, 404 if not in library
    - Old routes `POST /library/add/{id}`, `POST /library/sync/{id}`, `DELETE /library/{id}` are gone
    - `GET /library` and `POST /library/sync` are unchanged
  - Verify: route tests updated to use new paths; old-path tests removed
  - Files: `server/routes/library.py`, `tests/test_library_routes.py`

- [ ] Task: Add category endpoints in `library.py`
  - Acceptance:
    - `POST /library/category/{category_id}` returns 202 for known category, 404 for unknown;
      `vod_categories.in_library` is set to 1 before returning
    - `DELETE /library/category/{category_id}` returns 204 for known category, 404 for unknown;
      all linked in-library content is removed; `vod_categories.in_library` is cleared
  - Verify: new test classes `TestCategoryUpsert` and `TestCategoryDelete` in `test_library_routes.py`
  - Files: `server/routes/library.py`, `tests/test_library_routes.py`

- [ ] Task: Verify Phase 3
  - Acceptance: `pytest tests/ -q` exits 0 (full suite, no regressions)
  - Verify: run the command
  - Files: none

---

## Phase 4 — Docs + cleanup

- [ ] Task: Update `docs/library.md`
  - Acceptance: Endpoints section documents all four new endpoints and their status codes; no
    references to the removed endpoints (`/library/add/`, `/library/sync/{id}`, `DELETE /library/{id}`)
    remain; new `vod_categories` library fields (`in_library`, `added_at`) mentioned
  - Verify: read the file; grep for `add` and `sync` to confirm no stale paths
  - Files: `docs/library.md`

- [ ] Task: Update `AGENTS.md`
  - Acceptance: any endpoint listing or library section in `AGENTS.md` reflects the new routes
  - Verify: read the file for stale references
  - Files: `AGENTS.md`
