from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from stb_reader.exceptions import STBError, StreamError

router = APIRouter(prefix="/live-tv", tags=["live-tv"])


def _client(request: Request):
    return request.app.state.client


@router.get("/genres")
def get_genres(request: Request):
    return request.app.state.client.live_tv.get_genres()


@router.get("/channels")
def get_channels(
    request: Request,
    genre_id: str = "*",
    page: int = 1,
    sort: str = "number",
    hd: bool = False,
    fav: bool = False,
):
    result = request.app.state.client.live_tv.get_channels(
        genre_id=genre_id, page=page, sort=sort, hd=hd, fav=fav
    )
    return {
        "data": [vars(ch) for ch in result.items],
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }


@router.get("/channels/{channel_id}/stream")
def get_channel_stream(channel_id: str, request: Request):
    try:
        url = request.app.state.client.live_tv.get_stream_url_by_id(channel_id)
    except StreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except STBError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=502, detail=str(e))
    return RedirectResponse(url=url, status_code=302)
