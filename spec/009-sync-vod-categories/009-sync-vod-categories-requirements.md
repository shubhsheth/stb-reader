# Spec: Bulk Add VOD Category to Library

## Objective

Users need a way to add all VOD content in a given portal category to their local media library in a single operation. Today they must add items one at a time via `POST /library/add/{content_id}`, which is impractical for large categories. This feature adds a `POST /library/categories/{category_id}` endpoint that bulk-adds all not-yet-added items, marks them in the DB immediately, and generates `.strm` files in the background.

## User Stories

- As a user, I want to add an entire VOD category (e.g. "Kids Movies") to my library in one request so that I don't have to add hundreds of items one by one.
- As a user, I want to see immediately how many items were queued so I know the operation succeeded.
- As a user with a partially-added category, I want repeat calls to be safe — already-added items should be silently skipped.

## Functional Requirements

- FR-1: `POST /library/categories/{category_id}` accepts a category ID and returns HTTP 202 with `{"added": N}` where N is the count of items newly marked as in_library.
- FR-2: The endpoint returns HTTP 404 if `category_id` does not exist in `vod_categories`.
- FR-3: Items already in the library (`in_library = 1`) are silently skipped (not an error).
- FR-4: All newly-added items are marked `in_library = 1` synchronously before the response is returned, so they appear in `GET /library` immediately.
- FR-5: `.strm` file generation for all newly-added items runs in a single background thread, sequentially, reusing the existing `add_content()` logic and the configured request delay.
- FR-6: If the category exists but all its content is already in the library (or the category has no synced content), the endpoint returns 202 with `{"added": 0}`.

## Non-Functional Requirements

- NFR-1: The endpoint must not block the FastAPI event loop — background work uses `asyncio.to_thread`.
- NFR-2: No new DB migrations are required; the existing schema supports this feature.
- NFR-3: The implementation reuses existing `add_content()`, `add_to_library()`, and related helpers — no duplicate logic.

## Out of Scope

- Removing an entire category from the library (delete-by-category).
- Filtering content within the category (e.g. only movies, only series).
- Progress tracking or status polling for the background `.strm` generation job.
- Triggering a portal sync as part of this endpoint — it operates on already-cached data only.

## Assumptions

- `vod_content_category` is populated by the portal sync; this endpoint does not fetch from the portal.
- Sequential `.strm` generation with the existing delay is acceptable for large categories.
- The existing `add_content()` idempotency (calling `add_to_library()` again is harmless) is relied upon.

## Tech Stack

- Python 3.11+, FastAPI, SQLite (via `sqlite3`), `asyncio`
- Testing: `pytest`, `fastapi.testclient.TestClient`, `unittest.mock`

## Commands

```
Test:  pytest tests/
Lint:  (no linter configured; match existing code style)
```

## Project Structure

```
server/
  db.py              → DB helpers (add get_vod_category, get_category_content_ids)
  sync.py            → .strm generation (add add_category_content)
  routes/library.py  → API routes (add new endpoint)
tests/
  test_library_routes.py  → Route-level tests (add category endpoint tests)
  test_library_db.py      → DB helper tests (add tests for new helpers)
spec/009-sync-vod-categories/  → This spec
```

## Code Style

Match existing patterns exactly:

```python
# db.py — new helper
def get_vod_category(db: sqlite3.Connection, category_id: str) -> dict | None:
    row = db.execute(
        "SELECT * FROM vod_categories WHERE category_id = ?", (category_id,)
    ).fetchone()
    return dict(row) if row else None

# routes/library.py — new endpoint
@router.post("/library/categories/{category_id}", status_code=202)
async def add_category_to_library(category_id: str, request: Request):
    ...
    return {"added": len(content_ids)}
```

## Testing Strategy

- Framework: `pytest` with `TestClient` for route tests, plain `sqlite3` for DB unit tests.
- New route tests in `tests/test_library_routes.py` (same fixture pattern as `TestAddContent`).
- New DB helper tests in `tests/test_library_db.py`.
- All existing tests must continue to pass.

## Boundaries

- **Always:** Reuse existing helpers (`add_to_library`, `add_content`). Run `pytest tests/` before committing.
- **Ask first:** Any DB schema changes (migrations).
- **Never:** Fetch from the STB portal inside this endpoint. Duplicate `.strm`-path logic.

## Success Criteria

- `POST /library/categories/<valid_id>` with un-added items → 202, `{"added": N}`, all N items visible in `GET /library` immediately.
- `POST /library/categories/<valid_id>` when all items already added → 202, `{"added": 0}`.
- `POST /library/categories/<nonexistent>` → 404.
- Calling the endpoint twice is safe — second call returns `{"added": 0}`.
- All existing tests pass.
- New tests cover the three cases above.
