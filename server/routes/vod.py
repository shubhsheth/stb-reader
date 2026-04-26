from fastapi import APIRouter, Request
from ._helpers import paged_response, stream_redirect

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
    return paged_response(result)


@router.get("/content/{content_id}/seasons")
def get_seasons(content_id: str, request: Request):
    return request.app.state.client.vod.get_seasons(content_id)


@router.get("/content/{content_id}/seasons/{season_id}/episodes")
def get_episodes(content_id: str, season_id: str, request: Request):
    return request.app.state.client.vod.get_episodes(content_id, season_id)


@router.get("/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files")
def get_episode_files(series_id: str, season_id: str, episode_id: str, request: Request):
    return request.app.state.client.vod.get_episode_files(series_id, season_id, episode_id)


@router.get("/content/{series_id}/seasons/{season_id}/episodes/{episode_id}/files/{file_id}/stream")
def get_episode_file_stream(
    series_id: str, season_id: str, episode_id: str, file_id: str, request: Request
):
    return stream_redirect(
        request.app.state.client.vod.get_stream_url_by_file_id,
        series_id, season_id, episode_id, file_id,
    )


@router.get("/content/{content_id}/stream")
def get_content_stream(content_id: str, request: Request):
    return stream_redirect(request.app.state.client.vod.get_stream_url_by_content_id, content_id)


@router.get("/episodes/{episode_id}/stream")
def get_episode_stream(episode_id: str, request: Request, series_id: str):
    return stream_redirect(
        request.app.state.client.vod.get_stream_url_by_episode_id, episode_id, series_id
    )
