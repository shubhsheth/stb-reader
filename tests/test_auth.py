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
