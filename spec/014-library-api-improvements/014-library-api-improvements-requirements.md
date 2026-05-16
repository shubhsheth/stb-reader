# Spec 014: Library API Improvements

## Objective

Improve the `stb-reader` Python library by fixing bugs found through holistic review
against source STB portal implementations, removing API surface that shouldn't exist
in a library, adding missing functionality confirmed by multiple sources, and making
the API consistent and composable.

The user is a Python developer building applications on top of Stalker/Ministra STB
portals. Success means: bugs are gone, the public API is smaller and more predictable,
and the library works correctly against stricter portals that check device parameters.

---

## User Stories

- As a developer, I want `get_episodes()` to reliably return all episodes across
  paginated portals so that I don't silently miss episodes.
- As a developer, I want `get_categories()` to return all categories so that I can
  apply my own filtering policy.
- As a developer, I want a single `get_stream_url(cmd)` per service so that I know
  exactly how to get a playable URL regardless of content type.
- As a developer, I want `get_all_channels()` so that I can fetch the full channel
  list in one call on portals that support it.
- As a developer, I want `Channel.xmltv_id` so that I can correlate channels with
  EPG data from external sources.
- As a developer targeting strict portals, I want the library to send correct device
  parameters in `get_profile()` so that authentication succeeds.

---

## Functional Requirements

### Bugs
- **FR-1** `get_episodes()` pagination uses count-based termination (`seen >= total`)
  instead of page-math (`page * per_page >= total`), consistent with the fix already
  applied to `get_stream_url_by_id`.

### Removals
- **FR-2** `get_stream_url_by_content_id()` is removed from `VODService`.
- **FR-3** `get_categories()` returns all categories without any content filtering;
  the `censored` field on `Category` is the mechanism callers use to filter.
- **FR-4** All convenience stream methods are removed:
  - `ITVService.get_stream_url_by_id()`
  - `VODService.get_stream_url_by_file_id()`
  - `VODService.get_stream_url_by_first_file()`
  Only `get_stream_url(cmd: str) -> str` remains on each service.

### Correctness
- **FR-5** `get_profile()` sends device identification parameters derived from the
  session's `serial` and `mac`:
  - `device_id = SHA256(serial).hexdigest()`
  - `device_id2 = SHA256(mac).hexdigest()`
  - `signature = SHA256((serial + mac).encode()).hexdigest()`
- **FR-6** `session.signature` attribute is removed from `STBSession`; it was set in
  `handshake()` but never read anywhere.
- **FR-7** If `get_profile()` returns a non-empty `token` field, it is applied to
  `session.token` (some portals issue a refreshed token in the profile response).

### Additions
- **FR-8** `ITVService.get_all_channels() -> list[Channel]` wraps the portal's
  `get_all_channels` action (a single API call the portal assembles server-side)
  and returns the result as `list[Channel]`. No client-side loop or pagination.
- **FR-9** `Channel` model gains a `xmltv_id: str` field (default `""`). Both
  `get_channels()` and `get_all_channels()` populate it from the response.
- **FR-10** `_clean_url()` is moved from `live_tv.py` to `_http.py`. `vod.py` and
  `live_tv.py` import it from there.

### Roadmap (out of scope for this spec)
- Allow callers to configure which response fields are mapped onto `Content` and
  `Channel` objects (e.g. via field-include sets on `STBClient`). This would replace
  ad-hoc model expansion for fields like `rating_kinopoisk`, `director`, `actors`,
  `tmdb_id`, `hd` that are present on some portals and absent on others.

---

## Non-Functional Requirements

- **NFR-1** No new runtime dependencies are introduced.
- **NFR-2** All existing tests continue to pass after each task.
- **NFR-3** No public symbol that was part of the original `__init__.py` exports is
  silently left broken — removals are clean (no dangling imports).
- **NFR-4** The `Channel` model change (`xmltv_id`) uses a default value so existing
  code constructing `Channel` objects (e.g. in tests) does not break.

---

## Out of Scope

