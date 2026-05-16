# Live TV (ITV)

All live TV requests use `type=itv`. The typical flow is: get genres → get ordered list (per genre) → create link (when user selects a channel).

All requests require the `Authorization: Bearer {token}` header obtained from the [handshake](./authentication.md).

---

## Get Genres

Returns the list of channel categories (genres).

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value |
|-----------|-------|
| `type` | `itv` |
| `action` | `get_genres` |
| `JsHttpRequest` | `1-xml` |

**Response**

```json
{
  "js": [
    {
      "id": "1",
      "title": "News",
      "alias": "news",
      "censored": 0
    },
    {
      "id": "10",
      "title": "Adult Content",
      "alias": "adult",
      "censored": 1
    }
  ]
}
```

The payload is an array of genre objects.

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Genre identifier; use as `genre` param in `get_ordered_list` |
| `title` | string | Localised display name |
| `alias` | string | Lowercase alias |
| `censored` | int | `1` if the genre requires parental unlock |

**Source:** [`erkexzcx/stalkerhek` — channels.go](https://github.com/erkexzcx/stalkerhek/blob/master/stalker/channels.go)

---

## Get Ordered List (Channels)

Returns a paginated list of channels, optionally filtered by genre.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `itv` | |
| `action` | `get_ordered_list` | |
| `genre` | `{genre_id}` | Genre ID from `get_genres`. Use `*` for all channels. Special values: `pvr`, `dvb` |
| `p` | `0` | Page number, **0-indexed** |
| `fav` | `0` | `1` to return only favourited channels |
| `sortby` | `number` | Sort order: `number`, `name`, or `fav` |
| `hd` | `0` | `1` to filter HD channels only |
| `force_ch_link_check` | `0` | **[needs verification]** |
| `quality` | _(optional)_ | Quality filter **[needs verification]** |
| `from_ch_id` | _(optional)_ | Channel ID to start from; used for pagination in some clients **[needs verification]** |
| `JsHttpRequest` | `1-xml` | |

**Response**

```json
{
  "js": {
    "total_items": 250,
    "max_page_items": 20,
    "cur_page": 0,
    "selected_item": 0,
    "data": [
      {
        "id": "1",
        "number": "1",
        "name": "BBC One",
        "cmd": "http://stream.example.com:1234/ch/123/",
        "logo": "http://portal.example.com/logos/bbc1.png",
        "tv_genre_id": "1",
        "genre_title": "News",
        "status": 1,
        "hd": 0,
        "censored": 0,
        "allow_pvr": 1,
        "allow_local_pvr": 0
      }
    ]
  }
}
```

Top-level response fields:

| Field | Type | Notes |
|-------|------|-------|
| `total_items` | int | Total channels matching the query |
| `max_page_items` | int | Number of items per page |
| `cur_page` | int | Current page number (0-indexed) |
| `selected_item` | int | Index of the pre-selected item |
| `data` | array | Array of channel objects |

Channel object fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Channel identifier |
| `number` | string | Display channel number |
| `name` | string | Channel name |
| `cmd` | string | Streaming command; pass this value to `create_link` |
| `logo` | string | URL to channel logo image |
| `tv_genre_id` | string | Genre identifier |
| `genre_title` | string | Genre display name |
| `status` | int | `1` if the channel is active |
| `hd` | int | `1` if the channel is HD |
| `censored` | int | `1` if the channel requires parental unlock |
| `allow_pvr` | int | `1` if server-side PVR is available |
| `allow_local_pvr` | int | `1` if local PVR recording is supported |

**Pagination:** To retrieve all channels, iterate pages starting at `p=0` until you have collected `total_items` entries. Total pages = `ceil(total_items / max_page_items)`.

**Sources:**
- [`grinco/stalker_portal-1` — itv.class.php](https://github.com/grinco/stalker_portal-1/blob/master/server/lib/itv.class.php)
- [`iptvhakr/stalker_portal` — itv.class.php](https://github.com/iptvhakr/stalker_portal/blob/master/server/lib/itv.class.php)
- [`esxbr/plugin.video.stalker` — load_channels.py](https://github.com/esxbr/plugin.video.stalker/blob/master/load_channels.py)

---

## Create Link

Resolves the `cmd` value from `get_ordered_list` into a playable stream URL. Call this when the user selects a channel.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `itv` | |
| `action` | `create_link` | |
| `cmd` | `http://stream.example.com:1234/ch/123/` | The `cmd` value from the channel object |
| `series` | _(optional)_ | Series identifier for linked content **[needs verification]** |
| `forced_storage` | `undefined` | Storage override; `undefined` is the default value sent by most clients |
| `disable_ad` | `0` | `1` to disable ad insertion |
| `download` | `0` | `1` to request a downloadable link instead of a stream |
| `force_ch_link_check` | `0` | **[needs verification]** |
| `JsHttpRequest` | `1-xml` | |

**Success Response**

```json
{
  "js": {
    "id": "1",
    "cmd": "http://stream.example.com:1234/ch/123/?token=ABC123&expires=1735689600",
    "streamer_id": "1",
    "link_id": "5678",
    "load": "45",
    "error": ""
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Channel identifier |
| `cmd` | string | **Playable stream URL** — this is the URL to pass to a media player |
| `streamer_id` | string | Streaming server identifier |
| `link_id` | string | Link session identifier |
| `load` | string | Streaming server load as a percentage string |
| `error` | string | Empty string on success |

**Error Response**

```json
{
  "js": {
    "id": "0",
    "cmd": "",
    "storage_id": "",
    "load": "",
    "error": "nothing_to_play"
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `error` | string | Error code. Known values: `nothing_to_play`. Other values are portal-specific. |

**Sources:**
- [`grinco/stalker_portal-1` — itv.class.php `createLink` method](https://github.com/grinco/stalker_portal-1/blob/master/server/lib/itv.class.php)
- [`Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1` — stalker.py](https://github.com/Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1/blob/main/stalker.py)
