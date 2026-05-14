# Plan: Category Item Count (011)

## Implementation Order

Dependencies run bottom-up: DB → tests → UI (tests and UI can be done in parallel after the DB change).

```
Task 1: Update list_categories SQL (server/db.py)
  └─→ Task 2: Add TestListCategories tests (tests/test_library_db.py)
  └─→ Task 3: Add "Items" column to UI (server/static/index.html)
```

## Component Breakdown

### Task 1 — DB query (server/db.py)

Replace the existing `SELECT` in `list_categories` with a LEFT JOIN + COUNT + GROUP BY:

```sql
SELECT vc.category_id, vc.title, vc.in_library, vc.added_at,
       COUNT(vcc.content_id) AS item_count
FROM vod_categories vc
LEFT JOIN vod_content_category vcc ON vc.category_id = vcc.category_id
GROUP BY vc.category_id
ORDER BY vc.title
```

No other changes to `db.py`.

### Task 2 — Tests (tests/test_library_db.py)

Add `class TestListCategories` with:
- `test_item_count_zero_when_no_content` — seed a category with no content, assert `item_count == 0`
- `test_item_count_reflects_linked_content` — seed a category with 2 content items linked via `vod_content_category`, assert `item_count == 2`

Use existing helpers: `_seed_category`, `upsert_vod_content`, `upsert_vod_content_category`, `_vod_row`.

### Task 3 — UI (server/static/index.html)

In `renderCategories()`:
1. Add `<th>Items</th>` to the `<thead>` row (between Status and the empty actions column).
2. Add `<td>${cat.item_count}</td>` to each `<tr>` template in the same position.

## Risks

- None significant. The SQL change is additive and backward-compatible.
- The route is a passthrough, so no route logic is affected.
