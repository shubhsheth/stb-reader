# Plan: Category Content Folders (010)

## Components and Dependencies

```
strm_files.category_id column (DB migration)
    └─► add_strm_file() accepts category_id
        └─► _write_series_strm_files() stores category_id
            └─► add_content() passes category_id
                └─► add_or_sync_content() accepts + passes category_id & category_folder

movie_strm_path() / episode_strm_path() accept category_folder
    └─► _write_series_strm_files() passes category_folder
        └─► add_content() passes category_folder

Category route reads category title → sanitize → category_folder
    └─► calls add_or_sync_content with (category_folder, category_id)

New DB helper: get_strm_paths_for_category() + remove_category_strm_files()
    └─► Category delete route uses scoped removal
        └─► Checks remaining strm_files to decide if content stays in_library
```

## Implementation Order

Sequential — each group depends on the one above.

### Phase 1 — DB layer (foundation)

All other phases depend on the `category_id` column and updated `add_strm_file` signature.

1. **DB migration**: append `_add_col("strm_files", "category_id", "TEXT")` to `MIGRATIONS`.
2. **`add_strm_file`**: add `category_id: str | None = None` parameter; store it.
3. **New delete helpers**: `get_strm_paths_for_category(db, category_id)` and
   `remove_category_strm_files(db, category_id)` — used by the updated category delete route.

### Phase 2 — Path functions

Pure functions; no dependencies on Phase 1. Can be reviewed independently.

4. **`movie_strm_path`** / **`episode_strm_path`**: add `category_folder: str | None = None`.

### Phase 3 — Sync helpers

Depends on Phase 1 (add_strm_file signature) and Phase 2 (path functions).

5. **`_write_series_strm_files`**: add `category_folder` and `category_id` params; pass to
   path functions and `add_strm_file`.
6. **`add_content`**: add `category_folder` and `category_id` params; pass down.
7. **`add_or_sync_content`**: add `category_folder` and `category_id` params; pass to
   `add_content` and `sync_item` (sync_item already no-ops for movies, passes through for
   series episodes).

### Phase 4 — Routes

Depends on Phase 1 (delete helpers) and Phase 3 (add_or_sync_content signature).

8. **Category add route** (`POST /library/category/{id}`): look up category, sanitize title,
   pass `category_folder` and `category_id` to `add_or_sync_content`.
9. **Category delete route** (`DELETE /library/category/{id}`): replace `delete_content` fan-out
   with scoped removal using `remove_category_strm_files`; check remaining strm_files per content
   item; call `remove_from_library` only when count reaches zero.

### Phase 5 — Tests + docs

10. Extended tests covering all new behaviour.
11. `docs/library.md` updated with new folder layout.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `add_strm_file` call sites in `sync.py` break due to signature change | Add `category_id=None` default — all existing callers continue to work without change |
| Category delete removes too much (old all-content deletion) | New helper queries by `category_id`; content with NULL or different `category_id` rows is untouched |
| Existing `strm_files` rows (NULL `category_id`) silently included in a category delete | `WHERE category_id = ?` with a non-NULL value never matches NULL rows in SQLite |
| sanitize() produces the same folder name for two different categories | Acceptable — not addressed in this spec; categories with identical sanitized titles share a folder |

## Parallel vs Sequential

- Phases 1 and 2 are independent and could be developed in parallel.
- Phases 3, 4, 5 must follow Phase 1 and 2 in order.

## Verification Checkpoints

- After Phase 1: `pytest tests/test_library_db.py -q` passes.
- After Phase 2: `pytest tests/test_library_sync.py -q` passes (path function tests).
- After Phase 3: `pytest tests/test_library_sync.py -q` passes (sync helper tests).
- After Phase 4: `pytest tests/ -q` passes (full suite).
- After Phase 5: `pytest tests/ -q` passes; docs reviewed.
