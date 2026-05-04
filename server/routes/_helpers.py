from collections.abc import Callable
from urllib.parse import urljoin, quote
import logging
import re

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask
from stb_reader.exceptions import NotFoundError, STBError, StreamError

logger = logging.getLogger(__name__)

_FORWARD_REQUEST_HEADERS = {"range", "accept-encoding", "user-agent"}
_KEEP_RESPONSE_HEADERS = {
    "content-type", "content-length", "content-range", "accept-ranges"
}
_HLS_MIME_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl"}
_URI_ATTR_RE = re.compile(r'URI="([^"]*)"')
_NON_HLS_URL_SUFFIXES = frozenset(
    [".ts", ".aac", ".mp4", ".m4s", ".m4a", ".m4v", ".key", ".webm"]
)
_CDN_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _is_hls(url: str, content_type: str) -> bool:
    mime = content_type.split(";")[0].strip().lower()
    return mime in _HLS_MIME_TYPES or url.split("?")[0].lower().endswith(".m3u8")


def _url_is_clearly_not_hls(url: str) -> bool:
    """True when the URL path ends in a known non-HLS extension (segment, key, etc.)."""
    path = url.split("?")[0].lower()
    return any(path.endswith(s) for s in _NON_HLS_URL_SUFFIXES)


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
    has_range = "range" in {k.lower() for k in request.headers}

    if not (has_range and _url_is_clearly_not_hls(url)):
        # Fetch without Range first to detect HLS.
        # A Range header causes CDNs to return 206 partial content for playlists,
        # truncating the m3u8 before we can rewrite it.
        # Always send accept-encoding: identity so CDN returns uncompressed bytes;
        # forwarding the client's accept-encoding and having httpx silently decompress
        # would cause us to send decompressed data with a gzip content-encoding header.
        headers = {k: v for k, v in request.headers.items()
                   if k.lower() in _FORWARD_REQUEST_HEADERS and k.lower() != "range"}
        headers["accept-encoding"] = "identity"
        logger.info("proxy fetch: %s", url)
        client = httpx.AsyncClient(timeout=_CDN_TIMEOUT)
        req = client.build_request("GET", url, headers=headers)
        upstream = await client.send(req, stream=True, follow_redirects=True)

        content_type = upstream.headers.get("content-type", "")
        logger.info("proxy upstream %s status=%d ct=%s", url, upstream.status_code, content_type)

        if upstream.status_code >= 400:
            snippet = (await upstream.aread())[:200]
            await upstream.aclose()
            await client.aclose()
            logger.warning("upstream error for %s: status=%d body=%r", url, upstream.status_code, snippet)
            raise HTTPException(
                status_code=502,
                detail=f"upstream returned {upstream.status_code}: {snippet.decode('utf-8', errors='replace')}",
            )

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

        if not has_range:
            keep = {k: v for k, v in upstream.headers.items() if k.lower() in _KEEP_RESPONSE_HEADERS}

            async def cleanup_probe():
                await upstream.aclose()
                await client.aclose()

            return StreamingResponse(
                upstream.aiter_bytes(chunk_size=65536),
                status_code=upstream.status_code,
                headers=keep,
                background=BackgroundTask(cleanup_probe),
            )

        # Not HLS but Range was requested — close the probe and re-fetch with Range.
        await upstream.aclose()
        await client.aclose()

    # Fetch with the client's Range header (either skipped probe or re-fetch after probe).
    headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST_HEADERS}
    headers["accept-encoding"] = "identity"
    logger.info("proxy fetch (range): %s", url)
    client = httpx.AsyncClient(timeout=_CDN_TIMEOUT)
    req = client.build_request("GET", url, headers=headers)
    upstream = await client.send(req, stream=True, follow_redirects=True)
    content_type = upstream.headers.get("content-type", "")
    logger.info("proxy upstream %s status=%d ct=%s", url, upstream.status_code, content_type)

    if upstream.status_code >= 400:
        snippet = (await upstream.aread())[:200]
        await upstream.aclose()
        await client.aclose()
        logger.warning("upstream error for %s: status=%d body=%r", url, upstream.status_code, snippet)
        raise HTTPException(
            status_code=502,
            detail=f"upstream returned {upstream.status_code}: {snippet.decode('utf-8', errors='replace')}",
        )

    keep = {k: v for k, v in upstream.headers.items() if k.lower() in _KEEP_RESPONSE_HEADERS}

    async def cleanup_range():
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_bytes(chunk_size=65536),
        status_code=upstream.status_code,
        headers=keep,
        background=BackgroundTask(cleanup_range),
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

    logger.info("stream: CDN url=%s proxy=%s", url, settings.strm_proxy_streams)

    if not settings.strm_proxy_streams:
        return RedirectResponse(url=url, status_code=302)

    return await _proxy_url(url, request)


def paged_response(result) -> dict:
    return {
        "data": result.items,
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }
