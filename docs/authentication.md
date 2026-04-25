# Authentication

The STB authentication flow is two steps: a handshake to obtain a token, followed by a profile fetch that returns device and user configuration.

---

## Handshake

Obtains a session token. This is always the first request an STB makes.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `stb` | |
| `action` | `handshake` | |
| `prehash` | `0` | |
| `token` | _(empty string)_ | Empty on first request; may be reused on reconnect |
| `JsHttpRequest` | `1-xml` | Required on all requests |

Headers:

| Header | Example |
|--------|---------|
| `User-Agent` | `Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG250 stbapp ver: 4 rev: 2116 Mobile Safari/533.3` |
| `X-User-Agent` | `Model: MAG250; Link: Ethernet` |
| `Cookie` | `mac=00:1A:79:18:05:75; stb_lang=en; timezone=Europe/London` |

Cookie fields:

| Field | Example | Notes |
|-------|---------|-------|
| `mac` | `00:1A:79:18:05:75` | Device MAC address |
| `stb_lang` | `en` | UI language code |
| `timezone` | `Europe/London` | IANA timezone name |

`PHPSESSID` is **not** manually set. The server issues a `Set-Cookie: PHPSESSID=…` on this response; the HTTP client must store it and forward it on all subsequent requests automatically.

**Response**

```json
{
  "js": {
    "token": "C00F7332ED272F00D5FD3E82F567A282",
    "random": "..."
  }
}
```

Response fields:

| Field | Type | Notes |
|-------|------|-------|
| `token` | string | Session token; include as `Authorization: Bearer {token}` on all subsequent requests. If empty, the token sent in the request was accepted as-is. |
| `random` | string | Optional. If present: (1) compute `signature = SHA256(random).hexdigest().upper()`; (2) echo the raw value back as both `X-Random` and `Random` headers on every subsequent request. Portals that issue `random` will reject content requests missing these headers. |

**Sources:**
- [`erkexzcx/stalkerhek` — authentication.go](https://github.com/erkexzcx/stalkerhek/blob/master/stalker/authentication.go)
- [`LegendaryFire/magplex` — device.py](https://github.com/LegendaryFire/magplex/blob/master/magplex/device/device.py)

---

## Get Profile

Retrieves device configuration and user account information. Called immediately after handshake.

**Request**

```
GET {base_url}/stalker_portal/c/portal.php
```

Query parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `type` | `stb` | |
| `action` | `get_profile` | |
| `hd` | `1` | HD preference flag (0 or 1) |
| `sn` | `022017J023063` | Device serial number |
| `stb_type` | `MAG250` | STB model identifier |
| `image_version` | `218` | Firmware image version number |
| `auth_second_step` | `0` | |
| `hw_version` | `1.7-BD-00` | Hardware version string |
| `num_banks` | `1` | |
| `not_valid_token` | `0` | Set to `1` if previous token was rejected |
| `device_id` | _(device-specific)_ | Primary device identifier **[needs verification]** |
| `device_id2` | _(device-specific)_ | Secondary device identifier **[needs verification]** |
| `signature` | _(device-specific)_ | Device signature **[needs verification]** |
| `ver` | _(version string)_ | Client version string **[needs verification]** |
| `JsHttpRequest` | `1-xml` | |

Headers:

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {token}` |
| `User-Agent` | _(same STB UA as handshake)_ |
| `X-User-Agent` | `Model: MAG250; Link: Ethernet` |
| `Cookie` | `mac={MAC}; stb_lang=en; timezone={timezone}` |

**Response**

```json
{
  "js": {
    "id": "42",
    "name": "username",
    "sname": "Display Name",
    "pass": "hashed_password",
    "mac": "00:1A:79:18:05:75",
    "ip": "192.168.1.100",
    "lang": "en",
    "locale": "en_US",
    "timezone": "Europe/London",
    "stb_type": "MAG250",
    "hd": 1,
    "bright": 50,
    "contrast": 50,
    "saturation": 50,
    "volume": 50,
    "video_out": 1,
    "aspect": 1,
    "city_id": 1,
    "sn": "022017J023063"
  }
}
```

Response fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | User/subscriber identifier |
| `name` | string | Login username |
| `sname` | string | Display name |
| `pass` | string | Hashed password |
| `mac` | string | Device MAC address |
| `ip` | string | Client IP as seen by the server |
| `lang` | string | Language code (e.g. `en`) |
| `locale` | string | Locale string (e.g. `en_US`) |
| `timezone` | string | IANA timezone name |
| `stb_type` | string | STB model |
| `hd` | int | HD enabled: `0` or `1` |
| `bright` | int | Brightness setting (0–100) |
| `contrast` | int | Contrast setting (0–100) |
| `saturation` | int | Saturation setting (0–100) |
| `volume` | int | Volume setting (0–100) |
| `video_out` | int | Video output mode identifier |
| `aspect` | int | Aspect ratio identifier |
| `city_id` | int | City identifier for localisation |
| `sn` | string | Device serial number |

**Sources:**
- [`agsimeonov/StalkerTalker` — session.py](https://github.com/agsimeonov/StalkerTalker/blob/master/session.py)
- [`esxbr/plugin.video.stalker` — load_channels.py](https://github.com/esxbr/plugin.video.stalker/blob/master/load_channels.py)
- [`Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1` — stalker.py](https://github.com/Cyogenus/IPTV-MAC-STALKER-PLAYER-BY-MY-1/blob/main/stalker.py)
