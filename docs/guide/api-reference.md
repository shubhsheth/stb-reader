# API Reference

Complete reference for all public classes, methods, models, and exceptions.

---

## STBClient

```python
from stb_reader import STBClient
```

### Constructor

```python
STBClient(
    base_url: str,
    mac: str,
    serial: str = "000000000000",
    lang: str = "en",
    timezone: str = "Europe/London",
    portal_path: str = "stalker_portal/c/portal.php",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | required | Base URL of the STB portal (no trailing slash) |
| `mac` | `str` | required | Device MAC address |
| `serial` | `str` | `"000000000000"` | Device serial number |
| `lang` | `str` | `"en"` | Language code (e.g. `"en"`, `"de"`) |
| `timezone` | `str` | `"Europe/London"` | IANA timezone name (e.g. `"America/New_York"`) |
| `portal_path` | `str` | `"stalker_portal/c/portal.php"` | Path to the portal PHP endpoint |

### Methods

#### `authenticate() -> None`

Performs the two-step authentication handshake (token + profile). Must be called
before any service method. Safe to call again to force token renewal.

**Raises:** `AuthError` if the portal rejects the credentials.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `live_tv` | `ITVService` | Live-TV service — see below |
| `vod` | `VODService` | VOD service — see below |

---

## ITVService

Accessed as `client.live_tv`. Do not instantiate directly.

### `get_genres() -> list[Genre]`

Returns all channel genres.

**Raises:** `STBError` on portal communication failure.

---

### `get_channels(genre_id, page, sort, hd, fav) -> PagedResult[Channel]`

Returns a paginated list of channels.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `genre_id` | `str` | `"*"` | Genre ID from `get_genres()`. `"*"` for all channels. |
| `page` | `int` | `1` | Page number, 1-indexed |
| `sort` | `str` | `"number"` | Sort order: `"number"`, `"name"`, or `"fav"` |
| `hd` | `bool` | `False` | If `True`, return only HD channels |
| `fav` | `bool` | `False` | If `True`, return only favourited channels |

**Raises:** `STBError` on portal communication failure.

---

### `get_stream_url(cmd) -> str`

Resolves a channel `cmd` into a playable stream URL.

| Parameter | Type | Description |
|-----------|------|-------------|
| `cmd` | `str` | The `cmd` field from a `Channel` object |

**Raises:** `StreamError` if the portal refuses the stream.

---

### `get_stream_url_by_id(channel_id) -> str`

Finds a channel by ID across all pages and returns its stream URL.

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | `str` | The `id` field from a `Channel` object |

**Raises:**
- `NotFoundError` if no channel with that ID exists
- `StreamError` if the portal refuses the stream

---

## VODService

Accessed as `client.vod`. Do not instantiate directly.

### `get_categories() -> list[Category]`

Returns all VOD categories. Adult-titled categories are filtered automatically.

**Raises:** `STBError` on portal communication failure.

---

### `get_content(category_id, page, sort, fav) -> PagedResult[Content]`

Returns a paginated list of movies and series.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category_id` | `str` | `"*"` | Category ID from `get_categories()`. `"*"` for all content. |
| `page` | `int` | `1` | Page number, 1-indexed |
| `sort` | `str` | `"added"` | Sort order: `"added"`, `"popular"`, `"rating"`, or `"name"` |
| `fav` | `bool` | `False` | If `True`, return only favourited items |

**Raises:** `STBError` on portal communication failure.

---

### `get_seasons(series_id, page=1) -> PagedResult[Season]`

Returns seasons for a series, with pagination support.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `series_id` | `str` | required | The `id` from a `Content` object where `is_series=True` |
| `page` | `int` | `1` | Page number for pagination |

**Raises:** `STBError` on portal communication failure.

---

### `get_episodes(series_id, season_id, delay_s) -> list[Episode]`

Returns all episodes in a season. Automatically paginates across multiple pages.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `series_id` | `str` | required | The `id` from the `Content` object |
| `season_id` | `str` | required | The `id` from a `Season` object |
| `delay_s` | `float` | `0` | Seconds to sleep between paginated requests |

**Raises:** `STBError` on portal communication failure.

---

### `get_episode_files(series_id, season_id, episode_id) -> list[EpisodeFile]`

Returns all quality/language file variants for an episode.

| Parameter | Type | Description |
|-----------|------|-------------|
| `series_id` | `str` | The `id` from the `Content` object |
| `season_id` | `str` | The `id` from the `Season` object |
| `episode_id` | `str` | The `id` from an `Episode` object |

**Raises:** `STBError` on portal communication failure.

---

### `get_stream_url(cmd) -> str`

Resolves a VOD `cmd` string into a playable stream URL.

| Parameter | Type | Description |
|-----------|------|-------------|
| `cmd` | `str` | A `cmd` value from a `Content` or `EpisodeFile` object |

**Raises:** `StreamError` if the portal refuses the stream.

---

