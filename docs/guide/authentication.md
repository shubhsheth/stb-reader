# Authentication

## Overview

Before making any API calls you must authenticate:

```python
client.authenticate()
```

This single call performs two requests against the portal:

1. **Handshake** — exchanges device identity for a session token
2. **Get profile** — fetches device and user configuration using the token

Both steps happen automatically. You never need to call them separately.

---

## When to call authenticate()

Call it once, right after creating the client, before any other method:

```python
from stb_reader import STBClient

client = STBClient(base_url="http://portal.example.com", mac="00:1A:79:XX:XX:XX")
client.authenticate()  # must come first

genres = client.live_tv.get_genres()  # safe to call now
```

Calling any service method before `authenticate()` will fail because no session
token exists yet.

---

## Automatic token renewal

STB portal tokens expire after a period of inactivity. When a token expires, the
portal returns an auth-failure response to the next request. The library detects
this and **transparently re-authenticates once**, then retries the original request.

This means most long-running scripts never need to call `authenticate()` again:

```python
client.authenticate()

# Works even if the token expires mid-loop — the library renews it automatically
for page in range(1, 100):
    result = client.vod.get_content(page=page)
    process(result.items)
```

If re-authentication also fails (e.g. the subscription has been terminated), the
library raises `AuthError` from the retried call.

---

## Handling authentication errors

`AuthError` is raised when:

- The portal rejects the MAC address (unregistered device)
- The subscription has expired
- The portal is temporarily unavailable during the handshake
- Re-authentication fails after a token expiry

```python
from stb_reader import STBClient, AuthError

client = STBClient(base_url="http://portal.example.com", mac="00:1A:79:XX:XX:XX")

try:
    client.authenticate()
except AuthError as e:
    # Unrecoverable — bad credentials or expired subscription
    print(f"Cannot authenticate: {e}")
    raise
```

Do not retry `AuthError` in a loop — if the credentials are wrong, retrying will
not help and may trigger rate-limiting on the portal.

---

## Re-authenticating manually

If you need to force a fresh authentication (e.g. after your app has been paused
for a long time), call `authenticate()` again:

```python
# Force a fresh token
client.authenticate()
```

This is safe to call at any time and replaces the existing session token.

---

## Related

- [Error handling](./error-handling.md) — full exception reference including `AuthError`
- [Getting started](./getting-started.md) — complete first-call example
