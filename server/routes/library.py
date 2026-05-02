import sqlite3
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from stb_reader.exceptions import NotFoundError
from ..db import get_library_item, get_library_items
from ..sync import add_content, delete_content, sync_all, sync_item

router = APIRouter(tags=["library"])


class AddContentRequest(BaseModel):
    name: str
    year: str
    is_series: bool


@router.post("/library/add/{content_id}", status_code=201)
def add_library_content(content_id: str, body: AddContentRequest, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    try:
        count = add_content(
            db, vod,
            settings.strm_output_dir, settings.strm_server_base_url,
            content_id, body.name, body.year, body.is_series,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Content already in library")
    item = get_library_item(db, content_id)
    return {**item, "strm_count": count}


@router.get("/library")
def list_library(request: Request):
    return get_library_items(request.app.state.db)


@router.delete("/library/{content_id}", status_code=204)
def remove_library_content(content_id: str, request: Request):
    db = request.app.state.db
    if get_library_item(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    delete_content(db, content_id)


@router.post("/library/sync/{content_id}")
def sync_library_content(content_id: str, request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    if get_library_item(db, content_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    new_files = sync_item(db, vod, settings.strm_output_dir, settings.strm_server_base_url, content_id)
    return {"new_files": new_files}


@router.post("/library/sync")
def sync_library_all(request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    vod = request.app.state.client.vod
    return sync_all(db, vod, settings.strm_output_dir, settings.strm_server_base_url)
