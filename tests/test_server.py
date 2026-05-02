import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from stb_reader.models import Genre, Channel, Category, Content, Season, Episode, EpisodeFile, PagedResult
from stb_reader.exceptions import NotFoundError, STBError, StreamError


ENV_VARS = {
    "STB_PORTAL_URL": "http://portal.test",
    "STB_MAC": "00:1A:79:00:00:01",
    "STRM_OUTPUT_DIR": "/tmp/strm_test",
    "STRM_SERVER_BASE_URL": "http://localhost:8000",
    "STRM_DB_PATH": ":memory:",
    "STRM_SYNC_INTERVAL_HOURS": "0",
}


@pytest.fixture
def mock_client():
    c = MagicMock()
    c.authenticate.return_value = None
    return c


@pytest.fixture
def test_client(mock_client):
    import server.main as main_mod
    with patch.dict("os.environ", ENV_VARS):
        with patch("server.main.STBClient", return_value=mock_client):
            with TestClient(main_mod.app, raise_server_exceptions=False) as tc:
                yield tc, mock_client


# --- Health ---

def test_health(test_client):
    tc, _ = test_client
    resp = tc.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_required_env_raises():
    with patch.dict("os.environ", {}, clear=True):
        import os
        for k in ("STB_PORTAL_URL", "STB_MAC", "STB_SERIAL", "STB_LANG", "STB_TIMEZONE", "PORT"):
            os.environ.pop(k, None)
        from server.config import Settings
        import pydantic
        with pytest.raises((pydantic.ValidationError, Exception)):
            Settings()


# --- Live TV ---

class TestLiveTV:
    def test_get_genres(self, test_client):
        tc, mock = test_client
        mock.live_tv.get_genres.return_value = [
            Genre(id="1", title="News", alias="news", censored=False)
        ]
        resp = tc.get("/live-tv/genres")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "News"

    def test_get_channels(self, test_client):
        tc, mock = test_client
        mock.live_tv.get_channels.return_value = PagedResult(
            items=[Channel(id="1", number="1", name="BBC", cmd="x", logo="", genre_id="1", hd=False, censored=False)],
            total=1, page=1, per_page=14,
        )
        resp = tc.get("/live-tv/channels?genre_id=*&page=1&sort=number")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["name"] == "BBC"

    def test_get_channel_stream_redirects(self, test_client):
        tc, mock = test_client
        mock.live_tv.get_stream_url_by_id.return_value = "http://stream.test/live"
        resp = tc.get("/live-tv/channels/42/stream", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://stream.test/live"

    def test_get_channel_stream_404_when_not_found(self, test_client):
        tc, mock = test_client
        mock.live_tv.get_stream_url_by_id.side_effect = NotFoundError("channel not found")
        resp = tc.get("/live-tv/channels/999/stream", follow_redirects=False)
        assert resp.status_code == 404

    def test_get_channel_stream_502_on_stream_error(self, test_client):
        tc, mock = test_client
        mock.live_tv.get_stream_url_by_id.side_effect = StreamError("nothing_to_play")
        resp = tc.get("/live-tv/channels/1/stream", follow_redirects=False)
        assert resp.status_code == 502


# --- VOD ---

class TestVOD:
    def test_get_categories(self, test_client):
        tc, mock = test_client
        mock.vod.get_categories.return_value = [
            Category(id="5", title="Action", alias="action", censored=False)
        ]
        resp = tc.get("/vod/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["title"] == "Action"

    def test_get_content(self, test_client):
        tc, mock = test_client
        mock.vod.get_content.return_value = PagedResult(
            items=[Content(id="1", name="Movie", cmd="x", screenshot_uri="", genres="", year="", description="", rating="", duration="", is_series=False, fav=False)],
            total=1, page=1, per_page=14,
        )
        resp = tc.get("/vod/content?page=1&sort=added")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["name"] == "Movie"

    def test_get_seasons(self, test_client):
        tc, mock = test_client
        mock.vod.get_seasons.return_value = [Season(id="1", name="S1", video_id="200")]
        resp = tc.get("/vod/content/50/seasons")
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "S1"

    def test_get_episodes(self, test_client):
        tc, mock = test_client
        mock.vod.get_episodes.return_value = [Episode(id="1", name="Ep1", series_number="1", cmd="x")]
        resp = tc.get("/vod/content/50/seasons/1/episodes")
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Ep1"

    def test_get_content_stream_redirects(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_content_id.return_value = "http://stream.test/movie"
        resp = tc.get("/vod/content/77/stream", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://stream.test/movie"

    def test_get_content_stream_404_when_not_found(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_content_id.side_effect = NotFoundError("content not found")
        resp = tc.get("/vod/content/999/stream", follow_redirects=False)
        assert resp.status_code == 404

    def test_get_content_stream_502_on_stream_error(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_content_id.side_effect = StreamError("nothing_to_play")
        resp = tc.get("/vod/content/1/stream", follow_redirects=False)
        assert resp.status_code == 502

    def test_get_episode_stream_redirects(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_first_file.return_value = "http://cdn/hd.m3u8"
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/stream", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://cdn/hd.m3u8"

    def test_get_episode_stream_404_when_no_files(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_first_file.side_effect = NotFoundError("no files for episode")
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/stream", follow_redirects=False)
        assert resp.status_code == 404

    def test_get_episode_stream_502_on_stream_error(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_first_file.side_effect = StreamError("not_allow")
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/stream", follow_redirects=False)
        assert resp.status_code == 502

    def test_get_episode_files_returns_list(self, test_client):
        tc, mock = test_client
        mock.vod.get_episode_files.return_value = [
            EpisodeFile(id="1", name="English / HD (1080p)", cmd="/media/file_1.mpg"),
            EpisodeFile(id="2", name="English / SD (480p)", cmd="/media/file_2.mpg"),
        ]
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/files")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "1"
        assert data[0]["name"] == "English / HD (1080p)"

    def test_get_episode_files_returns_empty(self, test_client):
        tc, mock = test_client
        mock.vod.get_episode_files.return_value = []
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/files")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_episode_file_stream_redirects(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_file_id.return_value = "http://cdn/hd.m3u8"
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/files/1/stream", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://cdn/hd.m3u8"

    def test_get_episode_file_stream_404_when_not_found(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_file_id.side_effect = NotFoundError("file not found")
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/files/999/stream", follow_redirects=False)
        assert resp.status_code == 404

    def test_get_episode_file_stream_502_on_stream_error(self, test_client):
        tc, mock = test_client
        mock.vod.get_stream_url_by_file_id.side_effect = StreamError("nothing_to_play")
        resp = tc.get("/vod/content/10/seasons/1/episodes/55/files/1/stream", follow_redirects=False)
        assert resp.status_code == 502
