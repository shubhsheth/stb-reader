import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from stb_reader import STBClient
from .config import Settings


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
    from .routes.live_tv import router as live_tv_router
    from .routes.vod import router as vod_router
    app.include_router(live_tv_router)
    app.include_router(vod_router)
    yield


app = FastAPI(title="STB Reader", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
