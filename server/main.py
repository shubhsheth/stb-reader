import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from stb_reader import STBClient

from .config import Settings
from .db import count_vod_content, init_db
from .sync import run_library_sync
from .vod_sync import run_portal_sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    client = STBClient(
        base_url=settings.stb_portal_url,
        mac=settings.stb_mac,
        serial=settings.stb_serial,
        lang=settings.stb_lang,
        timezone=settings.stb_timezone,
        portal_path=settings.stb_portal_path,
    )
    client.authenticate()
    app.state.client = client

    db = init_db(str(Path(settings.strm_data_dir) / "data.db"))
    app.state.db = db
    app.state.settings = settings

    db_lock = threading.Lock()
    app.state.db_lock = db_lock

    from .routes.live_tv import router as live_tv_router
    from .routes.vod import router as vod_router
    from .routes.library import router as library_router
    from .routes.proxy import router as proxy_router
    app.include_router(live_tv_router)
    app.include_router(vod_router)
    app.include_router(library_router)
    app.include_router(proxy_router)
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")

    tasks = []

    async def _run_portal_sync():
        await asyncio.to_thread(
            run_portal_sync,
            db, db_lock, client.vod,
            settings.strm_output_dir,
            settings.vod_sync_request_delay_ms,
            settings.vod_sync_max_pages,
            settings.vod_sync_early_stop_pages,
            settings.vod_sync_full_sync_days,
        )

    async def _run_library_sync():
        await asyncio.to_thread(
            run_library_sync,
            db, client.vod,
            settings.strm_output_dir,
            settings.strm_server_base_url,
            settings.vod_sync_request_delay_ms / 1000,
        )

    if count_vod_content(db) == 0:
        tasks.append(asyncio.create_task(_run_portal_sync()))

    if settings.vod_sync_interval_hours > 0:
        async def _sync_loop():
            while True:
                await asyncio.sleep(settings.vod_sync_interval_hours * 3600)
                await _run_portal_sync()
                await _run_library_sync()

        tasks.append(asyncio.create_task(_sync_loop()))

    yield

    for task in tasks:
        task.cancel()


app = FastAPI(title="STB Reader", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}
