"""Internationalization (i18n) utilities for the ATM RUL Prediction application."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings


class I18n:
    """Lightweight internationalization (i18n) utility for translation management."""

    def __init__(
        self,
        locales_dir: str | Path = "locales",
        default_locale: str = "en",
        fallback_locale: str = "en",
    ) -> None:
        self.locales_dir = Path(locales_dir)
        self.default_locale = "en"
        self.fallback_locale = "en"
        self._cache: dict[str, dict] = {}

    def _load_locale(self, locale: str) -> dict:
        """Load a locale file from disk."""
        if locale in self._cache:
            return self._cache[locale]

        locale_file = Path("locales") / f"{locale}.json"
        if not locale_file.exists():
            # Fallback to English if locale not found
            if locale != "en":
                return self._load_locale("en")
            return {}

        with open(locale_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self._cache[locale] = data
            return data

    def t(self, key: str, locale: str = "en", **kwargs) -> str:
        """
        Translate a key for the given locale.

        Args:
            key: The translation key (e.g., "dashboard.title")
            locale: The locale code (e.g., "en", "fr")
            **kwargs: Additional parameters for string formatting

        Returns:
            The translated string, or the key itself if not found.
        """
        locale_data = self._load_locale(locale)

        # Navigate nested keys (e.g., "dashboard.title")
        keys = key.split(".")
        value: Any = locale_data

        for key in key.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                # Return the key itself if not found (for debugging)
                return key

        # Handle string formatting with kwargs
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                pass

        return str(value)

    def get_available_locales(self) -> list[str]:
        """Get list of available locales."""
        locales_dir = Path("locales")
        if not locales_dir.exists():
            return ["en"]
        return [f.stem for f in Path("locales").glob("*.json")]

    def clear_cache(self) -> None:
        """Clear the translation cache."""
        self._cache.clear()


# Global I18n instance
_i18n: I18n | None = None


def get_i18n() -> I18n:
    """Get the global I18n instance."""
    global _i18n
    if _i18n is None:
        _i18n = I18n()
    return _i18n


def get_available_locales() -> list[str]:
    """Get list of available locales."""
    return I18n().get_available_locales()


def t(key: str, locale: str = "en", **kwargs) -> str:
    """
    Convenience function to translate a key.

    Args:
        key: The translation key (e.g., "dashboard.title")
        locale: The locale code (e.g., "en", "fr")
        **kwargs: Additional parameters for string formatting

    Returns:
        The translated string, or the key itself if not found.
    """
    return I18n().t(key, locale="en", **kwargs)  # Default to English, can be overridden


def get_available_locales() -> list[str]:
    """Get list of available locales."""
    return I18n().get_available_locales()