- EPG / program guide support (`get_epg_info`) — confirmed gap but separate feature.
- Concurrent / parallel page fetching — the library is sequential; callers own loops.
- Portal path auto-detection (trying multiple portal path variants) — separate concern.
- Any change to the `PagedResult` model or pagination API for callers.
- Changes to `get_seasons()` or `get_episode_files()` beyond what FR-1 touches.
- Expanded `Content` model fields (`rating_kinopoisk`, `director`, `actors`, `tmdb_id`,
  `hd`) — deferred to the field-configuration roadmap item above.

---

## Assumptions

- The `serial` passed by the caller to `STBClient` is the actual device serial, not
  derived from the MAC. Device IDs are computed from it as-is.
- The `get_all_channels` action returns channel objects with the same fields as
  `get_ordered_list` (id, number, name, cmd, logo, tv_genre_id, hd, censored,
  xmltv_id). If a field is absent the parser defaults gracefully.
- Removing convenience stream methods is not a breaking change that needs a deprecation
  cycle — the library is pre-1.0 (version 0.1.0).
- `ADULT_TERMS` regex removal does not need a `censored` filter to replace it in
  `get_categories()` — callers decide their own policy.

---

## Tech Stack

- Python 3.11+
- `requests` (only runtime dependency)
- `pytest` + `responses` for tests
- `uv` for environment / dependency management

## Commands

```
Test:  uv run --extra test pytest tests/ -v
Lint:  (none configured — match existing code style)
```

---

## Project Structure

```
stb_reader/
  __init__.py       — public exports
  client.py         — STBClient
  auth.py           — handshake(), get_profile()
  _http.py          — STBSession, _clean_url (moving here)
  models.py         — dataclasses
  live_tv.py        — ITVService
  vod.py            — VODService
  exceptions.py     — exception hierarchy

tests/
  test_auth.py
  test_http.py
  test_live_tv.py
  test_vod.py

spec/014-library-api-improvements/
  014-library-api-improvements-requirements.md  ← this file
  014-library-api-improvements-plan.md
  014-library-api-improvements-implement.md
```

---

## Code Style

Match the existing codebase exactly. Key conventions:

```python
# Dataclass fields — positional, no defaults except for new additive fields
@dataclass
class Channel:
    id: str
    name: str
    xmltv_id: str = ""   # new additive field — default so existing constructors don't break

# Service methods — keyword args with defaults, type-annotated
def get_all_channels(self) -> list[Channel]:
    raw = self._s.get("itv", "get_all_channels")
    return [Channel(...) for c in _as_list(raw)]

# Imports — stdlib then internal; TYPE_CHECKING guard for session
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ._http import STBSession
```

No comments unless the why is non-obvious. No docstrings.

---

## Testing Strategy

- Framework: `pytest` with `responses` for HTTP mocking
- Tests live in `tests/`, one file per module
- Each functional requirement must have at least one test
- Removals: delete tests for removed methods; do not leave orphan test functions
- Additions: new methods get at least one happy-path test with a mocked response
- Bug fixes: add a regression test that would have caught the bug (multi-page episode
  test for FR-1)
- Run full suite after every task: `uv run --extra test pytest tests/ -v`

---

## Boundaries

- **Always:** Run full test suite after each task before moving to the next.
- **Always:** Update `__init__.py` exports to match — nothing exported that no longer
  exists, nothing new that should be public left unexported.
- **Ask first:** Any change to `PagedResult` or the public pagination API.
- **Ask first:** Adding a new runtime dependency.
- **Never:** Change the `portal_path`, `base_url`, `mac`, `serial`, `lang`, `timezone`
  parameters on `STBClient.__init__` — these are the stable public interface.
- **Never:** Remove `get_stream_url(cmd)` from either service.

---

## Success Criteria

- All 9 functional requirements (FR-1 through FR-10) have passing tests.
- `uv run --extra test pytest tests/ -v` passes with zero failures.
- `get_categories()` returns categories including those with `censored=True`.
- `get_episodes()` with a two-page mocked response returns episodes from both pages.
- `get_profile()` request includes `device_id`, `device_id2`, and `signature` params.
- `get_all_channels()` returns a `list[Channel]` from a single API call (no loop).
- `Channel` objects have a `xmltv_id` attribute.
- `_clean_url` is importable from `stb_reader._http`.
- No import of `_clean_url` from `live_tv` remains in `vod.py`.
- None of the removed methods appear anywhere in `stb_reader/`.
