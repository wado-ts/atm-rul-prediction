from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
import secrets
import hmac

from fastapi import APIRouter, Depends, Form, Request, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import UniqueViolation

from app.auth import (
    AUTH_COOKIE_NAME,
    create_access_token,
    hash_password,
    verify_password,
    get_current_user_optional,
    get_current_user,
)
from app.auth_db import (
    User,
    create_password_reset_token,
    create_user,
    get_user_by_email,
    get_institutions,
    reset_password_with_token,
    user_count,
)
from app.config import get_settings
from app.email import send_password_reset_email, smtp_is_configured

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


def _auth_context(request: Request, error: str | None = None, notice: str | None = None, institutions: list = None) -> dict:
    settings = get_settings()
    return {
        "request": request,
        "app_name": settings.app_name,
        "error": error,
        "notice": notice,
        "institutions": institutions or [],
        "csrf_token": request.session.get("csrf_token", secrets.token_urlsafe(32)),
    }


def _auth_response(user: User) -> RedirectResponse:
    """Create auth response with access token cookie."""
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        "atm_rul_token",
        create_access_token(user),
        httponly=True,
        samesite="lax",
        max_age=60 * 60,  # 1 hour
    )
    return response



@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Display login page with CSRF token."""
    # Generate new CSRF token for login form
    csrf_token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = csrf_token
    
    return templates.TemplateResponse(
        request,
        "auth.html",
        {
            "request": request,
            "error": None,
            "csrf_token": csrf_token,
            "app_name": get_settings().app_name,
        }
    )


@router.post("/login", response_model=None)
async def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse | HTMLResponse:
    """Handle login with CSRF protection."""
    
    # Verify CSRF token
    if not hmac.compare_digest(csrf_token, request.session.get("csrf_token", "")):
        return templates.TemplateResponse(
            request,
            "auth.html",
            {
                "request": request,
                "error": "Invalid CSRF token. Please refresh the page and try again.",
                "csrf_token": request.session.get("csrf_token", ""),
                "app_name": get_settings().app_name,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    user = get_user_by_email(email)
    if user is None or not verify_password(password, user.password_hash):
        # Regenerate CSRF token for retry
        new_csrf = secrets.token_urlsafe(32)
        request.session["csrf_token"] = new_csrf
        return templates.TemplateResponse(
            request,
            "auth.html",
            {
                "request": request,
                "error": "Invalid email or password",
                "csrf_token": new_csrf,
                "app_name": get_settings().app_name,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    
    # Regenerate CSRF token for authenticated session
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        "atm_rul_token",
        create_access_token(user),
        httponly=True,
        samesite="lax",
        max_age=60 * 60,  # 1 hour
    )
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    """Registration page."""
    csrf_token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = csrf_token
    institutions = get_institutions()
    # Convert to list of tuples (hashable) for Jinja2 compatibility
    institutions_tuples = [(inst.code, inst.name, inst.is_global) for inst in institutions]
    
    return templates.TemplateResponse(
        request,
        "auth.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "app_name": get_settings().app_name,
            "institutions": institutions_tuples,
        }
    )


@router.post("/register", response_model=None)
async def register(
    request: Request,
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    institution_code: Annotated[str | None, Form()] = None,
) -> RedirectResponse | HTMLResponse:
    """Register new user with CSRF protection."""
    # Convert institutions to tuples (hashable) for Jinja2 compatibility
    institutions_tuples = [(inst.code, inst.name, inst.is_global) for inst in get_institutions()]
    
    # Verify CSRF token
    if not hmac.compare_digest(csrf_token, request.session.get("csrf_token", "")):
        return templates.TemplateResponse(
            request,
            "auth.html",
            {
                "request": request,
                "error": "Invalid CSRF token. Please refresh and try again.",
                "csrf_token": request.session.get("csrf_token", ""),
                "app_name": get_settings().app_name,
                "institutions": institutions_tuples,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "auth.html",
            {"request": request, "error": "Password must be at least 8 characters.", "csrf_token": request.session.get("csrf_token", ""), "app_name": get_settings().app_name, "institutions": institutions_tuples},
            status_code=400,
        )
    
    # Generate new CSRF token for next request
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    
    try:
        user = create_user(
            email, 
            hash_password(password), 
            first_name=first_name,
            last_name=last_name,
            institution_code=institution_code if institution_code else None
        )
    except UniqueViolation:
        return templates.TemplateResponse(
            request,
            "auth.html",
            {"request": request, "error": "Email already registered.", "csrf_token": request.session.get("csrf_token", ""), "app_name": get_settings().app_name, "institutions": institutions_tuples},
            status_code=400,
        )
    
    return _auth_response(user)


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request) -> HTMLResponse:
    """Forgot password page."""
    csrf_token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = csrf_token
    
    return templates.TemplateResponse(
        request,
        "auth.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "app_name": get_settings().app_name,
            "notice": None,
        }
    )


@router.post("/forgot-password", response_model=None)
async def forgot_password(
    request: Request,
    email: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse:
    """Handle forgot password request."""
    # Verify CSRF token
    if not hmac.compare_digest(csrf_token, request.session.get("csrf_token", "")):
        return templates.TemplateResponse(
            request,
            "auth.html",
            {
                "request": request,
                "error": "Invalid CSRF token. Please refresh and try again.",
                "csrf_token": request.session.get("csrf_token", ""),
                "app_name": get_settings().app_name,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    # Always return the same response to avoid revealing whether an account exists.
    user = get_user_by_email(email)
    reset_url = None
    if user is not None:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=get_settings().password_reset_expiration_minutes
        )
        create_password_reset_token(user.id, token, expires_at)
        reset_url = f"{get_settings().password_reset_base_url.rstrip('/')}/auth/reset-password?token={token}"
        if smtp_is_configured():
            try:
                await send_password_reset_email(email, reset_url)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Password reset email delivery failed")
        elif get_settings().environment.lower() != "production":
            import logging
            logging.getLogger(__name__).info("Password reset link generated for local testing: %s", reset_url)

        if get_settings().environment.lower() == "production":
            reset_url = None

    new_csrf = secrets.token_urlsafe(32)
    request.session["csrf_token"] = new_csrf

    return templates.TemplateResponse(
        request,
        "auth.html",
        {
            "request": request,
            "csrf_token": new_csrf,
            "app_name": get_settings().app_name,
            "notice": "If an account exists with this email, you will receive password reset instructions.",
            "reset_url": reset_url,
        },
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str) -> HTMLResponse:
    csrf_token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse(
        request,
        "auth.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "app_name": get_settings().app_name,
            "reset_token": token,
            "reset_view": True,
        },
    )


@router.post("/reset-password", response_model=None)
async def reset_password(
    request: Request,
    token: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse | HTMLResponse:
    if not hmac.compare_digest(csrf_token, request.session.get("csrf_token", "")):
        return templates.TemplateResponse(
            request,
            "auth.html",
            {"request": request, "error": "Invalid CSRF token. Please refresh and try again.", "csrf_token": request.session.get("csrf_token", ""), "app_name": get_settings().app_name, "reset_view": True, "reset_token": token},
            status_code=400,
        )
    if len(password) < 8 or password != confirm_password:
        return templates.TemplateResponse(
            request,
            "auth.html",
            {"request": request, "error": "Password must be at least 8 characters and match confirmation.", "csrf_token": request.session.get("csrf_token", ""), "app_name": get_settings().app_name, "reset_view": True, "reset_token": token},
            status_code=400,
        )
    if not reset_password_with_token(token, hash_password(password)):
        return templates.TemplateResponse(
            request,
            "auth.html",
            {"request": request, "error": "This reset link is invalid or expired.", "csrf_token": request.session.get("csrf_token", ""), "app_name": get_settings().app_name, "reset_view": True, "reset_token": token},
            status_code=400,
        )
    return RedirectResponse("/auth/login?reset=success", status_code=303)


@router.post("/logout")
async def logout(response: Response) -> RedirectResponse:
    """Logout - clear session and cookies."""
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie("atm_rul_token")
    response.delete_cookie("session")
    return response