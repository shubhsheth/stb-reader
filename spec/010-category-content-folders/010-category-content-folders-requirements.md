# Spec: Category Content Folders (010)

## Objective

When content is added via a category sync, write its `.strm` files into a category-named
subfolder (`{STRM_OUTPUT_DIR}/{CategoryName}/Movies/…` or `{CategoryName}/TV/…`) instead of
the shared root `Movies/` or `TV/` folders. Single-item adds continue to use the root folders
unchanged. This gives Jellyfin a clean per-category library structure while keeping manually
added content in the familiar top-level layout.

**Who:** Users who manage a Jellyfin library via stb-reader and sync entire portal categories.  
**Why:** All content currently lands in the same `Movies/` / `TV/` folders regardless of origin,
making it impossible to separate categories as distinct Jellyfin libraries.

---

## User Stories

- As a user, I want category-synced content to appear in its own named folder so I can add each
  category as a separate Jellyfin library.
- As a user, I want single-item adds to continue working exactly as before — in the root
  `Movies/` or `TV/` folder.
- As a user, I want removing a category from the library to delete only that category's files,
  leaving any overlapping single-add content untouched.

---

## Functional Requirements

- **FR-1** `POST /library/content/{content_id}` (single add) — **unchanged**.
  - `.strm` files are written to `{STRM_OUTPUT_DIR}/Movies/{Name} ({Year})/` (movie) or
    `{STRM_OUTPUT_DIR}/TV/{Name} ({Year})/Season NN/` (series). No category subfolder.
  - Content that is already in the library is synced (new episodes only; movies are no-op).

- **FR-2** `POST /library/category/{category_id}` (category sync) — **modified folder target**.
  - `.strm` files are written to `{STRM_OUTPUT_DIR}/{CategoryName}/Movies/…` or
    `{STRM_OUTPUT_DIR}/{CategoryName}/TV/…`, where `{CategoryName}` is the sanitized
    `vod_categories.title` for that category (same `sanitize()` function used for content names).
  - Content that is **already in the library** (placed by a prior single add or a prior category
    sync) is **skipped entirely** — its existing files are not moved or duplicated.
  - The category's `in_library` and `added_at` fields in `vod_categories` continue to be set
    as they are today.

- **FR-3** `movie_strm_path()` and `episode_strm_path()` — each gain an optional
  `category_folder: str | None = None` parameter.
  - When `None`: path is `{output_dir}/Movies/…` or `{output_dir}/TV/…` (current behaviour).
  - When set: path is `{output_dir}/{category_folder}/Movies/…` or `{output_dir}/{category_folder}/TV/…`.

- **FR-4** `add_content()`, `_write_series_strm_files()`, `sync_item()`, and
  `add_or_sync_content()` each gain an optional `category_folder: str | None = None`,
  threaded through to path-building functions.

- **FR-5** Category route passes the sanitized category title as `category_folder` when calling
  `add_or_sync_content`. No schema change to `strm_files` is required — the path structure
  alone encodes which context placed the file.

- **FR-6** `DELETE /library/category/{category_id}` — **modified deletion scope**.
  - Computes the category folder prefix: `Path(output_dir) / sanitize(category["title"])`.
  - Queries `strm_files` for all rows belonging to content in this category, then filters to
    those whose `strm_path` starts with the category folder prefix.
  - Deletes those `.strm` files from disk and removes those rows from `strm_files`.
  - For each affected `content_id`: if no `strm_files` rows remain, clears its library flags
    (`in_library = 0`, `added_at = NULL`); otherwise leaves it in library.
  - Single-add files (under `{output_dir}/Movies/…` or `{output_dir}/TV/…`) never match the
    category prefix and are therefore never deleted by this operation.
  - Clears the category's own library flags in `vod_categories`.

- **FR-7** `DELETE /library/content/{content_id}` — **unchanged**.
  - Deletes **all** `strm_files` rows for that content (across all category folders) and all
    corresponding disk files. This is the same as the current behaviour.

---

## Non-Functional Requirements

- **NFR-1** No new external Python dependencies and no schema migrations required.
- **NFR-2** Category fan-out continues to run in a background task; the HTTP response must not block.
- **NFR-3** Sanitization of the category title uses the existing `sanitize()` function — no new
  character-escaping logic is introduced.

---

## Out of Scope

- Moving existing strm files when a category is re-synced (files written before this feature are
  left in place; new content in the category will go to the category folder going forward).
- Any schema changes to `strm_files` (no new columns needed).
- Supporting multiple category folders for the same content item (first-wins is the rule).
- Any changes to `POST /library/sync` (sync-all) behaviour.
- Any changes to `GET /library` or `GET /library/categories` response shapes.

---

## Assumptions

- Content that is already in the library when a category sync runs is always skipped, regardless
  of whether it was placed by a single add or a different category sync. "Already in library"
  means `vod_content.in_library = 1`.
