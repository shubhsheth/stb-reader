import logging
import threading
from collections.abc import Callable
from urllib.parse import urlparse
import requests
from .exceptions import AuthError, STBError, StreamError

_reauth_local = threading.local()

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
_X_USER_AGENT = "Model: MAG200; Link: WiFi"

_AUTH_FAILURE_PHRASES = {"Authorization failed", "Access denied"}
_REQUEST_TIMEOUT = 10


def _as_list(data) -> list:
    """Normalise portal responses that return either a list or {"data": [...]}."""
    return data if isinstance(data, list) else data.get("data", [])


def _is_auth_failure(text: str) -> bool:
    return any(phrase in text for phrase in _AUTH_FAILURE_PHRASES)


class STBSession:
    def __init__(self, base_url: str, mac: str, serial: str, lang: str, timezone: str, portal_path: str = "stalker_portal/c/portal.php") -> None:
        self.base_url = base_url.rstrip("/")
        self.mac = mac
        self.serial = serial
        self.lang = lang
        self.timezone = timezone
        self.portal_path = portal_path.strip("/")
        self.token = ""
        self.signature = ""
        self.extra_headers: dict = {}
        self.reauth_fn: Callable[[], None] | None = None
        self._reauth_lock = threading.Lock()
        self._cookies = {"stb_lang": lang, "mac": mac, "timezone": timezone}
        parsed = urlparse(self.base_url)
        self._base_headers = {
            "User-Agent": _USER_AGENT,
            "X-User-Agent": _X_USER_AGENT,
            "Accept-Language": "en,*",
            "Connection": "Keep-Alive",
            "Host": parsed.hostname,
            "Referer": self.base_url + "/",
        }
        self._session = requests.Session()

    def get(self, type_: str, action: str, _retry: bool = False, **params) -> dict:
        url = f"{self.base_url}/{self.portal_path}"
        query = {"JsHttpRequest": "1-xml", "type": type_, "action": action, **params}
        self._cookies["token"] = self.token
        headers = {**self._base_headers, "Authorization": f"Bearer {self.token}", **self.extra_headers}
        resp = self._session.get(url, params=query, headers=headers, cookies=self._cookies, timeout=_REQUEST_TIMEOUT)
        logger.debug("Response [%s %s]: %s", resp.status_code, action, resp.text[:500])
        if not resp.ok:
            raise STBError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if _is_auth_failure(resp.text):
            if self.reauth_fn and not _retry and not getattr(_reauth_local, 'active', False):
                with self._reauth_lock:
                    _reauth_local.active = True
                    try:
                        logger.debug("Auth failure on %s, re-authenticating", action)
                        self.reauth_fn()
                    finally:
                        _reauth_local.active = False
                return self.get(type_, action, _retry=True, **params)
            raise AuthError(f"Portal rejected request ({action}): {resp.text[:100]}")
        try:
            return resp.json()["js"]
        except (KeyError, ValueError):
            raise STBError(f"Invalid JSON response (status {resp.status_code}): {resp.text[:200]}")

    def resolve_stream_url(self, relative_cmd: str) -> str:
        """Follow a portal-relative ?token= URL with session cookies and return the final CDN URL."""
        full_url = f"{self.base_url}/{self.portal_path}{relative_cmd}"
        self._cookies["token"] = self.token
        resp = self._session.get(
            full_url,
            headers=self._base_headers,
            cookies=self._cookies,
            stream=True,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.close()
        if not resp.ok:
            raise StreamError(f"stream resolve failed ({resp.status_code})")
        return str(resp.url)

    def open_url(self, url: str) -> requests.Response:
        """Fetch a full URL for streaming (no portal auth needed, e.g. CDN URLs)."""
        resp = self._session.get(url, stream=True, timeout=_REQUEST_TIMEOUT)
        logger.debug("Stream response [%s]: %s", resp.status_code, resp.headers.get("content-type"))
        if not resp.ok:
            raise StreamError(f"stream fetch failed ({resp.status_code})")
        return resp

    def open_stream(self, cmd: str) -> requests.Response:
        """Open a streaming request for a portal-relative ?token= URL.

        Uses only base MAG device headers (no Authorization/X-Random) so
        load.php sees a genuine STB stream request rather than an API call.
        Session token travels in Cookie: token= for session validation;
        play token travels in the URL (?token=) for media lookup.
        """
        full_url = f"{self.base_url}/{self.portal_path}{cmd}"
        self._cookies["token"] = self.token
        resp = self._session.get(full_url, headers=self._base_headers, cookies=self._cookies, stream=True, timeout=_REQUEST_TIMEOUT)
        ct = resp.headers.get("content-type", "")
        logger.debug("Stream response [%s]: %s", resp.status_code, ct)
        if not resp.ok:
            raise StreamError(f"stream fetch failed ({resp.status_code})")
        if "json" in ct:
            body = resp.json()
            logger.error("load.php stream JSON: %s", body)
            raise StreamError(f"portal rejected stream: {body}")
        return resp
