from __future__ import annotations
from typing import TYPE_CHECKING
from .models import Genre, Channel, PagedResult
from .exceptions import STBError, StreamError
from ._http import _as_list, _clean_url

if TYPE_CHECKING:
    from ._http import STBSession


class ITVService:
    def __init__(self, session: "STBSession") -> None:
        self._s = session

    def get_genres(self) -> list[Genre]:
        data = self._s.get("itv", "get_genres")
        return [
            Genre(
                id=str(g["id"]),
                title=g.get("title", ""),
                alias=g.get("alias", ""),
                censored=bool(g.get("censored", False)),
            )
            for g in _as_list(data)
        ]

    def get_channels(
        self,
        genre_id: str = "*",
        page: int = 1,
        sort: str = "number",
        hd: bool = False,
        fav: bool = False,
    ) -> PagedResult[Channel]:
        raw = self._s.get(
            "itv",
            "get_ordered_list",
            genre=genre_id,
            p=page - 1,
            sortby=sort,
            hd=int(hd),
            fav=int(fav),
        )
        items = [
            Channel(
                id=str(c["id"]),
                number=str(c.get("number", "")),
                name=c.get("name", ""),
                cmd=c.get("cmd", ""),
                logo=c.get("logo", ""),
                genre_id=str(c.get("tv_genre_id", "")),
                hd=bool(c.get("hd", False)),
                censored=bool(c.get("censored", False)),
                xmltv_id=str(c.get("xmltv_id", "")),
            )
            for c in raw.get("data", [])
        ]
        return PagedResult(
            items=items,
            total=int(raw.get("total_items", 0)),
            page=page,
            per_page=int(raw.get("max_page_items", len(items))),
        )

    def get_all_channels(self) -> list[Channel]:
        raw = self._s.get("itv", "get_all_channels")
        return [
            Channel(
                id=str(c["id"]),
                number=str(c.get("number", "")),
                name=c.get("name", ""),
                cmd=c.get("cmd", ""),
                logo=c.get("logo", ""),
                genre_id=str(c.get("tv_genre_id", "")),
                hd=bool(c.get("hd", False)),
                censored=bool(c.get("censored", False)),
                xmltv_id=str(c.get("xmltv_id", "")),
            )
            for c in _as_list(raw)
        ]

    def get_stream_url(self, cmd: str) -> str:
        raw = self._s.get("itv", "create_link", cmd=cmd)
        if raw.get("error"):
            raise StreamError(raw["error"])
        url = raw.get("cmd", "")
        return _clean_url(url)

