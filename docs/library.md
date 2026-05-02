# Library API

The library feature lets you add movies and series to a persistent library. On add, the server
walks the portal's season/episode tree and writes Jellyfin-compatible `.strm` files to disk.
Each `.strm` file contains a single proxy URL that Jellyfin uses to fetch the stream.

## Concept

```
browse GET /vod/content
  → POST /library/add/{id}  (with name, year, is_series from browse result)
    → .strm files written to STRM_OUTPUT_DIR
    → Jellyfin picks up files, shows show with seasons + episodes
    → episode playback hits proxy → proxy resolves stream URL → Jellyfin plays it
```

Run `POST /library/sync` (or let the background task do it) to pick up newly added episodes
without re-adding the series.

---

## Endpoints

### `POST /library/add/{content_id}`

Add content to the library. Provide the name, year, and type from your browse results.

**Request body:**
```json
{"name": "Breaking Bad", "year": "2008", "is_series": true}
```

**Responses:**
- `201` — item added; body includes all item fields plus `strm_count` (number of `.strm` files written)
- `409` — already in the library

For a movie, one `.strm` file is written. For a series, one file is written per episode.

---

### `GET /library`

List all library items. Each item includes:
- `content_id`, `name`, `year`, `is_series`
- `added_at`, `last_synced_at` (ISO 8601 UTC; `last_synced_at` is null until first sync)
- `strm_count` (total `.strm` files for this item)

---

### `DELETE /library/{content_id}`

Remove an item. Deletes all associated `.strm` files from disk and all DB records.

- `204` — deleted
- `404` — not in library

---

### `POST /library/sync/{content_id}`

Sync a single series: walk the portal tree and write `.strm` files for any episodes not
already in the DB. No-op for movies (returns `0`).

**Response:** `{"new_files": 3}`

- `404` — not in library

---

### `POST /library/sync`

Sync all series in the library. Returns a per-item summary:

```json
[
  {"content_id": "123", "new_files": 2},
  {"content_id": "456", "new_files": 0}
]
```

---

## File Layout

Movies follow Jellyfin's movie naming convention:
```
{STRM_OUTPUT_DIR}/Movies/{Name} ({Year})/{Name} ({Year}).strm
```

Series follow Jellyfin's episode naming convention:
```
{STRM_OUTPUT_DIR}/TV/{Name} ({Year})/Season {NN}/{Name} ({Year}) - S{NN}E{NN} - {Episode Name}.strm
```

Filenames are sanitised: the characters `/ \ : * ? " < > |` are replaced with `-`.

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `STRM_OUTPUT_DIR` | yes | — | Root directory for `.strm` files |
| `STRM_SERVER_BASE_URL` | yes | — | Base URL embedded in `.strm` files (see below) |
| `STRM_DATA_DIR` | yes | — | Directory for persistent data; DB created at `{STRM_DATA_DIR}/library.db` |
| `STRM_SYNC_INTERVAL_HOURS` | no | `6` | Hours between background syncs; `0` disables |

The server refuses to start if any required variable is missing or empty.

---

## Choosing `STRM_SERVER_BASE_URL`

The URL in each `.strm` file must be reachable by whoever fetches the stream. Jellyfin's
playback mode determines who that is:

### Docker service name (recommended starting point)

```
STRM_SERVER_BASE_URL=http://stb-reader:8000
```

Works when Jellyfin and stb-reader are in the same Docker Compose network. Jellyfin's server
process resolves the service name. Breaks for direct-play clients outside Docker.

### Host LAN IP

```
STRM_SERVER_BASE_URL=http://192.168.1.x:8000
```

Works for direct-play on the LAN (client device fetches the URL directly). Does not work for
remote clients outside the LAN.

### Reverse proxy hostname

```
STRM_SERVER_BASE_URL=https://stb.yourdomain.com
```

Works for all playback modes and all clients including remote. Requires a reverse proxy in
front of stb-reader with a public hostname and TLS.

**Changing this value:** update `STRM_SERVER_BASE_URL`, then re-run `POST /library/sync` for
each series (or `POST /library/sync` for all). New `.strm` files will be written with the
updated URL. You must also delete and re-add movies since sync is a no-op for movies.

---

## Background Sync

On startup, if `STRM_SYNC_INTERVAL_HOURS > 0`, the server starts an asyncio background task
that sleeps for the configured interval then runs `POST /library/sync` logic. The task runs
*after* the first sleep (not immediately on startup) to avoid a burst of portal requests on
every restart.

Set `STRM_SYNC_INTERVAL_HOURS=0` to disable automatic sync entirely.
