"""Language detection and i18n middleware for FastAPI."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class I18nMiddleware(BaseHTTPMiddleware):
    """Middleware for language detection and injection."""

    def __init__(self, app):
        super().__init__(app)
        self.supported_locales = {"en", "fr"}
        self.default_locale = "en"
        self.cookie_name = "locale"
        self.cookie_max_age = 60 * 60 * 24 * 365  # 1 year

    async def dispatch(self, request, call_next):
        # Determine locale from request
        locale = self._get_locale_from_request(request)
        
        # Store locale in request state for use in templates and route handlers
        request.state.locale = locale

        # Process request
        response = await call_next(request)

        # Always update locale cookie to match current locale
        response.set_cookie(
            key="locale",
            value=locale,
            max_age=365 * 24 * 60 * 60,  # 1 year
            httponly=False,  # Allow JavaScript to read the cookie
            samesite="lax",
            secure=False,  # Set to True in production with HTTPS
        )

        return response

    def _get_locale_from_request(self, request) -> str:
        """Determine the locale from request."""
        # 1. Check query parameter
        locale = request.query_params.get("lang")
        if locale in ("en", "fr"):
            return locale

        # Check cookie
        locale = request.cookies.get("locale")
        if locale in ("en", "fr"):
            return locale

        # Check Accept-Language header
        accept_language = request.headers.get("accept-language", "")
        for lang in accept_language.split(","):
            lang = lang.split(";")[0].strip().lower()
            if lang in ("en", "fr"):
                return lang

        # Default to French
        return "fr"