from __future__ import annotations

import re
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response

from ._helpers import stream_response

router = APIRouter(tags=["xtream"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_auth(username: str, password: str, settings) -> None:
    if username != settings.xtream_username or password != settings.xtream_password:
        raise HTTPException(status_code=403, detail="Invalid credentials")


def _collect_all_pages(fn, max_pages: int = 0, **kwargs) -> list:
    items, page = [], 1
    while True:
        result = fn(**kwargs, page=page)
        items.extend(result.items)
        if not result.items or page * result.per_page >= result.total:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
    return items


def _safe_rating_5(rating: str) -> float:
    try:
        return float(rating) / 2 if rating else 0.0
    except ValueError:
        return 0.0


def _login_response(settings, request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    now = int(time.time())
    return {
        "user_info": {
            "username": settings.xtream_username,
            "password": settings.xtream_password,
            "message": "",
            "auth": 1,
            "status": "Active",
            "exp_date": None,
            "is_trial": "0",
            "active_cons": "0",
            "created_at": "0",
            "max_connections": "1",
            "allowed_output_formats": ["m3u8", "ts", "rtmp"],
        },
        "server_info": {
            "url": base,
            "port": str(request.url.port or 80),
            "https_port": "443",
            "server_protocol": request.url.scheme,
            "rtmp_port": "1935",
            "timezone": settings.stb_timezone,
            "timestamp_now": now,
            "time_now": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "process": True,
        },
    }


def _category_list(categories) -> list[dict]:
    return [
        {"category_id": c.id, "category_name": c.title, "parent_id": 0}
        for c in categories
    ]


# ---------------------------------------------------------------------------
# Player API — dispatcher
# ---------------------------------------------------------------------------

@router.get("/player_api.php")
@router.post("/player_api.php")
def player_api(
    request: Request,
    username: str = Query(...),
    password: str = Query(...),
    action: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    vod_id: str | None = Query(default=None),
    series_id: str | None = Query(default=None),
):
    settings = request.app.state.settings
    client = request.app.state.client

    _check_auth(username, password, settings)
    max_pages = settings.xtream_max_pages

    if action is None:
        return _login_response(settings, request)

    # --- Live TV ---
    if action == "get_live_categories":
        return _category_list(client.live_tv.get_genres())

    if action == "get_live_streams":
        genre = category_id or "*"
        channels = _collect_all_pages(client.live_tv.get_channels, max_pages=max_pages, genre_id=genre)
        return [
            {
                "num": i + 1,
                "name": ch.name,
                "stream_type": "live",
                "stream_id": int(ch.id),
                "stream_icon": ch.logo,
                "epg_channel_id": "",
                "added": "0",
                "category_id": ch.genre_id,
                "custom_sid": "",
                "tv_archive": 0,
                "direct_source": "",
                "tv_archive_duration": 0,
            }
            for i, ch in enumerate(channels)
        ]

    # --- VOD ---
    if action == "get_vod_categories":
        return _category_list(client.vod.get_categories())

    if action == "get_vod_streams":
        cat = category_id or "*"
        content = _collect_all_pages(client.vod.get_content, max_pages=max_pages, category_id=cat)
        movies = [c for c in content if not c.is_series]
        return [
            {
                "num": i + 1,
                "name": c.name,
                "stream_type": "movie",
                "stream_id": int(c.id),
                "stream_icon": c.screenshot_uri,
                "rating": c.rating,
                "rating_5based": _safe_rating_5(c.rating),
                "added": "0",
                "category_id": "",
                "container_extension": "mp4",
                "custom_sid": "",
                "direct_source": "",
            }
            for i, c in enumerate(movies)
        ]

    if action == "get_vod_info":
        if not vod_id:
            return {}
        all_content = _collect_all_pages(client.vod.get_content, max_pages=max_pages, category_id="*")
        for c in all_content:
            if c.id == str(vod_id) and not c.is_series:
                return {
                    "info": {
                        "name": c.name,
                        "cover_big": c.screenshot_uri,
                        "movie_image": c.screenshot_uri,
                        "releasedate": c.year,
                        "episode_run_time": c.duration,
                        "description": c.description,
                        "plot": c.description,
                        "genre": c.genres,
                        "rating": c.rating,
                        "duration_secs": 0,
                        "duration": c.duration,
                    },
                    "movie_data": {
                        "stream_id": int(c.id),
                        "name": c.name,
                        "added": "0",
                        "category_id": "",
                        "container_extension": "mp4",
                        "custom_sid": "",
                        "direct_source": "",
                    },
                }
        return {}

    # --- Series ---
    if action == "get_series_categories":
        return _category_list(client.vod.get_categories())

    if action == "get_series":
        cat = category_id or "*"
        content = _collect_all_pages(client.vod.get_content, max_pages=max_pages, category_id=cat)
        series = [c for c in content if c.is_series]
        return [
            {
                "num": i + 1,
                "name": c.name,
                "series_id": int(c.id),
                "cover": c.screenshot_uri,
                "plot": c.description,
                "cast": "",
                "director": "",
                "genre": c.genres,
                "releaseDate": c.year,
                "last_modified": "0",
                "rating": c.rating,
                "rating_5based": _safe_rating_5(c.rating),
                "backdrop_path": [],
                "youtube_trailer": "",
                "episode_run_time": "",
                "category_id": "",
            }
            for i, c in enumerate(series)
        ]

    if action == "get_series_info":
        if not series_id:
            return {}
        seasons = client.vod.get_seasons(str(series_id))

        episodes_dict: dict[str, list] = {}
        seasons_list = []

        for i, season in enumerate(seasons):
            m = re.search(r"\d+", season.name)
            season_num_str = m.group() if m else str(i + 1)
            season_num_int = int(season_num_str)

            episodes = client.vod.get_episodes(str(series_id), season.id)
            ep_list = [
                {
                    "id": ep.id,
                    "episode_num": int(ep.series_number) if ep.series_number.isdigit() else j + 1,
                    "title": ep.name,
                    "container_extension": "mp4",
                    "info": {
                        "duration_secs": 0,
                        "duration": "",
                        "movie_image": "",
                        "plot": "",
                        "releaseDate": "",
                    },
                    "custom_sid": "",
                    "added": "0",
                    "season": season_num_int,
                    "direct_source": "",
                }
                for j, ep in enumerate(episodes)
            ]
            episodes_dict[season_num_str] = ep_list
            seasons_list.append(
                {
                    "air_date": "",
                    "episode_count": len(episodes),
                    "id": season_num_int,
                    "name": season.name,
                    "overview": "",
                    "season_number": season_num_int,
                    "cover": "",
                    "cover_big": "",
                }
            )

        # Find series metadata
        all_content = _collect_all_pages(client.vod.get_content, max_pages=max_pages, category_id="*")
        series_meta = next((c for c in all_content if c.id == str(series_id) and c.is_series), None)

        info = {
            "name": series_meta.name if series_meta else "",
            "cover": series_meta.screenshot_uri if series_meta else "",
            "plot": series_meta.description if series_meta else "",
            "cast": "",
            "director": "",
            "genre": series_meta.genres if series_meta else "",
            "releaseDate": series_meta.year if series_meta else "",
            "last_modified": "0",
            "rating": series_meta.rating if series_meta else "",
            "rating_5based": _safe_rating_5(series_meta.rating if series_meta else ""),
            "backdrop_path": [],
            "youtube_trailer": "",
            "episode_run_time": "",
            "category_id": "",
        }

        return {"info": info, "episodes": episodes_dict, "seasons": seasons_list}

    # Unknown action
    return []


# ---------------------------------------------------------------------------
# Stream URL routes — specific prefixes BEFORE catch-all
# ---------------------------------------------------------------------------

@router.get("/movie/{username}/{password}/{vod_id}.{ext}")
async def vod_stream(
    request: Request,
    username: str,
    password: str,
    vod_id: int,
    ext: str,
) -> Response:
    settings = request.app.state.settings
    client = request.app.state.client
    _check_auth(username, password, settings)
    return await stream_response(
        settings, request, client.vod.get_stream_url_by_content_id, str(vod_id)
    )


@router.get("/series/{username}/{password}/{episode_id}.{ext}")
async def series_stream(
    request: Request,
    username: str,
    password: str,
    episode_id: int,
    ext: str,
) -> Response:
    settings = request.app.state.settings
    client = request.app.state.client
    _check_auth(username, password, settings)
    return await stream_response(
        settings, request, client.vod.get_stream_url_by_content_id, str(episode_id)
    )


@router.get("/{username}/{password}/{stream_id}")
@router.get("/{username}/{password}/{stream_id}.{ext}")
async def live_stream(
    request: Request,
    username: str,
    password: str,
    stream_id: int,
    ext: str = "m3u8",
) -> Response:
    settings = request.app.state.settings
    client = request.app.state.client
    _check_auth(username, password, settings)
    return await stream_response(
        settings, request, client.live_tv.get_stream_url_by_id, str(stream_id)
    )


# ---------------------------------------------------------------------------
# M3U playlist
# ---------------------------------------------------------------------------

@router.get("/get.php")
def m3u_playlist(
    request: Request,
    username: str = Query(...),
    password: str = Query(...),
    type: str = Query(default="m3u_plus"),
    output: str = Query(default="ts"),
) -> PlainTextResponse:
    settings = request.app.state.settings
    client = request.app.state.client
    _check_auth(username, password, settings)

    genres = {g.id: g.title for g in client.live_tv.get_genres()}
    channels = _collect_all_pages(client.live_tv.get_channels, max_pages=settings.xtream_max_pages)
    base = str(request.base_url).rstrip("/")

    lines = ["#EXTM3U"]
    for ch in channels:
        genre_name = genres.get(ch.genre_id, "")
        lines.append(
            f'#EXTINF:-1 tvg-id="" tvg-name="{ch.name}" tvg-logo="{ch.logo}" '
            f'group-title="{genre_name}",{ch.name}'
        )
        lines.append(f"{base}/{username}/{password}/{ch.id}.m3u8")

    return PlainTextResponse("\n".join(lines))


# ---------------------------------------------------------------------------
# XMLTV stub
# ---------------------------------------------------------------------------

@router.get("/xmltv.php")
def xmltv(
    request: Request,
    username: str = Query(...),
    password: str = Query(...),
) -> Response:
    settings = request.app.state.settings
    _check_auth(username, password, settings)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE tv SYSTEM "xmltv.dtd">'
        '<tv generator-info-name="stb-reader"></tv>'
    )
    return Response(content=content, media_type="application/xml")
