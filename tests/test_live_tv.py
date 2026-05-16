import pytest
import responses as responses_lib
from stb_reader._http import STBSession
from stb_reader._http import _clean_url
from stb_reader.live_tv import ITVService
from stb_reader.exceptions import STBError, StreamError
from tests.conftest import BASE_URL, MAC, PORTAL_URL


def _make_session():
    return STBSession(BASE_URL, MAC, "000000000000", "en", "Europe/London")


# --- _clean_url ---

def test_clean_url_strips_ffmpeg_prefix():
    assert _clean_url("ffmpeg http://stream.test/live") == "http://stream.test/live"


def test_clean_url_strips_auto_prefix():
    assert _clean_url("auto http://stream.test/live") == "http://stream.test/live"


def test_clean_url_no_prefix():
    assert _clean_url("http://stream.test/live") == "http://stream.test/live"


# --- get_genres ---

@responses_lib.activate
def test_get_genres_returns_list():
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": [{"id": "1", "title": "News", "alias": "news", "censored": False}]},
    )
    svc = ITVService(_make_session())
    genres = svc.get_genres()
    assert len(genres) == 1
    assert genres[0].id == "1"
    assert genres[0].title == "News"
    assert genres[0].alias == "news"
    assert genres[0].censored is False


# --- get_channels ---

@responses_lib.activate
def test_get_channels_page_translated_to_zero_index():
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [], "total_items": 0, "max_page_items": 14}},
    )
    svc = ITVService(_make_session())
    svc.get_channels(page=3)
    url = responses_lib.calls[0].request.url
    assert "p=2" in url


@responses_lib.activate
def test_get_channels_parses_channels():
    ch = {"id": "10", "number": "5", "name": "CNN", "cmd": "ffmpeg http://x", "logo": "", "tv_genre_id": "1", "hd": True, "censored": False}
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"data": [ch], "total_items": 1, "max_page_items": 14}},
    )
    svc = ITVService(_make_session())
    result = svc.get_channels()
    assert result.total == 1
    assert result.page == 1
    assert result.per_page == 14
    assert result.items[0].name == "CNN"
    assert result.items[0].hd is True


# --- get_all_channels ---

@responses_lib.activate
def test_get_all_channels_returns_list_from_single_call():
    channels = [
        {"id": "1", "number": "1", "name": "BBC", "cmd": "http://bbc", "logo": "", "tv_genre_id": "1", "hd": False, "censored": False, "xmltv_id": "bbc1.uk"},
        {"id": "2", "number": "2", "name": "ITV", "cmd": "http://itv", "logo": "", "tv_genre_id": "1", "hd": True, "censored": False, "xmltv_id": ""},
    ]
    responses_lib.add(responses_lib.GET, PORTAL_URL, json={"js": channels})
    svc = ITVService(_make_session())
    result = svc.get_all_channels()
    assert len(result) == 2
    assert len(responses_lib.calls) == 1
    assert result[0].name == "BBC"
    assert result[0].xmltv_id == "bbc1.uk"
    assert result[1].hd is True
    assert result[1].xmltv_id == ""


# --- get_stream_url ---

@responses_lib.activate
def test_get_stream_url_strips_prefix():
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"cmd": "ffmpeg http://cdn.test/stream", "error": ""}},
    )
    responses_lib.add(responses_lib.GET, "http://cdn.test/stream", body=b"")
    svc = ITVService(_make_session())
    url = svc.get_stream_url("ffmpeg http://cdn.test/stream")
    assert url == "http://cdn.test/stream"


@responses_lib.activate
def test_get_stream_url_raises_stream_error_on_error_field():
    responses_lib.add(
        responses_lib.GET, PORTAL_URL,
        json={"js": {"cmd": "", "error": "nothing_to_play"}},
    )
    svc = ITVService(_make_session())
    with pytest.raises(StreamError):
        svc.get_stream_url("http://x")
