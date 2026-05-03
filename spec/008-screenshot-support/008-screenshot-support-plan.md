# Plan: Screenshot Support (008)

## Components

1. **Backend endpoint** (`server/routes/vod.py`)
   - New route `GET /vod/content/{content_id}/screenshot`
   - Reuses `get_vod_content(db, content_id)` from `server/db.py:173`
   - Returns `RedirectResponse(302)` or `HTTPException(404)`
   - Import `get_vod_content` alongside existing DB imports

2. **UI thumbnail column** (`server/static/index.html`)
   - CSS: `.poster img { width: 56px; height: auto; border-radius: 2px; vertical-align: middle; }`
   - `renderResults`: prepend `<td class="poster"><img src="/vod/content/${id}/screenshot" alt="" onerror="this.style.display='none'"></td>`
   - `<thead>`: add blank `<th></th>` as first header

3. **Tests** (`tests/test_server.py`)
   - `TestScreenshot` class with three cases using in-memory DB seeded via `upsert_vod_content`

## Implementation Order

1. Backend endpoint (no UI dependency)
2. Tests (validates backend before touching UI)
3. UI (visual, verified manually)
4. Spec implement file + AGENTS.md

## Risks

- `screenshot_uri` may be a relative path on some portals → out of scope; we redirect whatever is stored.
- CORS on portal image servers → browser issue, not server issue; `onerror` hides the broken image.
