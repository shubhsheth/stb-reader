# Spec: Screenshot Support (008)

## Objective

Expose the `screenshot_uri` field — already stored in `vod_content` — via a dedicated API endpoint, and display the thumbnail in the search results UI. Users browsing search results will see poster artwork alongside each title.

## User Stories

- As a user, I want to see poster artwork for each search result so I can visually identify content faster.

## Functional Requirements

- FR-1: `GET /vod/content/{content_id}/screenshot` returns a `302` redirect to the `screenshot_uri` stored in the database for that content item.
- FR-2: The endpoint returns `404` when the `content_id` does not exist.
- FR-3: The endpoint returns `404` when `screenshot_uri` is empty or null.
- FR-4: The search results table displays a thumbnail image in the first column, sourced from the screenshot endpoint.
- FR-5: Rows whose screenshot endpoint returns a non-2xx response (broken/missing URI) display no broken-image icon — the `<img>` hides itself.

## Non-Functional Requirements

- NFR-1: The endpoint adds no latency to the portal or database beyond a single SQLite row lookup.
- NFR-2: The UI must not break if the screenshot endpoint is unavailable or slow.

## Out of Scope

- Caching or proxying screenshot image bytes (we redirect, we don't fetch).
- Uploading or editing screenshots.
- Screenshots for live TV channels or episodes.

## Assumptions

- `screenshot_uri` values are absolute HTTP(S) URLs that browsers can load directly after a redirect.
- No authentication is required to fetch screenshot images from the portal.

## Tech Stack

Python 3.11, FastAPI, SQLite (via `server/db.py`), vanilla JS/HTML frontend.

## Commands

```
Test:  pytest tests/
Run:   uvicorn server.main:app --reload
```

## Project Structure

```
server/routes/vod.py         → new endpoint added here
server/static/index.html     → UI thumbnail column
tests/test_server.py         → new TestScreenshot class
spec/008-screenshot-support/ → this spec
```

## Code Style

Match existing route style — plain `def`, `Request` as last arg, `HTTPException` for errors:

```python
@router.get("/content/{content_id}/screenshot")
def get_content_screenshot(content_id: str, request: Request):
    row = get_vod_content(request.app.state.db, content_id)
    if not row or not row.get("screenshot_uri"):
        raise HTTPException(status_code=404, detail="No screenshot available")
    return RedirectResponse(url=row["screenshot_uri"], status_code=302)
```

## Testing Strategy

pytest with FastAPI `TestClient`. Tests seed the in-memory DB directly, then hit the endpoint. Three cases: redirect success, 404 on missing content, 404 on empty URI.

## Boundaries

- Always: run `pytest tests/` before committing.
- Ask first: schema migrations, new dependencies.
- Never: proxy or cache image bytes, add auth to the screenshot endpoint.

## Success Criteria

- `GET /vod/content/{id}/screenshot` returns `302` with correct `Location` header when `screenshot_uri` is set.
- Returns `404` when content is not found or `screenshot_uri` is empty.
- Search results table shows a thumbnail column; missing screenshots produce no broken-image icon.
- Full test suite passes.
