import pytest
import responses as responses_lib
from stb_reader.vod import VODService
from stb_reader.exceptions import NotFoundError, STBError, StreamError
from tests.conftest import PORTAL_URL


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


@responses_lib.activate
def test_get_content_is_series_string_zero_is_false(session):
    item = {
        "id": "101", "name": "A Movie", "cmd": "", "screenshot_uri": "",
        "genres_str": "", "year": "2020", "description": "", "rating_imdb": "",
        "time": "90", "is_series": "0", "fav": False,
    }
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [item], "total_items": 1, "max_page_items": 14}},
    )
    svc = VODService(session)
    result = svc.get_content()
    assert result.items[0].is_series is False


@responses_lib.activate
def test_get_content_is_series_string_one_is_true(session):
    item = {
        "id": "102", "name": "A Show", "cmd": "", "screenshot_uri": "",
        "genres_str": "", "year": "2021", "description": "", "rating_imdb": "",
        "time": "30", "is_series": "1", "fav": False,
    }
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [item], "total_items": 1, "max_page_items": 14}},
    )
    svc = VODService(session)
    result = svc.get_content()
    assert result.items[0].is_series is True


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
        json={"js": {"data": [{"id": "99", "name": "Pilot", "series_number": "1", "cmd": "http://ep"}],
                     "total_items": 1, "max_page_items": 14}},
    )
    svc = VODService(session)
    eps = svc.get_episodes("50", "1")
    assert len(eps) == 1
    assert eps[0].name == "Pilot"
    assert eps[0].cmd == "http://ep"
    url = responses_lib.calls[0].request.url
    assert "movie_id=50" in url
    assert "season_id=1" in url


@responses_lib.activate
def test_get_episodes_paginates_all_pages(session):
    page1 = [{"id": str(i), "name": f"Ep {i}", "series_number": str(i), "cmd": ""} for i in range(1, 15)]
    page2 = [{"id": str(i), "name": f"Ep {i}", "series_number": str(i), "cmd": ""} for i in range(15, 21)]
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": page1, "total_items": 20, "max_page_items": 14}},
    )
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": page2, "total_items": 20, "max_page_items": 14}},
    )
    svc = VODService(session)
    eps = svc.get_episodes("50", "1")
    assert len(eps) == 20
    assert len(responses_lib.calls) == 2
    assert "p=2" in responses_lib.calls[1].request.url


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
