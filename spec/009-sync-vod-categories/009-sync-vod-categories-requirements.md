# Spec: Category-Level Library Management

## Objective

Users need bulk management of VOD categories: add all items in a category to the library, remove them, sync series episodes, and delete the category itself. Currently they must act on items one at a time, which is impractical for large categories.

Additionally, when a user adds an entire category they expect new items that appear in that category (after a portal sync) to be automatically added to their library. This requires persisting the user's *intent* at the category level, not just the current item states.

The frontend has no category UI at all today — a category panel must be added to the existing SPA (`server/static/index.html`). All backend work operates on already-cached portal data.

## User Stories

- As a user, I want to browse categories in the UI and see all available categories from my portal.
- As a user, I want to add all content in a category to my library with one click.
- As a user, I want new items that appear in a watched category (after a portal sync) to be automatically added to my library.
- As a user, I want to remove all library items in a category with one click.
- As a user, I want to sync (check for new episodes) all series in a category with one click.
- As a user, I want to delete a category I no longer want, removing it from my category list.
- As a user with a partially-added category, I want bulk-add to be idempotent — already-added items are silently skipped.

## Functional Requirements

### Category intent tracking
- FR-1: `vod_categories` gains an `auto_add` integer column (default 0). When `auto_add = 1`, every portal sync automatically adds any un-added items in that category to the library.
- FR-2: `POST /library/categories/{category_id}` sets `auto_add = 1` on the category, then adds all currently un-added items. Returns 202 with `{"added": N}`.
- FR-3: `DELETE /library/categories/{category_id}` sets `auto_add = 0` on the category, then removes all in-library items. Returns 202 with `{"removed": N}`. DB state is consistent before the response; file deletion runs in background.
- FR-4: After each full portal sync, `run_portal_sync()` checks all categories with `auto_add = 1` and calls `add_to_library` for any items not yet in the library, then queues `.strm` generation for them.

### Library bulk operations
- FR-5: `POST /library/categories/{category_id}/sync` returns HTTP 204 and kicks off background sync of all in-library series in the category.
- FR-6: All library category endpoints return 404 if `category_id` does not exist in `vod_categories`.
- FR-7: Newly-added items are marked `in_library = 1` synchronously (appear in `GET /library` immediately); `.strm` generation runs in a background thread.
- FR-8: Bulk operations are idempotent: already-added items are skipped on add; items not in library are skipped on remove.

### Category management
- FR-9: `DELETE /vod/categories/{category_id}` deletes the category from `vod_categories` and all rows in `vod_content_category` for that category. Returns 204. Returns 404 if the category does not exist. Items in `vod_content` are preserved; they simply lose the category association.

### UI — Category Panel
- FR-8: The existing SPA gains a category panel that loads all categories via `GET /vod/categories` on startup.
- FR-9: Selecting a category filters the content view to show only that category's items (using the existing `category_id` query parameter on `GET /vod/search` or `GET /vod/content`).
- FR-10: The category panel shows a bulk-action toolbar for the selected category with buttons: **Add All**, **Remove All**, **Sync All**, **Delete Category**.
- FR-11: **Add All** calls `POST /library/categories/{id}` and shows the returned count in the status bar.
- FR-12: **Remove All** calls `DELETE /library/categories/{id}` and shows the returned count in the status bar.
- FR-13: **Sync All** calls `POST /library/categories/{id}/sync`.
- FR-14: **Delete Category** calls `DELETE /vod/categories/{id}` and removes the category from the panel.
- FR-15: All four buttons follow the existing disable-during-request / show-error pattern.

## Non-Functional Requirements

- NFR-1: Background work uses `asyncio.to_thread` — the FastAPI event loop is never blocked.
- NFR-2: The only schema change is adding `auto_add INTEGER NOT NULL DEFAULT 0` to `vod_categories`, handled in `init_db` (no separate migration file needed).
- NFR-3: Implementation reuses `add_to_library`, `remove_from_library`, `add_content`, `sync_item` — no logic duplication.
- NFR-4: UI additions are embedded in the existing single-file SPA (`server/static/index.html`) — no new files.

## Out of Scope

- Progress tracking or status polling for background `.strm` generation.
- Triggering a portal sync from these endpoints.
- Filtering content within a category (e.g. only movies).
- Deleting `vod_content` rows when deleting a category (items are preserved).
- Pagination within a category view.
- Auto-add during incremental (early-stopped) syncs — only full syncs trigger auto-add.

