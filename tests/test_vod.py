import pytest
import responses as responses_lib
from stb_reader._http import STBSession
from stb_reader.vod import VODService
from stb_reader.exceptions import STBError, StreamError
from tests.conftest import BASE_URL, MAC, PORTAL_PATH


def _portal_url():
    return f"{BASE_URL}{PORTAL_PATH}"


def _make_session():
    return STBSession(BASE_URL, MAC, "000000000000", "en", "Europe/London")


# --- get_categories ---

@responses_lib.activate
def test_get_categories_returns_list():
    responses_lib.add(
        responses_lib.GET, _portal_url(),
        json={"js": [{"id": "5", "title": "Action", "alias": "action", "censored": False}]},
    )
    svc = VODService(_make_session())
    cats = svc.get_categories()
    assert len(cats) == 1
    assert cats[0].id == "5"
    assert cats[0].title == "Action"


# --- get_content ---

@responses_lib.activate
def test_get_content_page_is_1_indexed():
    responses_lib.add(
        responses_lib.GET, _portal_url(),
        json={"js": {"data": [], "total_items": 0, "max_page_items": 14}},
    )
    svc = VODService(_make_session())
    svc.get_content(page=3)
    url = responses_lib.calls[0].request.url
    assert "p=3" in url


@responses_lib.activate
def test_get_content_parses_content():
    item = {
        "id": "100", "name": "Inception", "cmd": "http://x", "screenshot_uri": "",
        "genres_str": "Sci-Fi", "year": "2010", "description": "A dream", "rating_imdb": "8.8",
        "time": "148", "is_series": False, "fav": False,
    }
    responses_lib.add(
        responses_lib.GET, _portal_url(),
        json={"js": {"data": [item], "total_items": 1, "max_page_items": 14}},
    )
    svc = VODService(_make_session())
    result = svc.get_content()
    assert result.total == 1
    assert result.items[0].name == "Inception"
    assert result.items[0].is_series is False


# --- get_seasons ---

@responses_lib.activate
def test_get_seasons_returns_list():
    responses_lib.add(
        responses_lib.GET, _portal_url(),
        json={"js": {"data": [{"id": "1", "name": "Season 1", "video_id": "200"}]}},
    )
    svc = VODService(_make_session())
    seasons = svc.get_seasons("50")
    assert len(seasons) == 1
    assert seasons[0].name == "Season 1"
    url = responses_lib.calls[0].request.url
    assert "movie_id=50" in url
    assert "season_id=0" in url
    assert "episode_id=0" in url


# --- get_episodes ---

@responses_lib.activate
def test_get_episodes_returns_list():
    responses_lib.add(
        responses_lib.GET, _portal_url(),
        json={"js": {"data": [{"id": "99", "name": "Pilot", "series_number": "1", "cmd": "http://ep"}]}},
    )
    svc = VODService(_make_session())
    eps = svc.get_episodes("50", "1")
    assert len(eps) == 1
    assert eps[0].name == "Pilot"
    assert eps[0].cmd == "http://ep"
    url = responses_lib.calls[0].request.url
    assert "movie_id=50" in url
    assert "season_id=1" in url


# --- get_stream_url ---

@responses_lib.activate
def test_get_stream_url_returns_clean_url():
    responses_lib.add(
        responses_lib.GET, _portal_url(),
        json={"js": {"cmd": "ffmpeg http://cdn/movie.mp4", "error": ""}},
    )
    svc = VODService(_make_session())
    url = svc.get_stream_url("http://cmd")
    assert url == "http://cdn/movie.mp4"



@responses_lib.activate
def test_get_stream_url_raises_stream_error():
    responses_lib.add(
        responses_lib.GET, _portal_url(),
        json={"js": {"cmd": "", "error": "nothing_to_play"}},
    )
    svc = VODService(_make_session())
    with pytest.raises(StreamError):
        svc.get_stream_url("http://cmd")


# --- get_stream_url_by_content_id ---

