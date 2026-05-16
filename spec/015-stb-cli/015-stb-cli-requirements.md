# Spec: STB CLI (015)

## Objective

Add a `stb` command-line tool to the `stb-reader` package so users can browse and stream STB portal content (live TV and VOD) from a terminal without writing Python. The CLI wraps the existing `STBClient` library and is distributed alongside it via the same `pip install stb-reader`.

Target user: someone who has access to a Ministra/Stalker STB portal and wants to look up channel lists, browse VOD, or resolve stream URLs from the shell.

## User Stories

- As a user, I want to run `stb init` once to save my portal URL and MAC address so I don't have to type them on every command.
- As a user, I want to list live TV genres and channels so I can find content to watch.
- As a user, I want to list VOD categories, movies/series, seasons, and episodes so I can browse content.
- As a user, I want to resolve a stream URL from a `cmd` string so I can pass it to a media player.

## Functional Requirements

- FR-1: `stb init` prompts for portal URL and MAC address interactively and saves them to `~/.stb/config` (JSON).
- FR-2: All commands except `stb init` read config from `~/.stb/config` and fail with a clear message if it is missing.
- FR-3: `stb live genres` prints a table of live TV genres (id, title).
- FR-4: `stb live channels` prints a table of channels (number, name, genre, HD). Accepts `--genre <id>`, `--hd`, and `--page N` flags. Default page is 1.
- FR-5: `stb vod categories` prints a table of VOD categories (id, title).
- FR-6: `stb vod list` prints a table of VOD content (id, name, year, genres, series). Accepts `--category <id>` and `--page N` flags. Default page is 1.
- FR-7: `stb vod seasons <series_id>` prints a table of seasons (id, name) for a series.
- FR-8: `stb vod episodes <series_id> <season_id>` prints a table of episodes (id, name, number) for a season.
- FR-9: `stb stream --type <live|vod> <cmd>` resolves a stream URL and prints it to stdout. `--type` is required.
- FR-10: Paginated commands (FR-4, FR-6) display a footer: `Page N of T (X total)`.
- FR-11: Errors (`AuthError`, `StreamError`, `STBError`) print a short message to stderr and exit with code 1. No tracebacks shown to the user.

## Non-Functional Requirements

- NFR-1: No new runtime dependencies beyond `click`. The library itself only requires `requests`.
- NFR-2: Table formatting uses stdlib only (no `rich`, no `tabulate`).
- NFR-3: Config file is plain JSON, human-readable and hand-editable.

## Out of Scope

- Interactive TUI or pager (content pipes to stdout; user runs through `less` if needed).
- `--json` output flag (human-readable tables only for now).
- Favourite filtering (`fav=True`) — library supports it but CLI does not expose it.
- Writing or modifying portal content.
- Config profiles or multiple portals.

## Assumptions

- `click` is acceptable as a new dependency.
- `~/.stb/config` is a suitable config location (single user, no system-wide config needed).
- The `cmd` field a user passes to `stb stream` comes from a prior `stb live channels` or `stb vod list` query — no validation of its format is needed.
- Table column widths are computed from content (no fixed-width layout required).

## Tech Stack

- Python ≥ 3.11
- Click (new dependency, added to `[project.dependencies]` in `pyproject.toml`)
- stdlib only for table formatting
- Existing: `STBClient`, `ITVService`, `VODService`, `AuthError`, `StreamError`, `STBError` from `stb_reader`

## Commands

```
Install:  pip install -e .
Test:     pytest tests/
Lint:     (none configured)
Run CLI:  stb --help
```

## Project Structure

```
stb_reader/
  cli/
    __init__.py       # exports `main` entry point
    main.py           # root Click group + `stb init`
    config.py         # ~/.stb/config read/write + get_client()
    live.py           # `stb live` subcommands
    vod.py            # `stb vod` subcommands
    formatting.py     # print_table() using stdlib
tests/
  test_cli_config.py  # unit tests for config.py
  test_cli_live.py    # CLI integration tests for live commands
  test_cli_vod.py     # CLI integration tests for vod commands
  test_cli_stream.py  # CLI integration tests for stream command
spec/
  015-stb-cli/        # this spec
```

## Code Style

Match the existing library style: dataclasses for models, type annotations throughout, no comments unless the why is non-obvious.

```python
@live.command("channels")
@click.option("--genre", default="*", help="Genre ID to filter by.")
@click.option("--hd", is_flag=True, default=False, help="HD channels only.")
@click.option("--page", default=1, show_default=True, help="Page number.")
@click.pass_context
def channels_cmd(ctx: click.Context, genre: str, hd: bool, page: int) -> None:
    client = get_client(ctx)
    result = client.live_tv.get_channels(genre_id=genre, page=page, hd=hd)
    print_table(
        ["#", "Name", "Genre ID", "HD"],
        [[c.number, c.name, c.genre_id, "yes" if c.hd else ""] for c in result.items],
        footer=f"Page {result.page} of {-(-result.total // result.per_page)} ({result.total} total)",
    )
```

- CLI modules use `@click.pass_context` and retrieve the client via `get_client(ctx)`.
- `get_client()` reads config, constructs `STBClient`, calls `authenticate()`, returns client.
- Error handling is centralised in `get_client()` and a top-level `except` in each command.

## Testing Strategy

- Framework: `pytest` + `responses` (already in test deps) + Click's `CliRunner`
- Tests live in `tests/` alongside existing test files
- Unit tests for `config.py`: read/write round-trip, missing file error
- Unit tests for `formatting.py`: column widths, footer, empty table
- Integration tests per command group using `CliRunner.invoke()` with mocked HTTP via `responses`
- No coverage target set; all commands must have at least one happy-path test and one error-path test

## Boundaries

- **Always:** Run `pytest tests/` before marking a task done. Follow existing naming and style conventions.
- **Ask first:** Adding dependencies beyond `click`. Changing `pyproject.toml` beyond adding `click` and the console script. Changing existing library code (`client.py`, `live_tv.py`, `vod.py`, etc.).
- **Never:** Catch and silently swallow exceptions. Show raw Python tracebacks to CLI users. Modify vendor or test infrastructure files.

## Success Criteria

- `pip install -e .` makes `stb` available on `$PATH`.
- `stb init` saves config; subsequent commands succeed without re-entering credentials.
- `stb live genres`, `stb live channels`, `stb vod categories`, `stb vod list`, `stb vod seasons <id>`, `stb vod episodes <id> <id>` all print formatted tables.
- `stb live channels --page 2` prints page 2 with a pagination footer.
- `stb stream --type live <cmd>` and `stb stream --type vod <cmd>` each print a resolved URL.
- Running any command without a config file prints a message directing the user to run `stb init` and exits with code 1.
- `pytest tests/` passes with no failures.

## Open Questions

None — all requirements confirmed with the user.
