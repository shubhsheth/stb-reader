# Spec: Extensive user-facing documentation (013)

## Objective

Create comprehensive user-facing documentation for the `stb-reader` Python library.
The existing `docs/` files are STB *protocol* references written for contributors who
need to understand raw HTTP semantics. There is nothing that teaches a Python developer
how to install the library, configure `STBClient`, call methods, handle errors, or
iterate paginated results.

**User:** A Python developer who has installed `stb-reader` and wants to understand
how to use it — from a complete beginner who has never touched an STB portal, to an
advanced user who needs a precise method signature.

**Success looks like:** A developer can open `docs/guide/getting-started.md`, follow
the steps, and have working code talking to their portal in under 10 minutes. They can
then navigate to topic-specific guides without ever reading the source code.

---

## User Stories

- As a first-time user, I want a getting-started guide so I can install the library and make my first API call without reading source code.
- As a developer integrating live TV, I want a complete live-TV guide so I know every method, parameter, and return type available.
- As a developer integrating VOD, I want separate guides for movies and series so I understand the different navigation flows.
- As a developer, I want an error-handling guide so I know which exceptions to catch and when to retry.
- As a developer, I want a pagination guide so I know how to fetch all pages of a large result set efficiently.
- As a developer, I want a single API reference page so I can look up any method signature, parameter, or model field without grepping source.

---

## Functional Requirements

- **FR-1:** `docs/guide/getting-started.md` explains installation, all five `STBClient` constructor parameters with types and defaults, and includes a complete runnable example (authenticate + live-TV call + VOD call).
- **FR-2:** `docs/guide/authentication.md` explains `authenticate()`, the two-step handshake/profile flow, the auto-reauth mechanism (transparent retry on token expiry), and `AuthError` failure scenarios with example handling code.
- **FR-3:** `docs/guide/live-tv.md` documents every `live_tv` method with signature, all parameters, return type, and a code example. The `Genre` and `Channel` model fields are fully described. An end-to-end example (genres → channels → stream URL) is included.
- **FR-4:** `docs/guide/vod.md` documents the movie-focused `vod` methods with the same completeness as FR-3. `Category` and `Content` model fields are fully described. Shows how to filter movies vs series using `Content.is_series`.
- **FR-5:** `docs/guide/series.md` documents the full series navigation path: `get_content()` → `get_seasons()` → `get_episodes()` → `get_episode_files()` → stream URL. `Season`, `Episode`, and `EpisodeFile` model fields are fully described. Explains the choice between `get_stream_url_by_first_file()` and `get_stream_url_by_file_id()`. Includes a complete end-to-end code example.
- **FR-6:** `docs/guide/pagination.md` documents `PagedResult` (all four fields), shows a generic fetch-all-pages pattern, and notes guidance on request pacing.
- **FR-7:** `docs/guide/error-handling.md` documents all four exception classes (`STBError`, `AuthError`, `StreamError`, `NotFoundError`), the conditions under which each is raised, the exception hierarchy, and recommended handling patterns with code examples.
- **FR-8:** `docs/guide/api-reference.md` is a complete, exhaustive reference: every public method with full signature (parameter names, types, defaults, return type), every model dataclass with all field names and types, every exception with its inheritance. Nothing is omitted.
- **FR-9:** `README.md` gains a "Documentation" section linking to each of the seven guide files.
- **FR-10:** `docs/library.md` is deleted (stale server-era content).

---

## Non-Functional Requirements

- **NFR-1:** All code examples are syntactically valid Python 3.11.
- **NFR-2:** All method signatures and model fields in the docs match the actual source code exactly (no guessed parameters, no invented defaults).
- **NFR-3:** Every guide is self-contained — a reader should not need to jump to another guide to follow the examples in it, except for deliberately cross-linked advanced topics.
- **NFR-4:** Docs use consistent formatting: fenced code blocks with `python` syntax tag, parameter tables with columns `Parameter | Type | Default | Description`, and section headers that match the method or topic name exactly.

---

## Out of Scope

