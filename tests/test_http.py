import click
import pytest
import responses as responses_lib
from stb_reader._http import STBSession, _reauth_local
from stb_reader.exceptions import AuthError, STBError
from tests.conftest import BASE_URL, MAC, SERIAL, LANG, TIMEZONE, PORTAL_URL


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


def test_audit_mode_off_by_default(mocked, session, monkeypatch):
    confirm_calls = []
    monkeypatch.setattr(click, "confirm", lambda *a, **k: confirm_calls.append(1) or True)
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {"result": "ok"}})
    result = session.get("stb", "handshake")
    assert result == {"result": "ok"}
    assert session.audit_mode is False
    assert confirm_calls == []


def test_audit_mode_includes_stb_requests(mocked, monkeypatch):
    session = STBSession(BASE_URL, MAC, SERIAL, LANG, TIMEZONE, audit_mode=True)
    confirm_calls = []
    monkeypatch.setattr(click, "confirm", lambda *a, **k: confirm_calls.append(1) or True)
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {"token": "abc"}})
    result = session.get("stb", "handshake")
    assert result == {"token": "abc"}
    assert len(confirm_calls) == 1


def test_audit_mode_prints_request_block(mocked, monkeypatch, capsys):
    session = STBSession(BASE_URL, MAC, SERIAL, LANG, TIMEZONE, audit_mode=True)
    monkeypatch.setattr(click, "confirm", lambda *a, **k: True)
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {"data": []}})
    session.get("vod", "get_ordered_list", category="5")
    out = capsys.readouterr().out
    assert "--- Audit: Outgoing Request ---" in out
    assert PORTAL_URL in out
    assert "type:   vod" in out
    assert "action: get_ordered_list" in out
    assert "category=5" in out


def test_audit_mode_prints_response_block(mocked, monkeypatch, capsys):
    session = STBSession(BASE_URL, MAC, SERIAL, LANG, TIMEZONE, audit_mode=True)
    monkeypatch.setattr(click, "confirm", lambda *a, **k: True)
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {"foo": "bar"}})
    session.get("vod", "get_categories")
    out = capsys.readouterr().out
    assert "--- Audit: Raw STB Response ---" in out
    assert '"js"' in out
    assert '"foo": "bar"' in out


def test_audit_mode_abort_on_no(mocked, monkeypatch):
    session = STBSession(BASE_URL, MAC, SERIAL, LANG, TIMEZONE, audit_mode=True)
    monkeypatch.setattr(click, "confirm", lambda *a, **k: False)
    with pytest.raises(click.exceptions.Abort):
        session.get("vod", "get_categories")
    assert len(mocked.calls) == 0


def test_audit_mode_token_not_in_output(mocked, monkeypatch, capsys):
    session = STBSession(BASE_URL, MAC, SERIAL, LANG, TIMEZONE, audit_mode=True)
    session.token = "secret123"
    monkeypatch.setattr(click, "confirm", lambda *a, **k: True)
    mocked.add(responses_lib.GET, PORTAL_URL, json={"js": {}})
    session.get("vod", "get_categories")
    out = capsys.readouterr().out
    assert "secret123" not in out
    assert "token:  [set]" in out


def test_audit_mode_abort_during_reauth_propagates(mocked, monkeypatch):
    session = STBSession(BASE_URL, MAC, SERIAL, LANG, TIMEZONE, audit_mode=True)

    confirms = iter([True, False])
    monkeypatch.setattr(click, "confirm", lambda *a, **k: next(confirms))

    def reauth():
        session.get("stb", "handshake")

    session.reauth_fn = reauth
    mocked.add(responses_lib.GET, PORTAL_URL, body="Authorization failed. 75")  # original call

    with pytest.raises(click.exceptions.Abort):
        session.get("vod", "get_categories")

    assert len(mocked.calls) == 1
    assert not session._reauth_lock.locked()
    assert not getattr(_reauth_local, "active", False)
