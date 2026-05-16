# 013 — Extensive user-facing documentation

## Goal

Create comprehensive user-facing documentation for the `stb-reader` Python library.
The existing `docs/` files are STB *protocol* references (raw HTTP, query params,
JSON fields) — useful for contributors, not for library users. New docs explain the
**Python API**: how to install, configure, call methods, handle errors, and iterate pages.

---

## Current state

| File | Content |
|------|---------|
| `README.md` | Quick-start (install + 10-line example). Good entry point. |
| `docs/README.md` | Protocol overview index. Stays as-is. |
| `docs/authentication.md` | Raw STB auth protocol reference. Stays as-is. |
| `docs/live-tv.md` | Raw ITV protocol reference. Stays as-is. |
| `docs/vod-series.md` | Raw VOD protocol reference. Stays as-is. |
| `docs/library.md` | Old server library docs. **Delete** — server is gone. |

No user-facing library documentation exists today.

---

## Target structure

New files live under `docs/guide/` to keep them separate from protocol references:

```
docs/guide/
  getting-started.md   Installation, configuration, first call
  authentication.md    How authenticate() works, token lifecycle, re-auth
  live-tv.md           Genres → channels → stream URL, full examples
  vod.md               Categories → movies → stream URL, full examples
  series.md            Categories → content → seasons → episodes → files → stream
  pagination.md        PagedResult, iterating all pages, lazy patterns
  error-handling.md    All exceptions, handling patterns, retry guidance
  api-reference.md     Complete reference: STBClient, services, models, exceptions
```

`README.md` will be updated to add a "Documentation" section linking to `docs/guide/`.

---

## Tasks

### Task 1 — `docs/guide/getting-started.md`
**Scope: S**

Cover: requirements, `pip install stb-reader`, minimal working example (authenticate + one live-TV call + one VOD call), common `STBClient` parameter values and where to find them.

Acceptance criteria:
- A user with no prior knowledge can copy-paste the example and get data
- All five `STBClient` constructor parameters are explained
- Verify: at least one runnable code block is present

---

### Task 2 — `docs/guide/authentication.md`
**Scope: S**

Cover: what `authenticate()` does (handshake → get_profile), when to call it (once at startup), the auto-reauth mechanism (transparent on token expiry), `AuthError` scenarios (bad MAC, expired subscription), manual re-auth pattern.

Acceptance criteria:
- Explains why `authenticate()` must be called before any other method
- Shows the auto-reauth behaviour and when it can still fail
- Includes a code example for catching `AuthError`

---

### Task 3 — `docs/guide/live-tv.md`
**Scope: S**

Cover: `get_genres()`, `get_channels()` with all parameters, iterating all channels across pages, `get_stream_url()`, `get_stream_url_by_id()`. Include a realistic end-to-end example: list genres, pick one, list channels, get a stream URL.

Acceptance criteria:
- Every `live_tv` method has its own section with signature, parameters, return type, and example
- Pagination example shows how to iterate all pages
- `Genre` and `Channel` model fields are documented

---

### Task 4 — `docs/guide/vod.md`
**Scope: S**

Cover: `get_categories()`, `get_content()` with all parameters, filtering movies vs series (`is_series`), `get_stream_url_by_content_id()`. Include an end-to-end movie example.

Acceptance criteria:
- Every `vod` method relevant to movies has its own section
- `Category` and `Content` model fields are documented
- Shows how to filter out series to get only movies

---

### Task 5 — `docs/guide/series.md`
**Scope: M`

Cover the full navigation path: `get_content()` → identify series (`is_series=True`) → `get_seasons()` → `get_episodes()` → `get_episode_files()` → `get_stream_url_by_first_file()` vs `get_stream_url_by_file_id()`. Include a complete end-to-end example: find a series, list seasons, list episodes, pick a quality, get the URL.

Acceptance criteria:
- `Season`, `Episode`, `EpisodeFile` model fields are documented
- Quality-selection pattern (single file vs multiple files) is explained
- Full end-to-end code example present

---

### Task 6 — `docs/guide/pagination.md`
**Scope: S**

Cover: `PagedResult` fields (`items`, `total`, `page`, `per_page`), the pattern for iterating all pages, when to use lazy vs eager iteration, performance note on request rate.

Acceptance criteria:
- `PagedResult` fields all documented
- Generic "fetch all pages" helper pattern shown
- Note on being polite with request rate (delay between pages)

---

### Task 7 — `docs/guide/error-handling.md`
**Scope: S**

Cover: exception hierarchy (`STBError` base, `AuthError`, `StreamError`, `NotFoundError`), when each is raised, recommended handling patterns (catching specific vs base), retry guidance.

Acceptance criteria:
- All four exception classes documented with the conditions that raise them
- Code example showing catch-by-specificity
- Guidance on when not to retry (e.g. `AuthError` on bad credentials)

---

### Task 8 — `docs/guide/api-reference.md`
**Scope: M**

Exhaustive reference covering:
- `STBClient` — constructor signature with all parameters, types, defaults
- `ITVService` — all methods with full signatures, parameter types/defaults, return types
- `VODService` — same
- All model dataclasses — all fields with types
- All exceptions — inheritance tree and trigger conditions

Acceptance criteria:
- Every public symbol is present
- Parameter types and defaults are accurate (verified against source)
- No method or model field is omitted

---

### Task 9 — Update `README.md` and delete `docs/library.md`
**Scope: XS**

- Add a "Documentation" section to `README.md` with links to each guide
- Delete `docs/library.md` (server-era file, now stale)

Acceptance criteria:
- `README.md` links to all 7 guide files
- `docs/library.md` no longer exists

---

## Dependency order

Tasks 1–8 are independent of each other (each is a self-contained doc file).
Task 9 depends on all others (can't link to files that don't exist yet).

Tasks 1–8 can be written in parallel; Task 9 runs last.
