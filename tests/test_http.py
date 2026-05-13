import pytest
import responses as responses_lib
from stb_reader._http import STBSession
from stb_reader.exceptions import AuthError, STBError
from tests.conftest import BASE_URL, MAC, LANG, TIMEZONE, PORTAL_URL


def test_correct_url(mocked, session):
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {"result": "ok"}})
    result = session.get("stb", "handshake")
    assert result == {"result": "ok"}
    assert mocked.calls[0].request.url.startswith(PORTAL_URL)


def test_required_query_params(mocked, session):
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {}})
    session.get("stb", "handshake", extra="val")
    url = mocked.calls[0].request.url
    assert "JsHttpRequest=1-xml" in url
    assert "type=stb" in url
    assert "action=handshake" in url
    assert "extra=val" in url


def test_authorization_header(mocked, session):
    session.token = "mytoken"
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {}})
    session.get("stb", "handshake")
    headers = mocked.calls[0].request.headers
    assert headers["Authorization"] == "Bearer mytoken"


def test_user_agent_headers(mocked, session):
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {}})
    session.get("stb", "handshake")
    headers = mocked.calls[0].request.headers
    assert "User-Agent" in headers
    assert "X-User-Agent" in headers


def test_cookie_header(mocked, session):
    session.token = "mytoken"
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {}})
    session.get("stb", "handshake")
    cookie = mocked.calls[0].request.headers["Cookie"]
    assert f"mac={MAC}" in cookie
    assert f"stb_lang={LANG}" in cookie
    assert f"timezone={TIMEZONE}" in cookie
    assert "token=mytoken" in cookie


def test_js_unwrapping(mocked, session):
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {"token": "abc123"}})
    result = session.get("stb", "handshake")
    assert result == {"token": "abc123"}


def test_stberror_on_4xx(mocked, session):
    mocked.add(responses_lib.GET, PORTAL_URL, status=401, body="Unauthorized")
    with pytest.raises(STBError):
        session.get("stb", "handshake")


def test_stberror_on_5xx(mocked, session):
    mocked.add(responses_lib.GET, PORTAL_URL, status=500, body="Server Error")
    with pytest.raises(STBError):
        session.get("stb", "handshake")


def test_autherror_on_auth_failure_body(mocked, session):
    mocked.add(responses_lib.GET, PORTAL_URL, body="Authorization failed. 75")
    with pytest.raises(AuthError):
        session.get("stb", "handshake")


def test_reauth_retry_on_auth_failure(mocked, session):
    reauth_calls = []

    def fake_reauth():
        reauth_calls.append(1)

    session.reauth_fn = fake_reauth
    mocked.add(responses_lib.GET, PORTAL_URL, body="Authorization failed. 75")
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {"ok": True}})
    result = session.get("stb", "handshake")
    assert result == {"ok": True}
    assert len(reauth_calls) == 1


def test_reauth_not_called_twice_on_persistent_failure(mocked, session):
    session.reauth_fn = lambda: None
    mocked.add(responses_lib.GET, PORTAL_URL, body="Authorization failed. 75")
    mocked.add(responses_lib.GET, PORTAL_URL, body="Authorization failed. 75")
    with pytest.raises(AuthError):
        session.get("stb", "handshake")


def test_reauth_raises_auth_error_when_reauth_itself_fails(mocked, session):
    # reauth_fn calls session.get internally (like the real authenticate())
    # If handshake also gets auth failure, we must raise AuthError instead of deadlocking
    def failing_reauth():
        session.get("stb", "handshake")

    session.reauth_fn = failing_reauth
    mocked.add(responses_lib.GET, PORTAL_URL, body="Authorization failed. 75")  # original call
    mocked.add(responses_lib.GET, PORTAL_URL, body="Authorization failed. 75")  # reauth's handshake
    with pytest.raises(AuthError):
        session.get("stb", "some_action")
