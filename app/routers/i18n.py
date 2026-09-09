"""API routes for i18n language switching."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/i18n", tags=["i18n"])


@router.post("/set-language")
async def set_language(lang: str, response: Response) -> dict:
    """Set the user's preferred language."""
    if lang not in ("en", "fr"):
        return {"error": "Unsupported language"}, 400

    response = Response(content='{"status": "ok"}')
    response.set_cookie(
        key="locale",
        value=lang,
        max_age=365 * 24 * 60 * 60,  # 1 year
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production with HTTPS
    )
    return {"status": "ok", "language": lang}


@router.get("/current-language")
async def get_current_language(request: Request) -> dict:
    """Get the current language from cookie or header."""
    locale = request.cookies.get("locale", "en")
    return {"language": locale}


@router.get("/available-languages")
async def get_available_languages() -> dict:
    """Get list of available languages."""
    return {
        "languages": [
            {"code": "en", "name": "English", "native": "English"},
            {"code": "fr", "name": "French", "native": "Français"},
        ]
    }