### `get_stream_url_by_content_id(content_id) -> str`

Returns the stream URL for a movie by its content ID.

| Parameter | Type | Description |
|-----------|------|-------------|
| `content_id` | `str` | The `id` from a `Content` object |

**Raises:** `StreamError` if the portal refuses the stream.

---

### `get_stream_url_by_first_file(series_id, season_id, episode_id) -> str`

Returns the stream URL for the first available file of an episode.

| Parameter | Type | Description |
|-----------|------|-------------|
| `series_id` | `str` | The `id` from the `Content` object |
| `season_id` | `str` | The `id` from the `Season` object |
| `episode_id` | `str` | The `id` from the `Episode` object |

**Raises:**
- `NotFoundError` if the episode has no files
- `StreamError` if the portal refuses the stream

---

### `get_stream_url_by_file_id(series_id, season_id, episode_id, file_id) -> str`

Returns the stream URL for a specific quality/language file of an episode.

| Parameter | Type | Description |
|-----------|------|-------------|
| `series_id` | `str` | The `id` from the `Content` object |
| `season_id` | `str` | The `id` from the `Season` object |
| `episode_id` | `str` | The `id` from the `Episode` object |
| `file_id` | `str` | The `id` from an `EpisodeFile` object |

**Raises:**
- `NotFoundError` if `file_id` is not found among the episode's files
- `StreamError` if the portal refuses the stream

---

## Models

All models are dataclasses importable from `stb_reader`.

### Genre

```python
from stb_reader import Genre
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Genre identifier |
| `title` | `str` | Display name |
| `alias` | `str` | Lowercase slug |
| `censored` | `bool` | `True` if parental unlock is required |

---

### Channel

```python
from stb_reader import Channel
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique channel identifier |
| `number` | `str` | Display channel number |
| `name` | `str` | Channel name |
| `cmd` | `str` | Streaming command — pass to `get_stream_url()` |
| `logo` | `str` | URL to the channel logo image |
| `genre_id` | `str` | ID of the channel's genre |
| `hd` | `bool` | `True` if the channel broadcasts in HD |
| `censored` | `bool` | `True` if parental unlock is required |

---

### Category

```python
from stb_reader import Category
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Category identifier |
| `title` | `str` | Display name |
| `alias` | `str` | Lowercase slug |
| `censored` | `bool` | `True` if parental unlock is required |

---

### Content

```python
from stb_reader import Content
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Content identifier |
| `name` | `str` | Title |
| `cmd` | `str` | Streaming command (for movies; for series navigate seasons/episodes first) |
| `screenshot_uri` | `str` | URL to poster or thumbnail image |
| `genres` | `str` | Comma-separated genre names |
| `year` | `str` | Release year |
| `description` | `str` | Synopsis text |
| `rating` | `str` | Rating value (format varies by portal) |
| `duration` | `str` | Duration in seconds; may be `"0"` for series |
| `is_series` | `bool` | `True` if the item has seasons/episodes |
| `fav` | `bool` | `True` if in the user's favourites |

---

### Season

```python
from stb_reader import Season
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Season identifier |
| `name` | `str` | Display name (e.g. `"Season 1"`) |
| `video_id` | `str` | ID of the parent series |

---

### Episode

```python
from stb_reader import Episode
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Episode identifier |
| `name` | `str` | Episode title |
| `series_number` | `str` | Episode number within the season |
| `cmd` | `str` | Streaming command |

---

### EpisodeFile

```python
from stb_reader import EpisodeFile
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | File identifier |
| `name` | `str` | Quality/language label (e.g. `"English / HD (1080p)"`) |
| `cmd` | `str` | Streaming command for this file |

---

### PagedResult

```python
from stb_reader import PagedResult
```

Generic container returned by paginated methods. `T` is `Channel` or `Content`.

| Field | Type | Description |
|-------|------|-------------|
| `items` | `list[T]` | Items on this page |
| `total` | `int` | Total number of items across all pages |
| `page` | `int` | Current page number (1-indexed) |
| `per_page` | `int` | Number of items per page (set by the portal) |

---

## Exceptions

All exceptions are importable from `stb_reader`.

### Exception hierarchy

```
STBError
├── AuthError
├── StreamError
└── NotFoundError
```

### STBError

Base class for all library exceptions. Catch this to handle any library error.

**Raised by:** any method, when the portal returns a non-2xx status, invalid JSON,
or any other unexpected communication error.

---

### AuthError(STBError)

**Raised by:** `authenticate()` and any service method when the portal returns an
auth-failure response and automatic re-authentication also fails.

---

### StreamError(STBError)

**Raised by:** all `get_stream_url*` methods when the portal returns an error field
in the stream-link response.

---

### NotFoundError(STBError)

**Raised by:**
- `get_stream_url_by_id()` — channel ID not found
- `get_stream_url_by_first_file()` — episode has no files
- `get_stream_url_by_file_id()` — file ID not found among episode files
