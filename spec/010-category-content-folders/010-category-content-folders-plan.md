# Plan: Category Content Folders (010)

## Components and Dependencies

```
movie_strm_path() / episode_strm_path() accept category_folder
    └─► _write_series_strm_files() passes category_folder
        └─► add_content() passes category_folder
            └─► add_or_sync_content() accepts + passes category_folder
                └─► sync_item() accepts + passes category_folder

Category route reads category title → sanitize → category_folder
    └─► calls add_or_sync_content(…, category_folder=folder)

New DB helper: remove_category_strm_files(db, content_ids, path_prefix)
    └─► Category delete route uses scoped removal
        └─► Checks remaining strm_files per content_id to decide if content stays in_library
```

## Implementation Order

Sequential — each group depends on the one above.

### Phase 1 — Path functions (no dependencies)

Pure functions; can be reviewed in isolation.

1. **`movie_strm_path`** / **`episode_strm_path`**: add `category_folder: str | None = None`.

### Phase 2 — Sync helpers

Depends on Phase 1 (updated path function signatures).

2. **`_write_series_strm_files`**: add `category_folder` param; pass to `episode_strm_path`.
3. **`add_content`**: add `category_folder` param; pass to `_write_series_strm_files` and
   `movie_strm_path`.
4. **`sync_item`**: add `category_folder` param; pass to `_write_series_strm_files`.
5. **`add_or_sync_content`**: add `category_folder` param; pass to `add_content` and `sync_item`.

### Phase 3 — DB helpers

No dependency on Phases 1–2; can be developed alongside them.

6. **`remove_category_strm_files`**: accepts a list of `content_id` values and a path prefix
   string; deletes `strm_files` rows whose `strm_path` starts with the prefix; returns deleted
   paths for disk cleanup.

### Phase 4 — Routes

Depends on Phase 2 (add_or_sync_content signature) and Phase 3 (delete helper).

7. **Category add route**: compute `folder = sanitize(cat["title"])`, pass as `category_folder`.
8. **Category delete route**: compute path prefix, call `remove_category_strm_files`, delete
   disk files, then clear library flags for content with no remaining strm rows.

### Phase 5 — Tests + docs

9. Extended tests for all new behaviour.
10. `docs/library.md` updated with new folder layout.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `category_folder=None` default breaks existing callers | All new params default to `None`; existing callers pass nothing and get current behaviour |
| Path prefix filter matches too broadly (e.g. "Action" prefix matches "Action-Comedy" folder) | Use `os.sep`-terminated prefix (`str(prefix) + os.sep`) to avoid partial name matches |
| Category title sanitizes to empty string | `sanitize()` only replaces specific unsafe chars; an all-unsafe title is pathological and not addressed here |

## Parallel vs Sequential

- Phase 1 and Phase 3 are independent and can be developed in parallel.
- Phase 2 depends on Phase 1.
- Phase 4 depends on Phases 2 and 3.
- Phase 5 follows Phase 4.

## Verification Checkpoints

- After Phase 1: `pytest tests/test_library_sync.py -q` passes (path function tests).
- After Phase 2: `pytest tests/test_library_sync.py -q` passes (sync helper tests).
- After Phase 3: `pytest tests/test_library_db.py -q` passes.
- After Phase 4: `pytest tests/ -q` passes (full suite).
- After Phase 5: `pytest tests/ -q` passes; docs reviewed.
