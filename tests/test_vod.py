import pytest
import responses as responses_lib
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from stb_reader.vod import VODService
from stb_reader.exceptions import NotFoundError, STBError, StreamError
from stb_reader.models import Category, Content, PagedResult
from tests.conftest import PORTAL_URL
from server.db import init_db, upsert_vod_content


BASE_ENV = {
    "STB_PORTAL_URL": "http://portal.test",
    "STB_MAC": "00:1A:79:00:00:01",
    "STRM_SERVER_BASE_URL": "http://stb-reader:8000",
    "VOD_SYNC_INTERVAL_HOURS": "0",
}


@pytest.fixture
def vod_client(tmp_path):
    real_db = init_db(":memory:")
    mock_client = MagicMock()
    mock_client.authenticate.return_value = None

    env = {
        **BASE_ENV,
        "STRM_OUTPUT_DIR": str(tmp_path),
        "STRM_DATA_DIR": str(tmp_path),
    }

    import server.main as main_mod
    with patch.dict("os.environ", env):
        with patch("server.main.STBClient", return_value=mock_client):
            with patch("server.main.init_db", return_value=real_db):
                with patch("server.main.count_vod_content", return_value=1):
                    with TestClient(main_mod.app, raise_server_exceptions=False) as tc:
                        yield tc, mock_client, real_db


def _vod_row(content_id, name="Movie", year="2020", is_series=0):
    return {
        "content_id": content_id, "name": name, "cmd": "", "screenshot_uri": "",
        "genres": "", "year": year, "description": f"Desc of {name}", "rating": "7.0",
        "duration": 90, "is_series": is_series, "fav": 0, "for_rent": 0, "lock": 0,
        "portal_raw": "{}", "synced_at": "2024-01-01T00:00:00+00:00",
    }


# --- get_categories ---

@responses_lib.activate
def test_get_categories_returns_list(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": [{"id": "5", "title": "Action", "alias": "action", "censored": False}]},
    )
    svc = VODService(session)
    cats = svc.get_categories()
    assert len(cats) == 1
    assert cats[0].id == "5"
    assert cats[0].title == "Action"


# --- get_content ---

@responses_lib.activate
def test_get_content_page_is_1_indexed(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [], "total_items": 0, "max_page_items": 14}},
    )
    svc = VODService(session)
    svc.get_content(page=3)
    url = responses_lib.calls[0].request.url
    assert "p=3" in url


@responses_lib.activate
def test_get_content_parses_content(session):
    item = {
        "id": "100", "name": "Inception", "cmd": "http://x", "screenshot_uri": "",
        "genres_str": "Sci-Fi", "year": "2010", "description": "A dream", "rating_imdb": "8.8",
        "time": "148", "is_series": False, "fav": False,
    }
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [item], "total_items": 1, "max_page_items": 14}},
    )
    svc = VODService(session)
    result = svc.get_content()
    assert result.total == 1
    assert result.items[0].name == "Inception"
    assert result.items[0].is_series is False


# --- get_seasons ---

@responses_lib.activate
def test_get_seasons_returns_list(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [{"id": "1", "name": "Season 1", "video_id": "200"}]}},
    )
    svc = VODService(session)
    seasons = svc.get_seasons("50")
    assert len(seasons) == 1
    assert seasons[0].name == "Season 1"
    url = responses_lib.calls[0].request.url
    assert "movie_id=50" in url
    assert "season_id=0" in url
    assert "episode_id=0" in url


# --- get_episodes ---

@responses_lib.activate
def test_get_episodes_returns_list(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [{"id": "99", "name": "Pilot", "series_number": "1", "cmd": "http://ep"}]}},
    )
    svc = VODService(session)
    eps = svc.get_episodes("50", "1")
    assert len(eps) == 1
    assert eps[0].name == "Pilot"
    assert eps[0].cmd == "http://ep"
    url = responses_lib.calls[0].request.url
    assert "movie_id=50" in url
    assert "season_id=1" in url


# --- get_stream_url ---

@responses_lib.activate
def test_get_stream_url_returns_clean_url(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"cmd": "ffmpeg http://cdn/movie.mp4", "error": ""}},
    )
    svc = VODService(session)
    url = svc.get_stream_url("http://cmd")
    assert url == "http://cdn/movie.mp4"


@responses_lib.activate
def test_get_stream_url_raises_stream_error(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"cmd": "", "error": "nothing_to_play"}},
    )
    svc = VODService(session)
    with pytest.raises(StreamError):
        svc.get_stream_url("http://cmd")


# --- get_stream_url_by_content_id ---

@responses_lib.activate
def test_get_stream_url_by_content_id_constructs_cmd(session):
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"cmd": "ffmpeg http://movie", "error": ""}})
    svc = VODService(session)
    url = svc.get_stream_url_by_content_id("77")
    assert url == "http://movie"
    assert "cmd=%2Fmedia%2F77.mpg" in responses_lib.calls[0].request.url


@responses_lib.activate
def test_get_stream_url_by_content_id_raises_on_stream_error(session):
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"cmd": "", "error": "not_allow"}})
    svc = VODService(session)
    with pytest.raises(StreamError):
        svc.get_stream_url_by_content_id("77")


# --- get_stream_url_by_first_file ---