@responses_lib.activate
def test_get_stream_url_by_content_id_finds_item():
    item = {"id": "77", "name": "Movie", "cmd": "ffmpeg http://movie", "screenshot_uri": "", "genres_str": "", "year": "", "description": "", "rating_imdb": "", "time": "", "is_series": False, "fav": False}
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [item], "total_items": 1, "max_page_items": 14}})
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"cmd": "ffmpeg http://movie", "error": ""}})
    svc = VODService(_make_session())
    url = svc.get_stream_url_by_content_id("77")
    assert url == "http://movie"


@responses_lib.activate
def test_get_stream_url_by_content_id_raises_when_not_found():
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [], "total_items": 0, "max_page_items": 14}})
    svc = VODService(_make_session())
    with pytest.raises(STBError, match="content not found"):
        svc.get_stream_url_by_content_id("999")


# --- get_stream_url_by_episode_id ---

@responses_lib.activate
def test_get_stream_url_by_episode_id_finds_episode():
    # seasons
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "1", "name": "S1", "video_id": "200"}]}})
    # episodes for season 1
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "55", "name": "Ep1", "series_number": "1", "cmd": "http://ep55"}]}})
    # create_link
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"cmd": "http://ep55", "error": ""}})
    svc = VODService(_make_session())
    url = svc.get_stream_url_by_episode_id("55", "10")
    assert url == "http://ep55"


@responses_lib.activate
def test_get_stream_url_by_episode_id_constructs_cmd_when_missing():
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "1", "name": "S1", "video_id": "200"}]}})
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "55", "name": "Ep1", "series_number": "1"}]}})
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"cmd": "http://cdn/stream.m3u8", "error": ""}})
    svc = VODService(_make_session())
    url = svc.get_stream_url_by_episode_id("55", "10")
    assert url == "http://cdn/stream.m3u8"
    assert "cmd=%2Fmedia%2F55.mpg" in responses_lib.calls[2].request.url


@responses_lib.activate
def test_open_episode_stream_uses_series_param_for_create_link():
    # get_info (parent VOD cmd)
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"cmd": "http://parent-cmd"}})
    # get_seasons
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "1", "name": "S1", "video_id": "200"}]}})
    # get_episodes
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "55", "name": "Ep1", "series_number": "3"}]}})
    # create_link returns full CDN URL
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"cmd": "ffmpeg http://cdn/stream.m3u8", "error": ""}})
    # open_url fetches the CDN stream
    responses_lib.add(responses_lib.GET, "http://cdn/stream.m3u8", status=200, body=b"video-bytes", headers={"Content-Type": "application/x-mpegURL"})
    svc = VODService(_make_session())
    resp = svc.open_episode_stream("55", "10")
    assert resp.status_code == 200
    create_link_url = responses_lib.calls[3].request.url
    assert "series=3" in create_link_url
    assert "forced_storage=0" in create_link_url
    assert "disable_ad=0" in create_link_url


@responses_lib.activate
def test_open_episode_stream_falls_back_to_open_stream_for_token_url():
    # get_info (parent cmd empty)
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"cmd": ""}})
    # get_seasons
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "1", "name": "S1", "video_id": "200"}]}})
    # get_episodes
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "55", "name": "Ep1", "series_number": "1"}]}})
    # create_link returns ?token= URL
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"cmd": "?token=abc123", "error": ""}})
    # open_stream fetches the token URL
    responses_lib.add(responses_lib.GET, _portal_url(), status=200, body=b"video-bytes", headers={"Content-Type": "video/mp2t"})
    svc = VODService(_make_session())
    resp = svc.open_episode_stream("55", "10")
    assert resp.status_code == 200
    assert "token=abc123" in responses_lib.calls[4].request.url


@responses_lib.activate
def test_get_stream_url_by_episode_id_raises_when_not_found():
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "1", "name": "S1", "video_id": "200"}]}})
    responses_lib.add(responses_lib.GET, _portal_url(), json={"js": {"data": [{"id": "1", "name": "Ep1", "series_number": "1", "cmd": "http://ep1"}]}})
    svc = VODService(_make_session())
    with pytest.raises(STBError, match="episode not found"):
        svc.get_stream_url_by_episode_id("999", "10")
