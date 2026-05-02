import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from stb_reader.models import Season, Episode, EpisodeFile
from server.db import init_db


BASE_ENV = {
    "STB_PORTAL_URL": "http://portal.test",
    "STB_MAC": "00:1A:79:00:00:01",
    "STRM_SERVER_BASE_URL": "http://stb-reader:8000",
    "STRM_SYNC_INTERVAL_HOURS": "0",
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

    mock_client.vod.get_episodes.side_effect = lambda cid, sid: ep_map[sid]
    mock_client.vod.get_episode_files.side_effect = lambda cid, sid, eid: file_map.get(eid, [])


class TestAddContent:
    def test_add_movie_returns_201(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        resp = tc.post("/library/add/m1", json={"name": "My Movie", "year": "2023", "is_series": False})
        assert resp.status_code == 201
        data = resp.json()
        assert data["content_id"] == "m1"
        strm = tmp_path / "Movies" / "My Movie (2023)" / "My Movie (2023).strm"
        assert strm.exists()

    def test_add_series_returns_correct_count(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        _setup_series_vod(mock_client, seasons=1, eps_per_season=2)
        resp = tc.post("/library/add/s1", json={"name": "My Show", "year": "2021", "is_series": True})
        assert resp.status_code == 201
        assert resp.json()["strm_count"] == 2

    def test_add_duplicate_returns_409(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        tc.post("/library/add/m1", json={"name": "Movie", "year": "2023", "is_series": False})
        resp = tc.post("/library/add/m1", json={"name": "Movie", "year": "2023", "is_series": False})
        assert resp.status_code == 409


class TestListLibrary:
    def test_lists_items_with_strm_count(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        tc.post("/library/add/m1", json={"name": "Movie", "year": "2023", "is_series": False})
        resp = tc.get("/library")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["strm_count"] == 1


class TestDeleteLibrary:
    def test_delete_returns_204(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        tc.post("/library/add/m1", json={"name": "Movie", "year": "2023", "is_series": False})
        strm = tmp_path / "Movies" / "Movie (2023)" / "Movie (2023).strm"
        assert strm.exists()
        resp = tc.delete("/library/m1")
        assert resp.status_code == 204
        assert not strm.exists()

    def test_delete_unknown_returns_404(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        resp = tc.delete("/library/unknown")
        assert resp.status_code == 404


class TestSyncContent:
    def test_sync_item_returns_new_file_count(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        _setup_series_vod(mock_client, seasons=1, eps_per_season=1)
        tc.post("/library/add/s1", json={"name": "Show", "year": "2020", "is_series": True})

        new_ep = Episode(id="1_2", name="Ep 2", series_number="2", cmd="x")
        orig = mock_client.vod.get_episodes.side_effect
        mock_client.vod.get_episodes.side_effect = lambda cid, sid: orig(cid, sid) + [new_ep]
        mock_client.vod.get_episode_files.side_effect = lambda cid, sid, eid: (
            [EpisodeFile(id=f"f_{eid}", name="HD", cmd="/media/x.mpg")]
        )

        resp = tc.post("/library/sync/s1")
        assert resp.status_code == 200
        assert resp.json()["new_files"] == 1

    def test_sync_unknown_returns_404(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        resp = tc.post("/library/sync/unknown")
        assert resp.status_code == 404

    def test_sync_all_returns_summary(self, library_client):
        tc, mock_client, db, tmp_path = library_client
        _setup_series_vod(mock_client, seasons=1, eps_per_season=1)
        tc.post("/library/add/s1", json={"name": "Show", "year": "2020", "is_series": True})
        resp = tc.post("/library/sync")
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert results[0]["content_id"] == "s1"
