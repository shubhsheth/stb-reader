from __future__ import annotations
from typing import TYPE_CHECKING
from .models import Category, Content, Season, Episode, PagedResult
from .exceptions import STBError, StreamError
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
            for c in (data if isinstance(data, list) else data.get("data", []))
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

    def get_stream_url(self, cmd: str) -> str:
        raw = self._s.get("vod", "create_link", cmd=cmd)
        if raw.get("error"):
            raise StreamError(raw["error"])
        url = raw.get("cmd", raw.get("url", ""))
        return _clean_url(url)

    def get_stream_url_by_content_id(self, content_id: str) -> str:
        page = 1
        while True:
            result = self.get_content(category_id="*", page=page)
            for item in result.items:
                if item.id == str(content_id):
                    return self.get_stream_url(item.cmd)
            if not result.items or page * result.per_page >= result.total:
                raise STBError("content not found")
            page += 1

    def get_stream_url_by_episode_id(self, episode_id: str, series_id: str) -> str:
        seasons = self.get_seasons(series_id)
        for season in seasons:
            episodes = self.get_episodes(series_id, season.id)
            for ep in episodes:
                if ep.id == str(episode_id):
                    return self.get_stream_url(ep.cmd)
        raise STBError("episode not found")
