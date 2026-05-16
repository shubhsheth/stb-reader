# CLI Reference

The `stb` command-line tool lets you browse and stream STB portal content from a terminal.

## Installation

```bash
pip install stb-reader
```

Verify the tool is available:

```bash
stb --help
```

## Configuration

Run `stb init` once to save your portal credentials to `~/.stb/config`:

```bash
stb init
```

You will be prompted for:

| Prompt | Default | Notes |
|---|---|---|
| Portal URL (no port) | _(required)_ | e.g. `http://192.168.1.10` |
| Port | _(blank)_ | e.g. `8080`; leave blank if included in URL |
| MAC address | _(required)_ | e.g. `00:1A:79:XX:XX:XX` |
| Serial | `000000000000` | Device serial number |
| Language | `en` | Portal language code |
| Timezone | `Europe/London` | IANA timezone name |
| Portal path | `stalker_portal/c/portal.php` | Path to the portal endpoint |

The config is saved as plain JSON and can be edited by hand:

```json
{
  "url": "http://192.168.1.10",
  "port": "8080",
  "mac": "00:1A:79:XX:XX:XX",
  "serial": "000000000000",
  "lang": "en",
  "timezone": "Europe/London",
  "portal_path": "stalker_portal/c/portal.php"
}
```

All commands except `stb init` read this file and exit with an error if it is missing.

## Global Flags

| Flag | Description |
|---|---|
| `--debug` | Print raw portal responses to stderr. Useful for diagnosing auth or stream failures. |

```bash
stb --debug live genres
```

## Live TV

### `stb live genres`

List all live TV genres.

```
ID    Title
----  -----------
1     General
2     Sports
3     News
```

### `stb live channels`

List channels, optionally filtered by genre or HD status.

```bash
stb live channels
stb live channels --genre 2
stb live channels --hd
stb live channels --page 2
```

| Flag | Default | Description |
|---|---|---|
| `--genre <id>` | `*` | Filter by genre ID (from `stb live genres`) |
| `--hd` | off | Show HD channels only |
| `--page <n>` | `1` | Page number |

```
#     Name            Genre ID  HD   CMD
----  --------------  --------  ---  -------------------
101   BBC One         1               ffmpeg://...
102   Sky Sports HD   2         yes  ffmpeg://...

Page 1 of 5 (48 total)
```

The `CMD` value is used with `stb stream` to resolve a playable URL.

## VOD

### `stb vod categories`

List all VOD categories.

```
ID    Title
----  -----------
1     Action
2     Comedy
```

### `stb vod list`

List VOD content, optionally filtered by category.

```bash
stb vod list
stb vod list --category 1
stb vod list --page 2
```

| Flag | Default | Description |
|---|---|---|
| `--category <id>` | `*` | Filter by category ID (from `stb vod categories`) |
| `--page <n>` | `1` | Page number |

```
ID    Name            Year  Genres   Series  CMD
----  --------------  ----  -------  ------  -----------
42    Inception       2010  Action           ffmpeg://...
99    Breaking Bad    2008  Drama    yes     ffmpeg://...

Page 1 of 12 (115 total)
```

### `stb vod seasons <series_id>`

List seasons for a series. The `series_id` is the ID from `stb vod list`.

```bash
stb vod seasons 99
```

```
ID    Name
----  --------
1     Season 1
2     Season 2
```

### `stb vod episodes <series_id> <season_id>`

List episodes for a season.

```bash
stb vod episodes 99 1
stb vod episodes 99 1 --page 2
```

| Flag | Default | Description |
|---|---|---|
| `--page <n>` | `1` | Page number |

```
ID    Name          #   CMD
----  ------------  --  -----------
201   Pilot         1   ffmpeg://...
202   Cat's in the  2   ffmpeg://...

Page 1 of 7 (62 total)
```

The `CMD` value is used with `stb stream` to resolve a playable URL.

## Stream URLs

### `stb stream --type <live|vod> <cmd>`

Resolve a stream URL and print it to stdout. The `--type` flag is required. The `<cmd>` value comes from the `CMD` column of a prior listing command.

```bash
stb stream --type live "ffmpeg://..."
stb stream --type vod "ffmpeg://..."
```

Pipe directly to a media player:

```bash
stb stream --type live "ffmpeg://..." | xargs mpv
```

## Error Handling

| Situation | Message | Exit code |
|---|---|---|
| Config file missing | `No config found. Run 'stb init' first.` | 1 |
| Authentication failure | Short description to stderr | 1 |
| Stream resolution failure | Short description to stderr | 1 |

No Python tracebacks are shown. Use `--debug` to see raw portal responses when diagnosing failures.
