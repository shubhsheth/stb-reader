# Plan: Filter Adult Categories

## Summary

Remove categories containing the words "adult" or "18+" (case-insensitive) when categories are fetched from the STB portal.

## Research Findings

- **Fetch point**: `stb_reader/vod.py:get_categories()` (lines 16–26) — constructs `Category` objects from the portal API response
- **Category model**: `stb_reader/models.py` — `Category(id, title, alias, censored)`; the `title` field is what should be checked
- **Sync flow**: `server/vod_sync.py` calls `vod.get_categories()` and upserts results into SQLite; filtering here prevents adult categories from ever entering the DB
- **Existing tests**: `tests/test_vod.py` covers `get_categories`

## Tasks

| # | Task | File(s) | Size | Verify |
|---|------|---------|------|--------|
| 1 | Add filter in `get_categories()` to exclude categories whose `title` contains "adult" or "18+" (case-insensitive) | `stb_reader/vod.py` | XS | Unit test |
| 2 | Add/update tests covering the filter | `tests/test_vod.py` | XS | `pytest tests/test_vod.py` |

## Dependencies

Task 2 depends on Task 1 (tests the implementation).

## Success Criteria

- `get_categories()` never returns a `Category` whose `title` matches `/adult|18\+/i`
- Existing tests still pass
- New tests confirm filtered-out and kept-in cases
