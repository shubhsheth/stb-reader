# Implementation Checklist: Category Item Count (011)

- [ ] Task 1: Update `list_categories` SQL in `server/db.py`
  - Acceptance: Function returns dicts with `item_count` (int); categories with no linked content return `item_count == 0`
  - Verify: `pytest tests/test_library_db.py` passes
  - Files: `server/db.py`

- [ ] Task 2: Add `TestListCategories` in `tests/test_library_db.py`
  - Acceptance: Two tests — zero-count case and N-count case — both pass
  - Verify: `pytest tests/test_library_db.py::TestListCategories`
  - Files: `tests/test_library_db.py`

- [ ] Task 3: Add "Items" column to category table in UI
  - Acceptance: `<th>Items</th>` and `<td>${cat.item_count}</td>` appear in `renderCategories()`
  - Verify: Load the Categories tab in the browser; confirm column is visible with numeric values
  - Files: `server/static/index.html`
