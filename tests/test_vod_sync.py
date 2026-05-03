import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from server.db import (
    add_strm_file,
    add_to_library,
    get_sync_state,
    get_vod_content,
    init_db,
    set_sync_state,
    upsert_vod_content,
)
from server.vod_sync import _build_content_row, _content_hash, run_portal_sync
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


# ---------------------------------------------------------------------------
# _content_hash
# ---------------------------------------------------------------------------
# _build_content_row: is_series string conversion
# ---------------------------------------------------------------------------

def test_build_content_row_is_series_string_zero():
    row = _build_content_row({"id": "1", "name": "Movie", "is_series": "0"})
    assert row["is_series"] == 0


def test_build_content_row_is_series_string_one():
    row = _build_content_row({"id": "2", "name": "Show", "is_series": "1"})
    assert row["is_series"] == 1


# ---------------------------------------------------------------------------

def test_content_hash_same_inputs_same_hash():
    row = {"name": "Movie", "year": "2020", "cmd": "/m/1.mpg", "genres": "Action", "rating": "7.0", "is_series": 0}
    assert _content_hash(row) == _content_hash(row)


def test_content_hash_different_name_different_hash():
    row = {"name": "Movie A", "year": "2020", "cmd": "/m/1.mpg", "genres": "Action", "rating": "7.0", "is_series": 0}
    row2 = {**row, "name": "Movie B"}
    assert _content_hash(row) != _content_hash(row2)


def test_content_hash_different_year_different_hash():
    row = {"name": "Movie", "year": "2020", "cmd": "/m/1.mpg", "genres": "", "rating": "", "is_series": 0}
    assert _content_hash(row) != _content_hash({**row, "year": "2021"})


def test_content_hash_stored_after_sync(db, lock):
    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)
    item = get_vod_content(db, "c1")
    assert item["content_hash"] is not None
    assert len(item["content_hash"]) == 32  # MD5 hex digest


# ---------------------------------------------------------------------------
# Early-stop
# ---------------------------------------------------------------------------

def _make_page(ids, name_prefix="Movie", year="2020", total=None, per_page=None):
    """Build a PagedResult from a list of string IDs."""
    items = [
        Content(id=cid, name=f"{name_prefix} {cid}", cmd=f"/m/{cid}.mpg", screenshot_uri="",
                genres="Action", year=year, description="", rating="7.0",
                duration="90", is_series=False, fav=False)
        for cid in ids
    ]
    n = total if total is not None else len(ids)
    pp = per_page if per_page is not None else len(ids)
    return PagedResult(items=items, total=n, page=1, per_page=pp)


def test_early_stop_halts_after_stable_pages(db, lock):
    """After early_stop_pages consecutive unchanged pages, sync stops fetching."""
    vod = MagicMock()
    vod.get_categories.return_value = []

    # First sync: populate pages 1-5 (ids p1_*, p2_*, … p5_*)
    pages_initial = [_make_page([f"p{p}_{i}" for i in range(2)], total=10, per_page=2) for p in range(1, 6)]
    vod.get_content.side_effect = pages_initial
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    # Second sync: page 1 is new content, pages 2-4 are unchanged, page 5 never fetched
    new_page1 = _make_page(["new1", "new2"], total=10, per_page=2)
    same_page2 = _make_page(["p2_0", "p2_1"], total=10, per_page=2)
    same_page3 = _make_page(["p3_0", "p3_1"], total=10, per_page=2)
    same_page4 = _make_page(["p4_0", "p4_1"], total=10, per_page=2)
    vod.get_content.reset_mock()
    vod.get_content.side_effect = [new_page1, same_page2, same_page3, same_page4]

    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=3, full_sync_days=0)

    # Stopped after page 4 (3 consecutive stable pages: 2, 3, 4)
    assert vod.get_content.call_count == 4  # new_page1 + same_page2 + same_page3 + same_page4
    assert get_vod_content(db, "new1") is not None
    assert get_vod_content(db, "p5_0") is not None   # still in DB from first sync


