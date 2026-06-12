# 018 — Audit Mode Requirements

## Problem

Users have no visibility into the exact portal requests being made on their behalf. There is no way to inspect, confirm, or reject a request before it is sent to the STB portal.

## Goal

Add an `--audit` flag to the CLI that intercepts each outgoing portal API request, shows it to the user, requires explicit confirmation before sending, and then shows the raw STB response before the normal formatted output.

## Scope

CLI-only feature. No changes to library public API surface. No changes to `live.py`, `vod.py`, `auth.py`, or any service files.

---

## Functional Requirements

### FR-1: Flag

- `stb --audit <subcommand>` activates audit mode for the duration of that invocation.
- `--audit` is a boolean flag on the root `main` Click group (alongside `--debug`).
- Default is off; no behavior change when flag is absent.

### FR-2: Request Interception (before sending)

For every call to `STBSession.get()`, including auth requests (`type_="stb"`: handshake, get_profile, and reauth triggered mid-request):

1. Print a labelled block showing:
   - Full portal URL
   - `type` and `action` values
   - All user-supplied params (everything except `JsHttpRequest`, `type`, `action`)
   - Token presence (`[set]` or `[not set]`) — never print the raw token value
2. Prompt: `Send this request? [Y/n]`

### FR-3: Abort path

If the user answers `n` (or `N`): raise `click.exceptions.Abort()`. The HTTP request must not be sent. Exit code 1, message `Aborted!`.

### FR-4: Raw response display (after sending)

If the user confirms:
1. Send the HTTP request normally.
2. After a successful response, print a labelled block containing the full raw JSON (`resp.json()`, including the `"js"` wrapper), pretty-printed with 2-space indent.
3. Then proceed with normal formatted output (table, etc.) unchanged.

### FR-5: Propagation

Audit mode must propagate from the CLI flag to `STBSession` without requiring changes to any leaf command (`live.py`, `vod.py`). `get_client()` reads the flag from the active Click context.

---

## Non-Functional Requirements

### NFR-1: No side effects when flag is absent

All existing behavior (output, exit codes, error handling) must be identical when `--audit` is not passed.

### NFR-2: Reauth aborts propagate cleanly

If a denied prompt occurs during a reauth-triggered handshake/get_profile (mid-request retry), the resulting `Abort` must propagate cleanly out of `STBSession.get()` without leaving the session in a locked or inconsistent state (the existing `_reauth_lock`/`finally` handling already covers this).

### NFR-3: Token privacy

The raw Bearer token value must never appear in audit output. Display `[set]` / `[not set]` only.

---

## Out of Scope

- Logging audit output to a file
- Auditing `open_url()` or `open_stream()` (stream fetches, not portal API calls)
- Any UI beyond the terminal (no TUI, no pager)
