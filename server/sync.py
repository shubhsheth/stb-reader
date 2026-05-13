import re
import sqlite3
from pathlib import Path

from .db import (
    add_strm_file,
    add_to_library,
    episode_exists,
    get_auto_add_categories,
    get_category_content_ids,
    get_library_item,
    get_library_items,
    get_vod_content,
    remove_from_library,
    set_last_synced,
)

_UNSAFE = re.compile(r'[/\\:*?"<>|]')


def sanitize(name: str) -> str:
    return _UNSAFE.sub("-", name)


def parse_season_num(season_name: str, fallback: int) -> int:
    m = re.search(r"\d+", season_name)
    return int(m.group()) if m else fallback


def movie_strm_path(output_dir: str, name: str, year: str) -> Path:
    s = sanitize(name)
    folder = f"{s} ({year})"
    return Path(output_dir) / "Movies" / folder / f"{folder}.strm"


def episode_strm_path(
    output_dir: str,
    name: str,
    year: str,
    season_num: int,
    ep_num: int,
    ep_name: str,
) -> Path:
    sname = sanitize(name)
    sep_name = sanitize(ep_name)
    show_folder = f"{sname} ({year})"
    season_folder = f"Season {season_num:02d}"
    filename = f"{show_folder} - S{season_num:02d}E{ep_num:02d} - {sep_name}.strm"
    return Path(output_dir) / "TV" / show_folder / season_folder / filename


def write_strm(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(url + "\n")


def _write_series_strm_files(
    db: sqlite3.Connection,
    vod,
    output_dir: str,
    server_base: str,
    content_id: str,
    name: str,
    year: str,
    delay_s: float = 0,
) -> int:
    count = 0
    seasons = vod.get_seasons(content_id)
    for s_idx, season in enumerate(seasons):
        season_num = parse_season_num(season.name, s_idx + 1)
        episodes = vod.get_episodes(content_id, season.id, delay_s=delay_s)
        for e_idx, episode in enumerate(episodes):
            if episode_exists(db, content_id, season.id, episode.id):
                continue
            files = vod.get_episode_files(content_id, season.id, episode.id)
            if not files:
                continue
            file = files[0]
            try:
                ep_num = int(episode.series_number) or (e_idx + 1)
            except (ValueError, TypeError):
                ep_num = e_idx + 1
            path = episode_strm_path(output_dir, name, year, season_num, ep_num, episode.name)
            url = (
                f"{server_base}/vod/content/{content_id}"
                f"/seasons/{season.id}/episodes/{episode.id}/files/{file.id}/stream"
            )
            write_strm(path, url)
            add_strm_file(db, content_id, season.id, episode.id, file.id, str(path))
            count += 1
    return count


def add_content(
    db: sqlite3.Connection,
    vod,
    output_dir: str,
    server_base: str,
    content_id: str,
    delay_s: float = 0,
) -> int:
    """Add content_id to library (must already exist in vod_content). Returns strm count."""
    item = get_vod_content(db, content_id)
    if item is None:
        raise KeyError(content_id)
    add_to_library(db, content_id)
    name, year, is_series = item["name"], item["year"], bool(item["is_series"])
    if not is_series:
        path = movie_strm_path(output_dir, name, year)
        url = f"{server_base}/vod/content/{content_id}/stream"
        write_strm(path, url)
        add_strm_file(db, content_id, None, None, content_id, str(path))
        return 1
    return _write_series_strm_files(db, vod, output_dir, server_base, content_id, name, year, delay_s)


def sync_item(
    db: sqlite3.Connection,
    vod,
    output_dir: str,
    server_base: str,
    content_id: str,
    delay_s: float = 0,
) -> int:
    item = get_library_item(db, content_id)
    if item is None or not item["is_series"]:
        return 0
    count = _write_series_strm_files(
        db, vod, output_dir, server_base, content_id, item["name"], item["year"], delay_s
    )
    set_last_synced(db, content_id)
    return count


def sync_all(
    db: sqlite3.Connection,
    vod,
    output_dir: str,
    server_base: str,
    delay_s: float = 0,
) -> None:
    for item in get_library_items(db):
        if not item["is_series"]:
            continue
        sync_item(db, vod, output_dir, server_base, item["content_id"], delay_s)


def delete_content(db: sqlite3.Connection, content_id: str) -> None:
    paths = remove_from_library(db, content_id)
    for p in paths:
        path = Path(p)
        path.unlink(missing_ok=True)
        for parent in [path.parent, path.parent.parent]:
            try:
                parent.rmdir()
            except OSError:
                break


def run_library_sync(
    db: sqlite3.Connection,
    vod,
    output_dir: str,
    server_base: str,
    delay_s: float = 0,
) -> None:
    """Add new items for watched categories then sync new episodes for all in-library series."""
    for cat in get_auto_add_categories(db):
        for cid in get_category_content_ids(db, cat["category_id"]):
            add_content(db, vod, output_dir, server_base, cid, delay_s)
    sync_all(db, vod, output_dir, server_base, delay_s)


def add_category_content(
    db: sqlite3.Connection,
    vod,
    output_dir: str,
    server_base: str,
    content_ids: list[str],
    delay_s: float = 0,
) -> int:
    count = 0
    for cid in content_ids:
        count += add_content(db, vod, output_dir, server_base, cid, delay_s)
    return count


def delete_strm_paths(paths: list[str]) -> None:
    for p in paths:
        path = Path(p)
        path.unlink(missing_ok=True)
        for parent in [path.parent, path.parent.parent]:
            try:
                parent.rmdir()
            except OSError:
                break


def sync_category_content(
    db: sqlite3.Connection,
    vod,
    output_dir: str,
    server_base: str,
    content_ids: list[str],
    delay_s: float = 0,
) -> None:
    for cid in content_ids:
        sync_item(db, vod, output_dir, server_base, cid, delay_s)
