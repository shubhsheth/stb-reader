# Ministra / Stalker Portal STB Client Protocol

Documentation of the HTTP protocol used by set-top box (STB) devices to communicate with a Ministra (formerly Stalker Middleware) portal.

---

## Scope

This repo documents the **STB client-facing protocol** — the requests an STB device (MAG box, emulator, or compatible app) makes against the portal. It covers:

- [Authentication](./authentication.md) — handshake and device profile
- [Live TV](./live-tv.md) — channel categories, channel list, stream URL creation
- [VOD & Series](./vod-series.md) — content categories, listings, season/episode navigation, stream URL creation

---

## Protocol Overview

All requests are HTTP GET. Every request routes through a single endpoint:

```
{base_url}/stalker_portal/c/portal.php
```

Where `{base_url}` is the portal host (e.g. `http://192.168.1.10:8080`).

The `type` and `action` query parameters determine which resource and operation are targeted. All responses are JSON wrapped in a `"js"` key:

```json
{ "js": <payload> }
```

The `JsHttpRequest=1-xml` parameter appears on virtually every request. Its purpose is to signal the server to return JSON rather than XML. It is treated as a required parameter in practice.

---

## Common Request Headers

Every request after the initial handshake must include these headers:

| Header | Example Value | Notes |
|--------|--------------|-------|
| `Authorization` | `Bearer C00F7332ED272F00D5FD3E82F567A282` | Token obtained from handshake |
| `User-Agent` | `Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG250 stbapp ver: 4 rev: 2116 Mobile Safari/533.3` | STB browser UA |
| `X-User-Agent` | `Model: MAG250; Link: Ethernet` | STB model and connection type |
| `Cookie` | `mac=00:1A:79:18:05:75; stb_lang=en; timezone=Europe/London` | MAC address, language, timezone |

The `Cookie` header carries the device's MAC address. Some portals use MAC address filtering and will reject requests from unrecognised MACs.

---

## Startup Sequence

An STB performs these requests in order on startup:

```
1. Handshake        type=stb  action=handshake       → obtain token
2. Get Profile      type=stb  action=get_profile      → device config + user info
3. Get Genres       type=itv  action=get_genres        → channel category list
4. Get Channels     type=itv  action=get_ordered_list  → paginated channel list per genre
5. Create Link      type=itv  action=create_link       → resolve playable stream URL
```

For VOD/Series the flow is:

```
1–2. Same auth sequence as above
3. Get Categories   type=vod  action=get_categories    → content category list
4. Get Content      type=vod  action=get_ordered_list  → paginated content list
5. (Series only)    type=vod  action=get_ordered_list  → seasons, then episodes
6. Create Link      type=vod  action=create_link       → resolve playable stream URL
```

---

## Sources

All schemas in this documentation are derived from the following open-source repositories and implementations:

- [`erkexzcx/stalkerhek`](https://github.com/erkexzcx/stalkerhek) — Go proxy revealing real request/response structure
- [`iptvhakr/stalker_portal`](https://github.com/iptvhakr/stalker_portal) — PHP server source (`itv.class.php`, `vod.class.php`, `load.php`)
- [`grinco/stalker_portal-1`](https://github.com/grinco/stalker_portal-1) — Alternate PHP source with response structures
- [`esxbr/plugin.video.stalker`](https://github.com/esxbr/plugin.video.stalker) — Python Kodi plugin (client-side parsing)
- [`Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1`](https://github.com/Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1) — Standalone Python player
- [`agsimeonov/StalkerTalker`](https://github.com/agsimeonov/StalkerTalker) — Python client
- [`DimitarCC/iptv-m3u-reader`](https://github.com/DimitarCC/iptv-m3u-reader) — Series field identification

Entries marked **[needs verification]** have ambiguity across sources and should be confirmed against live traffic.
