from fastapi import APIRouter, Request
from ._helpers import paged_response, stream_response

router = APIRouter(prefix="/live-tv", tags=["live-tv"])


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
    return paged_response(result)


@router.get("/channels/{channel_id}/stream")
async def get_channel_stream(channel_id: str, request: Request):
    return await stream_response(
        request.app.state.settings,
        request,
        request.app.state.client.live_tv.get_stream_url_by_id,
        channel_id,
    )
