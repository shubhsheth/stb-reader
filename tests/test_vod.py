import pytest
import responses as responses_lib
from stb_reader.vod import VODService
from stb_reader.exceptions import STBError, StreamError
from tests.conftest import PORTAL_URL


# --- get_categories ---

@responses_lib.activate
def test_get_categories_returns_all_including_adult(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": [
            {"id": "5", "title": "Action", "alias": "action", "censored": False},
            {"id": "9", "title": "Adult", "alias": "adult", "censored": True},
            {"id": "10", "title": "18+", "alias": "18plus", "censored": True},
        ]},
    )
    svc = VODService(session)
    cats = svc.get_categories()
    assert len(cats) == 3
    titles = [c.title for c in cats]
    assert "Adult" in titles
    assert "18+" in titles
    assert cats[1].censored is True


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
def test_get_episodes_returns_paged_result(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [{"id": "99", "name": "Pilot", "series_number": "1", "cmd": "http://ep"}],
                     "total_items": 50, "max_page_items": 14}},
    )
    svc = VODService(session)
    result = svc.get_episodes("50", "1")
    assert len(result.items) == 1
    assert result.items[0].name == "Pilot"
    assert result.items[0].cmd == "http://ep"
    assert result.total == 50
    assert result.per_page == 14
    assert result.page == 1
    assert len(responses_lib.calls) == 1
    url = responses_lib.calls[0].request.url
    assert "movie_id=50" in url
    assert "season_id=1" in url


@responses_lib.activate
def test_get_episodes_passes_page_param(session):
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [], "total_items": 50, "max_page_items": 14}},
    )
    svc = VODService(session)
    result = svc.get_episodes("50", "1", page=3)
    assert result.page == 3
    assert "p=3" in responses_lib.calls[0].request.url


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


