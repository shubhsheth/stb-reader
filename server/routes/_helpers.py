from collections.abc import Callable

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask
from stb_reader.exceptions import NotFoundError, STBError, StreamError

_FORWARD_REQUEST_HEADERS = {"range", "accept-encoding", "user-agent"}
_KEEP_RESPONSE_HEADERS = {
    "content-type", "content-length", "content-range", "accept-ranges", "content-encoding"
}


def stream_redirect(url_fn: Callable, *args, **kwargs) -> RedirectResponse:
    try:
        url = url_fn(*args, **kwargs)
    except StreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except STBError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return RedirectResponse(url=url, status_code=302)


async def stream_response(settings, request: Request, url_fn: Callable, *args, **kwargs) -> Response:
    try:
        url = url_fn(*args, **kwargs)
    except StreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except STBError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not settings.strm_proxy_streams:
        return RedirectResponse(url=url, status_code=302)

    forward = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST_HEADERS}
    client = httpx.AsyncClient()
    req = client.build_request("GET", url, headers=forward)
    upstream = await client.send(req, stream=True, follow_redirects=True)
    keep = {k: v for k, v in upstream.headers.items() if k.lower() in _KEEP_RESPONSE_HEADERS}

    async def cleanup():
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_bytes(chunk_size=65536),
        status_code=upstream.status_code,
        headers=keep,
        background=BackgroundTask(cleanup),
    )


def paged_response(result) -> dict:
    return {
        "data": result.items,
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }
