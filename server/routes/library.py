import asyncio
import sqlite3

from fastapi import APIRouter, HTTPException, Request

from ..db import get_library_item, get_library_items, get_vod_content
from ..sync import add_content, delete_content, sync_all, sync_item

router = APIRouter(tags=["library"])


@router.post("/library/add/{content_id}", status_code=201)
def add_library_content(content_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_vod_content(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Content not found in portal cache")
    if get_library_item(db, content_id) is not None:
        raise HTTPException(status_code=409, detail="Content already in library")
    try:
        strm_count = add_content(
            db, vod, settings.strm_output_dir, settings.strm_server_base_url, content_id,
            delay_s=settings.vod_sync_request_delay_ms / 1000,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Content already in library")
    item = get_library_item(db, content_id)
    return {**item, "strm_count": strm_count}


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
        sync_all,
        db, vod, settings.strm_output_dir, settings.strm_server_base_url,
        settings.vod_sync_request_delay_ms / 1000,
    ))