def test_early_stop_resets_on_changed_page(db, lock):
    """A changed page resets the consecutive stable counter."""
    vod = MagicMock()
    vod.get_categories.return_value = []

    # First sync: 5 pages of known content
    pages_initial = [_make_page([f"p{p}_{i}" for i in range(2)], total=10, per_page=2) for p in range(1, 6)]
    vod.get_content.side_effect = pages_initial
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    # Second sync: page 1 stable, page 2 changed (different name → different hash), pages 3-4 stable
    # page 1 stable(+1), page 2 changed(reset to 0), page 3 stable(+1), page 4 stable(+2>=2) → stop after page 4
    changed_page2 = _make_page(["p2_0", "p2_1"], name_prefix="Updated", total=10, per_page=2)
    pages_second = [
        _make_page(["p1_0", "p1_1"], total=10, per_page=2),
        changed_page2,
        _make_page(["p3_0", "p3_1"], total=10, per_page=2),
        _make_page(["p4_0", "p4_1"], total=10, per_page=2),
    ]
    vod.get_content.reset_mock()
    vod.get_content.side_effect = pages_second

    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=2, full_sync_days=0)

    assert vod.get_content.call_count == 4


def test_early_stop_skips_stale_cleanup(db, lock):
    """Stale content is preserved when sync ends with early-stop."""
    # First sync to establish hashes for the items that will appear
    vod = MagicMock()
    vod.get_categories.return_value = []
    vod.get_content.return_value = _make_page(["c1", "c2"], total=2, per_page=2)
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    # Insert stale content AFTER the full sync (so it survives phase 4 of the first run)
    upsert_vod_content(db, {
        "content_id": "stale", "name": "Old", "cmd": "", "screenshot_uri": "",
        "genres": "", "year": "2000", "description": "", "rating": "", "duration": 0,
        "is_series": 0, "fav": 0, "for_rent": 0, "lock": 0, "portal_raw": "{}",
        "synced_at": "2020-01-01T00:00:00+00:00",
    })
    db.commit()

    # Second sync: same page → triggers early-stop after 1 stable page; stale cleanup skipped
    vod.get_content.reset_mock()
    vod.get_content.side_effect = [_make_page(["c1", "c2"], total=2, per_page=2)]
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=1, full_sync_days=0)

    assert get_vod_content(db, "stale") is not None  # not cleaned up


def test_early_stop_disabled_when_zero(db, lock):
    """early_stop_pages=0 fetches all pages regardless of content."""
    vod = MagicMock()
    vod.get_categories.return_value = []

    # Two pages of initial content
    pages = [_make_page([f"p{p}_{i}" for i in range(2)], total=4, per_page=2) for p in range(1, 3)]
    vod.get_content.side_effect = pages
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    # Second run: same pages, early_stop_pages=0 → must fetch all pages
    pages = [_make_page([f"p{p}_{i}" for i in range(2)], total=4, per_page=2) for p in range(1, 3)]
    vod.get_content.side_effect = pages
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    assert vod.get_content.call_count == 4  # 2 pages × 2 runs


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def test_resume_continues_from_last_synced_page(db, lock):
    """If a previous sync was interrupted, the next run resumes from last_synced_page + 1."""
    vod = MagicMock()
    vod.get_categories.return_value = []
    # Simulate: portal has 3 pages; previous sync committed through page 2
    set_sync_state(db, last_sync_status="running", last_synced_page=2)

    page3 = _make_page(["c3_0", "c3_1"], total=6, per_page=2)
    vod.get_content.return_value = page3

    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    # Should have fetched only page 3 (resumed from page 2 + 1 = 3)
    vod.get_content.assert_called_once_with(category_id="*", page=3)


