# Error Handling

All exceptions are importable directly from `stb_reader`:

```python
from stb_reader import STBError, AuthError, StreamError, NotFoundError
```

---

## Exception hierarchy

```
STBError          ← base class for all library errors
├── AuthError     ← authentication / token problems
├── StreamError   ← portal rejected a stream request
└── NotFoundError ← requested item does not exist
```

---

## STBError

**Base class.** Catch this when you want to handle any library error in one place.

```python
from stb_reader import STBError

try:
    result = client.vod.get_content(page=1)
except STBError as e:
    print(f"Portal error: {e}")
```

**Raised when:**
- The portal returns a non-2xx HTTP status
- The portal returns a response that is not valid JSON
- Any other unexpected portal communication error

---

## AuthError

Raised when authentication fails or the portal rejects a request as unauthorised.

```python
from stb_reader import AuthError

try:
    client.authenticate()
except AuthError as e:
    print(f"Authentication failed: {e}")
```

**Raised when:**
- The handshake returns no token (portal rejected the MAC address)
- The portal returns an `"Authorization failed"` or `"Access denied"` response
- Re-authentication fails after a token expiry (both the original call and the
  automatic retry returned auth errors)

**Recovery guidance:**
- Do **not** retry `AuthError` in a tight loop — if credentials are wrong,
  retrying will not help
- Check that `base_url` and `mac` are correct
- Verify the subscription is active on the portal

---

## StreamError

Raised when the portal refuses to generate a playable stream URL.

```python
from stb_reader import StreamError

try:
    url = client.live_tv.get_stream_url(channel.cmd)
except StreamError as e:
    print(f"Stream unavailable: {e}")
```

**Raised when:**
- `get_stream_url()` — portal returns an error field (e.g. `"nothing_to_play"`)
- `get_stream_url_by_id()` — same, after locating the channel
- `get_stream_url_by_content_id()` — portal rejects the movie stream
- `get_stream_url_by_first_file()` — portal rejects the episode stream
- `get_stream_url_by_file_id()` — portal rejects the specific file stream

**Recovery guidance:**
- The channel or content may be temporarily offline
- The subscription may not include this channel/content
- Try again after a short delay for transient outages

---

## NotFoundError

Raised when a requested item cannot be found.

```python
from stb_reader import NotFoundError

try:
    url = client.live_tv.get_stream_url_by_id("99999")
except NotFoundError as e:
    print(f"Not found: {e}")
```

**Raised when:**
- `get_stream_url_by_id()` — no channel with that ID exists across all pages
- `get_stream_url_by_first_file()` — the episode has no files
- `get_stream_url_by_file_id()` — the specified `file_id` is not among the episode's files

**Recovery guidance:**
- Verify the ID is correct — IDs come from the portal and may change
- For `get_stream_url_by_first_file()`, the episode may genuinely have no available files

---

## Handling multiple exception types

Catch specific exceptions before the base class:

```python
from stb_reader import AuthError, StreamError, NotFoundError, STBError

try:
    url = client.vod.get_stream_url_by_content_id(content_id)
except AuthError:
    # Unrecoverable — stop and report
    raise
except NotFoundError:
    print("Content not found — skipping")
except StreamError as e:
    print(f"Stream unavailable (may be temporary): {e}")
except STBError as e:
    print(f"Unexpected portal error: {e}")
```

---

## Robust fetch with retry

For `StreamError` (transient failures), a simple retry with backoff:

```python
import time
from stb_reader import StreamError

def get_stream_with_retry(client, cmd, retries=3, delay=2.0):
    for attempt in range(retries):
        try:
            return client.live_tv.get_stream_url(cmd)
        except StreamError:
            if attempt < retries - 1:
                time.sleep(delay)
    raise StreamError(f"Stream unavailable after {retries} attempts")
```

---

## Related

- [Authentication](./authentication.md) — `AuthError` in the auth flow
- [API reference](./api-reference.md) — exception class definitions