- Docs site generation (Sphinx, MkDocs, Read the Docs) — markdown files only.
- Changelog or release notes.
- Tutorial videos or diagrams.
- Documentation for internal/private modules (`_http.py`, `auth.py`).
- Coverage of the STB protocol itself — that stays in the existing `docs/` protocol reference files.

---

## Assumptions

- Documentation lives in `docs/guide/` as plain markdown, rendered on GitHub.
- The existing protocol reference files (`docs/authentication.md`, `docs/live-tv.md`, `docs/vod-series.md`, `docs/README.md`) are left untouched.
- Code examples use realistic but fictional portal URLs and MAC addresses (e.g. `http://portal.example.com`, `00:1A:79:XX:XX:XX`).
- The `delay_s` parameter on `get_episodes()` is documented but not prominently featured — it is an advanced rate-limiting concern.

---

## Tech Stack

- Plain GitHub-flavoured Markdown (`.md`)
- No build tooling required

---

## Commands

```
View rendered locally:  python -m http.server (then open browser)
Verify links exist:     find docs/guide/ -name "*.md" | sort
Check no stale refs:    grep -r "library.md" docs/ README.md
```

---

## Project Structure

```
docs/
  README.md             Protocol overview index (unchanged)
  authentication.md     STB auth protocol reference (unchanged)
  live-tv.md            STB live-TV protocol reference (unchanged)
  vod-series.md         STB VOD protocol reference (unchanged)
  library.md            DELETED — stale server docs

  guide/                NEW — user-facing library documentation
    getting-started.md  Install, configure, first call
    authentication.md   authenticate(), auto-reauth, AuthError
    live-tv.md          All live_tv methods, Genre/Channel models
    vod.md              Movie vod methods, Category/Content models
    series.md           Full series navigation flow
    pagination.md       PagedResult, fetch-all-pages pattern
    error-handling.md   All exceptions, handling patterns
    api-reference.md    Complete method/model/exception reference

README.md               Updated: adds "Documentation" section with links
```

---

## Code Style

All code examples follow this style:

```python
from stb_reader import STBClient, STBError, AuthError, StreamError

client = STBClient(
    base_url="http://portal.example.com",
    mac="00:1A:79:XX:XX:XX",
)
client.authenticate()

# Each example is complete and runnable from this point
genres = client.live_tv.get_genres()
for genre in genres:
    print(genre.id, genre.title)
```

Parameter tables use this format:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | required | Base URL of the STB portal |
| `mac` | `str` | required | Device MAC address |

Model field tables use this format:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique channel identifier |
| `name` | `str` | Display name |

---

## Testing Strategy

Documentation has no automated tests. Verification is manual:

- **Correctness:** Every method signature is cross-checked against the source files (`stb_reader/live_tv.py`, `stb_reader/vod.py`, `stb_reader/models.py`, `stb_reader/exceptions.py`) before writing.
- **Completeness:** After writing, grep the source for every `def ` and confirm each is present in `api-reference.md`.
- **Syntax:** Code examples are read carefully for validity; no execution required.

---

## Boundaries

- **Always:** Cross-check every signature against source before documenting it; use `python` language tag on all code blocks; keep guide files self-contained.
- **Ask first:** Adding a new guide file not in the plan; changing the structure of existing protocol reference files.
- **Never:** Document private methods (prefixed `_`); invent parameter names or defaults not present in source; leave stale references to `docs/library.md` after it is deleted.

---

## Success Criteria

1. `docs/guide/` contains exactly these 8 files: `getting-started.md`, `authentication.md`, `live-tv.md`, `vod.md`, `series.md`, `pagination.md`, `error-handling.md`, `api-reference.md`.
2. Every public method on `ITVService` and `VODService` appears in `api-reference.md` with its correct signature.
3. Every model dataclass field appears in `api-reference.md` with its correct type.
4. `docs/library.md` does not exist.
5. `README.md` contains a "Documentation" section with links to all 8 guide files.
6. `grep -r "library.md" docs/ README.md` returns no matches.
7. A developer unfamiliar with the library can follow `getting-started.md` and produce working code using only that file.
8. All code blocks in all guide files use the `python` syntax tag and are syntactically valid.
