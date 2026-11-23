# Author: Oleh Riabtsev
# File: app/config.py
# Created: 2026-11-23
# Version: 1.1.0

"""
Application configuration module.
Loads environment variables (.env) and validates the workflows.yaml routing structure.
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StepType(str, Enum):
    """Execution mode of an approval stage."""
    SEQUENTIAL = "sequential"  # Sequential approval (one approver at a time)
    PARALLEL = "parallel"      # Parallel approval (all stage approvers simultaneously)


class RejectBehavior(str, Enum):
    """Transition action when a document is rejected at a stage."""
    RETURN_TO_INITIATOR = "return_to_initiator"


class WorkflowStepConfig(BaseModel):
    """Definition of a single approval step in workflows.yaml."""
    id: str = Field(..., min_length=1)
    name: dict[str, str]
    type: StepType
    approvers: list[str] = Field(..., min_length=1)
    on_reject: RejectBehavior = RejectBehavior.RETURN_TO_INITIATOR


class WorkflowDefinition(BaseModel):
    """Definition of a named approval workflow template."""
    name: dict[str, str]
    description: dict[str, str] | None = None
    default_lang: str | None = None
    steps: list[WorkflowStepConfig] = Field(..., min_length=1)


class WorkflowsConfig(BaseModel):
    """Root schema for workflows.yaml."""
    default_lang: str = "en"
    workflows: dict[str, WorkflowDefinition]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
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
    DEFAULT_LANG: str = "en"
    CONSOLE_LANG: str = "en"
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Returns a cached instance of environment settings."""
    return Settings()


@lru_cache
def get_workflows_config() -> WorkflowsConfig:
    """Loads and validates workflow routing definitions from the YAML file."""
    settings = get_settings()
    config_path = Path(settings.WORKFLOWS_CONFIG_PATH)
    if not config_path.exists():
        raise FileNotFoundError(f"Workflows config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw_data = yaml.safe_load(file) or {}

    return WorkflowsConfig.model_validate(raw_data)
