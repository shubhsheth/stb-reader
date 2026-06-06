# 018 — Audit Mode Plan

## Tasks

### Task 1 — STBSession: audit_mode param + interception in get() [S]

**File:** `stb_reader/_http.py`

**Changes:**
- Add `import click` and `import json` at the top.
- Add `audit_mode: bool = False` to `STBSession.__init__`; store as `self.audit_mode`.
- Add module-level helpers `_print_audit_request(url, query, token)` and `_print_audit_response(raw)`.
- In `STBSession.get()`:
  - After headers/cookies are assembled, before `self._session.get(...)`:
    - If `self.audit_mode and type_ != "stb"`: call `_print_audit_request`, then `click.confirm`; raise `Abort` if denied.
  - Parse response into `raw = resp.json()` (store once, avoid double-parse).
  - After auth/error checks, before returning:
    - If `self.audit_mode and type_ != "stb"`: call `_print_audit_response(raw)`.
  - Return `raw["js"]`.

**Helper output format:**

```
--- Audit: Outgoing Request ---
URL:    <url>
type:   <type_>
action: <action>
params: k=v, k=v      # omitted if no user params
token:  [set]|[not set]
```

```
--- Audit: Raw STB Response ---
<json.dumps(raw, indent=2)>
--- End Audit Response ---
```

**Acceptance criteria:**
- `STBSession(audit_mode=True).get("vod", "get_categories")` prints request block, prompts, prints response block.
- `STBSession(audit_mode=True).get("stb", "handshake")` prints nothing, prompts nothing.
- `STBSession(audit_mode=False).get(...)` has identical behavior to current code.
- Deny prompt → `click.exceptions.Abort` raised, no HTTP request sent.

**Verify:** `pytest tests/test_http.py`

**Depends on:** nothing

---

### Task 2 — STBClient: thread audit_mode through [XS]

**File:** `stb_reader/client.py`

**Changes:**
- Add `audit_mode: bool = False` to `STBClient.__init__`.
- Pass `audit_mode=audit_mode` to the `STBSession(...)` constructor call.

**Acceptance criteria:**
- `STBClient(base_url=..., mac=..., audit_mode=True)._session.audit_mode is True`
- `STBClient(base_url=..., mac=...)._session.audit_mode is False`

**Verify:** existing tests + quick manual check

**Depends on:** Task 1

---

### Task 3 — get_client(): read audit from Click context [XS]

**File:** `stb_reader/cli/config.py`

**Changes:**
- Inside `get_client()`, before constructing `STBClient`, read `audit_mode` from the active Click context:

```python
audit_mode = False
try:
    ctx = click.get_current_context()
    if ctx.obj:
        audit_mode = ctx.find_root().obj.get("audit", False)
except RuntimeError:
    pass  # no active Click context (e.g. direct library use or tests)
client = STBClient(**kwargs, audit_mode=audit_mode)
```

**Acceptance criteria:**
- When called inside a Click invocation with `--audit`, `client._session.audit_mode is True`.
- When called without a Click context (tests, library use), `audit_mode` defaults to `False`.

**Verify:** `pytest tests/test_cli_config.py`

**Depends on:** Task 2

---

### Task 4 — main(): add --audit flag [XS]

**File:** `stb_reader/cli/main.py`

**Changes:**
- Add `@click.option("--audit", is_flag=True, default=False, help="Intercept and confirm each portal request before sending.")` to `main`.
- Add `audit: bool` parameter to `main()`.
- Add `ctx.ensure_object(dict)` and `ctx.obj["audit"] = audit` to `main()` body.

**Acceptance criteria:**
- `stb --help` shows `--audit` option.
- `stb --audit vod categories` activates audit interception.
- `stb vod categories` (no flag) behaves identically to current behavior.

**Verify:** `pytest tests/` (full suite)

**Depends on:** Task 3

---

### Task 5 — Tests: audit mode unit tests [S]

**File:** `tests/test_http.py`

**New test cases:**

| Test | What it checks |
|------|---------------|
| `test_audit_mode_off_by_default` | `STBSession` with default args: no prompt, returns `js` normally |
| `test_audit_mode_skips_stb_requests` | `audit_mode=True`, `type_="stb"`: no `click.confirm` call, no audit output |
| `test_audit_mode_prints_request_block` | `audit_mode=True`, `type_="vod"`, confirm=True: output contains URL, type, action |
| `test_audit_mode_prints_response_block` | confirm=True: output contains `"js"` key from raw JSON |
| `test_audit_mode_abort_on_no` | confirm=False: `click.exceptions.Abort` raised, zero HTTP calls made |
| `test_audit_mode_token_not_in_output` | token value `"secret123"` does not appear in audit output |

Use `monkeypatch` to patch `click.confirm` and `click.echo`. Use `responses` fixture for HTTP mocking (already in conftest).

**Verify:** `pytest tests/test_http.py -v`

**Depends on:** Task 1

---

## Dependency Order

```
Task 1 (_http.py)
  └── Task 2 (client.py)
        └── Task 3 (config.py)
              └── Task 4 (main.py)
Task 1
  └── Task 5 (tests)
```

Tasks 4 and 5 can be done in parallel after their dependencies are met.

---

## Verification (end-to-end)

After all tasks:
1. `pytest tests/` — full suite passes
2. Manual: `stb --audit vod categories` shows request block, prompts, shows raw JSON + table on confirm
3. Manual: answer `n` → `Aborted!`, exit 1
4. Manual: `stb vod categories` (no flag) — no change in behavior
