# Plan: Episode Quality Levels

## Implementation Order

Dependencies flow in one direction: model → service → route → docs/tests.

```
1. EpisodeFile model        (models.py)
2. get_episode_files()      (vod.py)
3. get_stream_url_by_file_id() (vod.py)
4. Two new routes           (server/routes/vod.py)
5. docs update              (docs/vod-series.md)
6. Tests                    (tests/test_vod.py, tests/test_server.py)
```

## Component Design

### Model — `EpisodeFile` (`stb_reader/models.py`)

```python
@dataclass
class EpisodeFile:
    id: str
    name: str
    cmd: str
```

Minimal: `name` already encodes quality + language (portal formats it as
`"English / HD (1080p)"`). No need for separate fields.

### Service — `VODService` (`stb_reader/vod.py`)

**`get_episode_files(series_id, season_id, episode_id) -> list[EpisodeFile]`**

Portal call: `type=vod, action=get_ordered_list, movie_id=series_id,
season_id=season_id, episode_id=episode_id` (all non-zero triggers `getFilesList`
branch server-side). Returns `raw["data"]` list.

**`get_stream_url_by_file_id(series_id, season_id, episode_id, file_id) -> str`**

Calls `get_episode_files(...)`, finds the item where `f.id == file_id`, then calls
the existing `get_stream_url(f.cmd)` which calls `create_link` and returns a clean URL.
Raises `STBError("file not found")` if no match.

### Routes — `server/routes/vod.py`

```
GET /vod/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files
```
Returns `list[dict]` — `vars()` of each `EpisodeFile`.

```
GET /vod/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files/{file_id}/stream
```
Calls `get_stream_url_by_file_id(...)`, returns `RedirectResponse(url, 302)`.
Error handling mirrors `GET /vod/content/{content_id}/stream`:
- `StreamError` → 502
- `STBError("not found")` → 404
- other `STBError` → 502

### Docs — `docs/vod-series.md`

New section inserted between "Get Ordered List — Episodes" and "Create Link".
Title: **Get Ordered List — Files (Quality Variants)**. Documents:
- Request params: same as episodes but with non-zero `episode_id`
- Response structure: `id`, `name`, `cmd` per item
- Note: if the list has one entry, quality selection UI can be skipped

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Portal always returns a single file (no real choice) | Spec says return `[]` on empty and the single item when there's only one — caller decides UI |
| `file_id` contains special chars | It's an integer string from the portal; safe as path segment |
| `cmd` could start with `?` (portal-relative) | `get_stream_url()` calls `create_link` which returns a full URL; the redirect target is always absolute |

## Tasks

- [ ] Task: Add `EpisodeFile` dataclass
  - Acceptance: `EpisodeFile(id="1", name="English / HD", cmd="/media/f.mpg")` constructs without error
  - Verify: `pytest tests/` passes
  - Files: `stb_reader/models.py`

- [ ] Task: Add `get_episode_files()` to `VODService`
  - Acceptance: sends `get_ordered_list` with `movie_id`, `season_id`, `episode_id` all set; parses `data` list into `EpisodeFile` objects; returns `[]` on empty `data`
  - Verify: `pytest tests/test_vod.py`
  - Files: `stb_reader/vod.py`

- [ ] Task: Add `get_stream_url_by_file_id()` to `VODService`
  - Acceptance: finds file by ID and returns clean stream URL; raises `STBError("file not found")` when ID missing
  - Verify: `pytest tests/test_vod.py`
  - Files: `stb_reader/vod.py`

- [ ] Task: Add two routes to `server/routes/vod.py`
  - Acceptance: files list route returns array; stream route 302-redirects; 404 on missing file_id; 502 on stream error
  - Verify: `pytest tests/test_server.py`
  - Files: `server/routes/vod.py`

- [ ] Task: Write tests
  - Acceptance: all new paths covered per Testing Strategy in requirements
  - Verify: `pytest tests/`
  - Files: `tests/test_vod.py`, `tests/test_server.py`

- [ ] Task: Update `docs/vod-series.md`
  - Acceptance: new "Get Ordered List — Files" section present with request params and response structure
  - Verify: read the file
  - Files: `docs/vod-series.md`
