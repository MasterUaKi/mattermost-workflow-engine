# Author: Oleh Riabtsev
# File: app/i18n.py
# Created: 2026-11-23
# Version: 1.1.0

"""
Internationalization (i18n) module supporting:
- UI & REST API languages: English (en) and German (de), defaulting to English.
- Console & system log languages: English (en), German (de), and Russian (ru), configurable via CONSOLE_LANG.
"""

from pathlib import Path
from typing import Any
import yaml


UI_SUPPORTED_LANGUAGES = {"en", "de"}
CONSOLE_SUPPORTED_LANGUAGES = {"en", "de", "ru"}


class Translator:
    """Loads translation dictionaries and formats localized UI, API, and console log strings."""

    def __init__(
        self,
        locales_path: str,
        default_lang: str = "en",
        console_lang: str = "en",
    ) -> None:
        self.default_lang = default_lang.lower() if default_lang.lower() in UI_SUPPORTED_LANGUAGES else "en"
        self.console_lang = (
            console_lang.lower() if console_lang.lower() in CONSOLE_SUPPORTED_LANGUAGES else "en"
        )
        self._translations: dict[str, Any] = self._load_locales(locales_path)

    @staticmethod
    def _load_locales(locales_path: str) -> dict[str, Any]:
        """Loads the YAML translation dictionary from disk."""
        path = Path(locales_path)
        if not path.exists():
            raise FileNotFoundError(f"Locales file not found: {locales_path}")
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return data

    def normalize_lang(self, lang: str | None) -> str:
        """Returns a valid UI/API language code or falls back to the default language (en)."""
        if lang and lang.lower() in UI_SUPPORTED_LANGUAGES:
            return lang.lower()
        return self.default_lang

    def t(self, key: str, lang: str | None = None, **kwargs: Any) -> str:
        """
        Resolves a dot-separated UI/API translation key (e.g. 'card.btn_approve')
        and formats it with keyword arguments.
        """
        target_lang = self.normalize_lang(lang)
        value = self._resolve_key(target_lang, key)

        if value is None and target_lang != self.default_lang:
            value = self._resolve_key(self.default_lang, key)
        if value is None and target_lang != "en":
            value = self._resolve_key("en", key)
        if value is None:
            return key

        if kwargs:
            return str(value).format(**kwargs)
        return str(value)

    def t_log(self, key: str, **kwargs: Any) -> str:
        """
        Resolves a console/system log message using the configured CONSOLE_LANG (en | de | ru),
        falling back to English if missing.
        """
        full_key = key if key.startswith("logs.") else f"logs.{key}"
        value = self._resolve_key(self.console_lang, full_key)

        if value is None and self.console_lang != "en":
            value = self._resolve_key("en", full_key)
        if value is None:
            return full_key

        if kwargs:
            return str(value).format(**kwargs)
        return str(value)

    def get_localized_dict_value(self, mapping: dict[str, str] | None, lang: str | None = None) -> str:
        """Extracts a localized value from a dictionary inside workflows.yaml."""
        if not mapping:
            return ""
        target_lang = self.normalize_lang(lang)
        return (
            mapping.get(target_lang)
            or mapping.get(self.default_lang)
            or mapping.get("en")
            or next(iter(mapping.values()), "")
        )

    def _resolve_key(self, lang: str, key: str) -> Any:
        """Traverses nested keys in the translation dictionary."""
        node: Any = self._translations.get(lang, {})
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return None
        return node
