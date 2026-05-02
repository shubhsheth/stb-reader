import pytest
import sqlite3
from server.db import (
    init_db,
    add_library_item,
    get_library_item,
    get_library_items,
    delete_library_item,
    add_strm_file,
    episode_exists,
    set_last_synced,
)


@pytest.fixture
def db(tmp_path):
    return init_db(str(tmp_path / "test.db"))


def test_init_db_creates_tables(db):
    tables = {
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "library_items" in tables
    assert "strm_files" in tables


def test_add_and_get_library_item(db):
    add_library_item(db, "c1", "Movie", "2023", False)
    item = get_library_item(db, "c1")
    assert item is not None
    assert item["content_id"] == "c1"
    assert item["name"] == "Movie"
    assert item["year"] == "2023"
    assert item["is_series"] == 0


def test_duplicate_content_id_raises(db):
    add_library_item(db, "c1", "Movie", "2023", False)
    with pytest.raises(sqlite3.IntegrityError):
        add_library_item(db, "c1", "Movie", "2023", False)


def test_get_library_items_strm_count(db):
    add_library_item(db, "c1", "Show", "2020", True)
    items = get_library_items(db)
    assert items[0]["strm_count"] == 0
    add_strm_file(db, "c1", "s1", "e1", "f1", "/tmp/a.strm")
    add_strm_file(db, "c1", "s1", "e2", "f2", "/tmp/b.strm")
    items = get_library_items(db)
    assert items[0]["strm_count"] == 2


def test_delete_library_item_returns_paths_and_removes_rows(db):
    add_library_item(db, "c1", "Show", "2020", True)
    add_strm_file(db, "c1", "s1", "e1", "f1", "/tmp/x.strm")
    paths = delete_library_item(db, "c1")
    assert paths == ["/tmp/x.strm"]
    assert get_library_item(db, "c1") is None
    count = db.execute(
        "SELECT count(*) FROM strm_files WHERE content_id='c1'"
    ).fetchone()[0]
    assert count == 0


def test_episode_exists(db):
    add_library_item(db, "c1", "Show", "2020", True)
    assert not episode_exists(db, "c1", "s1", "e1")
    add_strm_file(db, "c1", "s1", "e1", "f1", "/tmp/ep.strm")
    assert episode_exists(db, "c1", "s1", "e1")


def test_set_last_synced(db):
    add_library_item(db, "c1", "Show", "2020", True)
    item = get_library_item(db, "c1")
    assert item["last_synced_at"] is None
    set_last_synced(db, "c1")
    item = get_library_item(db, "c1")
    assert item["last_synced_at"] is not None
