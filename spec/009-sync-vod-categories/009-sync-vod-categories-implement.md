# Implementation: Clean Library Endpoints (009)

## Ordered Tasks

### Task 1 — `server/sync.py`: Remove `run_library_sync`, clean up imports

**Changes:**
- Delete `run_library_sync` function (lines ~160–171)
- Remove `get_auto_add_categories` from DB imports (no longer used)
- Remove `get_category_content_ids` from DB imports (only used by `run_library_sync`)

**Keep:** `add_category_content`, `delete_strm_paths`, `sync_category_content`, all other helpers.

**Verify:** `grep -n "run_library_sync\|get_auto_add_categories" server/sync.py` returns nothing.

---

### Task 2 — `server/main.py`: Revert periodic library sync

**Changes:**
- Remove `run_library_sync` from the import line (`from .sync import run_library_sync`)
- Remove the `_run_library_sync` coroutine definition
- Remove the `await _run_library_sync()` call inside `_sync_loop`

**`_sync_loop` after change:**
```python
async def _sync_loop():
    while True:
        await asyncio.sleep(settings.vod_sync_interval_hours * 3600)
        await _run_portal_sync()
```

**Verify:** `grep -n "library_sync\|_run_library" server/main.py` returns nothing.

---

### Task 3 — `server/routes/library.py`: Replace six old endpoints with four new ones

**Remove these six endpoints:**
- `POST /library/add/{content_id}`
- `DELETE /library/{content_id}`
- `POST /library/sync/{content_id}`
- `POST /library/categories/{category_id}`
- `DELETE /library/categories/{category_id}`
- `POST /library/categories/{category_id}/sync`

**Keep unchanged:**
- `GET /library`
- `POST /library/sync` — but change implementation: call `sync_all` (not `run_library_sync`)

**Add four new endpoints:**

#### `POST /library/content/{content_id}` → 202
1. 404 if `get_vod_content(db, content_id)` is None
2. `add_to_library(db, content_id)` — idempotent
3. Background: `add_content(db, vod, output_dir, server_base, content_id, delay_s)`
4. Return 202

#### `DELETE /library/content/{content_id}` → 204
1. 404 if `get_library_item(db, content_id)` is None
2. `paths = remove_from_library(db, content_id)`
3. `delete_strm_paths(paths)` — synchronous, no background needed
4. Return 204

#### `POST /library/category/{category_id}` → 202
1. 404 if `get_vod_category(db, category_id)` is None
2. `set_category_auto_add(db, category_id, 1)`
3. Count items not yet in library: `new_ids = [cid for cid in get_category_content_ids(db, category_id) if get_library_item(db, cid) is None]` → `N = len(new_ids)`
4. `add_to_library(db, cid)` for ALL items in category (idempotent, not just new ones)
5. Background: `add_category_content(...)` for ALL items in category
6. Return 202 `{"added": N}`

**Note:** `get_category_content_ids` returns ALL content in the category (the name is slightly misleading — it's not filtered by library status). So step 3 uses a comprehension to count only the net-new ones before step 4 marks them all as in-library.

#### `DELETE /library/category/{category_id}` → 202
1. 404 if `get_vod_category(db, category_id)` is None
2. `set_category_auto_add(db, category_id, 0)`
3. `content_ids = get_category_library_content_ids(db, category_id)` — only in-library items
4. Collect paths: `paths = []`; for each `cid`: `paths.extend(remove_from_library(db, cid))`
5. Background: `delete_strm_paths(paths)`
6. Category record stays in `vod_categories`
7. Return 202 `{"removed": len(content_ids)}`

**Updated imports for library.py:**
```python
from ..db import (
    add_to_library,
    get_category_content_ids,
    get_category_library_content_ids,
    get_library_item,
    get_library_items,
    get_vod_category,
    get_vod_content,
    remove_from_library,
    set_category_auto_add,
)
from ..sync import (
    add_category_content,
    add_content,
    delete_strm_paths,
    sync_all,
)
```

**Verify:** `curl -s http://localhost:8000/openapi.json | python -m json.tool | grep '"path"'` shows the four new paths and two kept paths; old paths absent.

---

### Task 4 — `server/static/index.html`: Update endpoint paths

Update JavaScript fetch calls from old to new paths:

| Old path | New path |
|----------|----------|
| `POST /library/add/${id}` | `POST /library/content/${id}` |
| `DELETE /library/${id}` | `DELETE /library/content/${id}` |
| `POST /library/sync/${id}` | `POST /library/content/${id}` (idempotent — same endpoint) |
| `POST /library/categories/${id}` | `POST /library/category/${id}` |
| `DELETE /library/categories/${id}` | `DELETE /library/category/${id}` |
| `POST /library/categories/${id}/sync` | `POST /library/category/${id}` (same endpoint) |

**Verify:** `grep -n "library/add\|library/sync/\|library/categories" server/static/index.html` returns nothing.

---

### Task 5 — Tests: Update paths, add new coverage

**Update existing tests** that reference old endpoint paths to use new paths.

**New tests to add** (`tests/test_library_endpoints.py` or existing test file):

| Test | Scenario |
|------|----------|
| `test_post_content_404` | content_id not in vod_content → 404 |
| `test_post_content_adds` | happy path → 202, content marked in_library |
| `test_post_content_idempotent` | calling twice → both 202, no error |
| `test_delete_content_404` | not in library → 404 |
| `test_delete_content_removes` | happy path → 204, strm file deleted |
| `test_post_category_404` | category not in vod_categories → 404 |
| `test_post_category_sets_auto_add` | happy path → 202, auto_add=1 |
| `test_post_category_added_count` | N reflects only net-new items |
| `test_delete_category_404` | category not in vod_categories → 404 |
| `test_delete_category_clears_library` | happy path → 202, in_library cleared, auto_add=0 |
| `test_delete_category_keeps_category_record` | category still in GET /vod/categories after delete |

**Verify:** `uv run --extra test --extra server pytest tests/ -v` all green.

---

## Acceptance Criteria

1. `POST /library/content/{id}` on an already-added series triggers background refresh (new episodes picked up) without error.
2. `DELETE /library/category/{id}` → category still appears in `GET /vod/categories`.
3. `POST /library/sync` triggers sync for all in-library series (calls `sync_all`).
4. Portal sync schedule (`vod_sync_interval_hours`) does NOT trigger library sync.
5. All tests pass.
