import pytest
from pathlib import Path
from unittest.mock import MagicMock

from stb_reader.models import Season, Episode, EpisodeFile
from server.db import init_db, upsert_vod_content
from server.sync import (
    sanitize,
    parse_season_num,
    movie_strm_path,
    episode_strm_path,
    write_strm,
    add_content,
    sync_item,
    sync_all,
    delete_content,
    add_or_sync_content,
)


@pytest.fixture
def db():
    return init_db(":memory:")


def _seed(db, content_id, name, year, is_series=False):
    upsert_vod_content(db, {
        "content_id": content_id,
        "name": name,
        "cmd": f"/media/{content_id}.mpg",
        "screenshot_uri": "",
        "genres": "",
        "year": year,
        "description": "",
        "rating": "",
        "duration": 90,
        "is_series": int(is_series),
        "fav": 0,
        "for_rent": 0,
        "lock": 0,
        "portal_raw": "{}",
        "synced_at": "2024-01-01T00:00:00+00:00",
    })
    db.commit()


def _make_vod(seasons: int, eps_per_season: int, files_per_episode: int = 1) -> MagicMock:
    vod = MagicMock()
    season_objs = [
        Season(id=str(i + 1), name=f"Season {i + 1}", video_id="0")
        for i in range(seasons)
    ]
    vod.get_seasons.return_value = season_objs

    ep_map: dict[str, list[Episode]] = {}
    file_map: dict[str, list[EpisodeFile]] = {}
    for season in season_objs:
        eps = [
            Episode(id=f"{season.id}_{j + 1}", name=f"Episode {j + 1}", series_number=str(j + 1), cmd="x")
            for j in range(eps_per_season)
        ]
        ep_map[season.id] = eps
        for ep in eps:
            file_map[ep.id] = (
                [EpisodeFile(id=f"f_{ep.id}", name="HD", cmd="/media/x.mpg")]
                if files_per_episode > 0
                else []
            )

    vod.get_episodes.side_effect = lambda cid, sid, delay_s=0: ep_map[sid]
    vod.get_episode_files.side_effect = lambda cid, sid, eid: file_map[eid]
    return vod


# --- Helper function tests ---

def test_sanitize_replaces_forbidden():
    assert sanitize('a/b\\c:d*e?f"g<h>i|j') == "a-b-c-d-e-f-g-h-i-j"


def test_sanitize_leaves_safe_name():
    assert sanitize("Normal Name 2024") == "Normal Name 2024"


def test_parse_season_num_extracts_digit():
    assert parse_season_num("Season 2", 1) == 2


def test_parse_season_num_fallback():
    assert parse_season_num("Special", 3) == 3


def test_movie_strm_path(tmp_path):
    p = movie_strm_path(str(tmp_path), "My Movie", "2023")
    assert p == tmp_path / "Movies" / "My Movie (2023)" / "My Movie (2023).strm"


def test_movie_strm_path_with_category(tmp_path):
    p = movie_strm_path(str(tmp_path), "My Movie", "2023", category_folder="Action")
    assert p == tmp_path / "Action" / "Movies" / "My Movie (2023)" / "My Movie (2023).strm"


def test_episode_strm_path(tmp_path):
    p = episode_strm_path(str(tmp_path), "My Show", "2021", 1, 2, "Pilot")
    assert p == tmp_path / "TV" / "My Show (2021)" / "Season 01" / "My Show (2021) - S01E02 - Pilot.strm"


def test_episode_strm_path_with_category(tmp_path):
    p = episode_strm_path(str(tmp_path), "My Show", "2021", 1, 2, "Pilot", category_folder="Drama")
    assert p == tmp_path / "Drama" / "TV" / "My Show (2021)" / "Season 01" / "My Show (2021) - S01E02 - Pilot.strm"


def test_write_strm_creates_file(tmp_path):
    path = tmp_path / "sub" / "file.strm"
    write_strm(path, "http://example.com/stream")
    assert path.read_text() == "http://example.com/stream\n"


# --- Core function tests ---

def test_add_content_movie(db, tmp_path):
    _seed(db, "m1", "My Movie", "2023", is_series=False)
    vod = MagicMock()
    count = add_content(db, vod, str(tmp_path), "http://proxy:8000", "m1")
    assert count == 1
    path = tmp_path / "Movies" / "My Movie (2023)" / "My Movie (2023).strm"
    assert path.exists()
    assert path.read_text().strip() == "http://proxy:8000/vod/content/m1/stream"


