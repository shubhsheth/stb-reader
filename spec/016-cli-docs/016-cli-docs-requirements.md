# Spec: CLI Documentation & Docs Restructure (016)

## Objective

Two things at once, since they're inseparable:

1. **Restructure `docs/`** — the current `docs/` folder holds raw HTTP wire-protocol reference. The root `README.md` already points to `docs/guide/` for library user guides, but that directory doesn't exist. Renaming `docs/` → `docs/protocol/` makes the separation unambiguous and creates space for `docs/guide/`.

2. **Add CLI user documentation** — the `stb` CLI is fully implemented but has no user-facing docs. Add `docs/guide/cli.md` as the first file in `docs/guide/`.

Target user for `cli.md`: someone who has installed `stb-reader` and wants to use the `stb` command from a terminal — not necessarily a Python developer.

## Functional Requirements

- FR-1: Move all four files in `docs/` into `docs/protocol/` (`README.md`, `authentication.md`, `live-tv.md`, `vod-series.md`).
- FR-2: All cross-links within the moved files continue to resolve (they use relative `./` paths between siblings — no edits needed since they move together).
- FR-3: Update `AGENTS.md` to reference `docs/protocol/` instead of `docs/`.
- FR-4: Create `docs/guide/cli.md` covering: installation, `stb init`, global `--debug` flag, `stb live genres`, `stb live channels`, `stb vod categories`, `stb vod list`, `stb vod seasons`, `stb vod episodes`, `stb stream`, and error handling.
- FR-5: Add a link to `docs/guide/cli.md` in the root `README.md` Documentation section.

## Content Requirements for `docs/guide/cli.md`

### Installation
- `pip install stb-reader` installs the `stb` command.
- Verify with `stb --help`.

### Configuration — `stb init`
All seven prompts with their defaults:

| Prompt | Default |
|---|---|
| Portal URL (no port) | _(required)_ |
| Port | _(blank = no port)_ |
| MAC address | _(required)_ |
| Serial | `000000000000` |
| Language | `en` |
| Timezone | `Europe/London` |
| Portal path | `stalker_portal/c/portal.php` |

Config is saved as JSON to `~/.stb/config`. Include an example JSON block.

### Global flags
- `--debug`: prints raw portal responses to stderr. Useful for diagnosing auth or stream failures.

### `stb live genres`
Table output: ID, Title.

### `stb live channels`
Table output: #, Name, Genre ID, HD, CMD.
Options: `--genre <id>` (default `*`), `--hd` (flag), `--page <n>` (default 1).
Footer: `Page N of T (X total)`.

### `stb vod categories`
Table output: ID, Title.

### `stb vod list`
Table output: ID, Name, Year, Genres, Series, CMD.
Options: `--category <id>` (default `*`), `--page <n>` (default 1).
Footer: `Page N of T (X total)`.

### `stb vod seasons <series_id>`
Argument: `series_id` from the CMD column of `stb vod list`.
Table output: ID, Name.

### `stb vod episodes <series_id> <season_id>`
Arguments: `series_id`, `season_id` (ID from `stb vod seasons`).
Table output: ID, Name, #, CMD.
Option: `--page <n>` (default 1).

### `stb stream --type <live|vod> <cmd>`
Resolves a stream URL and prints it to stdout.
`--type` is required. `<cmd>` comes from the CMD column of a prior listing command.
Example: pipe directly to a media player.

### Error handling
- Missing config: `No config found. Run 'stb init' first.` — exits 1.
- Auth failure: short message to stderr — exits 1.
- Stream failure: short message to stderr — exits 1.
- No Python tracebacks shown.

## Non-Functional Requirements

- NFR-1: No code changes — documentation and file moves only.
- NFR-2: `docs/guide/cli.md` uses plain Markdown; no build tooling required.
- NFR-3: All existing relative cross-links within `docs/protocol/` continue to work after the move.

## Out of Scope

- Creating the other seven `docs/guide/` files referenced in `README.md` (getting-started, authentication, live-tv, vod, series, pagination, error-handling, api-reference) — those are future work.
- Changes to any Python source file.
- Adding a `docs/guide/README.md` index — the root `README.md` serves as the index.

## Assumptions

- Moving files via `git mv` preserves history.
- The four existing `docs/` files have no absolute links — confirmed from source; all cross-links are relative siblings.
- The root `README.md` Documentation section already lists `docs/guide/` links; we add `cli.md` to that list without removing the other placeholder entries.

## Tech Stack

- Plain Markdown
- Git (for `git mv`)

## Commands

```
Move files:  git mv docs/README.md docs/protocol/README.md  (repeat for each file)
Verify:      ls docs/protocol/
```

## Project Structure

```
docs/
  protocol/           ← renamed from docs/ (four existing files move here)
    README.md
    authentication.md
    live-tv.md
    vod-series.md
  guide/              ← new
    cli.md            ← new
```

## Testing Strategy

Manual verification only (documentation):
- All four `docs/protocol/` files exist and render.
- Cross-links within `docs/protocol/` resolve (relative siblings — no change needed).
- `docs/guide/cli.md` exists and covers all commands listed in FR-4.
- `README.md` Documentation section contains a link to `docs/guide/cli.md`.
- `AGENTS.md` references `docs/protocol/` not `docs/`.

## Boundaries

- **Always:** Use `git mv` (not `cp`+`rm`) to preserve history. Verify links after moving.
- **Ask first:** Any edits to Python source files. Creating additional `docs/guide/` files beyond `cli.md`.
- **Never:** Edit `pyproject.toml`, test files, or CI config.

## Success Criteria

- `ls docs/protocol/` lists all four original `docs/` files.
- `ls docs/guide/` lists `cli.md`.
- `docs/guide/cli.md` documents every `stb` subcommand: `init`, `live genres`, `live channels`, `stb vod categories`, `stb vod list`, `stb vod seasons`, `stb vod episodes`, `stb stream`.
- `README.md` has a working relative link to `docs/guide/cli.md`.
- `AGENTS.md` reflects the new `docs/protocol/` path.
- No broken relative links in any moved file.

## Open Questions

None.
