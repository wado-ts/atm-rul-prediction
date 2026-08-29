from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import close_pool
from app.routers import predictions
from app.scheduler import start_scheduler, stop_scheduler
from app.store import prediction_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    logger.info("%s started", get_settings().app_name)
    yield
    stop_scheduler()
    close_pool()
    logger.info("Shutdown complete")


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(predictions.router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    settings = get_settings()
    current_run = prediction_store.get_current_run()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "environment": settings.environment,
            "lookback_days": settings.lookback_days,
            "daily_run_hour": settings.daily_run_hour,
            "daily_run_minute": settings.daily_run_minute,
            "current_run": current_run,
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
