# Spec: Episode Quality Levels

## Objective

Expose the fourth navigation level of the Stalker Portal VOD hierarchy: quality/language
file variants per episode. Currently the app calls `create_link` with an episode's default
`cmd`, which picks whichever quality the portal happens to assign. Many portals store the
same episode at multiple quality levels (e.g. SD 480p, HD 1080p) and expose them via a
deeper `get_ordered_list` call. This feature surfaces those variants so callers can choose
before streaming.

Users are developers querying the REST API from media frontends or home-automation scripts.
Success looks like: a caller can list quality variants for an episode and redirect to the
stream for a specific quality without guessing at internal portal `cmd` values.

## User Stories

- As a developer, I want to list quality variants for a series episode so that I can
  present a quality picker to the end user.
- As a developer, I want to stream a specific quality variant by its ID so that I do not
  need to pass raw portal `cmd` values in my request.

## Functional Requirements

- FR-1: `GET /vod/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files`
  returns a JSON array of file objects for the given episode.
- FR-2: Each file object contains `id` (string), `name` (string, e.g.
  `"English / HD (1080p)"`), and `cmd` (string, e.g. `"/media/file_1.mpg"`).
- FR-3: If the portal returns no files, the endpoint returns an empty array `[]`
  (not a 404).
- FR-4: `GET /vod/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files/{file_id}/stream`
  resolves the file's `cmd` to a playable URL via `create_link` and returns HTTP 302.
- FR-5: If `file_id` does not match any file returned by the portal, the endpoint
  returns HTTP 404.
- FR-6: If `create_link` returns an error for the resolved `cmd`, the endpoint
  returns HTTP 502.
- FR-7: The underlying portal call uses `type=vod`, `action=get_ordered_list` with
  `movie_id`, `season_id`, and `episode_id` all set (non-zero), which triggers the
  portal's `getFilesList` branch.

## Non-Functional Requirements

- NFR-1: No new Python dependencies introduced.
- NFR-2: New code follows existing patterns in `stb_reader/vod.py` and
  `server/routes/vod.py` (dataclasses for models, `responses` library for tests).

## Out of Scope

- Quality variants for standalone movies (non-series content).
- Caching file lists locally.
- Automatically selecting a default quality when only one file is returned.
- Surfacing the `quality`, `languages`, or `protocol` fields as separate response fields
  (they are already embedded in `name` by the portal).

## Assumptions

- `file_id` corresponds to the `id` field in each file object returned by the portal.
- The stream endpoint 302-redirects to the resolved URL (consistent with
  `GET /vod/content/{id}/stream`), not a streaming proxy.
- Quality variants exist only for series episodes navigated via `movie_id + season_id +
  episode_id`; the branching is server-side in the portal's `getOrderedList()`.

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
  models.py          → dataclasses (add EpisodeFile here)
  vod.py             → VODService (add get_episode_files here)
server/
  routes/vod.py      → FastAPI routes (add two new routes here)
tests/
  test_vod.py        → unit tests for VODService
  test_server.py     → integration tests for routes
docs/
  vod-series.md      → protocol documentation (add new section)
spec/003-episode-quality-levels/
  003-episode-quality-levels-requirements.md  ← this file
  003-episode-quality-levels-plan.md
  003-episode-quality-levels-implement.md
```

## Code Style

Follow existing conventions in `stb_reader/models.py` and `stb_reader/vod.py`:

```python
# models.py — plain dataclass, no defaults unless necessary
@dataclass
class EpisodeFile:
    id: str
    name: str
    cmd: str

# vod.py — raw portal dict → dataclass, str() cast on ids
def get_episode_files(self, series_id: str, season_id: str, episode_id: str) -> list[EpisodeFile]:
    raw = self._s.get(
        "vod",
        "get_ordered_list",
        movie_id=series_id,
        season_id=season_id,
        episode_id=episode_id,
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

Framework: `pytest` with `responses` library for mocking HTTP to the portal.
Test locations: `tests/test_vod.py` (unit), `tests/test_server.py` (route integration).

Coverage expectations:
- Every new service method has at least one happy-path test and one edge-case test.
- Every new route has: success (200/302), not-found (404), and stream-error (502) tests.
- Use `responses_lib.activate` decorator + `responses_lib.add(...)` matching the portal URL.

## Boundaries

- **Always:** Run `pytest tests/` before committing; keep new code consistent with existing style.
- **Ask first:** Adding new dependencies; changing the URL shape of existing endpoints;
  altering how `open_episode_stream` or `get_stream_url` behave.
- **Never:** Remove or modify existing tests; expose raw portal `cmd` values as URL path
  segments (they may contain slashes); commit secrets.

## Success Criteria

- `GET /vod/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files` returns a
  JSON array where each item has `id`, `name`, and `cmd`.
- `GET /vod/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files/{file_id}/stream`
  returns HTTP 302 to a playable stream URL when `file_id` exists.
- Returns HTTP 404 when `file_id` is not found in the portal's file list.
- Returns HTTP 502 when `create_link` returns an error for the resolved `cmd`.
- `pytest tests/` passes with no regressions.
- `docs/vod-series.md` has a new "Get Ordered List — Files" section documenting the
  portal request/response for this level.
