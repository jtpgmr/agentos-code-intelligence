"""
App Settings
============

Shared runtime objects for the platform.
"""

from dataclasses import dataclass
from functools import lru_cache

from agno.models.openai import OpenAILike, OpenAIResponses
from pydantic import (
    Field,
    SecretStr,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_SETTINGS_CONFIG = SettingsConfigDict(
    extra="ignore",
    case_sensitive=False,
    env_file=".env",
    env_nested_delimiter="__",
    env_ignore_empty=True,
)


class AIModelSettings(BaseSettings):
    model_config = SettingsConfigDict({**BASE_SETTINGS_CONFIG, "env_prefix": "AI__"})

    api_key: SecretStr
    provider: str = "OpenAI"
    model_name: str = "gpt-5.6-luna"
    base_url: str | None = None


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG)

    ai: AIModelSettings = Field(default_factory=AIModelSettings)  # type: ignore[arg-type]


@lru_cache
def getSettings() -> AppSettings:
    return AppSettings()


@dataclass
class ModelProps:
    id: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None


def default_model(
    settings: AIModelSettings | None = None, model_name: str | None = None
) -> OpenAILike | OpenAIResponses:
    ai_settings: AIModelSettings = settings or getSettings().ai

    kwargs = ModelProps(
        id=model_name or ai_settings.model_name,
        api_key=ai_settings.api_key.get_secret_value(),
        provider=ai_settings.provider,
        base_url=ai_settings.base_url,
    )

    if not kwargs.provider or kwargs.provider.lower() == "openai":
        return OpenAIResponses(
            **kwargs.__dict__,
        )

    return OpenAILike(
        **kwargs.__dict__,
    )
