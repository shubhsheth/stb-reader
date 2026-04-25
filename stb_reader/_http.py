import requests
from .exceptions import STBError

_USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
_X_USER_AGENT = "Model: MAG200; Link: WiFi"


class STBSession:
    def __init__(self, base_url: str, mac: str, serial: str, lang: str, timezone: str, portal_path: str = "stalker_portal/c/portal.php") -> None:
        self.base_url = base_url.rstrip("/")
        self.mac = mac
        self.serial = serial
        self.lang = lang
        self.timezone = timezone
        self.portal_path = portal_path.strip("/")
        self.token = ""
        self._session = requests.Session()

    def get(self, type: str, action: str, **params) -> dict:
        url = f"{self.base_url}/{self.portal_path}"
        query = {"JsHttpRequest": "1-xml", "type": type, "action": action, **params}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": _USER_AGENT,
            "X-User-Agent": _X_USER_AGENT,
            "Cookie": (
                f"mac={self.mac}; "
                f"lang={self.lang}; "
                f"timezone={self.timezone}; "
                f"PHPSESSID=null"
            ),
        }
        resp = self._session.get(url, params=query, headers=headers)
        if not resp.ok:
            raise STBError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()["js"]
