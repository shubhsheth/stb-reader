# stb-reader

Python client library for [Ministra/Stalker](https://ministra.com/) STB portals. Retrieve live-TV channels, VOD content, series, episodes, and stream URLs with simple method calls.

## Installation

```bash
pip install stb-reader
```

Requires Python 3.11+ and has a single runtime dependency: `requests`.

## Quick start

```python
from stb_reader import STBClient

client = STBClient(
    base_url="http://your-portal.example.com",
    mac="00:1A:79:XX:XX:XX",
)
client.authenticate()

# Live TV
genres = client.live_tv.get_genres()
channels = client.live_tv.get_channels(genre_id="*", page=1)
stream_url = client.live_tv.get_stream_url(channels.items[0].cmd)

# VOD
categories = client.vod.get_categories()
content = client.vod.get_content(category_id="*", page=1)

# Series
seasons = client.vod.get_seasons(series_id="123")
episodes = client.vod.get_episodes(series_id="123", season_id=seasons[0].id)
stream_url = client.vod.get_stream_url_by_first_file(
    series_id="123",
    season_id=seasons[0].id,
    episode_id=episodes[0].id,
)
```

## API reference

### `STBClient(base_url, mac, serial, lang, timezone, portal_path)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_url` | required | Portal base URL |
| `mac` | required | Device MAC address |
| `serial` | `"000000000000"` | Device serial |
| `lang` | `"en"` | Portal language |
| `timezone` | `"Europe/London"` | Portal timezone |
| `portal_path` | `"stalker_portal/c/portal.php"` | Path to portal PHP endpoint |

### `client.live_tv`

| Method | Returns | Description |
|--------|---------|-------------|
| `get_genres()` | `list[Genre]` | All channel genres |
| `get_channels(genre_id, page, sort, hd, fav)` | `PagedResult[Channel]` | Paginated channel list |
| `get_stream_url(cmd)` | `str` | Resolved stream URL for a channel `cmd` |
| `get_stream_url_by_id(channel_id)` | `str` | Resolved stream URL by channel ID |

### `client.vod`

| Method | Returns | Description |
|--------|---------|-------------|
| `get_categories()` | `list[Category]` | All VOD categories |
| `get_content(category_id, page, sort, fav)` | `PagedResult[Content]` | Paginated VOD content |
| `get_seasons(series_id)` | `list[Season]` | Seasons for a series |
| `get_episodes(series_id, season_id)` | `list[Episode]` | All episodes in a season |
| `get_episode_files(series_id, season_id, episode_id)` | `list[EpisodeFile]` | Quality variants for an episode |
| `get_stream_url(cmd)` | `str` | Resolved stream URL for a VOD `cmd` |
| `get_stream_url_by_content_id(content_id)` | `str` | Stream URL for a movie by ID |
| `get_stream_url_by_first_file(series_id, season_id, episode_id)` | `str` | Stream URL for first file of an episode |
| `get_stream_url_by_file_id(series_id, season_id, episode_id, file_id)` | `str` | Stream URL for a specific file |

## Exceptions

All exceptions are importable from `stb_reader`:

| Exception | Raised when |
|-----------|-------------|
| `STBError` | Base class for all library errors |
| `AuthError` | Authentication / token failure |
| `StreamError` | Portal rejects a stream request |
| `NotFoundError` | Requested item not found |

## Documentation

Full guides are in [`docs/guide/`](docs/guide/):

- [CLI reference](docs/guide/cli.md) — `stb` command-line tool
- [Getting started](docs/guide/getting-started.md) — installation, configuration, first call
- [Authentication](docs/guide/authentication.md) — token lifecycle, auto-reauth, error handling
- [Live TV](docs/guide/live-tv.md) — genres, channels, stream URLs
- [VOD — Movies](docs/guide/vod.md) — categories, content listing, movie streams
- [Series](docs/guide/series.md) — seasons, episodes, quality selection
- [Pagination](docs/guide/pagination.md) — `PagedResult`, fetch-all-pages pattern
- [Error handling](docs/guide/error-handling.md) — all exceptions, recovery patterns
- [API reference](docs/guide/api-reference.md) — complete method, model, and exception reference

## License

MIT
