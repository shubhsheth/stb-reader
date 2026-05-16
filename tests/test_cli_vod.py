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
def test_vod_categories_prints_table():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": [
        {"id": "5", "title": "Action", "alias": "action", "censored": False},
    ]})
    result = CliRunner().invoke(main, ["vod", "categories"])
    assert result.exit_code == 0
    assert "Action" in result.output


@responses_lib.activate
def test_vod_list_prints_table_with_footer():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {
        "data": [{
            "id": "100", "name": "Inception", "cmd": "http://x", "screenshot_uri": "",
            "genres_str": "Sci-Fi", "year": "2010", "description": "", "rating_imdb": "8.8",
            "time": "148", "is_series": False, "fav": False,
        }],
        "total_items": 42, "max_page_items": 14,
    }})
    result = CliRunner().invoke(main, ["vod", "list"])
    assert result.exit_code == 0
    assert "Inception" in result.output
    assert "Page 1 of" in result.output
    assert "42 total" in result.output


@responses_lib.activate
def test_vod_seasons_prints_table():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {
        "data": [{"id": "1", "name": "Season 1", "video_id": "99"}],
        "total_items": 1, "max_page_items": 14,
    }})
    result = CliRunner().invoke(main, ["vod", "seasons", "99"])
    assert result.exit_code == 0
    assert "Season 1" in result.output


@responses_lib.activate
def test_vod_episodes_prints_table():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {
        "data": [{"id": "9", "name": "Pilot", "series_number": "1", "cmd": "http://ep"}],
        "total_items": 1, "max_page_items": 14,
    }})
    result = CliRunner().invoke(main, ["vod", "episodes", "99", "1"])
    assert result.exit_code == 0
    assert "Pilot" in result.output


@responses_lib.activate
def test_vod_stream_prints_url():
    _auth_stubs()
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {
        "cmd": "ffmpeg http://cdn/movie.mp4", "error": "",
    }})
    result = CliRunner().invoke(main, ["stream", "--type", "vod", "http://x"])
    assert result.exit_code == 0
    assert "http://cdn/movie.mp4" in result.output
