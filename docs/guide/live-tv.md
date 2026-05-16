# Live TV

All live-TV methods are on `client.live_tv`.

---

## Genres

### `get_genres()`

Returns all channel genres (categories).

```python
genres = client.live_tv.get_genres()
for genre in genres:
    print(f"{genre.id}: {genre.title}")
```

**Returns:** `list[Genre]`

#### Genre fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Genre identifier — pass this as `genre_id` to `get_channels()` |
| `title` | `str` | Display name (e.g. `"News"`, `"Sport"`) |
| `alias` | `str` | Lowercase slug (e.g. `"news"`, `"sport"`) |
| `censored` | `bool` | `True` if the genre requires parental unlock on the portal |

---

## Channels

### `get_channels(genre_id, page, sort, hd, fav)`

Returns a paginated list of channels.

```python
result = client.live_tv.get_channels(genre_id="*", page=1)
print(f"{result.total} channels, showing page {result.page}")
for ch in result.items:
    print(f"  [{ch.number}] {ch.name}")
```

**Returns:** `PagedResult[Channel]`

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `genre_id` | `str` | `"*"` | Genre ID from `get_genres()`. Use `"*"` for all channels. |
| `page` | `int` | `1` | Page number, 1-indexed |
| `sort` | `str` | `"number"` | Sort order: `"number"`, `"name"`, or `"fav"` |
| `hd` | `bool` | `False` | If `True`, return only HD channels |
| `fav` | `bool` | `False` | If `True`, return only favourited channels |

#### Channel fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique channel identifier |
| `number` | `str` | Display channel number |
| `name` | `str` | Channel name (e.g. `"BBC One"`) |
| `cmd` | `str` | Streaming command — pass this to `get_stream_url()` |
| `logo` | `str` | URL to the channel logo image |
| `genre_id` | `str` | ID of the genre this channel belongs to |
| `hd` | `bool` | `True` if the channel broadcasts in HD |
| `censored` | `bool` | `True` if the channel requires parental unlock |

---

## Stream URLs

### `get_stream_url(cmd)`

Resolves a channel's `cmd` value into a playable stream URL.

```python
result = client.live_tv.get_channels()
channel = result.items[0]
url = client.live_tv.get_stream_url(channel.cmd)
print(url)  # e.g. "http://stream.example.com/live/ch1.m3u8"
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `cmd` | `str` | The `cmd` value from a `Channel` object |

**Returns:** `str` — a playable URL ready to pass to a media player.

**Raises:** `StreamError` if the portal rejects the request (e.g. channel offline, not subscribed).

---

### `get_stream_url_by_id(channel_id)`

Convenience method: finds a channel by ID and returns its stream URL in one call.
Useful when you know the channel ID but don't have its `cmd` handy.

```python
url = client.live_tv.get_stream_url_by_id("42")
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | `str` | The `id` of the channel |

**Returns:** `str` — playable stream URL.

**Raises:**
- `NotFoundError` if no channel with that ID exists
- `StreamError` if the portal rejects the stream request

> **Note:** This method fetches all pages of channels to find the matching ID.
> For repeated lookups, prefer fetching channels once and calling `get_stream_url(ch.cmd)` directly.

---

## End-to-end example

```python
from stb_reader import STBClient, StreamError

client = STBClient(base_url="http://portal.example.com", mac="00:1A:79:XX:XX:XX")
client.authenticate()

# 1. List genres
genres = client.live_tv.get_genres()
news_genre = next((g for g in genres if "news" in g.title.lower()), None)

# 2. List channels in a genre (or all channels)
genre_id = news_genre.id if news_genre else "*"
result = client.live_tv.get_channels(genre_id=genre_id, page=1)

print(f"Found {result.total} channels in genre '{genre_id}'")
for ch in result.items:
    flag = "HD" if ch.hd else "SD"
    print(f"  [{ch.number}] {ch.name} ({flag})")

# 3. Get a stream URL
if result.items:
    first = result.items[0]
    try:
        url = client.live_tv.get_stream_url(first.cmd)
        print(f"\nStream URL for '{first.name}': {url}")
    except StreamError as e:
        print(f"Could not get stream: {e}")
```

---

## Fetching all channels

To collect every channel across all pages, see [Pagination](./pagination.md).
Quick example:

```python
all_channels = []
page = 1
while True:
    result = client.live_tv.get_channels(genre_id="*", page=page)
    all_channels.extend(result.items)
    if len(all_channels) >= result.total:
        break
    page += 1

print(f"Fetched {len(all_channels)} channels")
```

---

## Related

- [Pagination](./pagination.md) — `PagedResult` fields and fetch-all pattern
- [Error handling](./error-handling.md) — `StreamError`, `NotFoundError`
- [API reference](./api-reference.md) — complete `ITVService` reference
