import pytest
import responses as responses_lib
from click.testing import CliRunner
from stb_reader.cli.main import main
from stb_reader.cli import config as config_mod
from tests.conftest import PORTAL_URL


@pytest.fixture(autouse=True)
def tmp_config(tmp_path, monkeypatch):
    cfg = tmp_path / ".stb" / "config"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg)
    config_mod.save_config({"url": "http://portal.test", "mac": "00:1A:79:00:00:01"})
    return cfg


def _auth_stubs():
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"token": "tok"}})
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"id": "1"}})


@responses_lib.activate
def test_live_genres_prints_table():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": [
        {"id": "1", "title": "News", "alias": "news", "censored": False},
    ]})
    result = CliRunner().invoke(main, ["live", "genres"])
    assert result.exit_code == 0
    assert "News" in result.output
    assert "ID" in result.output


@responses_lib.activate
def test_live_channels_prints_table_with_footer():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {
        "data": [{"id": "10", "number": "1", "name": "BBC One", "cmd": "ffrt http://x",
                  "logo": "", "tv_genre_id": "1", "hd": True, "censored": False}],
        "total_items": 50, "max_page_items": 14,
    }})
    result = CliRunner().invoke(main, ["live", "channels"])
    assert result.exit_code == 0
    assert "BBC One" in result.output
    assert "Page 1 of" in result.output
    assert "50 total" in result.output


@responses_lib.activate
def test_live_channels_missing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "none")
    result = CliRunner().invoke(main, ["live", "channels"])
    assert result.exit_code != 0
    assert "stb init" in result.output


@responses_lib.activate
def test_live_stream_prints_url():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {
        "cmd": "ffmpeg http://cdn/stream.m3u8", "error": "",
    }})
    responses_lib.add(responses_lib.GET, "http://cdn/stream.m3u8", body=b"")
    result = CliRunner().invoke(main, ["stream", "--type", "live", "ffrt http://x"])
    assert result.exit_code == 0
    assert "http://cdn/stream.m3u8" in result.output
