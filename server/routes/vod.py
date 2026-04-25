from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from stb_reader.exceptions import STBError, StreamError

router = APIRouter(prefix="/vod", tags=["vod"])


@router.get("/categories")
def get_categories(request: Request):
    return request.app.state.client.vod.get_categories()


@router.get("/content")
def get_content(
    request: Request,
    category_id: str = "*",
    page: int = 1,
    sort: str = "added",
    fav: bool = False,
):
    result = request.app.state.client.vod.get_content(
        category_id=category_id, page=page, sort=sort, fav=fav
    )
    return {
        "data": [vars(c) for c in result.items],
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }


@router.get("/content/{content_id}/seasons")
def get_seasons(content_id: str, request: Request):
    return request.app.state.client.vod.get_seasons(content_id)


@router.get("/content/{content_id}/seasons/{season_id}/episodes")
def get_episodes(content_id: str, season_id: str, request: Request):
    return request.app.state.client.vod.get_episodes(content_id, season_id)


@router.get("/content/{content_id}/stream")
def get_content_stream(content_id: str, request: Request):
    try:
        url = request.app.state.client.vod.get_stream_url_by_content_id(content_id)
    except StreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except STBError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=502, detail=str(e))
    return RedirectResponse(url=url, status_code=302)


@router.get("/episodes/{episode_id}/stream")
def get_episode_stream(episode_id: str, request: Request, series_id: str):
    try:
        url = request.app.state.client.vod.get_stream_url_by_episode_id(episode_id, series_id)
    except StreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except STBError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=502, detail=str(e))
    return RedirectResponse(url=url, status_code=302)
