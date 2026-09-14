from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import close_pool
from app.scheduler import start_scheduler, stop_scheduler
from app.store import prediction_store
from app.auth_db import sync_institutions_from_oracle, init_auth_db
from app.auth import get_current_user_optional, get_current_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize auth database (creates DB if not exists, creates schema)
    try:
        init_auth_db()
    except Exception as e:
        logger.error("Failed to initialize auth database: %s", e)
    
    start_scheduler()
    # Sync institutions from Oracle on startup
    try:
        await sync_institutions_from_oracle()
    except Exception as e:
        logging.getLogger(__name__).warning("Institution sync failed: %s", e)
    logger.info("%s started", get_settings().app_name)
    yield
    stop_scheduler()
    close_pool()
    logger.info("Shutdown complete")


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)

# Session middleware for CSRF tokens and user session
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().jwt_secret_key,
    session_cookie="atm_session",
    max_age=60 * 60 * 24 * 30,  # 30 days
    same_site="lax",
    https_only=False,  # Set to True in production with HTTPS
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

from app.routers import predictions, auth as auth_router, i18n as i18n_router
from app.middleware import i18n as i18n_middleware

# Add i18n middleware for language detection
app.add_middleware(i18n_middleware.I18nMiddleware)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exc.status_code,
            "title": "Error",
            "detail": exc.detail
        },
        status_code=exc.status_code
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled global exception")
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
    
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": 500,
            "title": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later."
        },
        status_code=500
    )

app.include_router(predictions.router, prefix="/api", tags=["predictions"])
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(i18n_router.router, prefix="/i18n", tags=["i18n"])


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user=Depends(get_current_user_optional)):
    """Root redirects to dashboard if authenticated, otherwise to login."""
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/auth/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page_redirect():
    """Redirect /login to /auth/login for consistency."""
    return RedirectResponse(url="/auth/login", status_code=302)


@app.get("/register", response_class=HTMLResponse)
async def register_page_redirect():
    """Redirect /register to /auth/register for consistency."""
    return RedirectResponse(url="/auth/register", status_code=302)


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_redirect():
    """Redirect /forgot-password to /auth/forgot-password for consistency."""
    return RedirectResponse(url="/auth/forgot-password", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user=Depends(get_current_user_optional),
):
    """Protected dashboard page - requires authentication."""
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
        
    settings = get_settings()
    current_run = prediction_store.get_current_run()
    
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": "ATM Predictive Maintenance",
            "environment": "development",
            "lookback_days": 60,
            "daily_run_hour": 0,
            "daily_run_minute": 0,
            "current_run": current_run,
            "csrf_token": secrets.token_urlsafe(32),
            "is_global_user": current_user.institution_code == '0' if current_user.institution_code else False,
        },
    )




@app.get("/healthz")
async def healthz():
    return {"status": "ok"}