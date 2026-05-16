# Series

Series require a multi-step navigation: find the series in the content list, then
drill down through seasons, episodes, and (optionally) quality variants before
you can get a stream URL.

```
get_content()         →  Content (is_series=True)
  get_seasons()       →  list[Season]
    get_episodes()    →  list[Episode]
      get_episode_files()  →  list[EpisodeFile]   (optional: for quality selection)
        get_stream_url_by_file_id()  →  str
      get_stream_url_by_first_file() →  str        (shortcut: uses first file)
```

---

## Step 1 — Find the series

Use `get_content()` and filter by `is_series=True`:

```python
result = client.vod.get_content(category_id="*", page=1)
series_list = [item for item in result.items if item.is_series]
for s in series_list:
    print(f"{s.id}: {s.name} ({s.year})")
```

See [VOD guide](./vod.md) for the full `get_content()` reference.

---

## Step 2 — Get seasons

### `get_seasons(series_id)`

```python
seasons = client.vod.get_seasons(series_id="202")
for season in seasons:
    print(f"Season {season.id}: {season.name}")
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `series_id` | `str` | The `id` from a `Content` object where `is_series=True` |

**Returns:** `list[Season]`

#### Season fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Season identifier — pass this as `season_id` to `get_episodes()` |
| `name` | `str` | Display name (e.g. `"Season 1"`) |
| `video_id` | `str` | ID of the parent series |

---

## Step 3 — Get episodes

### `get_episodes(series_id, season_id, delay_s)`

Fetches all episodes in a season, automatically paginating across multiple pages.

```python
episodes = client.vod.get_episodes(series_id="202", season_id="1")
for ep in episodes:
    print(f"  E{ep.series_number}: {ep.name}")
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `series_id` | `str` | required | The `id` from the `Content` object |
| `season_id` | `str` | required | The `id` from a `Season` object |
| `delay_s` | `float` | `0` | Seconds to wait between paginated requests — useful for rate-limiting on large seasons |

**Returns:** `list[Episode]` — all episodes in the season (all pages collected).

#### Episode fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Episode identifier — pass this as `episode_id` to file/stream methods |
| `name` | `str` | Episode title (e.g. `"Pilot"`) |
| `series_number` | `str` | Episode number within the season (e.g. `"1"`, `"2"`) |
| `cmd` | `str` | Streaming command (may not be directly usable — see step 4) |

---

## Step 4 — Get a stream URL

You have two options depending on whether you want to offer quality selection.

---

### Option A — Simple: first file (no quality choice)

### `get_stream_url_by_first_file(series_id, season_id, episode_id)`

Returns the stream URL for the first available file of an episode. This is the
right choice when you don't need to present quality options to the user.

```python
url = client.vod.get_stream_url_by_first_file(
    series_id="202",
    season_id="1",
    episode_id="5001",
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `series_id` | `str` | The `id` from the `Content` object |
| `season_id` | `str` | The `id` from the `Season` object |
| `episode_id` | `str` | The `id` from the `Episode` object |

**Returns:** `str` — a playable URL.

**Raises:**
- `NotFoundError` if the episode has no files
- `StreamError` if the portal rejects the stream

---

### Option B — Quality selection: list files then choose

#### `get_episode_files(series_id, season_id, episode_id)`

Returns all available quality/language variants for an episode.

```python
files = client.vod.get_episode_files(
    series_id="202",
    season_id="1",
    episode_id="5001",
)
for f in files:
    print(f"  File {f.id}: {f.name}")
# Example output:
#   File 1: English / HD (1080p)
#   File 2: English / SD (480p)
```

**Returns:** `list[EpisodeFile]`

#### EpisodeFile fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | File identifier — pass this to `get_stream_url_by_file_id()` |
| `name` | `str` | Human-readable label combining language and quality (e.g. `"English / HD (1080p)"`) |
| `cmd` | `str` | Streaming command for this file |

---

#### `get_stream_url_by_file_id(series_id, season_id, episode_id, file_id)`

Streams a specific file chosen from `get_episode_files()`.

```python
url = client.vod.get_stream_url_by_file_id(
    series_id="202",
    season_id="1",
    episode_id="5001",
    file_id="1",         # HD version
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `series_id` | `str` | The `id` from the `Content` object |
| `season_id` | `str` | The `id` from the `Season` object |
| `episode_id` | `str` | The `id` from the `Episode` object |
| `file_id` | `str` | The `id` from an `EpisodeFile` object |

**Returns:** `str` — a playable URL.

**Raises:**
- `NotFoundError` if `file_id` is not found among the episode's files
- `StreamError` if the portal rejects the stream

---

## Complete end-to-end example

```python
from stb_reader import STBClient, NotFoundError, StreamError

client = STBClient(base_url="http://portal.example.com", mac="00:1A:79:XX:XX:XX")
client.authenticate()

# 1. Find a series
result = client.vod.get_content(category_id="*", sort="rating", page=1)
series_list = [item for item in result.items if item.is_series]

if not series_list:
    print("No series found on this page")
    exit()

show = series_list[0]
print(f"Selected: {show.name} ({show.year})")

# 2. List seasons
seasons = client.vod.get_seasons(series_id=show.id)
for season in seasons:
    print(f"  {season.name} (id={season.id})")

season = seasons[0]

# 3. List episodes
episodes = client.vod.get_episodes(series_id=show.id, season_id=season.id)
for ep in episodes:
    print(f"    E{ep.series_number}: {ep.name} (id={ep.id})")

episode = episodes[0]

# 4a. Quick stream (first file, no quality choice)
try:
    url = client.vod.get_stream_url_by_first_file(
        series_id=show.id,
        season_id=season.id,
        episode_id=episode.id,
    )
    print(f"\nStream URL: {url}")
except (NotFoundError, StreamError) as e:
    print(f"Could not stream: {e}")

# 4b. Quality selection (list files, pick one)
files = client.vod.get_episode_files(
    series_id=show.id,
    season_id=season.id,
    episode_id=episode.id,
)
if files:
    print("\nAvailable quality options:")
    for f in files:
        print(f"  [{f.id}] {f.name}")

    # Pick the first file (HD if available)
    chosen = files[0]
    try:
        url = client.vod.get_stream_url_by_file_id(
            series_id=show.id,
            season_id=season.id,
            episode_id=episode.id,
            file_id=chosen.id,
        )
        print(f"\nSelected '{chosen.name}': {url}")
    except (NotFoundError, StreamError) as e:
        print(f"Could not stream: {e}")
```

---

## Related

- [VOD guide](./vod.md) — `get_content()` and movie streaming
- [Pagination](./pagination.md) — fetching all content pages to find a series
- [Error handling](./error-handling.md) — `NotFoundError`, `StreamError`
- [API reference](./api-reference.md) — complete `VODService` reference
