import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from stb_reader.models import Season, Episode, EpisodeFile
from server.db import init_db, upsert_vod_content


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


class TestAddContent:
    def test_add_movie_returns_201(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1", "My Movie", "2023", is_series=0))
        db.commit()
        resp = tc.post("/library/add/m1")
        assert resp.status_code == 201
        data = resp.json()
        assert data["content_id"] == "m1"
        strm = tmp_path / "Movies" / "My Movie (2023)" / "My Movie (2023).strm"
        assert strm.exists()

    def test_add_series_returns_correct_count(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("s1", "My Show", "2021", is_series=1))
        db.commit()
        _setup_series_vod(mock_client, seasons=1, eps_per_season=2)
        resp = tc.post("/library/add/s1")
        assert resp.status_code == 201
        assert resp.json()["strm_count"] == 2

    def test_add_unknown_returns_404(self, library_client):
        tc, _, db, _ = library_client
        resp = tc.post("/library/add/unknown")
        assert resp.status_code == 404

    def test_add_duplicate_returns_409(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1"))
        db.commit()
        tc.post("/library/add/m1")
        resp = tc.post("/library/add/m1")
        assert resp.status_code == 409


class TestListLibrary:
    def test_lists_only_in_library_items(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1"))
        upsert_vod_content(db, _vod_row("m2"))
        db.commit()
        tc.post("/library/add/m1")
        resp = tc.get("/library")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["content_id"] == "m1"
        assert items[0]["strm_count"] == 1


class TestDeleteLibrary:
    def test_delete_returns_204_and_removes_strm(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("m1", "Movie", "2023"))
        db.commit()
        tc.post("/library/add/m1")
        strm = tmp_path / "Movies" / "Movie (2023)" / "Movie (2023).strm"
        assert strm.exists()
        resp = tc.delete("/library/m1")
        assert resp.status_code == 204
        assert not strm.exists()

    def test_delete_unknown_returns_404(self, library_client):
        tc, _, db, _ = library_client
        resp = tc.delete("/library/unknown")
        assert resp.status_code == 404


class TestSyncContent:
    def test_sync_item_returns_204(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("s1", "Show", "2020", is_series=1))
        db.commit()
        _setup_series_vod(mock_client, seasons=1, eps_per_season=1)
        tc.post("/library/add/s1")
        resp = tc.post("/library/sync/s1")
        assert resp.status_code == 204

    def test_sync_unknown_returns_404(self, library_client):
        tc, _, db, _ = library_client
        resp = tc.post("/library/sync/unknown")
        assert resp.status_code == 404

    def test_sync_all_returns_204(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        upsert_vod_content(db, _vod_row("s1", "Show", "2020", is_series=1))
        db.commit()
        _setup_series_vod(mock_client, seasons=1, eps_per_season=1)
        tc.post("/library/add/s1")
        resp = tc.post("/library/sync")
        assert resp.status_code == 204
