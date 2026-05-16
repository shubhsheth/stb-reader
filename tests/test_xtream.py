import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from stb_reader.models import Genre, Channel, Category, Content, Season, Episode, PagedResult
from stb_reader.exceptions import NotFoundError, StreamError


ENV_VARS = {
    "STB_PORTAL_URL": "http://portal.test",
    "STB_MAC": "00:1A:79:00:00:01",
    "STRM_OUTPUT_DIR": "/tmp/strm_test",
    "STRM_SERVER_BASE_URL": "http://localhost:8000",
    "STRM_DATA_DIR": "/tmp/strm_test",
    "STRM_SYNC_INTERVAL_HOURS": "0",
    "XTREAM_USERNAME": "testuser",
    "XTREAM_PASSWORD": "testpass",
}


def _paged(items, per_page=100):
    return PagedResult(items=items, total=len(items), page=1, per_page=per_page)


@pytest.fixture
def mock_client():
    c = MagicMock()
    c.authenticate.return_value = None
    return c


@pytest.fixture
def tc(mock_client):
    import server.main as main_mod
    from server.db import init_db
    real_db = init_db(":memory:")
    with patch.dict("os.environ", ENV_VARS):
        with patch("server.main.STBClient", return_value=mock_client):
            with patch("server.main.init_db", return_value=real_db):
                with TestClient(main_mod.app, raise_server_exceptions=False) as client:
                    yield client, mock_client


# Shorthand query params for valid auth
CREDS = "username=testuser&password=testpass"
BAD_CREDS = "username=wrong&password=wrong"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_valid_creds_accepted(self, tc):
        client, mock = tc
        mock.live_tv.get_genres.return_value = []
        resp = client.get(f"/player_api.php?{CREDS}&action=get_live_categories")
        assert resp.status_code == 200

    def test_invalid_creds_rejected(self, tc):
        client, _ = tc
        resp = client.get(f"/player_api.php?{BAD_CREDS}&action=get_live_categories")
        assert resp.status_code == 403

    def test_partial_creds_rejected(self, tc):
        client, _ = tc
        resp = client.get("/player_api.php?username=testuser&password=wrong")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Login / server info
# ---------------------------------------------------------------------------

class TestLogin:
    def test_no_action_returns_login(self, tc):
        client, _ = tc
        resp = client.get(f"/player_api.php?{CREDS}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_info"]["auth"] == 1
        assert body["user_info"]["username"] == "testuser"
        assert "server_info" in body
        assert "url" in body["server_info"]

    def test_post_also_works(self, tc):
        client, _ = tc
        resp = client.post(f"/player_api.php?{CREDS}")
        assert resp.status_code == 200
        assert resp.json()["user_info"]["auth"] == 1

    def test_unknown_action_returns_empty_list(self, tc):
        client, _ = tc
        resp = client.get(f"/player_api.php?{CREDS}&action=nonexistent_action")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_health_still_works(self, tc):
        client, _ = tc
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Live TV
# ---------------------------------------------------------------------------

