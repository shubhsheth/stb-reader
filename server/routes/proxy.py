from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from ._helpers import _proxy_url

router = APIRouter(tags=["proxy"])


@router.get("/proxy")
async def proxy(url: str = Query(...), request: Request = None):
    return await _proxy_url(url, request)

@router.get("/proxy/{path:path}")
async def proxy_with_path(path: str, url: str = Query(...), request: Request = None):
    return await _proxy_url(url, request)