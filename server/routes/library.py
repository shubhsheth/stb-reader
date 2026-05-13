import asyncio

from fastapi import APIRouter, HTTPException, Request

from ..db import (
    add_to_library,
    get_category_content_ids,
    get_category_library_content_ids,
    get_library_item,
    get_library_items,
    get_vod_category,
    get_vod_content,
    remove_from_library,
    set_category_auto_add,
)
from ..sync import (
    add_category_content,
    add_content,
    delete_content,
    delete_strm_paths,
    run_library_sync,
    sync_category_content,
    sync_item,
)

router = APIRouter(tags=["library"])


@router.post("/library/add/{content_id}", status_code=202)
async def add_library_content(content_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_vod_content(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Content not found in portal cache")
    if get_library_item(db, content_id) is not None:
        raise HTTPException(status_code=409, detail="Content already in library")
    add_to_library(db, content_id)
    asyncio.create_task(asyncio.to_thread(
        add_content,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url, content_id,
        settings.vod_sync_request_delay_ms / 1000,
    ))


@router.get("/library")
def list_library(request: Request):
    return get_library_items(request.app.state.db)


@router.delete("/library/{content_id}", status_code=204)
def remove_library_content(content_id: str, request: Request):
    db = request.app.state.db
    if get_library_item(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    delete_content(db, content_id)


@router.post("/library/sync/{content_id}", status_code=204)
async def sync_library_content(content_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_library_item(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    asyncio.create_task(asyncio.to_thread(
        sync_item,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url, content_id,
        settings.vod_sync_request_delay_ms / 1000,
    ))


@router.post("/library/sync", status_code=204)
async def sync_library_all(request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    asyncio.create_task(asyncio.to_thread(
        run_library_sync,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url,
        settings.vod_sync_request_delay_ms / 1000,
    ))


@router.post("/library/categories/{category_id}", status_code=202)
async def add_category_to_library(category_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_vod_category(db, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    set_category_auto_add(db, category_id, 1)
    content_ids = get_category_content_ids(db, category_id)
    for cid in content_ids:
        add_to_library(db, cid)
    asyncio.create_task(asyncio.to_thread(
        add_category_content,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url,
        content_ids, settings.vod_sync_request_delay_ms / 1000,
    ))
    return {"added": len(content_ids)}


@router.delete("/library/categories/{category_id}", status_code=202)
async def remove_category_from_library(category_id: str, request: Request):
    db = request.app.state.db
    if get_vod_category(db, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    set_category_auto_add(db, category_id, 0)
    content_ids = get_category_library_content_ids(db, category_id)
    all_paths = []
    for cid in content_ids:
        all_paths.extend(remove_from_library(db, cid))
    asyncio.create_task(asyncio.to_thread(delete_strm_paths, all_paths))
    return {"removed": len(content_ids)}


@router.post("/library/categories/{category_id}/sync", status_code=204)
async def sync_category_library(category_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_vod_category(db, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    content_ids = get_category_library_content_ids(db, category_id)
    asyncio.create_task(asyncio.to_thread(
        sync_category_content,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url,
        content_ids, settings.vod_sync_request_delay_ms / 1000,
    ))