def test_resume_from_failed_status(db, lock):
    """Resume also triggers when previous status was 'failed'."""
    vod = MagicMock()
    vod.get_categories.return_value = []
    set_sync_state(db, last_sync_status="failed", last_synced_page=1)

    page2 = _make_page(["c2"], total=2, per_page=1)
    vod.get_content.return_value = page2

    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    vod.get_content.assert_called_once_with(category_id="*", page=2)


def test_no_resume_after_success(db, lock):
    """A previously successful sync always restarts from page 1."""
    vod = MagicMock()
    vod.get_categories.return_value = []
    set_sync_state(db, last_sync_status="success", last_synced_page=3)

    page1 = _make_page(["c1"], total=1, per_page=1)
    vod.get_content.return_value = page1

    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    vod.get_content.assert_called_once_with(category_id="*", page=1)


def test_last_synced_page_reset_after_completion(db, lock):
    """last_synced_page is reset to 0 after a clean finish."""
    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)
    assert get_sync_state(db)["last_synced_page"] == 0


# ---------------------------------------------------------------------------
# Periodic full-sync override
# ---------------------------------------------------------------------------

def test_full_sync_forced_when_no_previous_full_sync(db, lock):
    """With no last_full_sync_at, early_stop_pages is overridden to 0."""
    vod = MagicMock()
    vod.get_categories.return_value = []

    # Populate initial data so early-stop would normally fire, then clear last_full_sync_at
    pages = [_make_page([f"p{p}_{i}" for i in range(2)], total=4, per_page=2) for p in range(1, 3)]
    vod.get_content.side_effect = pages
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)
    set_sync_state(db, last_full_sync_at=None)  # simulate no previous full sync

    # Second run: early_stop_pages=1 but full_sync_days=7 forces full sync (last_full_sync_at is NULL)
    vod.get_content.reset_mock()
    pages = [_make_page([f"p{p}_{i}" for i in range(2)], total=4, per_page=2) for p in range(1, 3)]
    vod.get_content.side_effect = pages
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=1, full_sync_days=7)

    assert vod.get_content.call_count == 2  # all 2 pages fetched in the second sync


def test_full_sync_forced_when_overdue(db, lock):
    """When last_full_sync_at is older than full_sync_days, early-stop is overridden."""
    vod = MagicMock()
    vod.get_categories.return_value = []

    # Populate initial data
    pages = [_make_page([f"p{p}_{i}" for i in range(2)], total=4, per_page=2) for p in range(1, 3)]
    vod.get_content.side_effect = pages
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)

    # Manually set last_full_sync_at to 8 days ago
    old_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    set_sync_state(db, last_full_sync_at=old_ts)

    # Second run with full_sync_days=7: overdue → full sync, not early-stop
    pages = [_make_page([f"p{p}_{i}" for i in range(2)], total=4, per_page=2) for p in range(1, 3)]
    vod.get_content.side_effect = pages
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=1, full_sync_days=7)

    assert vod.get_content.call_count == 4


def test_last_full_sync_at_updated_after_full_sync(db, lock):
    """last_full_sync_at is updated when a full (non-early-stop) sync completes."""
    vod = _make_vod()
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)
    state = get_sync_state(db)
    assert state["last_full_sync_at"] is not None


def test_last_full_sync_at_not_updated_after_early_stop(db, lock):
    """last_full_sync_at is NOT updated when sync ends via early-stop."""
    vod = MagicMock()
    vod.get_categories.return_value = []

    # First full sync to populate hashes
    vod.get_content.return_value = _make_page(["c1", "c2"], total=2, per_page=2)
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=0, full_sync_days=0)
    first_full_sync_at = get_sync_state(db)["last_full_sync_at"]

    # Second sync: same content → early-stop fires
    vod.get_content.side_effect = [_make_page(["c1", "c2"], total=2, per_page=2)]
    run_portal_sync(db, lock, vod, "/output", delay_ms=0, max_pages=0, early_stop_pages=1, full_sync_days=0)

    assert get_sync_state(db)["last_full_sync_at"] == first_full_sync_at
