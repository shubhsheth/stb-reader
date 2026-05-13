import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------

def _add_col(table: str, col: str, defn: str):
    """Return a migration step that adds a column only when it is absent."""
    def _step(db: sqlite3.Connection) -> None:
        existing = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        if col not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
    return _step


# Append-only — never insert, delete, or reorder entries.
# list index + 1  ==  schema version stored in PRAGMA user_version.
# Simple column additions: use _add_col().
# Multi-statement / FTS / data migrations: define a named function above and
# append it here.
MIGRATIONS: list = [
    _add_col("vod_content",    "content_hash",       "TEXT"),
    _add_col("vod_content",    "in_library",          "INTEGER NOT NULL DEFAULT 0"),
    _add_col("vod_content",    "added_at",            "TEXT"),
    _add_col("vod_content",    "last_synced_at",      "TEXT"),
    _add_col("vod_sync_state", "content_count",       "INTEGER NOT NULL DEFAULT 0"),
    _add_col("vod_sync_state", "error_message",       "TEXT"),
    _add_col("vod_sync_state", "last_synced_page",    "INTEGER NOT NULL DEFAULT 0"),
    _add_col("vod_sync_state", "last_full_sync_at",   "TEXT"),
    _add_col("vod_categories", "auto_add",            "INTEGER NOT NULL DEFAULT 0"),
]


def _migrate(db: sqlite3.Connection) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    for i, step in enumerate(MIGRATIONS[version:], start=version + 1):
        step(db)
        db.execute(f"PRAGMA user_version = {i}")
        db.commit()


# ---------------------------------------------------------------------------


