"""
App Settings
============

Shared runtime objects for the platform.
"""

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from agno.models.openai import OpenAILike, OpenAIResponses
from agno.models.openrouter import OpenRouterResponses
from pydantic import (
    DirectoryPath,
    Field,
    SecretStr,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_SETTINGS_CONFIG = SettingsConfigDict(
    extra="ignore",
    case_sensitive=False,
    env_file=".env",
    env_ignore_empty=True,
)


class AISettings(BaseSettings):
    model_config = SettingsConfigDict({**BASE_SETTINGS_CONFIG, "env_prefix": "AI_"})

    api_key: SecretStr
    provider: str = "OpenAI"
    model_name: str = "gpt-5.6-luna"
    base_url: str | None = None


class SlackSettings(BaseSettings):
    model_config = SettingsConfigDict({**BASE_SETTINGS_CONFIG, "env_prefix": "SLACK_"})

    bot_token: SecretStr
    signing_secret: SecretStr


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG)

    runtime_env: str = "prd"
    codebase_dir: DirectoryPath = Path(__file__).resolve().parent.parent

    # Used by the scheduler and the OAuth server when MCP OAuth is enabled.
    agentos_url: str = "http://127.0.0.1:8000"

    ai: AISettings = Field(default_factory=AISettings)  # type: ignore[arg-type]
    slack: SlackSettings = Field(default_factory=SlackSettings)  # type: ignore[arg-type]


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


class ProviderClasses(Enum):
    openai = OpenAIResponses
    openrouter = OpenRouterResponses


@dataclass
class ModelProps:
    id: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None


def default_model(settings: AISettings | None = None, model_name: str | None = None) -> OpenAILike | OpenAIResponses:
    ai_settings: AISettings = settings or get_settings().ai

    kwargs = ModelProps(
        id=model_name or ai_settings.model_name,
        api_key=ai_settings.api_key.get_secret_value(),
        provider=ai_settings.provider,
        base_url=ai_settings.base_url,
    )

    model_provider = kwargs.provider.lower() if kwargs.provider else "openai"

    response_class = (
        ProviderClasses[model_provider].value if model_provider in ProviderClasses.__members__ else OpenAILike
    )

    return response_class(
        **kwargs.__dict__,
        store=False,  # Disable stateful features by default
    )
