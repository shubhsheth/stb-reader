# Library API

The library feature lets you add movies and series to a persistent library. On add, the server
walks the portal's season/episode tree and writes Jellyfin-compatible `.strm` files to disk.
Each `.strm` file contains a single proxy URL that Jellyfin uses to fetch the stream.

## Concept

```
browse GET /vod/content or GET /vod/categories
  → POST /library/content/{id}  or  POST /library/category/{id}
    → .strm files written to STRM_OUTPUT_DIR
    → Jellyfin picks up files, shows show with seasons + episodes
    → episode playback hits proxy → proxy resolves stream URL → Jellyfin plays it
```

Run `POST /library/sync` (or let the background task do it) to pick up newly added episodes
without re-adding the series.

---

## Endpoints

### `POST /library/content/{content_id}`

Add content to the library, or sync it if already present (idempotent). File-writing happens
in a background task.

**Responses:**
- `202` — accepted; `.strm` files will be written asynchronously
- `404` — content not found in the local portal cache

For a movie, one `.strm` file is written. For a series, one file is written per episode.
Re-posting a series already in the library writes only new episodes (no-op for movies).

---

### `DELETE /library/content/{content_id}`

Remove an item. Deletes all associated `.strm` files from disk and clears library flags.

- `204` — deleted
- `404` — not in library

---

### `POST /library/category/{category_id}`

Add or sync every content item linked to a category (idempotent). Each item is processed the
same way as `POST /library/content/{content_id}`. Also marks the category itself as
in-library (`in_library = 1`, `added_at` set on first call).

**Responses:**
- `202` — accepted; all fan-out tasks run asynchronously
- `404` — category not found in the local portal cache

---

### `DELETE /library/category/{category_id}`

Remove every content item in the category from the library, regardless of whether those items
belong to other categories. Clears the category's in-library flag.

- `204` — done (even if no items were in the library)
- `404` — category not found in the local portal cache

---

### `GET /library`

List all library items. Each item includes:
- `content_id`, `name`, `year`, `is_series`
- `added_at`, `last_synced_at` (ISO 8601 UTC; `last_synced_at` is null until first sync)
- `strm_count` (total `.strm` files for this item)

---

### `POST /library/sync`

Sync all series in the library: walk the portal tree and write `.strm` files for any episodes
not already in the DB. No-op for movies. Runs as a background task.

- `204` — accepted

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
| `STRM_DATA_DIR` | yes | — | Directory for persistent data; DB created at `{STRM_DATA_DIR}/data.db` |
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
