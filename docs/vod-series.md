# VOD & Series

All VOD and series requests use `type=vod`. The typical flow is: get categories → get ordered list (content) → for series: get seasons → get episodes → create link.

All requests require the `Authorization: Bearer {token}` header obtained from the [handshake](./authentication.md).

---

## Get Categories

Returns the list of VOD/series categories.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value |
|-----------|-------|
| `type` | `vod` |
| `action` | `get_categories` |
| `JsHttpRequest` | `1-xml` |

**Response**

```json
{
  "js": [
    {
      "id": "1",
      "title": "Action",
      "alias": "action",
      "censored": 0
    },
    {
      "id": "2",
      "title": "Drama",
      "alias": "drama",
      "censored": 0
    }
  ]
}
```

The payload is an array of category objects.

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Category identifier; use as `category` param in `get_ordered_list` |
| `title` | string | Localised display name |
| `alias` | string | Lowercase alias |
| `censored` | int | `1` if the category requires parental unlock |

**Sources:**
- [`Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1` — stalker.py](https://github.com/Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1/blob/main/stalker.py)
- [`iptvhakr/stalker_portal` — vod.class.php `getCategories`](https://github.com/iptvhakr/stalker_portal/blob/master/server/lib/vod.class.php)

---

## Get Ordered List — Content

Returns a paginated list of movies and series. Items with `is_series=1` require further navigation through seasons and episodes before a stream URL can be created.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `vod` | |
| `action` | `get_ordered_list` | |
| `category` | `{category_id}` | Category ID from `get_categories`. Omit or leave empty for all content. |
| `p` | `1` | Page number, **1-indexed** |
| `sortby` | `added` | Sort order: `added`, `popular`, `rating`, `name` |
| `not_ended` | `0` | `1` to exclude finished/complete series |
| `fav` | `0` | `1` to return only favourited items |
| `JsHttpRequest` | `1-xml` | |

**Response**

```json
{
  "js": {
    "total_items": 500,
    "max_page_items": 20,
    "data": [
      {
        "id": "101",
        "name": "Inception",
        "cmd": "/media/file_101.mpg",
        "screenshot_uri": "http://portal.example.com/screenshots/101.jpg",
        "genres_str": "Sci-Fi, Thriller",
        "for_rent": 0,
        "fav": 0,
        "lock": 0,
        "is_series": 0,
        "year": "2010",
        "description": "A thief who steals corporate secrets...",
        "rating": "8.8",
        "duration": "8880"
      },
      {
        "id": "202",
        "name": "Breaking Bad",
        "cmd": "/media/file_202.mpg",
        "screenshot_uri": "http://portal.example.com/screenshots/202.jpg",
        "genres_str": "Drama, Crime",
        "for_rent": 0,
        "fav": 0,
        "lock": 0,
        "is_series": 1,
        "year": "2008",
        "description": "A high school chemistry teacher...",
        "rating": "9.5",
        "duration": "0"
      }
    ]
  }
}
```

Top-level response fields:

| Field | Type | Notes |
|-------|------|-------|
| `total_items` | int | Total items matching the query |
| `max_page_items` | int | Items per page |
| `data` | array | Array of content objects |

Content object fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Content identifier; use as `movie_id` for series navigation |
| `name` | string | Title |
| `cmd` | string | Streaming command; pass to `create_link` for movies. For series (`is_series=1`), use `id` to navigate seasons first. |
| `screenshot_uri` | string | URL to poster/thumbnail image |
| `genres_str` | string | Comma-separated genre names |
| `for_rent` | int | `1` if the item requires rental/purchase |
| `fav` | int | `1` if the item is in the user's favourites |
| `lock` | int | `1` if the item is parental-locked |
| `is_series` | int | `1` if this is a series (has seasons/episodes); `0` for a standalone movie |
| `year` | string | Release year |
| `description` | string | Synopsis text |
| `rating` | string | Rating value (format varies by portal) |
| `duration` | string | Duration in seconds; may be `"0"` for series |

**Pagination:** Iterate pages starting at `p=1`. Total pages = `ceil(total_items / max_page_items)`.

**Sources:**
- [`esxbr/plugin.video.stalker` — load_channels.py](https://github.com/esxbr/plugin.video.stalker/blob/master/load_channels.py)
- [`Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1` — stalker.py](https://github.com/Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1/blob/main/stalker.py)
- [`DimitarCC/iptv-m3u-reader` — StalkerProvider.py](https://github.com/DimitarCC/iptv-m3u-reader/blob/main/src/StalkerProvider.py)

---

## Get Ordered List — Seasons

For items where `is_series=1`, retrieve the list of seasons before fetching episodes. Pass `season_id=0` and `episode_id=0` to list seasons.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `vod` | |
| `action` | `get_ordered_list` | |
| `movie_id` | `{series_id}` | The `id` from the content list item |
| `season_id` | `0` | Zero to list seasons |
| `episode_id` | `0` | Zero to list seasons |
| `p` | `1` | Page number |
| `JsHttpRequest` | `1-xml` | |

**Response**

```json
{
  "js": {
    "total_items": 5,
    "data": [
      {
        "id": "1",
        "video_id": "202",
        "name": "Season 1",
        "is_season": true
      },
      {
        "id": "2",
        "video_id": "202",
        "name": "Season 2",
        "is_season": true
      }
    ]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Season identifier; use as `season_id` to fetch episodes |
| `video_id` | string | Parent series identifier |
| `name` | string | Season display name (e.g. `"Season 1"`) |
| `is_season` | bool | Always `true` for season objects |

---

## Get Ordered List — Episodes

Pass a non-zero `season_id` and `episode_id=0` to list episodes within a season.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `vod` | |
| `action` | `get_ordered_list` | |
| `movie_id` | `{series_id}` | The `id` from the content list item |
| `season_id` | `{season_id}` | The `id` from the seasons response |
| `episode_id` | `0` | |
| `p` | `1` | Page number |
| `JsHttpRequest` | `1-xml` | |

**Response**

```json
{
  "js": {
    "total_items": 7,
    "data": [
      {
        "id": "5001",
        "name": "Pilot",
        "series_number": "1",
        "cmd": "/media/file_5001.mpg"
      },
      {
        "id": "5002",
        "name": "Cat's in the Bag",
        "series_number": "2",
        "cmd": "/media/file_5002.mpg"
      }
    ]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Episode identifier |
| `name` | string | Episode title |
| `series_number` | string | Episode number within the season |
| `cmd` | string | Streaming command; pass to `create_link` |

**Sources (seasons & episodes):**
- [`Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1` — stalker.py](https://github.com/Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1/blob/main/stalker.py)
- [`iptvhakr/stalker_portal` — vod.class.php `getOrderedList`, `getSeasonsList`, `getEpisodesList`](https://github.com/iptvhakr/stalker_portal/blob/master/server/lib/vod.class.php)

---

## Create Link

Resolves the `cmd` value from a movie or episode into a playable stream URL.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `vod` | |
| `action` | `create_link` | |
| `cmd` | `/media/file_5001.mpg` | The `cmd` value from the content/episode object **[exact format needs verification against live portal]** |
| `series` | `{episode_number}` | For series episodes, the `series_number` value. Omit for movies. |
| `forced_storage` | _(optional)_ | Storage server override |
| `JsHttpRequest` | `1-xml` | |

**Success Response**

```json
{
  "js": {
    "cmd": "http://storage.example.com:80/vod/file_5001.m3u8",
    "url": "http://storage.example.com:80/vod/file_5001.m3u8",
    "error": ""
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `cmd` | string | Playable stream URL |
| `url` | string | Same as `cmd`; both fields are present in most responses **[needs verification]** |
| `error` | string | Empty string on success |

**Stream URL formats**

The returned URL format depends on the portal's streaming backend. Known formats observed in open-source implementations:

| Format | Example |
|--------|---------|
| Direct HTTP | `http://storage.example.com/vod/file.mp4` |
| HLS | `http://storage.example.com/vod/file.m3u8` |
| ffmpeg-wrapped | `ffmpeg http://storage.example.com/vod/file.mp4` |
| Tokenised (Flussonic, Nginx, Wowza, Akamai) | URL contains `token=` or `expires=` query params |

When the response `cmd` starts with `ffmpeg `, strip the prefix before passing the URL to a media player.

**Error Response**

```json
{
  "js": {
    "cmd": "",
    "url": "",
    "error": "not_allow"
  }
}
```

Known error values: `not_allow`, `nothing_to_play`. Other values are portal-specific.

**Sources:**
- [`iptvhakr/stalker_portal` — vod.class.php `createLink`](https://github.com/iptvhakr/stalker_portal/blob/master/server/lib/vod.class.php)
- [`Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1` — stalker.py](https://github.com/Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1/blob/main/stalker.py)
- [`kens13/Kens13_Repo` — stalker.py](https://github.com/kens13/Kens13_Repo)
