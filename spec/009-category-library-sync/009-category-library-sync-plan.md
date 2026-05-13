# Plan: Category Library Sync (009)

## Components & Dependencies

```
db.py  ──→  sync.py  ──→  routes/library.py
  │            │                 │
  ▼            ▼                 ▼
test_library_db.py  test_library_sync.py  test_library_routes.py
                                          docs/library.md
```

Everything is sequential: the DB helpers must exist before the sync helper can call them,
and the sync helper must exist before routes can dispatch to it.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Removing old endpoints breaks existing tests | Update route tests in the same commit as the route changes (Phase 3) |
| `add_content` in `sync.py` already calls `add_to_library` internally; double-calling is safe (idempotent UPDATE) but must be verified | Cover the add-then-add-again path in sync helper tests |
| Category fan-out enqueues N background tasks at once; could flood the portal | Delay is already threaded through all callers; no additional mitigation needed for this spec |

---

## Implementation Order

### Phase 1 — DB helpers (`server/db.py` + `tests/test_library_db.py`)

Add two read-only query functions. No schema changes; both operate on existing tables.

**`get_category(db, category_id) -> dict | None`**
- `SELECT * FROM vod_categories WHERE category_id = ?`
- Returns `dict(row)` or `None`

**`get_content_ids_for_category(db, category_id) -> list[str]`**
- `SELECT content_id FROM vod_content_category WHERE category_id = ?`
- Returns a list of content_id strings (may be empty)

Verify: new unit tests in `test_library_db.py` cover both functions.
Check: `pytest tests/test_library_db.py -q` passes.

---

### Phase 2 — Sync helper (`server/sync.py` + `tests/test_library_sync.py`)

Add one function that implements the idempotent add-or-sync logic.

**`add_or_sync_content(db, vod, output_dir, server_base, content_id, delay_s) -> int`**
```
if get_library_item(db, content_id) is None:
    return add_content(db, vod, output_dir, server_base, content_id, delay_s)
else:
    return sync_item(db, vod, output_dir, server_base, content_id, delay_s)
```

`add_content` already calls `add_to_library` internally, so no extra DB call is needed on the
add path. `sync_item` already handles the series-only / movie-noop distinction.

Verify: unit tests in `test_library_sync.py` cover:
- Not-in-library path → delegates to `add_content`
- Already-in-library path → delegates to `sync_item`

Check: `pytest tests/test_library_sync.py -q` passes.

---

### Phase 3 — Routes (`server/routes/library.py` + `tests/test_library_routes.py`)

Replace all three old handlers and add two new category handlers. `GET /library` and
`POST /library/sync` are untouched.

**Remove:**
- `POST /library/add/{content_id}`
- `POST /library/sync/{content_id}`
- `DELETE /library/{content_id}`

**Add / replace with:**

`POST /library/content/{content_id}` (FR-1)
- 404 if `get_vod_content` returns None
- Enqueue `add_or_sync_content` as background task
- Return 202

`DELETE /library/content/{content_id}` (FR-2)
- 404 if `get_library_item` returns None
- Call `delete_content` synchronously (matches existing delete pattern)
- Return 204

`POST /library/category/{category_id}` (FR-3)
- 404 if `get_category` returns None
- Fetch `get_content_ids_for_category`
- Enqueue one `add_or_sync_content` background task per content_id
- Return 202

`DELETE /library/category/{category_id}` (FR-4)
- 404 if `get_category` returns None
- Fetch `get_content_ids_for_category`
- Call `delete_content` for each content_id that is currently in the library
  (skip items not in library to avoid errors from `delete_content`'s path cleanup)
- Return 204

Update `test_library_routes.py`:
- Rename existing test classes to use new endpoint paths
- Remove test for 409 (duplicate add is now silently a sync, not an error)
- Add `TestCategoryUpsert` — 202 on valid category, 404 on unknown
- Add `TestCategoryDelete` — 204 on valid category (items removed), 404 on unknown

Check: `pytest tests/test_library_routes.py -q` passes, then `pytest tests/ -q` passes.

---

### Phase 4 — Docs (`docs/library.md`)

Rewrite the Endpoints section to reflect the four new endpoints and remove the three old ones.
No other sections need changing.

Check: manual review for accuracy.

---

## Verification Checkpoints

| After phase | Check |
|-------------|-------|
| 1 | `pytest tests/test_library_db.py -q` |
| 2 | `pytest tests/test_library_sync.py -q` |
| 3 | `pytest tests/ -q` (full suite) |
| 4 | Read `docs/library.md`, confirm no stale endpoint references |
