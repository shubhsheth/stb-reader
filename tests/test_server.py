import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from stb_reader.models import Genre, Channel, Category, Content, Season, Episode, EpisodeFile, PagedResult
from stb_reader.exceptions import NotFoundError, STBError, StreamError
from server.db import upsert_vod_content


ENV_VARS = {
    "STB_PORTAL_URL": "http://portal.test",
    "STB_MAC": "00:1A:79:00:00:01",
    "STRM_OUTPUT_DIR": "/tmp/strm_test",
    "STRM_SERVER_BASE_URL": "http://localhost:8000",
    "STRM_DATA_DIR": "/tmp/strm_test",
    "STRM_SYNC_INTERVAL_HOURS": "0",
}

ENV_VARS_PROXY = {**ENV_VARS, "STRM_PROXY_STREAMS": "true"}


@pytest.fixture
def mock_client():
    c = MagicMock()
    c.authenticate.return_value = None
    return c


@pytest.fixture
def test_client(mock_client):
    import server.main as main_mod
    from server.db import init_db
    real_db = init_db(":memory:")
    with patch.dict("os.environ", ENV_VARS):
        with patch("server.main.STBClient", return_value=mock_client):
            with patch("server.main.init_db", return_value=real_db):
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


_VOD_ROW = {
    "content_id": "c1",
    "name": "Test Movie",
    "cmd": "/media/c1.mpg",
    "screenshot_uri": "/stalker_portal/screenshots/c1.jpg",
    "genres": "Action",
    "year": "2023",
    "description": "A film",
    "rating": "8.0",
    "duration": 90,
    "is_series": 0,
    "fav": 0,
    "for_rent": 0,
    "lock": 0,
    "portal_raw": "{}",
    "synced_at": "2024-01-01T00:00:00+00:00",
}


