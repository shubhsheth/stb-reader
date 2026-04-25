from dataclasses import dataclass, field
from ._http import STBSession
from .auth import handshake, get_profile
from .live_tv import ITVService
from .vod import VODService


@dataclass
class STBClient:
    base_url: str
    mac: str
    serial: str = "000000000000"
    lang: str = "en"
    timezone: str = "Europe/London"
    portal_path: str = "stalker_portal/c/portal.php"
    _session: STBSession = field(init=False, repr=False)
    live_tv: ITVService = field(init=False, repr=False)
    vod: VODService = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._session = STBSession(self.base_url, self.mac, self.serial, self.lang, self.timezone, self.portal_path)
        self.live_tv = ITVService(self._session)
        self.vod = VODService(self._session)

    def authenticate(self) -> None:
        handshake(self._session)
        get_profile(self._session)