class TestLiveTV:
    def test_get_live_categories(self, tc):
        client, mock = tc
        mock.live_tv.get_genres.return_value = [
            Genre(id="1", title="Sports", alias="sports", censored=False),
            Genre(id="2", title="News", alias="news", censored=False),
        ]
        resp = client.get(f"/player_api.php?{CREDS}&action=get_live_categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0] == {"category_id": "1", "category_name": "Sports", "parent_id": 0}
        assert data[1]["category_id"] == "2"

    def test_get_live_streams_returns_all_channels(self, tc):
        client, mock = tc
        mock.live_tv.get_channels.return_value = _paged([
            Channel(id="10", number="1", name="CNN", cmd="x", logo="http://logo.png", genre_id="1", hd=True, censored=False),
            Channel(id="20", number="2", name="BBC", cmd="y", logo="", genre_id="2", hd=False, censored=False),
        ])
        resp = client.get(f"/player_api.php?{CREDS}&action=get_live_streams")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["stream_id"] == 10
        assert data[0]["stream_type"] == "live"
        assert data[0]["name"] == "CNN"
        assert data[0]["stream_icon"] == "http://logo.png"
        assert data[0]["num"] == 1
        assert data[1]["stream_id"] == 20

    def test_get_live_streams_passes_category_id(self, tc):
        client, mock = tc
        mock.live_tv.get_channels.return_value = _paged([])
        client.get(f"/player_api.php?{CREDS}&action=get_live_streams&category_id=5")
        call_kwargs = mock.live_tv.get_channels.call_args
        assert call_kwargs.kwargs.get("genre_id") == "5"

    def test_get_live_streams_default_category_is_wildcard(self, tc):
        client, mock = tc
        mock.live_tv.get_channels.return_value = _paged([])
        client.get(f"/player_api.php?{CREDS}&action=get_live_streams")
        call_kwargs = mock.live_tv.get_channels.call_args
        assert call_kwargs.kwargs.get("genre_id") == "*"

    def test_get_live_streams_required_fields_present(self, tc):
        client, mock = tc
        mock.live_tv.get_channels.return_value = _paged([
            Channel(id="1", number="1", name="Ch1", cmd="x", logo="", genre_id="1", hd=False, censored=False),
        ])
        data = client.get(f"/player_api.php?{CREDS}&action=get_live_streams").json()
        item = data[0]
        for field in ("num", "name", "stream_type", "stream_id", "stream_icon",
                      "epg_channel_id", "added", "category_id", "custom_sid",
                      "tv_archive", "direct_source", "tv_archive_duration"):
            assert field in item, f"missing field: {field}"


# ---------------------------------------------------------------------------
# VOD
# ---------------------------------------------------------------------------

def _movie(id="100", name="Movie A", rating="7.5"):
    return Content(id=id, name=name, cmd="x", screenshot_uri="http://img.png",
                   genres="Action", year="2023", description="desc", rating=rating,
                   duration="120", is_series=False, fav=False)


def _series(id="200", name="Show A"):
    return Content(id=id, name=name, cmd="x", screenshot_uri="http://img.png",
                   genres="Drama", year="2022", description="plot", rating="8.0",
                   duration="", is_series=True, fav=False)


class TestVOD:
    def test_get_vod_categories(self, tc):
        client, mock = tc
        mock.vod.get_categories.return_value = [
            Category(id="5", title="Action", alias="action", censored=False),
        ]
        resp = client.get(f"/player_api.php?{CREDS}&action=get_vod_categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0] == {"category_id": "5", "category_name": "Action", "parent_id": 0}

    def test_get_vod_streams_only_movies(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_movie(), _series()])
        resp = client.get(f"/player_api.php?{CREDS}&action=get_vod_streams")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["stream_type"] == "movie"
        assert data[0]["stream_id"] == 100
        assert data[0]["name"] == "Movie A"

    def test_get_vod_streams_rating_5based(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_movie(rating="8.0")])
        data = client.get(f"/player_api.php?{CREDS}&action=get_vod_streams").json()
        assert data[0]["rating_5based"] == pytest.approx(4.0)

    def test_get_vod_streams_empty_rating(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_movie(rating="")])
        data = client.get(f"/player_api.php?{CREDS}&action=get_vod_streams").json()
        assert data[0]["rating_5based"] == 0.0

    def test_get_vod_streams_required_fields(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_movie()])
        item = client.get(f"/player_api.php?{CREDS}&action=get_vod_streams").json()[0]
        for f in ("num", "name", "stream_type", "stream_id", "stream_icon",
                  "rating", "rating_5based", "added", "category_id",
                  "container_extension", "custom_sid", "direct_source"):
            assert f in item

    def test_get_vod_info_found(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_movie(id="42")])
        resp = client.get(f"/player_api.php?{CREDS}&action=get_vod_info&vod_id=42")
        assert resp.status_code == 200
        body = resp.json()
        assert "info" in body
        assert "movie_data" in body
        assert body["movie_data"]["stream_id"] == 42
        assert body["info"]["name"] == "Movie A"

    def test_get_vod_info_not_found(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_movie(id="42")])
        body = client.get(f"/player_api.php?{CREDS}&action=get_vod_info&vod_id=999").json()
        assert body == {}

    def test_get_vod_info_skips_series(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_series(id="42")])
        body = client.get(f"/player_api.php?{CREDS}&action=get_vod_info&vod_id=42").json()
        assert body == {}


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