def init_db(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS vod_content (
            content_id      TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            cmd             TEXT NOT NULL DEFAULT '',
            screenshot_uri  TEXT,
            genres          TEXT,
            year            TEXT NOT NULL DEFAULT '',
            description     TEXT,
            rating          TEXT,
            duration        INTEGER,
            is_series       INTEGER NOT NULL DEFAULT 0,
            fav             INTEGER NOT NULL DEFAULT 0,
            for_rent        INTEGER NOT NULL DEFAULT 0,
            lock            INTEGER NOT NULL DEFAULT 0,
            portal_raw      TEXT,
            synced_at       TEXT,
            content_hash    TEXT,
            in_library      INTEGER NOT NULL DEFAULT 0,
            added_at        TEXT,
            last_synced_at  TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS vod_content_fts USING fts5(
            content_id UNINDEXED,
            name,
            description,
            content=vod_content,
            content_rowid=rowid
        );

        CREATE TABLE IF NOT EXISTS vod_categories (
            category_id TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            alias       TEXT,
            synced_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vod_content_category (
            content_id  TEXT NOT NULL REFERENCES vod_content(content_id),
            category_id TEXT NOT NULL REFERENCES vod_categories(category_id),
            PRIMARY KEY (content_id, category_id)
        );

        CREATE TABLE IF NOT EXISTS vod_sync_state (
            id                    INTEGER PRIMARY KEY CHECK (id = 1),
            last_sync_started_at  TEXT,
            last_sync_finished_at TEXT,
            last_sync_status      TEXT NOT NULL DEFAULT 'idle',
            content_count         INTEGER NOT NULL DEFAULT 0,
            error_message         TEXT,
            last_synced_page      INTEGER NOT NULL DEFAULT 0,
            last_full_sync_at     TEXT
        );

        INSERT OR IGNORE INTO vod_sync_state (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS strm_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id  TEXT NOT NULL REFERENCES vod_content(content_id),
            season_id   TEXT,
            episode_id  TEXT,
            file_id     TEXT NOT NULL,
            strm_path   TEXT NOT NULL UNIQUE,
            created_at  TEXT NOT NULL
        );
    """)
    _migrate(db)
    return db


# ---------------------------------------------------------------------------
# vod_content — portal sync helpers
# ---------------------------------------------------------------------------

def upsert_vod_content(db: sqlite3.Connection, row: dict) -> dict | None:
    """Upsert a content row. Returns the existing row before update, or None if new."""
    existing = get_vod_content(db, row["content_id"])
    row = {**row, "content_hash": row.get("content_hash")}
    db.execute(
        """
        INSERT INTO vod_content
            (content_id, name, cmd, screenshot_uri, genres, year, description,
             rating, duration, is_series, fav, for_rent, lock, portal_raw, synced_at,
             content_hash)
        VALUES
            (:content_id, :name, :cmd, :screenshot_uri, :genres, :year, :description,
             :rating, :duration, :is_series, :fav, :for_rent, :lock, :portal_raw, :synced_at,
             :content_hash)
        ON CONFLICT(content_id) DO UPDATE SET
            name           = excluded.name,
            cmd            = excluded.cmd,
            screenshot_uri = excluded.screenshot_uri,
            genres         = excluded.genres,
            year           = excluded.year,
            description    = excluded.description,
            rating         = excluded.rating,
            duration       = excluded.duration,
            is_series      = excluded.is_series,
            fav            = excluded.fav,
            for_rent       = excluded.for_rent,
            lock           = excluded.lock,
            portal_raw     = excluded.portal_raw,
            synced_at      = excluded.synced_at,
            content_hash   = excluded.content_hash
        """,
        row,
    )
    # Keep FTS in sync with the content table
    db.execute(
        "INSERT OR REPLACE INTO vod_content_fts(rowid, content_id, name, description)"
        " SELECT rowid, content_id, name, description FROM vod_content WHERE content_id = ?",
        (row["content_id"],),
    )
    return existing


def get_vod_content(db: sqlite3.Connection, content_id: str) -> dict | None:
    row = db.execute(
        "SELECT * FROM vod_content WHERE content_id = ?", (content_id,)
    ).fetchone()
    return dict(row) if row else None


def get_content_hashes(db: sqlite3.Connection, content_ids: list[str]) -> dict[str, str]:
    """Returns {content_id: content_hash} for the given IDs (omits rows with NULL hash)."""
    if not content_ids:
        return {}
    placeholders = ",".join("?" * len(content_ids))
    rows = db.execute(
        f"SELECT content_id, content_hash FROM vod_content"
        f" WHERE content_id IN ({placeholders})",
        content_ids,
    ).fetchall()
    return {r[0]: r[1] for r in rows if r[1]}


def count_vod_content(db: sqlite3.Connection) -> int:
    return db.execute("SELECT count(*) FROM vod_content").fetchone()[0]


def search_vod_content(
    db: sqlite3.Connection,
    query: str,
    page: int,
    page_size: int,
    is_series: int | None,
    category_id: str | None = None,
) -> tuple[list[dict], int]:
    series_filter = "" if is_series is None else f"AND c.is_series = {int(is_series)}"
    offset = (page - 1) * page_size

    if query:
        fts_query = query.replace('"', '""')
        if category_id:
            cat_join = "JOIN vod_content_category cc ON cc.content_id = c.content_id"
            cat_filter = "AND cc.category_id = ?"
            count_params: tuple = (fts_query, category_id)
            rows_params: tuple = (fts_query, category_id, page_size, offset)
        else:
            cat_join = cat_filter = ""
            count_params = (fts_query,)
            rows_params = (fts_query, page_size, offset)
        count_sql = (
            f"SELECT count(*) FROM vod_content_fts f"
            f" JOIN vod_content c ON c.content_id = f.content_id {cat_join}"
            f" WHERE vod_content_fts MATCH ? {cat_filter} {series_filter}"
        )
        rows_sql = (
            f"SELECT c.* FROM vod_content_fts f"
            f" JOIN vod_content c ON c.content_id = f.content_id {cat_join}"
            f" WHERE vod_content_fts MATCH ? {cat_filter} {series_filter}"
            f" ORDER BY rank LIMIT ? OFFSET ?"
        )
    else:
        # Category browse — no FTS required
        count_params = (category_id,)
        rows_params = (category_id, page_size, offset)
        count_sql = (
            f"SELECT count(*) FROM vod_content c"
            f" JOIN vod_content_category cc ON cc.content_id = c.content_id"
            f" WHERE cc.category_id = ? {series_filter}"
        )
        rows_sql = (
            f"SELECT c.* FROM vod_content c"
            f" JOIN vod_content_category cc ON cc.content_id = c.content_id"
            f" WHERE cc.category_id = ? {series_filter}"
            f" ORDER BY c.name LIMIT ? OFFSET ?"
        )

    total = db.execute(count_sql, count_params).fetchone()[0]
    rows = db.execute(rows_sql, rows_params).fetchall()
    return [dict(r) for r in rows], total


def delete_vod_content_rows(
    db: sqlite3.Connection, content_ids: list[str]
) -> list[str]:
    """Delete vod_content rows and their strm_files. Returns strm_paths for disk cleanup."""
    if not content_ids:
        return []
    placeholders = ",".join("?" * len(content_ids))
    paths = [
        r[0]
        for r in db.execute(
            f"SELECT strm_path FROM strm_files WHERE content_id IN ({placeholders})",
            content_ids,
        ).fetchall()
    ]
    db.execute(f"DELETE FROM vod_content_fts WHERE content_id IN ({placeholders})", content_ids)
    db.execute(f"DELETE FROM strm_files WHERE content_id IN ({placeholders})", content_ids)
    db.execute(f"DELETE FROM vod_content_category WHERE content_id IN ({placeholders})", content_ids)
    db.execute(f"DELETE FROM vod_content WHERE content_id IN ({placeholders})", content_ids)
    db.commit()
    return paths


def upsert_vod_category(
    db: sqlite3.Connection, category_id: str, title: str, alias: str
) -> None:
    db.execute(
        "INSERT INTO vod_categories (category_id, title, alias, synced_at)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(category_id) DO UPDATE SET"
        " title=excluded.title, alias=excluded.alias, synced_at=excluded.synced_at",
        (category_id, title, alias or "", _now()),
    )


def upsert_vod_content_category(
    db: sqlite3.Connection, content_id: str, category_id: str
) -> None:
    db.execute(
        "INSERT OR IGNORE INTO vod_content_category (content_id, category_id) VALUES (?, ?)",
        (content_id, category_id),
    )


def get_vod_category(db: sqlite3.Connection, category_id: str) -> dict | None:
    row = db.execute(
        "SELECT * FROM vod_categories WHERE category_id = ?", (category_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_vod_categories(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("SELECT * FROM vod_categories ORDER BY title").fetchall()
    return [dict(r) for r in rows]


def set_category_auto_add(db: sqlite3.Connection, category_id: str, value: int) -> None:
    db.execute(
        "UPDATE vod_categories SET auto_add = ? WHERE category_id = ?", (value, category_id)
    )
    db.commit()


def get_auto_add_categories(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("SELECT * FROM vod_categories WHERE auto_add = 1").fetchall()
    return [dict(r) for r in rows]


def get_category_content_ids(db: sqlite3.Connection, category_id: str) -> list[str]:
    """Return content IDs in the category that are not yet in the library."""
    rows = db.execute(
        "SELECT c.content_id FROM vod_content c"
        " JOIN vod_content_category cc ON cc.content_id = c.content_id"
        " WHERE cc.category_id = ? AND c.in_library = 0",
        (category_id,),
    ).fetchall()
    return [r[0] for r in rows]


def get_category_library_content_ids(db: sqlite3.Connection, category_id: str) -> list[str]:
    """Return content IDs in the category that are already in the library."""
    rows = db.execute(
        "SELECT c.content_id FROM vod_content c"
        " JOIN vod_content_category cc ON cc.content_id = c.content_id"
        " WHERE cc.category_id = ? AND c.in_library = 1",
        (category_id,),
    ).fetchall()
    return [r[0] for r in rows]


def delete_vod_category(db: sqlite3.Connection, category_id: str) -> bool:
    """Delete category and its content associations. Returns False if not found."""
    if not db.execute(
        "SELECT 1 FROM vod_categories WHERE category_id = ?", (category_id,)
    ).fetchone():
        return False
    db.execute("DELETE FROM vod_content_category WHERE category_id = ?", (category_id,))
    db.execute("DELETE FROM vod_categories WHERE category_id = ?", (category_id,))
    db.commit()
    return True


# ---------------------------------------------------------------------------
# vod_sync_state
# ---------------------------------------------------------------------------

def get_sync_state(db: sqlite3.Connection) -> dict:
    return dict(db.execute("SELECT * FROM vod_sync_state WHERE id = 1").fetchone())


def set_sync_state(db: sqlite3.Connection, **kwargs) -> None:
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    db.execute(f"UPDATE vod_sync_state SET {sets} WHERE id = 1", list(kwargs.values()))
    db.commit()


# ---------------------------------------------------------------------------
# Library management (operates on vod_content library columns)
# ---------------------------------------------------------------------------

def add_to_library(db: sqlite3.Connection, content_id: str) -> None:
    db.execute(
        "UPDATE vod_content SET in_library = 1, added_at = ? WHERE content_id = ?",
        (_now(), content_id),
    )
    db.commit()


def get_library_items(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("""
        SELECT c.*,
               (SELECT count(*) FROM strm_files sf WHERE sf.content_id = c.content_id) AS strm_count
        FROM vod_content c
        WHERE c.in_library = 1
    """).fetchall()
    return [dict(r) for r in rows]


def get_library_item(db: sqlite3.Connection, content_id: str) -> dict | None:
    row = db.execute(
        "SELECT * FROM vod_content WHERE content_id = ? AND in_library = 1",
        (content_id,),
    ).fetchone()
    return dict(row) if row else None


def remove_from_library(db: sqlite3.Connection, content_id: str) -> list[str]:
    """Clear library flags and delete strm_files rows. Returns strm_paths for disk cleanup."""
    paths = [
        r[0]
        for r in db.execute(
            "SELECT strm_path FROM strm_files WHERE content_id = ?", (content_id,)
        ).fetchall()
    ]
    db.execute("DELETE FROM strm_files WHERE content_id = ?", (content_id,))
    db.execute(
        "UPDATE vod_content SET in_library = 0, added_at = NULL, last_synced_at = NULL"
        " WHERE content_id = ?",
        (content_id,),
    )
    db.commit()
    return paths


# ---------------------------------------------------------------------------
# strm_files helpers
# ---------------------------------------------------------------------------

def add_strm_file(
    db: sqlite3.Connection,
    content_id: str,
    season_id: str | None,
    episode_id: str | None,
    file_id: str,
    strm_path: str,
) -> None:
    db.execute(
        "INSERT INTO strm_files (content_id, season_id, episode_id, file_id, strm_path, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (content_id, season_id, episode_id, file_id, strm_path, _now()),
    )
    db.commit()


def get_strm_files(db: sqlite3.Connection, content_id: str) -> list[dict]:
    rows = db.execute(
        "SELECT * FROM strm_files WHERE content_id = ?", (content_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def episode_exists(
    db: sqlite3.Connection, content_id: str, season_id: str, episode_id: str
) -> bool:
    row = db.execute(
        "SELECT 1 FROM strm_files WHERE content_id = ? AND season_id = ? AND episode_id = ?",
        (content_id, season_id, episode_id),
    ).fetchone()
    return row is not None


def set_last_synced(db: sqlite3.Connection, content_id: str) -> None:
    db.execute(
        "UPDATE vod_content SET last_synced_at = ? WHERE content_id = ?",
        (_now(), content_id),
    )
    db.commit()
