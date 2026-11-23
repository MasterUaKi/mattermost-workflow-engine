# Автор: Oleh Riabtsev
# Файл: app/config.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Модуль конфигурации приложения.
Отвечает за чтение переменных окружения (.env) и валидацию структуры файла workflows.yaml.
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StepType(str, Enum):
    """Тип выполнения этапа согласования."""
    SEQUENTIAL = "sequential"  # Последовательное согласование (один участник за раз)
    PARALLEL = "parallel"      # Параллельное согласование (все участники этапа одновременно)


class RejectBehavior(str, Enum):
    """Действие при отклонении документа на этапе."""
    RETURN_TO_INITIATOR = "return_to_initiator"


class WorkflowStepConfig(BaseModel):
    """Описание одного этапа маршрута согласования из workflows.yaml."""
    id: str = Field(..., min_length=1)
    name: dict[str, str]
    type: StepType
    approvers: list[str] = Field(..., min_length=1)
    on_reject: RejectBehavior = RejectBehavior.RETURN_TO_INITIATOR


class WorkflowDefinition(BaseModel):
    """Описание конкретного шаблона маршрута согласования."""
    name: dict[str, str]
    description: dict[str, str] | None = None
    default_lang: str | None = None
    steps: list[WorkflowStepConfig] = Field(..., min_length=1)


class WorkflowsConfig(BaseModel):
    """Корневая модель файла workflows.yaml."""
    default_lang: str = "de"
    workflows: dict[str, WorkflowDefinition]


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из переменных окружения."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Mattermost Document Approval Engine"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    MATTERMOST_URL: str = "http://localhost:8065"
    MATTERMOST_BOT_TOKEN: str
    MATTERMOST_WEBHOOK_SECRET: str | None = None

    DATABASE_URL: str = "sqlite+aiosqlite:///./workflow_engine.db"
    WORKFLOWS_CONFIG_PATH: str = "workflows.yaml"
    LOCALES_PATH: str = "locales.yaml"
    UPLOAD_DIR: str = "uploads"
    DEFAULT_LANG: str = "de"
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Возвращает кешированный экземпляр настроек окружения."""
    return Settings()


@lru_cache
def get_workflows_config() -> WorkflowsConfig:
    """Загружает и валидирует конфигурацию маршрутов из YAML-файла."""
    settings = get_settings()
    config_path = Path(settings.WORKFLOWS_CONFIG_PATH)
    if not config_path.exists():
        raise FileNotFoundError(f"Workflows config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw_data = yaml.safe_load(file) or {}

    return WorkflowsConfig.model_validate(raw_data)
