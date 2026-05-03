from collections.abc import Callable
from urllib.parse import urljoin, quote
import re

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask
from stb_reader.exceptions import NotFoundError, STBError, StreamError

_FORWARD_REQUEST_HEADERS = {"range", "accept-encoding", "user-agent"}
_KEEP_RESPONSE_HEADERS = {
    "content-type", "content-length", "content-range", "accept-ranges", "content-encoding"
}
_HLS_MIME_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl"}
_URI_ATTR_RE = re.compile(r'URI="([^"]*)"')


def _is_hls(url: str, content_type: str) -> bool:
    mime = content_type.split(";")[0].strip().lower()
    return mime in _HLS_MIME_TYPES or url.split("?")[0].lower().endswith(".m3u8")


def _rewrite_m3u8(content: str, base_url: str, proxy_base: str) -> str:
    """Rewrite all URLs in an HLS playlist to go through the proxy endpoint.

    Handles both plain URL lines (segments, sub-playlists) and URI= attributes
    inside tag lines (#EXT-X-MEDIA, #EXT-X-KEY, #EXT-X-MAP, etc.).
    """
    def _proxy(uri: str) -> str:
        return f"{proxy_base}/proxy?url={quote(urljoin(base_url, uri), safe='')}"

    out = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            line = _URI_ATTR_RE.sub(lambda m: f'URI="{_proxy(m.group(1))}"', line)
        elif stripped:
            line = _proxy(stripped)
        out.append(line)
    return "\n".join(out)


async def _proxy_url(url: str, request: Request) -> Response:
    # Fetch without Range first — a Range header causes CDNs to return 206 partial
    # content for playlists, which truncates the m3u8 before we can rewrite it.
    forward_no_range = {k: v for k, v in request.headers.items()
                        if k.lower() in _FORWARD_REQUEST_HEADERS and k.lower() != "range"}
    client = httpx.AsyncClient()
    req = client.build_request("GET", url, headers=forward_no_range)
    upstream = await client.send(req, stream=True, follow_redirects=True)

    content_type = upstream.headers.get("content-type", "")
    if _is_hls(str(upstream.url), content_type):
        body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        proxy_base = str(request.base_url).rstrip("/")
        rewritten = _rewrite_m3u8(body.decode("utf-8", errors="replace"), str(upstream.url), proxy_base)
        rewritten_bytes = rewritten.encode("utf-8")
        return Response(
            content=rewritten_bytes,
            status_code=200,
            headers={
                "content-type": content_type or "application/vnd.apple.mpegurl",
                "content-length": str(len(rewritten_bytes)),
            },
        )

    # Not HLS — if the client sent a Range header, re-fetch with it so seeking works.
    if "range" in {k.lower() for k in request.headers}:
        await upstream.aclose()
        await client.aclose()
        client = httpx.AsyncClient()
        forward = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST_HEADERS}
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

    # FFmpeg/ffprobe identifies itself as "Lavf/X.X.X" (libavformat). These clients
    # follow redirects natively and probe HLS directly from the CDN without issues.
    # Sending them through the proxy chain breaks ffprobe's deep stream analysis.
    ua = request.headers.get("user-agent", "")
    if not settings.strm_proxy_streams or ua.startswith("Lavf/"):
        return RedirectResponse(url=url, status_code=302)

    return await _proxy_url(url, request)


def paged_response(result) -> dict:
    return {
        "data": result.items,
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }
