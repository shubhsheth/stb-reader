import pytest
import responses as responses_lib
from stb_reader import STBClient
from stb_reader.auth import handshake, get_profile
from stb_reader.exceptions import AuthError
from tests.conftest import BASE_URL, MAC, PORTAL_PATH


def _portal_url():
    return f"{BASE_URL}{PORTAL_PATH}"


def _qs(call):
    from urllib.parse import urlparse, parse_qs
    return parse_qs(urlparse(call.request.url).query)


@responses_lib.activate
def test_handshake_sets_token():
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"token": "tok123"}})
    from stb_reader._http import STBSession
    session = STBSession(BASE_URL, MAC, "000000000000", "en", "Europe/London")
    handshake(session)
    assert session.token == "tok123"


@responses_lib.activate
def test_handshake_raises_auth_error_when_no_token():
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {}})
    from stb_reader._http import STBSession
    session = STBSession(BASE_URL, MAC, "000000000000", "en", "Europe/London")
    with pytest.raises(AuthError):
        handshake(session)


@responses_lib.activate
def test_authenticate_calls_handshake_then_profile():
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"token": "t1"}})
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"login": "user1"}})
    client = STBClient(BASE_URL, MAC)
    client.authenticate()
    calls = responses_lib.calls
    assert len(calls) == 2
    assert "action=handshake" in calls[0].request.url
    assert "action=get_profile" in calls[1].request.url


@responses_lib.activate
def test_authenticate_token_propagated_to_second_request():
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"token": "tok_abc"}})
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {}})
    client = STBClient(BASE_URL, MAC)
    client.authenticate()
    assert responses_lib.calls[1].request.headers["Authorization"] == "Bearer tok_abc"



@responses_lib.activate
def test_get_profile_sends_device_params_when_device_id_provided():
    import hashlib
    from stb_reader._http import STBSession
    serial = "TESTSERIAL"
    device_id = hashlib.sha256(serial.encode()).hexdigest()
    session = STBSession(BASE_URL, MAC, serial, "en", "Europe/London", device_id=device_id)
    session.token = "tok"
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {}})
    get_profile(session)
    qs = _qs(responses_lib.calls[0])
    assert qs["device_id"][0] == device_id
    assert qs["device_id2"][0] == hashlib.sha256(MAC.encode()).hexdigest()
    assert qs["signature"][0] == hashlib.sha256((serial + MAC).encode()).hexdigest()


@responses_lib.activate
def test_get_profile_omits_device_params_when_device_id_not_provided():
    from stb_reader._http import STBSession
    session = STBSession(BASE_URL, MAC, "TESTSERIAL", "en", "Europe/London")
    session.token = "tok"
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {}})
    get_profile(session)
    qs = _qs(responses_lib.calls[0])
    assert "device_id" not in qs
    assert "device_id2" not in qs
    assert "signature" not in qs


@responses_lib.activate
def test_get_profile_applies_refreshed_token():
    from stb_reader._http import STBSession
    session = STBSession(BASE_URL, MAC, "000000000000", "en", "Europe/London")
    session.token = "old_token"
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"token": "new_token"}})
    get_profile(session)
    assert session.token == "new_token"


@responses_lib.activate
def test_get_profile_ignores_empty_token():
    from stb_reader._http import STBSession
    session = STBSession(BASE_URL, MAC, "000000000000", "en", "Europe/London")
    session.token = "original"
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"token": ""}})
    get_profile(session)
    assert session.token == "original"
