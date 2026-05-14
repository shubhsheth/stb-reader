# Implementation Checklist: Category Item Count (011)

- [ ] Task 1: Update `list_categories` SQL in `server/db.py`
  - Acceptance: Function returns dicts with `item_count` (int); categories with no linked content return `item_count == 0`
  - Verify: `pytest tests/test_library_db.py` passes
  - Files: `server/db.py`

- [ ] Task 2: Add `TestListCategories` in `tests/test_library_db.py`
  - Acceptance: Two tests — zero-count case and N-count case — both pass
  - Verify: `pytest tests/test_library_db.py::TestListCategories`
  - Files: `tests/test_library_db.py`

- [ ] Task 3: Show item count as subtext in the title cell
  - Acceptance: Title cell renders category name on one line and dimmed "N items" beneath it; no new column added; `.item-count` CSS rule dims the subtext
  - Verify: Load the Categories tab in the browser; confirm count appears under each title without adding a column
  - Files: `server/static/index.html`