def test_add_content_series_2x2(db, tmp_path):
    _seed(db, "s1", "My Show", "2021", is_series=True)
    vod = _make_vod(2, 2)
    count = add_content(db, vod, str(tmp_path), "http://proxy:8000", "s1")
    assert count == 4


def test_add_content_missing_raises_key_error(db, tmp_path):
    vod = MagicMock()
    with pytest.raises(KeyError):
        add_content(db, vod, str(tmp_path), "http://proxy:8000", "missing")


def test_add_content_skips_episode_with_no_files(db, tmp_path):
    _seed(db, "s1", "Show", "2020", is_series=True)
    vod = _make_vod(1, 2, files_per_episode=0)
    count = add_content(db, vod, str(tmp_path), "http://proxy:8000", "s1")
    assert count == 0


def test_sync_item_skips_existing_episodes(db, tmp_path):
    _seed(db, "s1", "Show", "2020", is_series=True)
    vod = _make_vod(1, 2)
    add_content(db, vod, str(tmp_path), "http://proxy:8000", "s1")

    new_ep = Episode(id="1_3", name="Episode 3", series_number="3", cmd="x")
    orig_side_effect = vod.get_episodes.side_effect
    vod.get_episodes.side_effect = lambda cid, sid, delay_s=0: orig_side_effect(cid, sid) + [new_ep]
    vod.get_episode_files.side_effect = lambda cid, sid, eid: (
        [EpisodeFile(id=f"f_{eid}", name="HD", cmd="/media/x.mpg")]
    )

    new = sync_item(db, vod, str(tmp_path), "http://proxy:8000", "s1")
    assert new == 1


def test_sync_item_movie_noop(db, tmp_path):
    _seed(db, "m1", "Movie", "2023", is_series=False)
    vod = MagicMock()
    add_content(db, vod, str(tmp_path), "http://proxy:8000", "m1")
    vod.reset_mock()
    result = sync_item(db, vod, str(tmp_path), "http://proxy:8000", "m1")
    assert result == 0
    vod.get_seasons.assert_not_called()


def test_sync_all_processes_all_series(db, tmp_path):
    _seed(db, "s1", "Show A", "2020", is_series=True)
    _seed(db, "s2", "Show B", "2021", is_series=True)
    vod = _make_vod(1, 1)
    add_content(db, vod, str(tmp_path), "http://proxy:8000", "s1")
    add_content(db, vod, str(tmp_path), "http://proxy:8000", "s2")
    # Both already synced — running again should not raise and should call get_seasons for each
    sync_all(db, vod, str(tmp_path), "http://proxy:8000")
    assert vod.get_seasons.call_count == 4  # 2 from add_content + 2 from sync_all


def test_delete_content_removes_files(db, tmp_path):
    _seed(db, "m1", "Movie", "2023", is_series=False)
    vod = MagicMock()
    add_content(db, vod, str(tmp_path), "http://proxy:8000", "m1")
    path = tmp_path / "Movies" / "Movie (2023)" / "Movie (2023).strm"
    assert path.exists()
    delete_content(db, "m1")
    assert not path.exists()


# --- add_or_sync_content tests ---

def test_add_or_sync_adds_when_not_in_library(db, tmp_path):
    _seed(db, "m1", "Movie", "2023", is_series=False)
    vod = MagicMock()
    count = add_or_sync_content(db, vod, str(tmp_path), "http://proxy:8000", "m1")
    assert count == 1
    path = tmp_path / "Movies" / "Movie (2023)" / "Movie (2023).strm"
    assert path.exists()


def test_add_or_sync_syncs_when_already_in_library(db, tmp_path):
    _seed(db, "s1", "Show", "2021", is_series=True)
    vod = _make_vod(1, 1)
    add_content(db, vod, str(tmp_path), "http://proxy:8000", "s1")

    new_ep = Episode(id="1_2", name="Episode 2", series_number="2", cmd="x")
    orig = vod.get_episodes.side_effect
    vod.get_episodes.side_effect = lambda cid, sid, delay_s=0: orig(cid, sid) + [new_ep]
    vod.get_episode_files.side_effect = lambda cid, sid, eid: (
        [EpisodeFile(id=f"f_{eid}", name="HD", cmd="/media/x.mpg")]
    )

    count = add_or_sync_content(db, vod, str(tmp_path), "http://proxy:8000", "s1")
    assert count == 1
