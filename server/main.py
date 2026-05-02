import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from stb_reader import STBClient
from .config import Settings
from .db import init_db
from .sync import sync_all


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

    from .routes.live_tv import router as live_tv_router
    from .routes.vod import router as vod_router
    from .routes.library import router as library_router
    app.include_router(live_tv_router)
    app.include_router(vod_router)
    app.include_router(library_router)

    task = None
    if settings.strm_sync_interval_hours > 0:
        async def _sync_loop():
            while True:
                await asyncio.sleep(settings.strm_sync_interval_hours * 3600)
                await asyncio.to_thread(
                    sync_all, db, app.state.client.vod,
                    settings.strm_output_dir, settings.strm_server_base_url,
                )
        task = asyncio.create_task(_sync_loop())

    yield

    if task:
        task.cancel()


app = FastAPI(title="STB Reader", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
