# Автор: Oleh Riabtsev
# Файл: app/i18n.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Модуль интернационализации (i18n) для поддержки немецкого (de) и английского (en) языков
в сообщениях Mattermost, ответах REST API и системных логах.
"""

from pathlib import Path
from typing import Any
import yaml


SUPPORTED_LANGUAGES = {"de", "en"}


class Translator:
    """Класс для загрузки словаря переводов и форматирования локализованных строк."""

    def __init__(self, locales_path: str, default_lang: str = "de") -> None:
        self.default_lang = default_lang if default_lang in SUPPORTED_LANGUAGES else "de"
        self._translations: dict[str, Any] = self._load_locales(locales_path)

    @staticmethod
    def _load_locales(locales_path: str) -> dict[str, Any]:
        """Загружает YAML-файл с переводами с диска."""
        path = Path(locales_path)
        if not path.exists():
            raise FileNotFoundError(f"Locales file not found: {locales_path}")
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return data

    def normalize_lang(self, lang: str | None) -> str:
        """Возвращает валидный код языка или язык по умолчанию."""
        if lang and lang.lower() in SUPPORTED_LANGUAGES:
            return lang.lower()
        return self.default_lang

    def t(self, key: str, lang: str | None = None, **kwargs: Any) -> str:
        """
        Извлекает строку по составному ключу (например, 'card.btn_approve')
        и подставляет именованные аргументы.
        """
        target_lang = self.normalize_lang(lang)
        value = self._resolve_key(target_lang, key)

        # Резервный поиск на языке по умолчанию и английском
        if value is None and target_lang != self.default_lang:
            value = self._resolve_key(self.default_lang, key)
        if value is None and target_lang != "en":
            value = self._resolve_key("en", key)
        if value is None:
            return key

        if kwargs:
            return str(value).format(**kwargs)
        return str(value)

    def get_localized_dict_value(self, mapping: dict[str, str] | None, lang: str | None = None) -> str:
        """Извлекает локализованное значение из словаря конфигурационного файла workflows.yaml."""
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
        """Проходит по вложенным ключам словаря переводов."""
        node: Any = self._translations.get(lang, {})
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return None
        return node
