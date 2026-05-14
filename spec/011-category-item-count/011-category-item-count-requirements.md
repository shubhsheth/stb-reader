# Spec: Category Item Count (011)

## Objective

When a user views the Library → Categories tab, they currently see category name, library status, and action buttons — but no indication of how many content items belong to each category. This makes it hard to judge which categories are worth adding. We'll surface an item count so users can make informed decisions.

## User Stories

- As a user browsing the Categories tab, I want to see how many items each category contains so that I can decide which ones to add to my library.

## Functional Requirements

- FR-1: `GET /library/categories` must include an `item_count` field on each category object, representing the total number of content items linked to that category via `vod_content_category`.
- FR-2: `item_count` must be `0` for categories with no linked content (not `null` or absent).
- FR-3: The item count must be shown as subtext within the title cell — e.g., the category name on one line and a dimmed "42 items" beneath it. No separate column.

## Non-Functional Requirements

- NFR-1: The DB query must remain a single SQL statement (no N+1 queries).

## Out of Scope

- Filtering or sorting by item count in the UI.
- Showing how many of those items are already in the user's library (library_count).
- Any changes to the `/vod/categories` endpoint.

## Assumptions

- `item_count` = total rows in `vod_content_category` for that category; no filter on `vod_content.in_library`.
- No schema migration is required — the count is derived from the existing junction table.
- The route (`GET /library/categories`) passes the DB result through directly; no Pydantic model or serialization layer to update.

## Tech Stack

- Python 3.11, FastAPI, SQLite (`sqlite3`)
- Vanilla JS frontend (`server/static/index.html`)
- pytest

## Commands

```
Test:  pytest tests/
Lint:  (none configured)
Dev:   uvicorn server.main:app --reload
```

## Project Structure

```
server/
  db.py                    ← list_categories query lives here
  routes/library.py        ← GET /library/categories route
  static/index.html        ← renderCategories() UI function
tests/
  test_library_db.py       ← DB-level tests (add TestListCategories here)
spec/011-category-item-count/
  011-category-item-count-requirements.md  ← this file
  011-category-item-count-plan.md
  011-category-item-count-implement.md
```

## Code Style

```python
# db.py style — raw SQL, fetchall, return list[dict]
def list_categories(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("""
        SELECT vc.category_id, vc.title, vc.in_library, vc.added_at,
               COUNT(vcc.content_id) AS item_count
        FROM vod_categories vc
        LEFT JOIN vod_content_category vcc ON vc.category_id = vcc.category_id
        GROUP BY vc.category_id
        ORDER BY vc.title
    """).fetchall()
    return [dict(r) for r in rows]
```

```js
// index.html style — subtext inside the title cell
`<td class="title">${esc(cat.title)}<br><small class="item-count">${cat.item_count} items</small></td>`
```

## Testing Strategy

- Framework: pytest
- Test file: `tests/test_library_db.py` — add `class TestListCategories`
- Two cases:
  1. Category with no linked content → `item_count == 0`
  2. Category with N linked items → `item_count == N`
- No route-level test needed (route is a passthrough with no logic).

## Boundaries

- **Always:** Run `pytest tests/` before committing.
- **Ask first:** Any changes to the DB schema or other DB helper functions.
- **Never:** Modify unrelated tests or helper functions.

## Success Criteria

- SC-1: `GET /library/categories` response includes `item_count` (integer ≥ 0) on every object.
- SC-2: `item_count` equals the number of rows in `vod_content_category` for that category.
- SC-3: The Categories tab shows the item count as dimmed subtext beneath each category title in the title cell; the table column count is unchanged.
- SC-4: `pytest tests/` passes with no regressions.

## Open Questions

None.