- The sanitized category title is stable enough to use as a folder name. If the portal renames a
  category, existing files stay in the old-named folder; this is not addressed here.
- `strm_files.strm_path` remains `UNIQUE`. Since the same episode is never written to two
  locations (first-wins skips), no UNIQUE violation can occur.

---

## Tech Stack

Python 3.11, FastAPI, SQLite (via `sqlite3`), no new dependencies.

---

## Commands

```
Test:  pytest tests/ -q
Lint:  ruff check server/ tests/
Dev:   uvicorn server.main:app --reload
```

---

## Project Structure

```
server/
  sync.py           ← path-building and sync helpers (modified)
  db.py             ← migration + add_strm_file + new delete helpers (modified)
  routes/
    library.py      ← category route passes category context (modified)
tests/
  test_library_sync.py   ← path function tests + category sync tests (extended)
  test_library_db.py     ← migration + add_strm_file + delete helper tests (extended)
  test_library_routes.py ← category delete scoped-removal tests (extended)
docs/
  library.md        ← updated folder layout documentation
spec/
  010-category-content-folders/   ← this spec
```

---

## Code Style

Match existing patterns exactly. Path functions stay pure (no DB, no I/O):

```python
def movie_strm_path(
    output_dir: str, name: str, year: str, category_folder: str | None = None
) -> Path:
    s = sanitize(name)
    folder = f"{s} ({year})"
    base = Path(output_dir) / category_folder if category_folder else Path(output_dir)
    return base / "Movies" / folder / f"{folder}.strm"
```

Sync helpers stay thin — validate, compute path, delegate to `write_strm` and `add_strm_file`:

```python
def add_content(
    db, vod, output_dir, server_base, content_id,
    delay_s=0, category_folder=None, category_id=None,
) -> int:
    ...
```

Route handlers stay thin — look up category title, sanitize, enqueue:

```python
@router.post("/library/category/{category_id}", status_code=202)
async def upsert_library_category(category_id: str, request: Request):
    ...
    cat = get_category(db, category_id)
    folder = sanitize(cat["title"])
    async def _sync_category():
        for content_id in content_ids:
            await asyncio.to_thread(
                add_or_sync_content,
                db, vod, settings.strm_output_dir, settings.strm_server_base_url,
                content_id, settings.vod_sync_request_delay_ms / 1000,
                folder,
            )
    asyncio.create_task(_sync_category())
```

---

## Testing Strategy

- **Framework:** pytest; `TestClient` (FastAPI) for route tests; plain pytest for unit tests.
- **Path function tests** (`test_library_sync.py`): assert exact `Path` values with and without
  `category_folder`.
- **Sync integration tests** (`test_library_sync.py`): category sync writes files under the
  category subfolder; single add writes files under root; already-in-library content is skipped.
- **DB tests** (`test_library_db.py`): new deletion helper filters by path prefix, returns
  correct paths, and cleans up library flags correctly.
- **Route tests** (`test_library_routes.py`): `DELETE /library/category/{id}` removes only
  that category's files; content with only category files is removed from library; content
  with additional files (hypothetically) remains.
- Every new code path reachable from a public function must have at least one test.

---

## Boundaries

- **Always:** run `pytest tests/ -q` before committing; keep path functions pure (no I/O, no DB).
- **Ask first:** any schema changes to `strm_files` or other tables.
- **Never:** move or delete strm files that belong to a different category or single-add context
  when processing a category deletion; add new Python dependencies.

---

## Success Criteria

1. `POST /library/category/{id}` for a category titled "Action" writes movie files under
   `{STRM_OUTPUT_DIR}/Action/Movies/…` and series files under `{STRM_OUTPUT_DIR}/Action/TV/…`.
2. `POST /library/content/{id}` (single add) continues to write under
   `{STRM_OUTPUT_DIR}/Movies/…` or `{STRM_OUTPUT_DIR}/TV/…` — no subfolder.
3. If content is already `in_library = 1`, a subsequent category sync does not write any new
   `.strm` files for it and does not change its existing file paths.
4. `DELETE /library/category/{id}` deletes only `.strm` files (disk + DB rows) whose path
   starts with `{STRM_OUTPUT_DIR}/{sanitized_category_title}/`.
5. After a category delete, a content item whose only strm files were in that category folder
   has `in_library = 0` and no remaining `strm_files` rows.
6. After a category delete, a content item that also has a single-add strm file (under root
   `Movies/` or `TV/`) remains `in_library = 1` and its single-add file is untouched.
7. `DELETE /library/content/{id}` still removes all strm files for that content (unchanged).
8. No changes to the `strm_files` schema — no new columns or migrations.
9. `pytest tests/ -q` exits 0 with no failures.

---

## Open Questions

None — all design decisions resolved prior to spec.