class TestScreenshot:
    def test_redirects_to_screenshot_uri(self, test_client):
        tc, _ = test_client
        db = tc.app.state.db
        upsert_vod_content(db, _VOD_ROW)
        resp = tc.get("/vod/content/c1/screenshot", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://portal.test/stalker_portal/screenshots/c1.jpg"

    def test_redirects_absolute_screenshot_uri_unchanged(self, test_client):
        tc, _ = test_client
        db = tc.app.state.db
        upsert_vod_content(db, {**_VOD_ROW, "screenshot_uri": "http://cdn.example.com/img/c1.jpg"})
        resp = tc.get("/vod/content/c1/screenshot", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://cdn.example.com/img/c1.jpg"

    def test_404_when_content_not_found(self, test_client):
        tc, _ = test_client
        resp = tc.get("/vod/content/nonexistent/screenshot", follow_redirects=False)
        assert resp.status_code == 404

    def test_404_when_screenshot_uri_empty(self, test_client):
        tc, _ = test_client
        db = tc.app.state.db
        upsert_vod_content(db, {**_VOD_ROW, "screenshot_uri": ""})
        resp = tc.get("/vod/content/c1/screenshot", follow_redirects=False)
        assert resp.status_code == 404


@pytest.fixture
def test_client_proxy(mock_client):
    import server.main as main_mod
    from server.db import init_db
    real_db = init_db(":memory:")
    with patch.dict("os.environ", ENV_VARS_PROXY):
        with patch("server.main.STBClient", return_value=mock_client):
            with patch("server.main.init_db", return_value=real_db):
                with TestClient(main_mod.app, raise_server_exceptions=False) as tc:
                    yield tc, mock_client


def _make_upstream(body: bytes = b"videodata", status: int = 200, headers: dict | None = None):
    """Build a mock httpx response that supports async streaming and buffered reads."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.headers = headers or {"content-type": "video/mp4", "content-length": str(len(body))}
    resp.url = "http://cdn/stream"

    async def _aiter_bytes(chunk_size=65536):
        yield body

    async def _aread():
        return body

    async def _aclose():
        pass

    resp.aiter_bytes = _aiter_bytes
    resp.aread = _aread
    resp.aclose = _aclose
    return resp


class TestProxyMode:
    def _patch_httpx(self, url: str, body: bytes = b"videodata", status: int = 200, headers: dict | None = None):
        upstream = _make_upstream(body, status, headers)
        mock_client_obj = AsyncMock()
        mock_client_obj.build_request.return_value = MagicMock()
        mock_client_obj.send = AsyncMock(return_value=upstream)
        mock_client_obj.aclose = AsyncMock()
        return patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_client_obj)

    def test_vod_content_stream_proxies_bytes(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/movie.mp4"
        with self._patch_httpx("http://cdn/movie.mp4"):
            resp = tc.get("/vod/content/77/stream")
        assert resp.status_code == 200
        assert resp.content == b"videodata"
        assert resp.headers["content-type"] == "video/mp4"

    def test_vod_episode_stream_proxies_bytes(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_first_file.return_value = "http://cdn/ep.mp4"
        with self._patch_httpx("http://cdn/ep.mp4"):
            resp = tc.get("/vod/content/10/seasons/1/episodes/55/stream")
        assert resp.status_code == 200
        assert resp.content == b"videodata"

    def test_vod_episode_file_stream_proxies_bytes(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_file_id.return_value = "http://cdn/file.mp4"
        with self._patch_httpx("http://cdn/file.mp4"):
            resp = tc.get("/vod/content/10/seasons/1/episodes/55/files/1/stream")
        assert resp.status_code == 200
        assert resp.content == b"videodata"

    def test_live_tv_channel_stream_proxies_bytes(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.live_tv.get_stream_url_by_id.return_value = "http://cdn/live.ts"
        with self._patch_httpx("http://cdn/live.ts"):
            resp = tc.get("/live-tv/channels/42/stream")
        assert resp.status_code == 200
        assert resp.content == b"videodata"

    def test_proxy_forwards_range_header_for_non_hls(self, test_client_proxy):
        # For non-HLS content, Range is forwarded on a second request so seeking works.
        # The first request (no Range) detects content type; the second carries the Range.
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/movie.mp4"
        upstream = _make_upstream(b"partial", status=206, headers={
            "content-type": "video/mp4",
            "content-range": "bytes 0-5/100",
            "content-length": "6",
        })
        mock_httpx_client = AsyncMock()
        mock_httpx_client.build_request.return_value = MagicMock()
        mock_httpx_client.send = AsyncMock(return_value=upstream)
        mock_httpx_client.aclose = AsyncMock()
        with patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_httpx_client):
            resp = tc.get("/vod/content/77/stream", headers={"Range": "bytes=0-5"})
        assert resp.status_code == 206
        assert resp.headers["content-range"] == "bytes 0-5/100"
        # build_request is called twice: first without Range, then with Range
        all_calls = mock_httpx_client.build_request.call_args_list
        assert len(all_calls) == 2
        first_headers = {k.lower() for k in all_calls[0][1]["headers"]}
        second_headers = {k.lower() for k in all_calls[1][1]["headers"]}
        assert "range" not in first_headers
        assert "range" in second_headers

    def test_lavf_user_agent_proxied_in_proxy_mode(self, test_client_proxy):
        # FFmpeg/ffprobe (Lavf UA) goes through the proxy in proxy mode so that:
        # - all CDN requests originate from the server (IP-lock consistency)
        # - HLS seeking uses individual fast proxy requests rather than a long CDN scan
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/movie.mp4"
        with self._patch_httpx("http://cdn/movie.mp4"):
            resp = tc.get(
                "/vod/content/77/stream",
                headers={"User-Agent": "Lavf/61.7.100"},
            )
        assert resp.status_code == 200
        assert resp.content == b"videodata"

    def test_hls_playlist_served_as_200_even_when_cdn_returns_206(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/path/playlist.m3u8"
        playlist = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000000\ntracks-v1a1/mono.m3u8\n"
        upstream = _make_upstream(
            playlist.encode(),
            status=206,  # CDN returned partial — we must still serve complete 200
            headers={"content-type": "application/vnd.apple.mpegurl"},
        )
        upstream.url = "http://cdn/path/playlist.m3u8"
        mock_httpx_client = AsyncMock()
        mock_httpx_client.build_request.return_value = MagicMock()
        mock_httpx_client.send = AsyncMock(return_value=upstream)
        mock_httpx_client.aclose = AsyncMock()
        with patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_httpx_client):
            resp = tc.get("/vod/content/77/stream", headers={"Range": "bytes=0-100"})
        assert resp.status_code == 200
        assert "/proxy?url=" in resp.text
        # Range must NOT have been sent to the CDN for the playlist fetch
        first_headers = {k.lower() for k in mock_httpx_client.build_request.call_args[1]["headers"]}
        assert "range" not in first_headers

    def test_proxy_404_on_not_found(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.side_effect = NotFoundError("not found")
        resp = tc.get("/vod/content/999/stream")
        assert resp.status_code == 404

    def test_proxy_502_on_stream_error(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.side_effect = StreamError("no stream")
        resp = tc.get("/vod/content/1/stream")
        assert resp.status_code == 502

    def test_proxy_rewrites_hls_urls_through_proxy_endpoint(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/path/playlist.m3u8"
        playlist = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=1000000\n"
            "tracks-v1a1/mono.m3u8?token=abc\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=500000\n"
            "tracks-t1/mono.m3u8?token=abc\n"
        )
        upstream = _make_upstream(
            playlist.encode(),
            status=200,
            headers={"content-type": "application/vnd.apple.mpegurl"},
        )
        upstream.url = "http://cdn/path/playlist.m3u8"
        mock_httpx_client = AsyncMock()
        mock_httpx_client.build_request.return_value = MagicMock()
        mock_httpx_client.send = AsyncMock(return_value=upstream)
        mock_httpx_client.aclose = AsyncMock()
        with patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_httpx_client):
            resp = tc.get("/vod/content/77/stream")
        assert resp.status_code == 200
        body = resp.text
        # URLs must go through /proxy so all CDN requests originate from the server
        assert "/proxy?url=" in body
        assert "cdn%2Fpath%2Ftracks-v1a1" in body
        assert "cdn%2Fpath%2Ftracks-t1" in body
        assert "#EXT-X-STREAM-INF" in body

    def test_proxy_rewrites_absolute_urls_through_proxy_endpoint(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/path/playlist.m3u8"
        playlist = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=1000000\n"
            "http://other-cdn/tracks-v1a1/mono.m3u8\n"
        )
        upstream = _make_upstream(
            playlist.encode(),
            status=200,
            headers={"content-type": "application/vnd.apple.mpegurl"},
        )
        upstream.url = "http://cdn/path/playlist.m3u8"
        mock_httpx_client = AsyncMock()
        mock_httpx_client.build_request.return_value = MagicMock()
        mock_httpx_client.send = AsyncMock(return_value=upstream)
        mock_httpx_client.aclose = AsyncMock()
        with patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_httpx_client):
            resp = tc.get("/vod/content/77/stream")
        assert "/proxy?url=" in resp.text
        assert "other-cdn" in resp.text

    def test_proxy_endpoint_streams_non_hls(self, test_client_proxy):
        tc, _ = test_client_proxy
        upstream = _make_upstream(b"segmentdata", status=200, headers={"content-type": "video/mp2t"})
        upstream.url = "http://cdn/seg001.ts"
        mock_httpx_client = AsyncMock()
        mock_httpx_client.build_request.return_value = MagicMock()
        mock_httpx_client.send = AsyncMock(return_value=upstream)
        mock_httpx_client.aclose = AsyncMock()
        with patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_httpx_client):
            resp = tc.get("/proxy?url=http://cdn/seg001.ts")
        assert resp.status_code == 200
        assert resp.content == b"segmentdata"

    def test_proxy_rewrites_uri_attributes_in_hls_tags(self, test_client_proxy):
        # URI= attributes in #EXT-X-MEDIA, #EXT-X-KEY, #EXT-X-MAP must also go through /proxy
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/path/playlist.m3u8"
        playlist = (
            '#EXTM3U\n'
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",URI="tracks-t1/mono.m3u8"\n'
            '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
            '#EXT-X-MAP:URI="init.mp4"\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=1000000,AUDIO="audio"\n'
            'tracks-v1a1/mono.m3u8\n'
        )
        upstream = _make_upstream(
            playlist.encode(),
            status=200,
            headers={"content-type": "application/vnd.apple.mpegurl"},
        )
        upstream.url = "http://cdn/path/playlist.m3u8"
        mock_httpx_client = AsyncMock()
        mock_httpx_client.build_request.return_value = MagicMock()
        mock_httpx_client.send = AsyncMock(return_value=upstream)
        mock_httpx_client.aclose = AsyncMock()
        with patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_httpx_client):
            resp = tc.get("/vod/content/77/stream")
        body = resp.text
        assert resp.status_code == 200
        # All URI= attributes must point through /proxy (no bare relative or CDN URLs left)
        assert 'URI="tracks-t1' not in body, "audio URI not rewritten"
        assert 'URI="key.bin"' not in body, "key URI not rewritten"
        assert 'URI="init.mp4"' not in body, "map URI not rewritten"
        assert body.count("/proxy?url=") == 4  # audio URI, key URI, map URI, stream URI


class TestCORS:
    def test_cors_header_on_proxy_endpoint(self, test_client_proxy):
        tc, _ = test_client_proxy
        upstream = _make_upstream(b"seg", status=200, headers={"content-type": "video/mp2t"})
        upstream.url = "http://cdn/seg.ts"
        mock_httpx_client = AsyncMock()
        mock_httpx_client.build_request.return_value = MagicMock()
        mock_httpx_client.send = AsyncMock(return_value=upstream)
        mock_httpx_client.aclose = AsyncMock()
        with patch("server.routes._helpers.httpx.AsyncClient", return_value=mock_httpx_client):
            resp = tc.get("/proxy?url=http://cdn/seg.ts", headers={"Origin": "http://player.example.com"})
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_cors_header_on_stream_endpoint(self, test_client_proxy):
        tc, mock = test_client_proxy
        mock.vod.get_stream_url_by_content_id.return_value = "http://cdn/movie.mp4"
        with patch("server.routes._helpers.httpx.AsyncClient") as mock_cls:
            upstream = _make_upstream()
            mock_instance = AsyncMock()
            mock_instance.build_request.return_value = MagicMock()
            mock_instance.send = AsyncMock(return_value=upstream)
            mock_instance.aclose = AsyncMock()
            mock_cls.return_value = mock_instance
            resp = tc.get("/vod/content/77/stream", headers={"Origin": "http://player.example.com"})
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_cors_preflight_options(self, test_client):
        tc, _ = test_client
        resp = tc.options(
            "/proxy?url=http://cdn/seg.ts",
            headers={"Origin": "http://player.example.com", "Access-Control-Request-Method": "GET"},
        )
        assert resp.status_code in (200, 204)
        assert resp.headers.get("access-control-allow-origin") == "*"
