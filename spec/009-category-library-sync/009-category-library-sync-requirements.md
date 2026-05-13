# Spec: Category Library Sync (009)

## Objective

Restructure the library API so that a single `POST` endpoint handles both add and sync
(idempotent upsert), and add a new category-level operation that fans out to every content item
in a portal category — letting users add or remove an entire category's worth of content in one
request.

**Who:** Users who manage a local Jellyfin library backed by stb-reader.
**Why:** The current split between `/library/add/` and `/library/sync/` is confusing and requires
two separate calls for the same logical operation. Category-level control removes the need to
add content one item at a time.

---

## User Stories

- As a user, I want to add or sync a single piece of content with one endpoint, without needing
  to know whether it is already in my library.
- As a user, I want to point at a category and have every item in it added to my library (or
  synced if already present) with a single request.
- As a user, I want to remove an entire category from my library without having to delete each
  item individually.

---

## Functional Requirements

- **FR-1** `POST /library/content/{content_id}` — idempotent add-or-sync.
  - If the content is not yet in the library: add it (write `.strm` files) then mark it as in-library.
  - If the content is already in the library: sync it (write `.strm` files for any new episodes; no-op for movies).
  - Content must exist in the local `vod_content` cache; return 404 otherwise.
  - Returns `202 Accepted`; the actual file-writing happens in a background task.

- **FR-2** `DELETE /library/content/{content_id}` — remove a single item.
  - Deletes all `.strm` files for the item and clears its library flags.
  - Returns `404` if the item is not currently in the library.
  - Returns `204 No Content` on success.

- **FR-3** `POST /library/category/{category_id}` — idempotent add-or-sync for an entire category.
  - Looks up all content IDs linked to `category_id` in the local `vod_content_category` table.
  - For each content ID, applies the same add-or-sync logic as FR-1.
  - Returns `404` if `category_id` is not found in the local `vod_categories` cache.
  - Returns `202 Accepted`; all file-writing happens in a background task.
  - Content that belongs to multiple categories is unaffected by the category-level call
    (each item is processed independently; being in another category is irrelevant here).

- **FR-4** `DELETE /library/category/{category_id}` — remove all content exclusive to this category.
  - Looks up all content IDs linked to `category_id`.
  - For each content ID, removes it from the library **only if** it does not also belong to any
    other category that has at least one content item still in the library.
  - Returns `404` if `category_id` is not found in the local `vod_categories` cache.
  - Returns `204 No Content` on success (even if no items were removed).

- **FR-5** Existing `POST /library/sync` (sync-all) is **preserved** as-is. It is unrelated to
  the category endpoints and should continue to work.

- **FR-6** Old endpoints `POST /library/add/{content_id}` and `POST /library/sync/{content_id}`
  are **removed** and replaced entirely by `POST /library/content/{content_id}`.
  `DELETE /library/{content_id}` is **removed** and replaced by `DELETE /library/content/{content_id}`.

---

## Non-Functional Requirements

- **NFR-1** Category fan-out (FR-3, FR-4) must not block the HTTP response; all portal/disk I/O
  happens in a background thread via `asyncio.to_thread`, same pattern as existing routes.
- **NFR-2** No new external dependencies. Use the existing SQLite schema and sync helpers.
- **NFR-3** New routes must follow the same error-response shape used by existing routes
  (FastAPI `HTTPException` with a `detail` string).

---

## Out of Scope

- Persisting "category subscriptions" so that new content added to a category in the portal is
  automatically added to the library on next portal sync.
- Live category lookup from the portal on demand (this spec uses only the local cache).
- Bulk status reporting per content item in the `202` response body.
- Any changes to the `GET /library` endpoint or its response shape.
- Any changes to `POST /library/sync` (sync-all).

---

## Assumptions

- `vod_content_category` is populated by the existing portal sync and is considered the source
  of truth for which content belongs to which category.
- The "exclusive to this category" check in FR-4 is based on the library state at delete time,
  not on portal category membership. If content is in the library but assigned to two categories,
  deleting one category leaves the content in the library.
