# Spec: VOD Movie Stream Link — Direct File Navigation

## Objective

Replace the looping `GET /vod/content/{content_id}/stream` endpoint for standalone movies
with a direct-navigation URL that mirrors the series pattern. The current implementation
calls `get_stream_url_by_content_id`, which paginates through **all** portal content pages
until it finds the matching item — O(n) portal requests per stream. The goal is O(1): encode
all IDs needed for a single targeted portal call into the URL path, exactly as series episodes
already do.

Users are developers querying the REST API from media frontends or home-automation scripts.
Success looks like: a caller can list file variants for a movie and stream one by ID without
triggering a full content scan.

## User Stories

- As a developer, I want to list quality/file variants for a standalone movie so that I can
  present a quality picker without triggering a full content-page scan.
- As a developer, I want to stream a specific movie file by its ID so that the server makes
  exactly one portal API call to resolve the stream URL.

## Functional Requirements

- FR-1: `GET /vod/content/{content_id}/files` returns a JSON array of file objects for a
  standalone movie (is_series=0), using a direct portal call (no full content scan).
- FR-2: Each file object contains `id` (string), `name` (string), and `cmd` (string) —
  identical shape to episode file objects from spec 003.
- FR-3: If the portal returns no files, the endpoint returns an empty array `[]` (not 404).
- FR-4: `GET /vod/content/{content_id}/files/{file_id}/stream` resolves the file's `cmd` to
  a playable URL via `create_link` and returns HTTP 302.
- FR-5: If `file_id` does not match any file returned by the portal, the endpoint returns
  HTTP 404.
- FR-6: If `create_link` returns an error, the endpoint returns HTTP 502.
- FR-7: The underlying portal call for FR-1/FR-4 must not iterate content pages; it must use
  `get_ordered_list` with `movie_id` set to the content ID to retrieve files directly.

## Non-Functional Requirements

- NFR-1: No new Python dependencies.
- NFR-2: New code follows existing patterns in `stb_reader/vod.py` and `server/routes/vod.py`.
- NFR-3: Existing `GET /vod/content/{content_id}/stream` endpoint is removed once the new
  route is in place (it is the only caller of `get_stream_url_by_content_id`).

## Out of Scope

- Migrating callers outside this repo to use the new URL shape (that is a client concern).
- Caching movie file lists.
- Automatically selecting a default quality when only one file is returned.
- Changing how series episodes are streamed (spec 003 already handles that path).

## Assumptions

- A1: The portal supports `get_ordered_list` with `movie_id=content_id` (and appropriate
  `season_id`/`episode_id` values) to retrieve file variants for a standalone movie in one
  request — **[NEEDS CLARIFICATION: what exact `season_id` / `episode_id` values does the
  portal expect for a movie? e.g. both `0`, or both equal to `content_id`, or something
  else?]**
- A2: Movie files returned by this call have the same `id`, `name`, `cmd` shape as episode
  files from spec 003.
- A3: The `category_id` query parameter in the old movie stream URL was never used by the
  portal call and can be dropped.
- A4: `file_id` corresponds to the `id` field in each file object.
- A5: The new stream endpoint 302-redirects (consistent with all other stream routes); no
  streaming proxy.

## Tech Stack

Python 3.11+, FastAPI, `requests`, `pytest` + `responses` (mocking), `httpx` (test client).

## Commands

```
Test:  pytest tests/
Lint:  (no linter configured — match existing code style)
Dev:   uvicorn server.main:app --reload
```

## Project Structure

```
stb_reader/
  vod.py             → VODService: add get_movie_files(); remove get_stream_url_by_content_id()
server/
  routes/vod.py      → add /content/{id}/files and /content/{id}/files/{fid}/stream;
                       remove /content/{id}/stream
tests/
  test_vod.py        → unit tests for new service method; remove old looping-method tests
  test_server.py     → route integration tests for new endpoints
docs/
  vod-series.md      → add "Movie Files" section documenting the portal call
spec/004-vod-movie-stream-link/
  004-vod-movie-stream-link-requirements.md  ← this file
  004-vod-movie-stream-link-plan.md
  004-vod-movie-stream-link-implement.md
```

## Code Style

Follow existing conventions in `stb_reader/vod.py`:

```python
# New service method — same shape as get_episode_files, minus season/episode params
def get_movie_files(self, content_id: str) -> list[EpisodeFile]:
    raw = self._s.get(
        "vod",
        "get_ordered_list",
        movie_id=content_id,
        season_id=???,    # see A1 — to be confirmed
        episode_id=???,   # see A1 — to be confirmed
    )
    return [
        EpisodeFile(
            id=str(f["id"]),
            name=f.get("name", ""),
            cmd=f.get("cmd", ""),
        )
        for f in raw.get("data", [])
    ]
```

## Testing Strategy

Framework: `pytest` with `responses` library for portal HTTP mocking.
- `tests/test_vod.py`: unit tests for `get_movie_files()` (happy path + empty list).
- `tests/test_server.py`: route tests for `/files` (200) and `/files/{id}/stream`
  (302 success, 404 not found, 502 stream error).
- Use `responses_lib.activate` + `responses_lib.add(...)` as in existing tests.

## Boundaries

- **Always:** Run `pytest tests/` before committing; keep new code consistent with existing style.
- **Ask first:** Changing the URL shape of existing series endpoints; adding dependencies.
- **Never:** Expose raw portal `cmd` values as URL path segments; commit secrets; delete
  passing tests without replacing them.

## Success Criteria

- `GET /vod/content/{content_id}/files` returns a JSON array with `id`, `name`, `cmd` per item.
- `GET /vod/content/{content_id}/files/{file_id}/stream` returns HTTP 302 to a playable URL.
- Returns HTTP 404 when `file_id` is not in the portal's file list.
- Returns HTTP 502 when `create_link` returns an error.
- `pytest tests/` passes with no regressions.
- The old `GET /vod/content/{content_id}/stream` route no longer exists.
- `docs/vod-series.md` has a new "Movie Files" section describing the portal call.

## Open Questions

| # | Question | Options | Implication if left open |
|---|----------|---------|--------------------------|
| 1 | What `season_id` / `episode_id` values does the portal expect in `get_ordered_list` to return files for a standalone movie? | Both `0`; both equal to `content_id`; `season_id=0, episode_id=content_id`; other | Wrong values → portal returns seasons list or empty data instead of files; whole feature breaks |
