from ._http import STBSession
from .auth import handshake, get_profile
from .live_tv import ITVService
from .vod import VODService


class STBClient:
    def __init__(
        self,
        base_url: str,
        mac: str,
        serial: str = "000000000000",
        lang: str = "en",
        timezone: str = "Europe/London",
        portal_path: str = "stalker_portal/c/portal.php",
        device_id: str | None = None,
        device_id2: str | None = None,
    ) -> None:
        self._session = STBSession(base_url, mac, serial, lang, timezone, portal_path, device_id, device_id2)
        self._session.reauth_fn = self.authenticate
        self.live_tv = ITVService(self._session)
        self.vod = VODService(self._session)

    def authenticate(self) -> None:
        handshake(self._session)
        get_profile(self._session)