- Background task errors (file-write failures, portal timeouts) are handled the same way as the
  existing `add_content` / `sync_item` helpers — they surface in server logs but do not
  propagate as HTTP errors to the caller (already the established pattern).

---

## Tech Stack

Python 3.11, FastAPI, SQLite (via `sqlite3`), no new dependencies.

---

## Commands

```
Test:   pytest tests/ -q
Lint:   ruff check server/ tests/
Types:  mypy server/ (if configured)
Dev:    uvicorn server.main:app --reload
```

---

## Project Structure

```
server/
  routes/
    library.py      ← route handlers (modified)
  sync.py           ← sync logic helpers (possibly extended)
  db.py             ← DB helpers (possibly extended with category queries)
tests/
  test_library_routes.py   ← route-level tests (modified + new)
  test_library_sync.py     ← unit tests for sync helpers (no change expected)
  test_library_db.py       ← DB helper tests (extended if new helpers added)
docs/
  library.md        ← updated to reflect new endpoints
```

---

## Code Style

Match existing patterns exactly:

```python
@router.post("/library/content/{content_id}", status_code=202)
async def upsert_library_content(content_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_vod_content(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Content not found in portal cache")
    asyncio.create_task(asyncio.to_thread(
        add_or_sync_content,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url, content_id,
        settings.vod_sync_request_delay_ms / 1000,
    ))
```

- Route handlers stay thin: validate, enqueue background task, return.
- Heavy logic lives in `server/sync.py` or `server/db.py`.
- No docstrings on routes; keep inline comments only when the WHY is non-obvious.

---

## Testing Strategy

- **Framework:** pytest with `TestClient` (FastAPI) for route tests; plain pytest for unit tests.
- **Route tests** (`test_library_routes.py`): cover HTTP status codes and verify DB state after
  synchronous execution (mock background tasks where needed).
- **Unit tests** (`test_library_sync.py`, `test_library_db.py`): cover new helpers directly
  (e.g. `add_or_sync_content`, `get_content_ids_for_category`, `get_exclusive_content_ids`).
- No coverage target mandated, but every new code path reachable from a public function must
  have at least one test.

---

## Boundaries

- **Always:** run `pytest` before committing; match existing file/function naming conventions.
- **Ask first:** schema migrations (adding columns or tables to `db.py`); removing existing DB
  helper functions used outside `library.py`.
- **Never:** change `POST /library/sync` (sync-all) behaviour; touch `vod_sync.py` or portal
  sync logic; add new Python dependencies.

---

## Success Criteria

1. `POST /library/content/{content_id}` on an item **not** in the library results in it being
   marked in-library and `.strm` files written to disk.
2. `POST /library/content/{content_id}` on an item **already** in the library triggers a sync
   (new episode `.strm` files are written; movies are a no-op) without returning an error.
3. `DELETE /library/content/{content_id}` removes the item and its `.strm` files; a subsequent
   `GET /library` does not include it.
4. `POST /library/category/{category_id}` fans out to every content item in the category,
   applying add-or-sync to each.
5. `DELETE /library/category/{category_id}` removes from the library only those items that do
   not belong to any other category still represented in the library.
6. All four new endpoints return `404` when given an unknown ID.
7. `POST /library/sync` (sync-all) continues to work correctly after the refactor.
8. Old endpoints (`/library/add/`, `/library/sync/{id}`, `DELETE /library/{id}`) return `404`
   (i.e. they no longer exist).
9. All existing and new tests pass (`pytest tests/ -q` exits 0).

---

## Open Questions

| # | Question | Options | Implication if left open |
|---|----------|---------|--------------------------|
| 1 | For `DELETE /library/category/{category_id}`, should "exclusive" mean "no other *library* category" or "no other *portal* category"? | Library categories only / All portal categories | Affects how the SQL query is written; library-only is the conservative default in this spec |
| 2 | Should `POST /library/category/{category_id}` return the count of items enqueued in the response body, or always an empty `202`? | Count in body / Empty 202 | Minor — empty 202 keeps parity with the content endpoint |
