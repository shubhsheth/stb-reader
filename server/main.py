from contextlib import asynccontextmanager
from fastapi import FastAPI
from stb_reader import STBClient
from .config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    client = STBClient(
        base_url=settings.stb_portal_url,
        mac=settings.stb_mac,
        serial=settings.stb_serial,
        lang=settings.stb_lang,
        timezone=settings.stb_timezone,
    )
    client.authenticate()
    app.state.client = client
    yield


app = FastAPI(title="STB Reader", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


def _include_routers():
    from .routes.live_tv import router as live_tv_router
    from .routes.vod import router as vod_router
    app.include_router(live_tv_router)
    app.include_router(vod_router)


_include_routers()
