import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ..db import count_vod_content, get_sync_state, search_vod_content
from ..vod_sync import run_portal_sync
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


@router.get("/content/{content_id}/seasons/{season_id}/episodes/{episode_id}/files")
def get_episode_files(content_id: str, season_id: str, episode_id: str, request: Request):
    return request.app.state.client.vod.get_episode_files(content_id, season_id, episode_id)


@router.get("/content/{content_id}/seasons/{season_id}/episodes/{episode_id}/stream")
def get_episode_stream(content_id: str, season_id: str, episode_id: str, request: Request):
    return stream_redirect(
        request.app.state.client.vod.get_stream_url_by_first_file,
        content_id, season_id, episode_id,
    )


@router.get("/content/{content_id}/seasons/{season_id}/episodes/{episode_id}/files/{file_id}/stream")
def get_episode_file_stream(
    content_id: str, season_id: str, episode_id: str, file_id: str, request: Request
):
    return stream_redirect(
        request.app.state.client.vod.get_stream_url_by_file_id,
        content_id, season_id, episode_id, file_id,
    )


@router.get("/content/{content_id}/stream")
def get_content_stream(content_id: str, request: Request):
    return stream_redirect(request.app.state.client.vod.get_stream_url_by_content_id, content_id)


@router.post("/sync", status_code=202)
async def trigger_sync(request: Request):
    db = request.app.state.db
    state = get_sync_state(db)
    if state["last_sync_status"] == "running":
        raise HTTPException(status_code=409, detail="Sync already running")
    settings = request.app.state.settings
    lock = request.app.state.db_lock

    async def _run():
        await asyncio.to_thread(
            run_portal_sync,
            db, lock,
            request.app.state.client.vod,
            settings.strm_output_dir,
            settings.vod_sync_request_delay_ms,
            settings.vod_sync_max_pages,
        )

    asyncio.create_task(_run())
    return {"detail": "Sync started"}


@router.get("/sync/status")
def sync_status(request: Request):
    return get_sync_state(request.app.state.db)


@router.get("/search")
def search(
    request: Request,
    query: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    is_series: int | None = Query(default=None),
):
    db = request.app.state.db
    if count_vod_content(db) == 0:
        raise HTTPException(status_code=503, detail="Portal content not yet synced")
    items, total = search_vod_content(db, query, page, page_size, is_series)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
