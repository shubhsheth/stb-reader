from collections.abc import Callable
from urllib.parse import urljoin, quote, urlparse
import logging
import re
import gzip

import httpx
from cachetools import TTLCache
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask
from stb_reader.exceptions import NotFoundError, STBError, StreamError

logger = logging.getLogger(__name__)

# -----------------------------
# CONFIG / GLOBALS
# -----------------------------

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

client = httpx.AsyncClient(
    timeout=_CDN_TIMEOUT,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    http2=True,
)

playlist_cache = TTLCache(maxsize=1000, ttl=5)


# -----------------------------
# HELPERS
# -----------------------------

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
        if uri.startswith(proxy_base):
            return uri  # ✅ (3) avoid double proxying

        full = urljoin(base_url, uri)
        parsed = urlparse(full)

        # Extract filename (preserve extension!)
        filename = parsed.path.rsplit("/", 1)[-1] or "file"

        return f"{proxy_base}/proxy/{filename}?url={quote(full, safe=':/?&=%')}"

    out = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            line = _URI_ATTR_RE.sub(lambda m: f'URI="{_proxy(m.group(1))}"', line)
        elif stripped:
            line = _proxy(stripped)
        out.append(line)
    return "\n".join(out)


async def _fetch_with_retry(req, stream=True, retries=3):
    last_exc = None
    for attempt in range(retries):
        try:
            return await client.send(req, stream=stream, follow_redirects=True)
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning("retry %d failed: %s", attempt + 1, exc)
    raise last_exc


def _fix_content_type(url: str, content_type: str) -> str:
    if content_type:
        return content_type

    path = url.split("?")[0].lower()
    if path.endswith(".ts"):
        return "video/mp2t"
    if path.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if path.endswith(".mp4") or path.endswith(".m4s"):
        return "video/mp4"

    return "application/octet-stream"


# -----------------------------
# MAIN PROXY
# -----------------------------

async def _proxy_url(url: str, request: Request) -> Response:
    has_range = "range" in {k.lower() for k in request.headers}

    # -----------------------------
    # PROBE (no-range)
    # -----------------------------
    if not (has_range and _url_is_clearly_not_hls(url)):
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() in _FORWARD_REQUEST_HEADERS and k.lower() != "range"
        }
        headers["accept-encoding"] = "identity"

        logger.info("proxy fetch: %s", url)

        req = client.build_request("GET", url, headers=headers)

        try:
            upstream = await _fetch_with_retry(req)
        except httpx.HTTPError as exc:
            logger.warning("CDN error for %s: %s", url, exc)
            raise HTTPException(status_code=502, detail=f"CDN error: {exc}")

        content_type = upstream.headers.get("content-type", "")
        logger.info(
            "proxy: %s → %s (%d, %s)",
            url,
            upstream.url,
            upstream.status_code,
            content_type,
        )

        if upstream.status_code >= 400:
            snippet = (await upstream.aread())[:200]
            await upstream.aclose()
            raise HTTPException(
                status_code=502,
                detail=f"upstream returned {upstream.status_code}: {snippet.decode(errors='replace')}",
            )

        # -----------------------------
        # HLS PLAYLIST
        # -----------------------------
        if _is_hls(str(upstream.url), content_type):
            cache_key = str(upstream.url)

            if cache_key in playlist_cache:
                await upstream.aclose()
                return Response(
                    content=playlist_cache[cache_key],
                    media_type="application/vnd.apple.mpegurl",
                )

            raw = await upstream.aread()

            if upstream.headers.get("content-encoding") == "gzip":
                raw = gzip.decompress(raw)

            proxy_base = str(request.base_url).rstrip("/")
            rewritten = _rewrite_m3u8(
                raw.decode("utf-8", errors="replace"),
                str(upstream.url),
                proxy_base,
            )

            rewritten_bytes = rewritten.encode("utf-8")
            playlist_cache[cache_key] = rewritten_bytes

            await upstream.aclose()

            return Response(
                content=rewritten_bytes,
                status_code=200,
                headers={
                    "content-type": "application/vnd.apple.mpegurl",
                    "content-length": str(len(rewritten_bytes)),
                },
            )

        # -----------------------------
        # NON-HLS STREAM (no range)
        # -----------------------------
        if not has_range:
            keep = {
                k: v for k, v in upstream.headers.items()
                if k.lower() in _KEEP_RESPONSE_HEADERS
            }

            keep["content-type"] = _fix_content_type(url, keep.get("content-type"))

            async def cleanup():
                await upstream.aclose()

            return StreamingResponse(
                upstream.aiter_bytes(chunk_size=65536),
                status_code=upstream.status_code,
                headers=keep,
                background=BackgroundTask(cleanup),
            )

        await upstream.aclose()

    # -----------------------------
    # RANGE REQUEST (segments)
    # -----------------------------
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() in _FORWARD_REQUEST_HEADERS
    }
    headers["accept-encoding"] = "identity"

    logger.debug("segment request: %s range=%s", url, headers.get("range"))

    req = client.build_request("GET", url, headers=headers)

    try:
        upstream = await _fetch_with_retry(req)
    except httpx.HTTPError as exc:
        logger.warning("CDN error for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail=f"CDN error: {exc}")

    if upstream.status_code >= 400:
        snippet = (await upstream.aread())[:200]
        await upstream.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"upstream returned {upstream.status_code}: {snippet.decode(errors='replace')}",
        )

    keep = {
        k: v for k, v in upstream.headers.items()
        if k.lower() in _KEEP_RESPONSE_HEADERS
    }

    keep["content-type"] = _fix_content_type(url, keep.get("content-type"))

    async def cleanup():
        await upstream.aclose()

    return StreamingResponse(
        upstream.aiter_bytes(chunk_size=65536),
        status_code=upstream.status_code,
        headers=keep,
        background=BackgroundTask(cleanup),
    )


# -----------------------------
# EXISTING FUNCTIONS (unchanged)
# -----------------------------

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

    if urlparse(url).scheme not in ("http", "https"):
        logger.warning("stream: non-HTTP scheme in %s, redirecting", url)
        return RedirectResponse(url=url, status_code=302)

    return await _proxy_url(url, request)


def paged_response(result) -> dict:
    return {
        "data": result.items,
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }