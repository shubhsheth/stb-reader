# Spec: VOD Movie Stream Link — Direct cmd Construction

## Objective

Replace the looping `GET /vod/content/{content_id}/stream` implementation with a single
portal call. The current `get_stream_url_by_content_id` paginates through all portal content
pages to find a matching item and read its `cmd` — O(n) portal requests. The fix: the
portal's `cmd` for a standalone movie always follows the pattern `/media/{content_id}.mpg`,
so it can be constructed directly and passed to `create_link` in one call.

The URL shape does not change. Only the implementation changes.

## User Stories

- As a developer, I want `GET /vod/content/{content_id}/stream` to resolve the stream URL
  in a single portal request instead of scanning all content pages.

## Functional Requirements

- FR-1: `GET /vod/content/{content_id}/stream` continues to return HTTP 302 to a playable
  stream URL.
- FR-2: The implementation constructs the portal `cmd` as `/media/{content_id}.mpg` directly
  instead of iterating content pages.
- FR-3: If `create_link` returns an error, the endpoint returns HTTP 502.
- FR-4: The old paginating `get_stream_url_by_content_id` implementation is removed.

## Non-Functional Requirements

- NFR-1: No new Python dependencies.
- NFR-2: The number of portal HTTP requests for a movie stream drops from O(n pages) to 1.

## Out of Scope

- Changing the route URL shape.
- Handling movies whose `cmd` deviates from the `/media/{id}.mpg` pattern.
- Listing quality variants for movies (portal does not expose a files list for movies).

## Assumptions

- A1: All standalone movies use `/media/{content_id}.mpg` as their portal `cmd`. This is
  confirmed by the portal content listing and matches the existing fallback pattern in
  `get_stream_url_by_episode_id`.
- A2: The `category_id` query parameter in the old URL was never passed to the portal and
  can be dropped from consideration.

## Tech Stack

Python 3.11+, FastAPI, `requests`, `pytest` + `responses`, `httpx`.

## Commands

```
Test:  pytest tests/
Dev:   uvicorn server.main:app --reload
```

## Project Structure

```
stb_reader/
  vod.py          → replace get_stream_url_by_content_id body (one line)
tests/
  test_vod.py     → replace looping test with direct-cmd test
```

## Code Style

```python
# Before (loops all pages):
def get_stream_url_by_content_id(self, content_id: str) -> str:
    page = 1
    while True:
        ...

# After (single call):
def get_stream_url_by_content_id(self, content_id: str) -> str:
    return self.get_stream_url(f"/media/{content_id}.mpg")
```

## Testing Strategy

Replace the two existing `test_get_stream_url_by_content_id_*` tests with:
- One test: constructs cmd as `/media/{id}.mpg` and calls `create_link` once.
- One test: raises `StreamError` when `create_link` returns an error.

## Boundaries

- **Always:** Run `pytest tests/` before committing.
- **Never:** Expose raw `cmd` values in URL paths; delete passing tests without replacing them.

## Success Criteria

- `GET /vod/content/{content_id}/stream` returns HTTP 302 to a playable URL.
- Returns HTTP 502 when `create_link` returns an error.
- `pytest tests/` passes with no regressions.
- The implementation makes exactly one portal HTTP request (no page loop).

## Open Questions

None — all assumptions confirmed by user.
