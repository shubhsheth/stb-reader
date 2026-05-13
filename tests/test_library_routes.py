import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from stb_reader.models import Season, Episode, EpisodeFile
from server.db import (
    init_db,
    upsert_vod_content,
    upsert_vod_category,
    upsert_vod_content_category,
    add_to_library,
    add_strm_file,
)


BASE_ENV = {
    "STB_PORTAL_URL": "http://portal.test",
    "STB_MAC": "00:1A:79:00:00:01",
    "STRM_SERVER_BASE_URL": "http://stb-reader:8000",
    "VOD_SYNC_INTERVAL_HOURS": "0",
}


def _vod_row(content_id, name="My Movie", year="2023", is_series=0):
    return {
        "content_id": content_id,
        "name": name,
        "cmd": f"/media/{content_id}.mpg",
        "screenshot_uri": "",
        "genres": "Action",
        "year": year,
        "description": "",
        "rating": "7.0",
        "duration": 90,
        "is_series": is_series,
        "fav": 0,
        "for_rent": 0,
        "lock": 0,
        "portal_raw": "{}",
        "synced_at": "2024-01-01T00:00:00+00:00",
    }


@pytest.fixture
def library_client(tmp_path):
    real_db = init_db(":memory:")
    mock_client = MagicMock()
    mock_client.authenticate.return_value = None

    env = {
        **BASE_ENV,
        "STRM_OUTPUT_DIR": str(tmp_path),
        "STRM_DATA_DIR": str(tmp_path),
    }

    import server.main as main_mod
    with patch.dict("os.environ", env):
        with patch("server.main.STBClient", return_value=mock_client):
            with patch("server.main.init_db", return_value=real_db):
                with patch("server.main.count_vod_content", return_value=1):
                    with TestClient(main_mod.app, raise_server_exceptions=False) as tc:
                        yield tc, mock_client, real_db, tmp_path


def _setup_series_vod(mock_client, seasons: int = 1, eps_per_season: int = 2) -> None:
    season_objs = [
        Season(id=str(i + 1), name=f"Season {i + 1}", video_id="0")
        for i in range(seasons)
    ]
    mock_client.vod.get_seasons.return_value = season_objs

    ep_map: dict[str, list[Episode]] = {}
    file_map: dict[str, list[EpisodeFile]] = {}
    for season in season_objs:
        eps = [
            Episode(id=f"{season.id}_{j + 1}", name=f"Ep {j + 1}", series_number=str(j + 1), cmd="x")
            for j in range(eps_per_season)
        ]
        ep_map[season.id] = eps
        for ep in eps:
            file_map[ep.id] = [EpisodeFile(id=f"f_{ep.id}", name="HD", cmd="/media/x.mpg")]

    mock_client.vod.get_episodes.side_effect = lambda cid, sid, delay_s=0: ep_map[sid]
    mock_client.vod.get_episode_files.side_effect = lambda cid, sid, eid: file_map.get(eid, [])


