import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from server.db import (
    add_strm_file,
    add_to_library,
    get_sync_state,
    get_vod_content,
    init_db,
    upsert_vod_content,
)
from server.vod_sync import run_portal_sync
from stb_reader.exceptions import AuthError, STBError
from stb_reader.models import Category, Content, PagedResult


def _make_vod(noop=False):
    """Return a mock VODService with one category and one page of two items."""
    vod = MagicMock()
    vod.get_categories.return_value = [
        Category(id="1", title="Movies", alias="movies", censored=False)
    ]
    items = [
        Content(
            id="c1", name="Action Movie", cmd="/m/c1.mpg", screenshot_uri="",
            genres="Action", year="2020", description="Boom", rating="7.0",
            duration="90", is_series=False, fav=False,
        ),
        Content(
            id="c2", name="Drama Show", cmd="/m/c2.mpg", screenshot_uri="",
            genres="Drama", year="2021", description="Cry", rating="8.0",
            duration="30", is_series=True, fav=False,
        ),
    ]
    vod.get_content.return_value = PagedResult(items=items, total=2, page=1, per_page=14)
    return vod


@pytest.fixture
def db(tmp_path):
    return init_db(str(tmp_path / "test.db"))


@pytest.fixture
def lock():
    return threading.Lock()


def test_sync_populates_vod_content(db, lock):
    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0)
    assert get_vod_content(db, "c1") is not None
    assert get_vod_content(db, "c2") is not None


def test_sync_sets_status_success(db, lock):
    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0)
    state = get_sync_state(db)
    assert state["last_sync_status"] == "success"
    assert state["content_count"] == 2


def test_sync_delay_called_between_requests(db, lock):
    vod = _make_vod()
    with patch("server.vod_sync.time.sleep") as mock_sleep:
        run_portal_sync(db, lock, vod, "/output", delay_ms=250, max_pages=0)
    assert mock_sleep.call_count >= 1
    for c in mock_sleep.call_args_list:
        assert c == call(0.25)


def test_sync_max_pages_stops_early(db, lock):
    vod = MagicMock()
    vod.get_categories.return_value = []
    page1_items = [
        Content(id=f"c{i}", name=f"Movie {i}", cmd="", screenshot_uri="",
                genres="", year="2020", description="", rating="", duration="90",
                is_series=False, fav=False)
        for i in range(3)
    ]
    page2_items = [
        Content(id=f"d{i}", name=f"Other {i}", cmd="", screenshot_uri="",
                genres="", year="2020", description="", rating="", duration="90",
                is_series=False, fav=False)
        for i in range(3)
    ]
    vod.get_content.side_effect = [
        PagedResult(items=page1_items, total=6, page=1, per_page=3),
        PagedResult(items=page2_items, total=6, page=2, per_page=3),
    ]
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=1)
    # Only page 1 fetched
    assert vod.get_content.call_count == 1
    assert get_vod_content(db, "c0") is not None
    assert get_vod_content(db, "d0") is None


def test_sync_max_pages_skips_stale_cleanup(db, lock):
    # Pre-populate a row that won't appear in the capped sync
    upsert_vod_content(db, {
        "content_id": "old", "name": "Old", "cmd": "", "screenshot_uri": "",
        "genres": "", "year": "2000", "description": "", "rating": "", "duration": 0,
        "is_series": 0, "fav": 0, "for_rent": 0, "lock": 0, "portal_raw": "{}",
        "synced_at": "2020-01-01T00:00:00+00:00",
    })
    db.commit()
    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=1)
    # Stale row preserved because sync was capped
    assert get_vod_content(db, "old") is not None


def test_sync_stale_content_removed_on_full_sync(db, lock, tmp_path):
    # Pre-populate a stale row with a strm file
    upsert_vod_content(db, {
        "content_id": "stale", "name": "Gone", "cmd": "", "screenshot_uri": "",
        "genres": "", "year": "2000", "description": "", "rating": "", "duration": 0,
        "is_series": 0, "fav": 0, "for_rent": 0, "lock": 0, "portal_raw": "{}",
        "synced_at": "2020-01-01T00:00:00+00:00",
    })
    db.commit()
    add_to_library(db, "stale")
    strm = tmp_path / "stale.strm"
    strm.write_text("http://x\n")
    add_strm_file(db, "stale", None, None, "stale", str(strm))

    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0)

    assert get_vod_content(db, "stale") is None
    assert not strm.exists()


def test_sync_preserves_in_library_on_upsert(db, lock):
    upsert_vod_content(db, {
        "content_id": "c1", "name": "Action Movie", "cmd": "", "screenshot_uri": "",
        "genres": "", "year": "2020", "description": "", "rating": "", "duration": 0,
        "is_series": 0, "fav": 0, "for_rent": 0, "lock": 0, "portal_raw": "{}",
        "synced_at": "2020-01-01T00:00:00+00:00",
    })
    db.commit()
    add_to_library(db, "c1")

    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0)

    item = get_vod_content(db, "c1")
    assert item["in_library"] == 1
    assert item["added_at"] is not None


def test_sync_content_changed_resets_library(db, lock, tmp_path):
    # Insert c1 with completely different name (< 75% similar)
    upsert_vod_content(db, {
        "content_id": "c1", "name": "Totally Different Film", "cmd": "", "screenshot_uri": "",
        "genres": "", "year": "1990", "description": "", "rating": "", "duration": 0,
        "is_series": 0, "fav": 0, "for_rent": 0, "lock": 0, "portal_raw": "{}",
        "synced_at": "2020-01-01T00:00:00+00:00",
    })
    db.commit()
    add_to_library(db, "c1")
    strm = tmp_path / "old.strm"
    strm.write_text("http://x\n")
    add_strm_file(db, "c1", None, None, "c1", str(strm))

    vod = _make_vod()  # returns c1 as "Action Movie" / 2020
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0)

    item = get_vod_content(db, "c1")
    assert item["in_library"] == 0
    assert item["added_at"] is None
    assert not strm.exists()
    assert item["name"] == "Action Movie"


def test_sync_page_error_skipped_and_finishes_success(db, lock):
    vod = MagicMock()
    vod.get_categories.return_value = []
    good_items = [
        Content(id="c1", name="Movie", cmd="", screenshot_uri="",
                genres="", year="2020", description="", rating="", duration="90",
                is_series=False, fav=False)
    ]
    vod.get_content.side_effect = [
        STBError("portal error"),
        PagedResult(items=good_items, total=1, page=2, per_page=1),
    ]
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=2)
    state = get_sync_state(db)
    assert state["last_sync_status"] == "success"
    assert get_vod_content(db, "c1") is not None


def test_sync_auth_error_sets_failed(db, lock):
    vod = MagicMock()
    vod.get_categories.return_value = []
    vod.get_content.side_effect = AuthError("token expired")
    with pytest.raises(AuthError):
        run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0)
    state = get_sync_state(db)
    assert state["last_sync_status"] == "failed"
    assert "token expired" in state["error_message"]