@responses_lib.activate
def test_get_stream_url_by_first_file_streams_first_file(session):
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"data": [
        {"id": "1", "name": "HD", "cmd": "/media/file_1.mpg"},
        {"id": "2", "name": "SD", "cmd": "/media/file_2.mpg"},
    ]}})
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"cmd": "http://cdn/hd.m3u8", "error": ""}})
    svc = VODService(session)
    url = svc.get_stream_url_by_first_file("10", "1", "55")
    assert url == "http://cdn/hd.m3u8"
    assert "cmd=%2Fmedia%2Ffile_1.mpg" in responses_lib.calls[1].request.url


@responses_lib.activate
def test_get_stream_url_by_first_file_raises_when_no_files(session):
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"data": []}})
    svc = VODService(session)
    with pytest.raises(NotFoundError, match="no files for episode"):
        svc.get_stream_url_by_first_file("10", "1", "55")


@responses_lib.activate
def test_get_stream_url_by_first_file_raises_on_stream_error(session):
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"data": [
        {"id": "1", "name": "HD", "cmd": "/media/file_1.mpg"},
    ]}})
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"cmd": "", "error": "not_allow"}})
    svc = VODService(session)
    with pytest.raises(StreamError):
        svc.get_stream_url_by_first_file("10", "1", "55")


# --- get_episode_files ---

@responses_lib.activate
def test_get_episode_files_returns_list(session):
    files = [
        {"id": "1", "name": "English / HD (1080p)", "cmd": "/media/file_1.mpg"},
        {"id": "2", "name": "English / SD (480p)", "cmd": "/media/file_2.mpg"},
    ]
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": files}},
    )
    svc = VODService(session)
    result = svc.get_episode_files("10", "1", "55")
    assert len(result) == 2
    assert result[0].id == "1"
    assert result[0].name == "English / HD (1080p)"
    assert result[0].cmd == "/media/file_1.mpg"
    url = responses_lib.calls[0].request.url
    assert "movie_id=10" in url
    assert "season_id=1" in url
    assert "episode_id=55" in url


@responses_lib.activate
def test_get_episode_files_returns_empty_list(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": []}},
    )
    svc = VODService(session)
    result = svc.get_episode_files("10", "1", "55")
    assert result == []


# --- get_stream_url_by_file_id ---

@responses_lib.activate
def test_get_stream_url_by_file_id_finds_file(session):
    files = [{"id": "2", "name": "English / SD (480p)", "cmd": "/media/file_2.mpg"}]
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"data": files}})
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": {"cmd": "http://cdn/sd.m3u8", "error": ""}})
    svc = VODService(session)
    url = svc.get_stream_url_by_file_id("10", "1", "55", "2")
    assert url == "http://cdn/sd.m3u8"


@responses_lib.activate
def test_get_stream_url_by_file_id_raises_when_not_found(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [{"id": "1", "name": "English / HD", "cmd": "/media/file_1.mpg"}]}},
    )
    svc = VODService(session)
    with pytest.raises(NotFoundError, match="file not found"):
        svc.get_stream_url_by_file_id("10", "1", "55", "999")


# --- /vod/sync, /vod/sync/status, /vod/search ---

class TestVodSync:
    def test_trigger_sync_returns_202(self, vod_client):
        tc, mock_client, db = vod_client
        with patch("server.routes.vod.run_portal_sync"):
            resp = tc.post("/vod/sync")
        assert resp.status_code == 202

    def test_trigger_sync_while_running_returns_409(self, vod_client):
        from server.db import set_sync_state
        tc, mock_client, db = vod_client
        set_sync_state(db, last_sync_status="running")
        resp = tc.post("/vod/sync")
        assert resp.status_code == 409

    def test_sync_status_returns_state(self, vod_client):
        tc, mock_client, db = vod_client
        resp = tc.get("/vod/sync/status")
        assert resp.status_code == 200
        assert resp.json()["last_sync_status"] == "idle"


class TestVodSearch:
    def test_search_returns_503_when_empty(self, vod_client):
        from server.db import set_sync_state
        tc, mock_client, db = vod_client
        # db is empty — override the startup mock for this test
        with patch("server.routes.vod.count_vod_content", return_value=0):
            resp = tc.get("/vod/search?query=action")
        assert resp.status_code == 503

    def test_search_returns_matching_results(self, vod_client):
        tc, mock_client, db = vod_client
        upsert_vod_content(db, _vod_row("c1", "Action Hero"))
        upsert_vod_content(db, _vod_row("c2", "Drama Queens"))
        db.commit()
        resp = tc.get("/vod/search?query=Action")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["content_id"] == "c1"

    def test_search_is_series_filter(self, vod_client):
        tc, mock_client, db = vod_client
        upsert_vod_content(db, _vod_row("c1", "Action Movie", is_series=0))
        upsert_vod_content(db, _vod_row("c2", "Action Show", is_series=1))
        db.commit()
        resp = tc.get("/vod/search?query=Action&is_series=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["content_id"] == "c2"

    def test_search_pagination(self, vod_client):
        tc, mock_client, db = vod_client
        for i in range(5):
            upsert_vod_content(db, _vod_row(f"c{i}", f"Action Film {i}"))
        db.commit()
        resp = tc.get("/vod/search?query=Action&page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
