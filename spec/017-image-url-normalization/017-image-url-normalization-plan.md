# 017 — Image URL Normalization: Planning & Task Breakdown

## Problem

Stalker portals return `logo` (Channel) and `screenshot_uri` (Content) as either:
- Absolute URLs: `http://portal.example.com/logos/bbc1.png` ✓
- Relative paths: `/stalker_portal/screenshots/c1.jpg` ✗ (unusable by consumers)

The library currently passes these through unchanged. Consumers receive broken relative paths with no way to resolve them since they don't have access to the internal `base_url`.

Evidence: commit `c674bd7` shows a now-deleted server route that patched this at response time. That workaround is gone; the fix belongs in the library.

---

## Scope Assessment

**XS change** — touches 3 files (1 helper + 2 service files), plus 2 test files. No new abstractions, no API changes, no model changes.

Per the guide, this qualifies as a "single-file change with obvious scope" (slightly expanded to 3 files). Task breakdown is straightforward.

---

## Dependency Map

```
Task 1: Add _resolve_image_url helper in _http.py
    └── Task 2: Apply in live_tv.py (logo)
    └── Task 3: Apply in vod.py (screenshot_uri)
            └── Task 4: Tests (unit + integration)
```

Tasks 2 and 3 can run in parallel after Task 1.

---

## Tasks

### Task 1 — Add `_resolve_image_url` helper (XS)
**File:** `stb_reader/_http.py`

Add alongside `_clean_url`:
```python
def _resolve_image_url(base_url: str, raw: str) -> str:
    if not raw or raw.startswith(("http://", "https://")):
        return raw
    from urllib.parse import urljoin
    return urljoin(base_url.rstrip("/") + "/", raw.lstrip("/"))
```

Note: `urllib.parse` is already imported at the top of `_http.py`.

**Acceptance criteria:**
- `_resolve_image_url("http://p.example.com", "/logo.png")` → `"http://p.example.com/logo.png"`
- `_resolve_image_url("http://p.example.com", "http://cdn.com/logo.png")` → `"http://cdn.com/logo.png"`
- `_resolve_image_url("http://p.example.com", "")` → `""`

**Verify:** Unit test the helper directly.

---

### Task 2 — Apply to `logo` in `live_tv.py` (XS)
**File:** `stb_reader/live_tv.py`

- Import `_resolve_image_url` on line 6 (alongside existing `_as_list, _clean_url`)
- In `get_channels()` (line 50): `logo=_resolve_image_url(self._s.base_url, c.get("logo", ""))`
- In `get_all_channels()` (line 73): same change

**Acceptance criteria:**
- Relative logo URL → absolute
- Absolute logo URL → unchanged
- Missing logo → empty string

---

### Task 3 — Apply to `screenshot_uri` in `vod.py` (XS)
**File:** `stb_reader/vod.py`

- Import `_resolve_image_url` on line 6 (alongside existing `_as_list, _clean_url`)
- In `get_content()` (line 49): `screenshot_uri=_resolve_image_url(self._s.base_url, c.get("screenshot_uri", ""))`

**Acceptance criteria:** Same three cases as Task 2 but for VOD content.

---

### Task 4 — Tests (S)
**Files:** `tests/test_live_tv.py`, `tests/test_vod.py`

Add test cases covering:
1. Relative path → resolved absolute URL (using a mock `base_url`)
2. Already-absolute URL → unchanged
3. Empty string → empty string

**Acceptance criteria:** `pytest tests/` passes with all new tests green.

---

## Verification (End-to-End)

```bash
pytest tests/ -v
```

All existing tests pass. New tests cover the three URL forms for both `logo` and `screenshot_uri`.

---

## Not In Scope

- Fetching image bytes (library stays URL-only)
- Caching or proxying images
- CLI display of images
- Handling `//protocol-relative` URLs (rare in practice; `urljoin` handles them correctly as a side effect)
