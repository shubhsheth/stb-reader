import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS library_items (
            content_id     TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            year           TEXT NOT NULL,
            is_series      INTEGER NOT NULL,
            added_at       TEXT NOT NULL,
            last_synced_at TEXT
        );

        CREATE TABLE IF NOT EXISTS strm_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id  TEXT NOT NULL REFERENCES library_items(content_id),
            season_id   TEXT,
            episode_id  TEXT,
            file_id     TEXT NOT NULL,
            strm_path   TEXT NOT NULL UNIQUE,
            created_at  TEXT NOT NULL
        );
    """)
    db.commit()
    return db


def add_library_item(
    db: sqlite3.Connection, content_id: str, name: str, year: str, is_series: bool
) -> None:
    db.execute(
        "INSERT INTO library_items (content_id, name, year, is_series, added_at) VALUES (?, ?, ?, ?, ?)",
        (content_id, name, year, int(is_series), _now()),
    )
    db.commit()


def get_library_items(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("""
        SELECT li.*,
               (SELECT count(*) FROM strm_files sf WHERE sf.content_id = li.content_id) AS strm_count
        FROM library_items li
    """).fetchall()
    return [dict(r) for r in rows]


def get_library_item(db: sqlite3.Connection, content_id: str) -> dict | None:
    row = db.execute(
        "SELECT * FROM library_items WHERE content_id = ?", (content_id,)
    ).fetchone()
    return dict(row) if row else None


def delete_library_item(db: sqlite3.Connection, content_id: str) -> list[str]:
    paths = [
        r[0]
        for r in db.execute(
            "SELECT strm_path FROM strm_files WHERE content_id = ?", (content_id,)
        ).fetchall()
    ]
    db.execute("DELETE FROM strm_files WHERE content_id = ?", (content_id,))
    db.execute("DELETE FROM library_items WHERE content_id = ?", (content_id,))
    db.commit()
    return paths


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
        "UPDATE library_items SET last_synced_at = ? WHERE content_id = ?",
        (_now(), content_id),
    )
    db.commit()