## Assumptions

- `vod_content_category` is populated by the portal sync; category endpoints do not fetch from the portal.
- `GET /vod/categories` already exists (`server/routes/vod.py:13`); the UI calls it directly.
- `GET /vod/content` or `GET /vod/search` already accepts a `category_id` filter; the UI uses this.
- Sequential `.strm` generation with the configured delay is acceptable for large categories.
- Auto-add on sync only runs during full syncs (`max_pages == 0 and not early_stopped`), consistent with the existing category association phase in `run_portal_sync()`.

## Tech Stack

- Backend: Python 3.11+, FastAPI, SQLite (`sqlite3`), `asyncio`
- Frontend: Vanilla JS + HTML/CSS, embedded in `server/static/index.html` (no build step)
- Testing: `pytest`, `fastapi.testclient.TestClient`, `unittest.mock`

## Commands

```
Test:  pytest tests/
Dev:   (serve via uvicorn, test UI in browser)
```

## Project Structure

```
server/
  db.py              → Add get_vod_category, get_category_content_ids,
                         get_category_library_content_ids, delete_vod_category,
                         set_category_auto_add, get_auto_add_categories;
                         update init_db to add auto_add column
  sync.py            → Add add_category_content, delete_strm_paths,
                         sync_category_content
  routes/library.py  → Add POST/DELETE /library/categories/{id},
                         POST /library/categories/{id}/sync
  routes/vod.py      → Add DELETE /vod/categories/{id}
  vod_sync.py        → Hook auto-add into run_portal_sync() after
                         category association phase
  static/index.html  → Add category panel + bulk-action toolbar
tests/
  test_library_routes.py  → Category library endpoint tests
  test_library_db.py      → New DB helper tests
  test_vod.py             → Delete-category endpoint test
  test_vod_sync.py        → Auto-add on sync test
spec/009-sync-vod-categories/  → This spec
```

## Code Style

Match existing patterns exactly:

```python
# db.py
def get_vod_category(db: sqlite3.Connection, category_id: str) -> dict | None:
    row = db.execute(
        "SELECT * FROM vod_categories WHERE category_id = ?", (category_id,)
    ).fetchone()
    return dict(row) if row else None

# routes/library.py
@router.post("/library/categories/{category_id}", status_code=202)
async def add_category_to_library(category_id: str, request: Request):
    ...
    return {"added": len(content_ids)}
```

```javascript
// index.html — follows existing fetch pattern
async function bulkAddCategory(categoryId) {
  const res = await apiFetch(`/library/categories/${categoryId}`, { method: 'POST' });
  showStatus(`Added ${res.added} items`);
}
```

## Testing Strategy

- Backend: `pytest` + `TestClient`. New route tests in `test_library_routes.py` and `test_vod.py`.
- DB helpers: plain unit tests in `test_library_db.py`.
- UI: manual browser verification (no automated frontend tests in this project).
- All existing tests must continue to pass.

## Boundaries

- **Always:** Reuse existing helpers. Run `pytest tests/` before committing.
- **Ask first:** Adding a `GET /vod/content?category_id=` param if it doesn't already exist.
- **Never:** Fetch from the STB portal inside these endpoints. Duplicate `.strm`-path logic. Add new static files.

## Success Criteria

**API:**
- `POST /library/categories/<id>` → 202 `{"added": N}`, all N items in_library=1 immediately, `auto_add=1` set; 404 for unknown id; 202+0 if all already added.
- `DELETE /library/categories/<id>` → 202 `{"removed": N}`, all N items in_library=0 immediately, `auto_add=0` set; 404 for unknown id; 202+0 if none in library.
- `POST /library/categories/<id>/sync` → 204; 404 for unknown id.
- `DELETE /vod/categories/<id>` → 204, category and its content_category rows gone; 404 for unknown id.
- Idempotency: calling add twice returns `{"added": 0}` on second call.

**Auto-add on sync:**
- After a full portal sync, any item newly associated with an `auto_add=1` category that is not yet in the library gets added automatically.
- Confirmed by a test that runs a sync after adding new items to a watched category.

**UI:**
- Category panel lists all portal categories.
- Selecting a category filters the content list to that category's items.
- Add All / Remove All buttons update the status bar with the count returned.
- Delete Category removes it from the panel immediately.
- Buttons are disabled during requests and show errors on failure.

**Regression:**
- All existing tests pass.
- New tests cover all four API endpoints (happy path + 404).
