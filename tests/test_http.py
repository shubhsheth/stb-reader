import pytest
import responses as responses_lib
from stb_reader._http import STBSession
from stb_reader.exceptions import STBError
from tests.conftest import BASE_URL, MAC, LANG, TIMEZONE, PORTAL_PATH


def _portal_url():
    return f"{BASE_URL}{PORTAL_PATH}"


def test_correct_url(mocked, session):
    mocked.add(responses_lib.GET, _portal_url(), json={"js": {"result": "ok"}})
    result = session.get("stb", "handshake")
    assert result == {"result": "ok"}
    assert mocked.calls[0].request.url.startswith(_portal_url())


def test_required_query_params(mocked, session):
    mocked.add(responses_lib.GET, _portal_url(), json={"js": {}})
    session.get("stb", "handshake", extra="val")
    url = mocked.calls[0].request.url
    assert "JsHttpRequest=1-xml" in url
    assert "type=stb" in url
    assert "action=handshake" in url
    assert "extra=val" in url


def test_authorization_header(mocked, session):
    session.token = "mytoken"
    mocked.add(responses_lib.GET, _portal_url(), json={"js": {}})
    session.get("stb", "handshake")
    headers = mocked.calls[0].request.headers
    assert headers["Authorization"] == "Bearer mytoken"


def test_user_agent_headers(mocked, session):
    mocked.add(responses_lib.GET, _portal_url(), json={"js": {}})
    session.get("stb", "handshake")
    headers = mocked.calls[0].request.headers
    assert "User-Agent" in headers
    assert "X-User-Agent" in headers


def test_cookie_header(mocked, session):
    mocked.add(responses_lib.GET, _portal_url(), json={"js": {}})
    session.get("stb", "handshake")
    cookie = mocked.calls[0].request.headers["Cookie"]
    assert f"mac={MAC}" in cookie
    assert f"lang={LANG}" in cookie
    assert f"timezone={TIMEZONE}" in cookie


def test_js_unwrapping(mocked, session):
    mocked.add(responses_lib.GET, _portal_url(), json={"js": {"token": "abc123"}})
    result = session.get("stb", "handshake")
    assert result == {"token": "abc123"}


def test_stberror_on_4xx(mocked, session):
    mocked.add(responses_lib.GET, _portal_url(), status=401, body="Unauthorized")
    with pytest.raises(STBError):
        session.get("stb", "handshake")


def test_stberror_on_5xx(mocked, session):
    mocked.add(responses_lib.GET, _portal_url(), status=500, body="Server Error")
    with pytest.raises(STBError):
        session.get("stb", "handshake")
