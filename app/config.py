# Author: Oleh Riabtsev
# File: app/config.py
# Created: 2026-11-23
# Version: 1.3.0

"""
Application configuration module.
Loads environment variables (.env) and validates workflow routing structures,
including conditional alternative rejection branches and custom field schemas.
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StepType(str, Enum):
    """Execution mode of an approval stage."""
    SEQUENTIAL = "sequential"  # Sequential approval (one approver at a time)
    PARALLEL = "parallel"      # Parallel approval (all stage approvers simultaneously)


class RejectBehavior(str, Enum):
    """Transition action when a document is rejected at a stage."""
    RETURN_TO_INITIATOR = "return_to_initiator"
    GOTO_STEP = "goto_step"


class CustomFieldType(str, Enum):
    """Supported data types for dynamic document fields."""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    URL = "url"


class CustomFieldDefinition(BaseModel):
    """Schema for a predefined or ad-hoc document metadata field."""
    name: str = Field(..., min_length=1, max_length=120)
    type: CustomFieldType = CustomFieldType.TEXT
    default_value: str | None = None
    required: bool = False


class WorkflowStepConfig(BaseModel):
    """Definition of a single approval step in a workflow template."""
    id: str = Field(..., min_length=1)
    name: dict[str, str]
    type: StepType = StepType.SEQUENTIAL
    approvers: list[str] = Field(..., min_length=1)
    is_alternative: bool = False
    on_reject: RejectBehavior = RejectBehavior.RETURN_TO_INITIATOR
    on_reject_step_id: str | None = None

    @model_validator(mode="after")
    def validate_rejection_target(self) -> "WorkflowStepConfig":
        """Prevents self-referencing rejection loops and ensures target step ID is provided."""
        if self.on_reject == RejectBehavior.GOTO_STEP:
            if not self.on_reject_step_id:
                raise ValueError("on_reject_step_id is required when on_reject is 'goto_step'")
            if self.on_reject_step_id == self.id:
                raise ValueError("A step cannot route rejection to itself")
        return self


class WorkflowDefinition(BaseModel):
    """Definition of a named approval workflow template."""
    name: dict[str, str]
    description: dict[str, str] | None = None
    default_lang: str | None = None
    steps: list[WorkflowStepConfig] = Field(..., min_length=1)
    default_fields: list[CustomFieldDefinition] = Field(default_factory=list)


class WorkflowsConfig(BaseModel):
    """Root schema for workflows.yaml."""
    default_lang: str = "en"
    workflows: dict[str, WorkflowDefinition]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Mattermost Document Approval Engine"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    STUDIO_PUBLIC_URL: str = "http://localhost:8000"
    MATTERMOST_URL: str = "http://localhost:8065"
    MATTERMOST_BOT_TOKEN: str
    MATTERMOST_WEBHOOK_SECRET: str | None = None
    ENABLE_BOT_WS_LISTENER: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./workflow_engine.db"
    AUTO_CREATE_TABLES: bool = False
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
    """Loads and validates initial workflow routing definitions from the YAML file."""
    settings = get_settings()
    config_path = Path(settings.WORKFLOWS_CONFIG_PATH)
    if not config_path.exists():
        raise FileNotFoundError(f"Workflows config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw_data = yaml.safe_load(file) or {}

    return WorkflowsConfig.model_validate(raw_data)
