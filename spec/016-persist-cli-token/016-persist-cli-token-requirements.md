# Spec: Persist CLI Auth Token (016)

## Objective

Eliminate the redundant handshake that occurs on every CLI invocation by persisting the session token to disk. On the next CLI call the cached token is loaded and used directly; if it has expired the existing in-process re-auth path fires automatically and the refreshed token is written back to disk.

Target user: anyone running `stb` CLI commands repeatedly (e.g. in scripts or quickly browsing channels). Today each command does a full handshake round-trip before doing its real work; after this change only the first invocation (or the one after a token expiry) pays that cost.

## User Stories

- As a CLI user, I want subsequent `stb` commands to skip the auth handshake so they respond faster.
- As a CLI user, I want the cache to refresh transparently when my token expires so I never have to manually re-authenticate.

## Functional Requirements

- FR-1: After a successful `authenticate()` call, the CLI writes the session token and any extra headers (`X-Random`, `Random`) to `~/.stb/token` as JSON.
- FR-2: On every CLI invocation, `get_client()` attempts to load `~/.stb/token`. If a valid token is found, it is applied to the session and `authenticate()` is **not** called.
- FR-3: When the loaded token causes an auth failure, the existing `_http.py` re-auth path calls `authenticate()` which refreshes the session. The CLI wrapper then saves the new token to `~/.stb/token`.
- FR-4: If `~/.stb/token` is missing or contains invalid JSON, `get_client()` falls back to a full `authenticate()` call and saves the resulting token.
- FR-5: The token file is written with the same directory guarantees as the config file (`~/.stb/` created if absent).

## Non-Functional Requirements

- NFR-1: No new runtime dependencies. Uses only `json` and `pathlib` (already in use in `config.py`).
- NFR-2: The token file is human-readable JSON so users can inspect or delete it manually.
- NFR-3: No changes to library code (`client.py`, `_http.py`, `auth.py`). All changes are CLI-only.
- NFR-4: Thread safety is not a concern for the CLI (single-process, sequential commands).

## Out of Scope

- `stb logout` command or explicit token invalidation command.
- Token expiry timestamps / TTL-based eviction (rely on re-auth-on-failure instead).
- Library-level token persistence (library callers manage their own sessions).
- Multi-profile or per-portal token caching.
- File permissions hardening (e.g. `chmod 600`) — left for a future security hardening pass.

## Assumptions

- The session token returned by the portal is stable enough to reuse across CLI invocations (i.e. not invalidated purely by time between calls in normal usage).
- `~/.stb/token` is an acceptable path (same parent directory as `~/.stb/config`).
- `extra_headers` on the session (e.g. `X-Random`) must also be persisted; some portals require them alongside the token on every request.
- Deleting `~/.stb/token` is the supported manual "logout" / cache-clear mechanism.

## Tech Stack

- Python ≥ 3.11
- stdlib only: `json`, `pathlib.Path`
- `pytest` + `responses` + Click's `CliRunner` for tests

## Commands

```
Test:    pytest tests/
Install: pip install -e .
Run CLI: stb --help
```

## Project Structure

```
stb_reader/
  cli/
    config.py       ← only file changed (add TOKEN_PATH, save_token, load_token; modify get_client)
tests/
  test_cli_config.py  ← new test cases added here
spec/
  016-persist-cli-token/   ← this spec
```

## Code Style

Match the existing `config.py` style: plain functions, no classes, type annotations, no comments unless the why is non-obvious.

```python
TOKEN_PATH = Path.home() / ".stb" / "token"

def save_token(session) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps({
        "token": session.token,
        "extra_headers": session.extra_headers,
    }))

def load_token() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text())
    except (json.JSONDecodeError, KeyError):
        return None
```

`get_client()` wraps `client.authenticate` so every auth (initial or re-auth) persists the token:

```python
def get_client() -> STBClient:
    cfg = load_config()
    ...
    client = STBClient(**kwargs)

    def _auth_and_save():
        client.authenticate()
        save_token(client._session)

    client._session.reauth_fn = _auth_and_save

    cached = load_token()
    if cached:
        client._session.token = cached["token"]
        client._session.extra_headers.update(cached.get("extra_headers", {}))
    else:
        _auth_and_save()

    return client
```

## Testing Strategy

- Framework: `pytest` with `monkeypatch` and Click's `CliRunner`.
- All new tests go in `tests/test_cli_config.py` alongside existing config tests.
- No new test files needed.
- Each new functional requirement has at least one happy-path and one error-path test.

Test cases:

| Test | Requirement |
|------|-------------|
| `test_save_and_load_token` — round-trip token + extra_headers | FR-1, FR-5 |
| `test_load_token_missing` — returns `None` when file absent | FR-4 |
| `test_load_token_corrupt` — returns `None` on bad JSON | FR-4 |
| `test_get_client_saves_token_on_fresh_auth` — no cache → authenticate called → token written | FR-1, FR-2 |
| `test_get_client_uses_cached_token` — cache present → authenticate not called → token applied | FR-2 |
| `test_get_client_reauth_updates_token` — reauth_fn fires → updated token written to disk | FR-3 |

## Boundaries

- **Always:** Run `pytest tests/` before marking done. Keep all changes inside `cli/config.py` and `tests/test_cli_config.py`.
- **Ask first:** Any change to library files (`client.py`, `_http.py`, `auth.py`). Adding a new CLI command (e.g. `stb logout`). Changing the token file path or format after the spec is approved.
- **Never:** Silently swallow `IOError` / `PermissionError` when writing the token file (let it surface). Touch files outside `cli/config.py` and its test.

## Success Criteria

- Running `stb live genres` twice in succession: the second invocation does not perform a network handshake (observable via `--debug` logging or by mocking).
- When the token file contains a stale token, the command still succeeds after a transparent re-auth, and the token file is updated with the new token.
- Deleting `~/.stb/token` and re-running any command causes a fresh handshake and recreates the file.
- `pytest tests/` passes with no failures and no regressions in existing tests.

## Open Questions

None — all requirements confirmed with the user.
