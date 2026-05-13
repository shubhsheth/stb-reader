import asyncio

from fastapi import APIRouter, HTTPException, Request

from ..db import (
    add_category_to_library,
    get_category,
    get_content_ids_for_category,
    get_library_item,
    get_library_items,
    get_vod_content,
    list_categories,
    remove_category_from_library,
)
from ..sync import add_or_sync_content, delete_content, sync_all

router = APIRouter(tags=["library"])


@router.post("/library/content/{content_id}", status_code=202)
async def upsert_library_content(content_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_vod_content(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Content not found in portal cache")
    asyncio.create_task(asyncio.to_thread(
        add_or_sync_content,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url, content_id,
        settings.vod_sync_request_delay_ms / 1000,
    ))


@router.delete("/library/content/{content_id}", status_code=204)
def remove_library_content(content_id: str, request: Request):
    db = request.app.state.db
    if get_library_item(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    delete_content(db, content_id)


@router.post("/library/category/{category_id}", status_code=202)
async def upsert_library_category(category_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_category(db, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found in portal cache")
    add_category_to_library(db, category_id)
    content_ids = get_content_ids_for_category(db, category_id)

    async def _sync_category():
        for content_id in content_ids:
            await asyncio.to_thread(
                add_or_sync_content,
                db, vod, settings.strm_output_dir, settings.strm_server_base_url,
                content_id, settings.vod_sync_request_delay_ms / 1000,
            )

    asyncio.create_task(_sync_category())


@router.delete("/library/category/{category_id}", status_code=204)
def remove_library_category(category_id: str, request: Request):
    db = request.app.state.db
    lock = request.app.state.db_lock
    if get_category(db, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found in portal cache")
    with lock:
        for content_id in get_content_ids_for_category(db, category_id):
            if get_library_item(db, content_id) is not None:
                delete_content(db, content_id)
        remove_category_from_library(db, category_id)


@router.get("/library/categories")
def list_library_categories(request: Request):
    return list_categories(request.app.state.db)


@router.get("/library")
def list_library(request: Request):
    return get_library_items(request.app.state.db)


@router.post("/library/sync", status_code=204)
async def sync_library_all(request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    asyncio.create_task(asyncio.to_thread(
        sync_all,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url,
        settings.vod_sync_request_delay_ms / 1000,
    ))
