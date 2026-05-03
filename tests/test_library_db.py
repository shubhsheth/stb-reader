import pytest
import sqlite3
from server.db import (
    init_db,
    add_to_library,
    get_library_item,
    get_library_items,
    remove_from_library,
    add_strm_file,
    episode_exists,
    set_last_synced,
    upsert_vod_content,
    get_vod_content,
    count_vod_content,
    get_sync_state,
    set_sync_state,
)


@pytest.fixture
def db(tmp_path):
    return init_db(str(tmp_path / "test.db"))


def _vod_row(content_id="c1", name="Movie", year="2023", is_series=0):
    return {
        "content_id": content_id,
        "name": name,
        "cmd": "/media/c1.mpg",
        "screenshot_uri": "",
        "genres": "Action",
        "year": year,
        "description": "A film",
        "rating": "8.0",
        "duration": 90,
        "is_series": is_series,
        "fav": 0,
        "for_rent": 0,
        "lock": 0,
        "portal_raw": "{}",
        "synced_at": "2024-01-01T00:00:00+00:00",
    }


def test_init_db_creates_tables(db):
    tables = {
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','shadow')"
        ).fetchall()
    }
    assert "vod_content" in tables
    assert "strm_files" in tables
    assert "vod_sync_state" in tables


def test_upsert_vod_content_inserts_and_returns_none_for_new(db):
    old = upsert_vod_content(db, _vod_row())
    db.commit()
    assert old is None
    assert get_vod_content(db, "c1") is not None


def test_upsert_vod_content_returns_existing_on_update(db):
    upsert_vod_content(db, _vod_row())
    db.commit()
    old = upsert_vod_content(db, _vod_row(name="Updated Movie"))
    db.commit()
    assert old["name"] == "Movie"
    assert get_vod_content(db, "c1")["name"] == "Updated Movie"


def test_upsert_preserves_library_fields(db):
    upsert_vod_content(db, _vod_row())
    db.commit()
    add_to_library(db, "c1")
    upsert_vod_content(db, _vod_row(name="New Name"))
    db.commit()
    item = get_vod_content(db, "c1")
    assert item["in_library"] == 1
    assert item["added_at"] is not None
    assert item["name"] == "New Name"


def test_add_to_library_sets_flags(db):
    upsert_vod_content(db, _vod_row())
    db.commit()
    add_to_library(db, "c1")
    item = get_library_item(db, "c1")
    assert item is not None
    assert item["in_library"] == 1
    assert item["added_at"] is not None


def test_get_library_item_returns_none_when_not_in_library(db):
    upsert_vod_content(db, _vod_row())
    db.commit()
    assert get_library_item(db, "c1") is None


def test_get_library_items_only_returns_in_library(db):
    upsert_vod_content(db, _vod_row("c1"))
    upsert_vod_content(db, _vod_row("c2"))
    db.commit()
    add_to_library(db, "c1")
    items = get_library_items(db)
    assert len(items) == 1
    assert items[0]["content_id"] == "c1"


def test_get_library_items_strm_count(db):
    upsert_vod_content(db, _vod_row("c1", is_series=1))
    db.commit()
    add_to_library(db, "c1")
    items = get_library_items(db)
    assert items[0]["strm_count"] == 0
    add_strm_file(db, "c1", "s1", "e1", "f1", "/tmp/a.strm")
    add_strm_file(db, "c1", "s1", "e2", "f2", "/tmp/b.strm")
    items = get_library_items(db)
    assert items[0]["strm_count"] == 2


def test_remove_from_library_returns_paths_and_clears_flags(db):
    upsert_vod_content(db, _vod_row("c1", is_series=1))
    db.commit()
    add_to_library(db, "c1")
    add_strm_file(db, "c1", "s1", "e1", "f1", "/tmp/x.strm")
    paths = remove_from_library(db, "c1")
    assert paths == ["/tmp/x.strm"]
    # Row still exists in vod_content but not in library
    assert get_library_item(db, "c1") is None
    assert get_vod_content(db, "c1") is not None
    count = db.execute("SELECT count(*) FROM strm_files WHERE content_id='c1'").fetchone()[0]
    assert count == 0


def test_episode_exists(db):
    upsert_vod_content(db, _vod_row("c1", is_series=1))
    db.commit()
    add_to_library(db, "c1")
    assert not episode_exists(db, "c1", "s1", "e1")
    add_strm_file(db, "c1", "s1", "e1", "f1", "/tmp/ep.strm")
    assert episode_exists(db, "c1", "s1", "e1")


def test_set_last_synced(db):
    upsert_vod_content(db, _vod_row())
    db.commit()
    add_to_library(db, "c1")
    item = get_library_item(db, "c1")
    assert item["last_synced_at"] is None
    set_last_synced(db, "c1")
    item = get_library_item(db, "c1")
    assert item["last_synced_at"] is not None


def test_count_vod_content(db):
    assert count_vod_content(db) == 0
    upsert_vod_content(db, _vod_row("c1"))
    upsert_vod_content(db, _vod_row("c2"))
    db.commit()
    assert count_vod_content(db) == 2


def test_sync_state_default_idle(db):
    state = get_sync_state(db)
    assert state["last_sync_status"] == "idle"
    assert state["content_count"] == 0


def test_set_sync_state(db):
    set_sync_state(db, last_sync_status="running", content_count=42)
    state = get_sync_state(db)
    assert state["last_sync_status"] == "running"
    assert state["content_count"] == 42


def test_init_db_migrates_old_schema():
    """init_db must add new columns to a database created with an older schema."""
    import tempfile, os
    from server.db import MIGRATIONS
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        # Build a minimal old-schema database (missing last_synced_page / last_full_sync_at)
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE vod_content (
                content_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                cmd TEXT NOT NULL DEFAULT '', screenshot_uri TEXT,
                genres TEXT, year TEXT NOT NULL DEFAULT '',
                description TEXT, rating TEXT, duration INTEGER,
                is_series INTEGER NOT NULL DEFAULT 0,
                fav INTEGER NOT NULL DEFAULT 0,
                for_rent INTEGER NOT NULL DEFAULT 0,
                lock INTEGER NOT NULL DEFAULT 0,
                portal_raw TEXT, synced_at TEXT
            );
            CREATE TABLE vod_sync_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_started_at TEXT, last_sync_finished_at TEXT,
                last_sync_status TEXT NOT NULL DEFAULT 'idle'
            );
            INSERT INTO vod_sync_state (id) VALUES (1);
        """)
        old.close()

        db = init_db(path)
        # These calls must not raise OperationalError
        set_sync_state(db, last_synced_page=5, last_full_sync_at="2024-01-01T00:00:00+00:00")
        state = get_sync_state(db)
        assert state["last_synced_page"] == 5
        assert state["last_full_sync_at"] == "2024-01-01T00:00:00+00:00"
        # Schema version must equal the number of applied migrations
        version = db.execute("PRAGMA user_version").fetchone()[0]
        assert version == len(MIGRATIONS)
        db.close()
    finally:
        os.unlink(path)


def test_init_db_fresh_schema_has_correct_version():
    """A brand-new database must have user_version == len(MIGRATIONS)."""
    from server.db import MIGRATIONS
    db = init_db(":memory:")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(MIGRATIONS)
