# Getting Started

## Installation

```bash
pip install stb-reader
```

Requires Python 3.11 or later. The only runtime dependency is `requests`.

---

## What you need

To use this library you need access to a Ministra/Stalker STB portal. You will need:

| Item | Example | Where to find it |
|------|---------|-----------------|
| Portal URL | `http://192.168.1.10:8080` | Your provider or router admin panel |
| MAC address | `00:1A:79:XX:XX:XX` | Printed on your STB device, or provided by your IPTV provider |

---

## Creating a client

```python
from stb_reader import STBClient

client = STBClient(
    base_url="http://portal.example.com",
    mac="00:1A:79:XX:XX:XX",
)
```

### Constructor parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | required | Base URL of the STB portal, without a trailing slash |
| `mac` | `str` | required | Device MAC address used to identify this client to the portal |
| `serial` | `str` | `"000000000000"` | Device serial number; most portals accept the default |
| `lang` | `str` | `"en"` | Language code sent to the portal (e.g. `"en"`, `"de"`, `"fr"`) |
| `timezone` | `str` | `"Europe/London"` | IANA timezone name (e.g. `"America/New_York"`, `"Asia/Tokyo"`) |
| `portal_path` | `str` | `"stalker_portal/c/portal.php"` | Path to the portal endpoint; only change this if your provider uses a non-standard path |

---

## Authenticating

Before calling any other method, call `authenticate()`:

```python
client.authenticate()
```

This performs the two-step STB handshake — obtaining a session token and fetching
the device profile. After this, the client handles token renewal automatically.

See [Authentication](./authentication.md) for details on what happens under the hood
and how to handle authentication errors.

---

## Your first calls

```python
from stb_reader import STBClient, AuthError

client = STBClient(
    base_url="http://portal.example.com",
    mac="00:1A:79:XX:XX:XX",
)

try:
    client.authenticate()
except AuthError as e:
    print(f"Authentication failed: {e}")
    raise

# List live-TV genres
genres = client.live_tv.get_genres()
for genre in genres:
    print(f"Genre {genre.id}: {genre.title}")

# List first page of channels
channels = client.live_tv.get_channels(genre_id="*", page=1)
print(f"{channels.total} channels total")
for ch in channels.items:
    print(f"  [{ch.number}] {ch.name} (HD: {ch.hd})")

# Get stream URL for the first channel
if channels.items:
    url = client.live_tv.get_stream_url(channels.items[0].cmd)
    print(f"Stream URL: {url}")

# List VOD categories
categories = client.vod.get_categories()
for cat in categories:
    print(f"Category {cat.id}: {cat.title}")

# List first page of VOD content
content = client.vod.get_content(category_id="*", page=1)
print(f"{content.total} items total")
for item in content.items:
    kind = "Series" if item.is_series else "Movie"
    print(f"  [{kind}] {item.name} ({item.year})")
```

---

## Next steps

- [Authentication](./authentication.md) — token lifecycle and error handling
- [Live TV guide](./live-tv.md) — channels, genres, stream URLs
- [VOD guide](./vod.md) — movies, categories, stream URLs
- [Series guide](./series.md) — seasons, episodes, quality selection
- [Pagination](./pagination.md) — fetching all pages of a large result set
- [Error handling](./error-handling.md) — all exceptions and recovery patterns
- [API reference](./api-reference.md) — complete method and model reference
