"""
App Settings
============

Shared runtime objects for the platform.
"""

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from agno.models.openai import OpenAILike, OpenAIResponses
from agno.models.openrouter import OpenRouterResponses
from agno.os.mcp_auth_builtin import AgentOSBuiltinAuth
from fastmcp.server.auth.providers.workos import AuthKitProvider
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


class BaseAuthSettings(BaseSettings):
    model_config = SettingsConfigDict({**BASE_SETTINGS_CONFIG, "env_prefix": "AUTH_"})


class AuthType(str, Enum):
    BUILTIN = "builtin"
    WORKOS = "workos"


class AgentOSBuiltinAuthSettings(BaseAuthSettings):
    mcp_connect_secret: SecretStr
    signing_key_material: SecretStr


class WorkOSAuthSettings(BaseAuthSettings):
    authkit_domain: SecretStr
    client_id: SecretStr


def create_agentos_builtin_auth(auth_base_url: str) -> AgentOSBuiltinAuth:
    auth_settings = AgentOSBuiltinAuthSettings()  # type: ignore[arg-type]

    return AgentOSBuiltinAuth(
        url=auth_base_url,
        secret=auth_settings.mcp_connect_secret.get_secret_value(),
        signing_key_material=(auth_settings.signing_key_material.get_secret_value()),
    )


def create_workos_auth(auth_base_url: str) -> AuthKitProvider:
    auth_settings = WorkOSAuthSettings()  # type: ignore[arg-type]
    return AuthKitProvider(
        authkit_domain=auth_settings.authkit_domain.get_secret_value(),
        base_url=auth_base_url,
    )


auth_types = {
    AuthType.BUILTIN: create_agentos_builtin_auth,
    AuthType.WORKOS: create_workos_auth,
}


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


# MCP_CONNECT_SECRET = getenv("MCP_CONNECT_SECRET", "")

# mcp_auth = None
# if MCP_CONNECT_SECRET:
#     from agno.os.mcp_auth_builtin import AgentOSBuiltinAuth

#     mcp_auth = AgentOSBuiltinAuth(
#         url=agentos_url,
#         secret=MCP_CONNECT_SECRET,
#         signing_key_material=getenv("AGENTOS_MCP_SIGNING_KEY"),
#     )


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG)

    runtime_env: str = "prd"
    codebase_dir: DirectoryPath = Path(__file__).resolve().parent.parent

    # Used by the scheduler and the OAuth server when MCP OAuth is enabled.
    agentos_url: str = "http://127.0.0.1:8000"

    ai: AISettings = Field(default_factory=AISettings)  # type: ignore[arg-type]
    slack: SlackSettings = Field(default_factory=SlackSettings)  # type: ignore[arg-type]
    auth_type: Literal[AuthType.BUILTIN, AuthType.WORKOS] | None = None

    @property
    def auth_provider(self) -> AgentOSBuiltinAuth | AuthKitProvider | None:
        if not self.auth_type:
            return None

        return auth_types[self.auth_type](self.agentos_url)


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