class TestSeries:
    def test_get_series_categories(self, tc):
        client, mock = tc
        mock.vod.get_categories.return_value = [
            Category(id="9", title="Drama", alias="drama", censored=False),
        ]
        resp = client.get(f"/player_api.php?{CREDS}&action=get_series_categories")
        data = resp.json()
        assert data[0]["category_id"] == "9"
        assert data[0]["category_name"] == "Drama"

    def test_get_series_only_series(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_movie(), _series(id="200")])
        data = client.get(f"/player_api.php?{CREDS}&action=get_series").json()
        assert len(data) == 1
        assert data[0]["series_id"] == 200
        assert data[0]["name"] == "Show A"

    def test_get_series_required_fields(self, tc):
        client, mock = tc
        mock.vod.get_content.return_value = _paged([_series()])
        item = client.get(f"/player_api.php?{CREDS}&action=get_series").json()[0]
        for f in ("num", "name", "series_id", "cover", "plot", "cast", "director",
                  "genre", "releaseDate", "last_modified", "rating", "rating_5based",
                  "backdrop_path", "youtube_trailer", "episode_run_time", "category_id"):
            assert f in item

    def test_get_series_info(self, tc):
        client, mock = tc
        mock.vod.get_seasons.return_value = [
            Season(id="10", name="Season 1", video_id="200"),
            Season(id="20", name="Season 2", video_id="200"),
        ]
        mock.vod.get_episodes.return_value = [
            Episode(id="501", name="Pilot", series_number="1", cmd="x"),
            Episode(id="502", name="Episode 2", series_number="2", cmd="y"),
        ]
        mock.vod.get_content.return_value = _paged([_series(id="200")])

        resp = client.get(f"/player_api.php?{CREDS}&action=get_series_info&series_id=200")
        assert resp.status_code == 200
        body = resp.json()

        assert "info" in body
        assert "episodes" in body
        assert "seasons" in body

        # Episodes keyed by season number string
        assert "1" in body["episodes"]
        assert "2" in body["episodes"]
        eps = body["episodes"]["1"]
        assert len(eps) == 2
        assert eps[0]["id"] == "501"
        assert eps[0]["season"] == 1
        assert eps[0]["episode_num"] == 1

        seasons = body["seasons"]
        assert len(seasons) == 2
        assert seasons[0]["season_number"] == 1
        assert seasons[0]["episode_count"] == 2

    def test_get_series_info_season_name_parse_fallback(self, tc):
        client, mock = tc
        mock.vod.get_seasons.return_value = [
            Season(id="10", name="Specials", video_id="300"),  # no digit → fallback to "1"
        ]
        mock.vod.get_episodes.return_value = []
        mock.vod.get_content.return_value = _paged([_series(id="300")])

        body = client.get(f"/player_api.php?{CREDS}&action=get_series_info&series_id=300").json()
        assert "1" in body["episodes"]


# ---------------------------------------------------------------------------
# Stream delivery routes
# ---------------------------------------------------------------------------

class TestStreamRoutes:
    def test_live_stream_redirect(self, tc):
        client, mock = tc
        mock.live_tv.get_stream_url_by_id.return_value = "http://cdn.test/live/1.m3u8"
        resp = client.get("/testuser/testpass/10", follow_redirects=False)
        assert resp.status_code == 302
        assert "cdn.test" in resp.headers["location"]

    def test_live_stream_with_ext(self, tc):
        client, mock = tc
        mock.live_tv.get_stream_url_by_id.return_value = "http://cdn.test/live/1.m3u8"
        resp = client.get("/testuser/testpass/10.m3u8", follow_redirects=False)
        assert resp.status_code == 302

    def test_live_stream_auth_fail(self, tc):
        client, _ = tc
        resp = client.get("/testuser/WRONG/10", follow_redirects=False)
        assert resp.status_code == 403

    def test_live_stream_not_found(self, tc):
        client, mock = tc
        mock.live_tv.get_stream_url_by_id.side_effect = NotFoundError("not found")
        resp = client.get("/testuser/testpass/999", follow_redirects=False)
        assert resp.status_code == 404

    def test_vod_stream_redirect(self, tc):
        client, mock = tc
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn.test/movie.mp4"
        resp = client.get("/movie/testuser/testpass/42.mp4", follow_redirects=False)
        assert resp.status_code == 302
        assert "cdn.test" in resp.headers["location"]
        mock.vod.get_stream_url_by_content_id.assert_called_once_with("42")

    def test_vod_stream_auth_fail(self, tc):
        client, _ = tc
        resp = client.get("/movie/testuser/WRONG/42.mp4", follow_redirects=False)
        assert resp.status_code == 403

    def test_series_stream_redirect(self, tc):
        client, mock = tc
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn.test/ep.mp4"
        resp = client.get("/series/testuser/testpass/501.mp4", follow_redirects=False)
        assert resp.status_code == 302
        mock.vod.get_stream_url_by_content_id.assert_called_once_with("501")

    def test_series_stream_auth_fail(self, tc):
        client, _ = tc
        resp = client.get("/series/testuser/WRONG/501.mp4", follow_redirects=False)
        assert resp.status_code == 403

    def test_health_not_shadowed_by_live_stream_route(self, tc):
        client, _ = tc
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_player_api_not_shadowed(self, tc):
        client, _ = tc
        resp = client.get(f"/player_api.php?{CREDS}")
        assert resp.status_code == 200
        assert "user_info" in resp.json()

