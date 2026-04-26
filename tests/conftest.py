import pytest
import responses as responses_lib
from stb_reader._http import STBSession

BASE_URL = "http://portal.test"
MAC = "00:1A:79:00:00:01"
SERIAL = "000000000000"
LANG = "en"
TIMEZONE = "Europe/London"
PORTAL_PATH = "/stalker_portal/c/portal.php"
PORTAL_URL = f"{BASE_URL}{PORTAL_PATH}"


@pytest.fixture
def session():
    return STBSession(BASE_URL, MAC, SERIAL, LANG, TIMEZONE)


@pytest.fixture
def mocked():
    with responses_lib.RequestsMock() as rsps:
        yield rsps
