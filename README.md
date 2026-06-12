# stb-reader

Python client library and CLI for [Ministra/Stalker](https://ministra.com/) STB portals. Browse live TV channels, VOD content, and series, or resolve stream URLs — from Python code or straight from the terminal.

## Install

```bash
pip install stb-reader
```

Requires Python 3.11+.

## Quick start — CLI

```bash
stb init                       # save portal URL and MAC address once
stb live channels              # browse channels
stb stream --type live <cmd>   # get a stream URL
```

See the [CLI reference](docs/guide/cli.md) for all commands.

## Quick start — Python

```python
from stb_reader import STBClient

client = STBClient(
    base_url="http://your-portal.example.com",
    mac="00:1A:79:XX:XX:XX",
)
client.authenticate()

# Live TV
channels = client.live_tv.get_channels(genre_id="*", page=1)
stream_url = client.live_tv.get_stream_url(channels.items[0].cmd)

# VOD
content = client.vod.get_content(category_id="*", page=1)

# Series
seasons = client.vod.get_seasons(series_id="123")
episodes = client.vod.get_episodes(series_id="123", season_id=seasons.items[0].id)
stream_url = client.vod.get_stream_url_by_first_file(
    series_id="123",
    season_id=seasons.items[0].id,
    episode_id=episodes.items[0].id,
)
```

## Documentation

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