class TestUpsertContent:
    def test_returns_202_for_new_content(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1"))
        db.commit()
        resp = tc.post("/library/content/m1")
        assert resp.status_code == 202

    def test_returns_202_for_content_already_in_library(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1", is_series=0))
        db.commit()
        add_to_library(db, "m1")
        resp = tc.post("/library/content/m1")
        assert resp.status_code == 202

    def test_returns_404_for_unknown_content(self, library_client):
        tc, _, db, _ = library_client
        resp = tc.post("/library/content/unknown")
        assert resp.status_code == 404


class TestDeleteContent:
    def test_returns_204_and_removes_strm(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1", "Movie", "2023"))
        db.commit()
        add_to_library(db, "m1")
        strm = tmp_path / "Movies" / "Movie (2023)" / "Movie (2023).strm"
        strm.parent.mkdir(parents=True, exist_ok=True)
        strm.write_text("http://x\n")
        add_strm_file(db, "m1", None, None, "m1", str(strm))
        resp = tc.delete("/library/content/m1")
        assert resp.status_code == 204
        assert not strm.exists()

    def test_returns_404_when_not_in_library(self, library_client):
        tc, _, db, _ = library_client
        resp = tc.delete("/library/content/unknown")
        assert resp.status_code == 404


class TestListLibrary:
    def test_lists_only_in_library_items(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1"))
        upsert_vod_content(db, _vod_row("m2"))
        db.commit()
        add_to_library(db, "m1")
        resp = tc.get("/library")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["content_id"] == "m1"


class TestSyncAll:
    def test_sync_all_returns_204(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("s1", "Show", "2020", is_series=1))
        db.commit()
        _setup_series_vod(mock_client, seasons=1, eps_per_season=1)
        add_to_library(db, "s1")
        resp = tc.post("/library/sync")
        assert resp.status_code == 204


class TestAuthErrorHandling:
    def test_auth_error_during_series_sync_does_not_crash_server(self, library_client):
        """AuthError raised inside a sync task must be caught by the done-callback,
        not surface as an unhandled task exception that could crash the server."""
        import logging
        from stb_reader.exceptions import AuthError

        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("s1", "Show", "2020", is_series=1))
        db.commit()
        mock_client.vod.get_seasons.side_effect = AuthError("Portal rejected request (get_ordered_list): Authorization failed")

        with tc as client:
            resp = client.post("/library/content/s1")
        assert resp.status_code == 202

    def test_auth_error_during_sync_all_does_not_crash_server(self, library_client):
        from stb_reader.exceptions import AuthError

        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("s1", "Show", "2020", is_series=1))
        db.commit()
        add_to_library(db, "s1")
        mock_client.vod.get_seasons.side_effect = AuthError("Portal rejected request (get_ordered_list): Authorization failed")

        with tc as client:
            resp = client.post("/library/sync")
        assert resp.status_code == 204


class TestCategoryUpsert:
    def test_returns_202_for_known_category(self, library_client):
        tc, _, db, _ = library_client
        upsert_vod_category(db, "cat1", "Action", "")
        db.commit()
        resp = tc.post("/library/category/cat1")
        assert resp.status_code == 202

    def test_sets_in_library_on_category(self, library_client):
        from server.db import get_category
        tc, _, db, _ = library_client
        upsert_vod_category(db, "cat1", "Action", "")
        db.commit()
        tc.post("/library/category/cat1")
        cat = get_category(db, "cat1")
        assert cat["in_library"] == 1
        assert cat["added_at"] is not None

    def test_returns_404_for_unknown_category(self, library_client):
        tc, _, db, _ = library_client
        resp = tc.post("/library/category/unknown")
        assert resp.status_code == 404

    def test_category_sync_passes_category_folder_to_add_or_sync(self, library_client):
        tc, _, db, _ = library_client
        upsert_vod_category(db, "cat1", "Action Movies", "")
        upsert_vod_content(db, _vod_row("m1", "Die Hard", "1988"))
        db.commit()
        upsert_vod_content_category(db, "m1", "cat1")
        db.commit()
        calls = []
        with patch("server.routes.library.add_or_sync_content", side_effect=lambda *a, **kw: calls.append((a, kw)) or 1):
            tc.post("/library/category/cat1")
        assert any(kw.get("category_folder") == "Action Movies" or (len(a) > 6 and a[6] == "Action Movies") for a, kw in calls)

    def test_enqueues_task_for_each_content_item(self, library_client):
        tc, _, db, _ = library_client
        upsert_vod_category(db, "cat1", "Action", "")
        upsert_vod_content(db, _vod_row("m1"))
        upsert_vod_content(db, _vod_row("m2"))
        db.commit()
        upsert_vod_content_category(db, "m1", "cat1")
        upsert_vod_content_category(db, "m2", "cat1")
        db.commit()
        resp = tc.post("/library/category/cat1")
        assert resp.status_code == 202


class TestCategoryDelete:
    def test_returns_204_for_known_category(self, library_client):
        tc, _, db, _ = library_client
        upsert_vod_category(db, "cat1", "Action", "")
        db.commit()
        resp = tc.delete("/library/category/cat1")
        assert resp.status_code == 204

    def test_removes_only_category_files_and_clears_library_flag(self, library_client):
        from server.db import get_library_item, get_category
        tc, _, db, tmp_path = library_client
        upsert_vod_category(db, "cat1", "Action", "")
        upsert_vod_content(db, _vod_row("m1", "Movie", "2023"))
        db.commit()
        upsert_vod_content_category(db, "m1", "cat1")
        db.commit()
        add_to_library(db, "m1")
        # File placed under the category folder
        strm = tmp_path / "Action" / "Movies" / "Movie (2023)" / "Movie (2023).strm"
        strm.parent.mkdir(parents=True, exist_ok=True)
        strm.write_text("http://x\n")
        add_strm_file(db, "m1", None, None, "m1", str(strm))

        resp = tc.delete("/library/category/cat1")
        assert resp.status_code == 204
        assert get_library_item(db, "m1") is None
        assert not strm.exists()
        assert get_category(db, "cat1")["in_library"] == 0

    def test_single_add_file_survives_category_delete(self, library_client):
        from server.db import get_library_item
        tc, _, db, tmp_path = library_client
        upsert_vod_category(db, "cat1", "Action", "")
        upsert_vod_content(db, _vod_row("m1", "Movie", "2023"))
        db.commit()
        upsert_vod_content_category(db, "m1", "cat1")
        db.commit()
        add_to_library(db, "m1")
        # File placed via single-add (root folder, no category prefix)
        root_strm = tmp_path / "Movies" / "Movie (2023)" / "Movie (2023).strm"
        root_strm.parent.mkdir(parents=True, exist_ok=True)
        root_strm.write_text("http://x\n")
        add_strm_file(db, "m1", None, None, "m1", str(root_strm))

        resp = tc.delete("/library/category/cat1")
        assert resp.status_code == 204
        # Content still in library — its root strm file was not deleted
        assert get_library_item(db, "m1") is not None
        assert root_strm.exists()

    def test_returns_404_for_unknown_category(self, library_client):
        tc, _, db, _ = library_client
        resp = tc.delete("/library/category/unknown")
        assert resp.status_code == 404

    def test_succeeds_when_no_content_in_library(self, library_client):
        tc, _, db, _ = library_client
        upsert_vod_category(db, "cat1", "Action", "")
        upsert_vod_content(db, _vod_row("m1"))
        db.commit()
        upsert_vod_content_category(db, "m1", "cat1")
        db.commit()
        # m1 is NOT in library
        resp = tc.delete("/library/category/cat1")
        assert resp.status_code == 204
