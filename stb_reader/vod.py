from __future__ import annotations
from typing import TYPE_CHECKING
from .models import Category, Content, Season, Episode, EpisodeFile, PagedResult
from .exceptions import NotFoundError, STBError, StreamError
from ._http import _as_list
from .live_tv import _clean_url

if TYPE_CHECKING:
    from ._http import STBSession


class VODService:
    def __init__(self, session: "STBSession") -> None:
        self._s = session

    def get_categories(self) -> list[Category]:
        data = self._s.get("vod", "get_categories")
        return [
            Category(
                id=str(c["id"]),
                title=c.get("title", ""),
                alias=c.get("alias", ""),
                censored=bool(c.get("censored", False)),
            )
            for c in _as_list(data)
        ]

    def get_content(
        self,
        category_id: str = "*",
        page: int = 1,
        sort: str = "added",
        fav: bool = False,
    ) -> PagedResult[Content]:
        raw = self._s.get(
            "vod",
            "get_ordered_list",
            category=category_id,
            p=page,
            sortby=sort,
            fav=int(fav),
            not_ended=0,
        )
        items = [
            Content(
                id=str(c["id"]),
                name=c.get("name", ""),
                cmd=c.get("cmd", ""),
                screenshot_uri=c.get("screenshot_uri", ""),
                genres=c.get("genres_str", ""),
                year=str(c.get("year", "")),
                description=c.get("description", ""),
                rating=str(c.get("rating_imdb", "")),
                duration=str(c.get("time", "")),
                is_series=bool(c.get("is_series", False)),
                fav=bool(c.get("fav", False)),
            )
            for c in raw.get("data", [])
        ]
        return PagedResult(
            items=items,
            total=int(raw.get("total_items", 0)),
            page=page,
            per_page=int(raw.get("max_page_items", len(items))),
        )

    def get_seasons(self, series_id: str) -> list[Season]:
        raw = self._s.get(
            "vod",
            "get_ordered_list",
            movie_id=series_id,
            season_id=0,
            episode_id=0,
        )
        return [
            Season(
                id=str(s["id"]),
                name=s.get("name", ""),
                video_id=str(s.get("video_id", "")),
            )
            for s in raw.get("data", [])
        ]

    def get_episodes(self, series_id: str, season_id: str) -> list[Episode]:
        raw = self._s.get(
            "vod",
            "get_ordered_list",
            movie_id=series_id,
            season_id=season_id,
            episode_id=0,
        )
        return [
            Episode(
                id=str(e["id"]),
                name=e.get("name", ""),
                series_number=str(e.get("series_number", "")),
                cmd=e.get("cmd", ""),
            )
            for e in raw.get("data", [])
        ]

    def get_episode_files(self, series_id: str, season_id: str, episode_id: str) -> list[EpisodeFile]:
        raw = self._s.get(
            "vod",
            "get_ordered_list",
            movie_id=series_id,
            season_id=season_id,
            episode_id=episode_id,
        )
        return [
            EpisodeFile(
                id=str(f["id"]),
                name=f.get("name", ""),
                cmd=f.get("cmd", ""),
            )
            for f in raw.get("data", [])
        ]

    def get_stream_url_by_file_id(
        self, series_id: str, season_id: str, episode_id: str, file_id: str
    ) -> str:
        files = self.get_episode_files(series_id, season_id, episode_id)
        for f in files:
            if f.id == str(file_id):
                return self.get_stream_url(f.cmd)
        raise NotFoundError("file not found")

    def get_stream_url(self, cmd: str) -> str:
        raw = self._s.get("vod", "create_link", cmd=cmd)
        if raw.get("error"):
            raise StreamError(raw["error"])
        url = raw.get("cmd", raw.get("url", ""))
        return _clean_url(url)

    def get_stream_url_by_content_id(self, content_id: str) -> str:
        return self.get_stream_url(f"/media/{content_id}.mpg")

