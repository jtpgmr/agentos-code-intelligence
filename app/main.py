"""
AgentOS Entrypoint
==================
"""

from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path

from agno.os import AgentOS, MCPConfig
from agno.os.config import AuthorizationConfig
from agno.os.interfaces.agui import AGUI
from agno.utils.log import log_info

from agents.agui_openui_assistant import agui_openui_assistant
from agents.builder import platform_builder
from agents.engineer import platform_engineer
from agents.manager import platform_manager
from agents.slack_interface_assistant import slack_interface_assistant
from app.knowledge import product_knowledge, shared_knowledge
from app.registry import registry
from app.schedules import register_schedules
from app.settings import get_settings
from db import get_postgres_db
from teams.lead import agno_team
from workflows.deployment_check import deployment_check
from workflows.run_evals import run_evals

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
# runtime_env = getenv("RUNTIME_ENV", "prd")
# Used by the scheduler and the OAuth server when MCP OAuth is enabled.
# agentos_url = getenv("AGENTOS_URL", "http://127.0.0.1:8000")

settings = get_settings()
print(settings)
agentos_url, runtime_env = settings.agentos_url, settings.runtime_env

# slack_settings = settings.slack
slack_bot_token, slack_signing_secret = settings.slack.bot_token, settings.slack.signing_secret

# ---------------------------------------------------------------------------
# Interfaces
# - Agno becomes available on Slack when both env vars are set
# ---------------------------------------------------------------------------
# SLACK_BOT_TOKEN = getenv("SLACK_BOT_TOKEN", "")
# SLACK_SIGNING_SECRET = getenv("SLACK_SIGNING_SECRET", "")


interfaces: list = []
if slack_bot_token and slack_signing_secret:
    from agno.os.interfaces.slack import Slack

    interfaces.append(
        Slack(
            agent=slack_interface_assistant,
            streaming=True,
            token=slack_bot_token.get_secret_value(),
            signing_secret=slack_signing_secret.get_secret_value(),
            loading_text="Pulling the thread...",
            resolve_user_identity=True,
            # reply_to_mentions_only=False,
        )
    )

interfaces.append(AGUI(agent=agui_openui_assistant))
# ---------------------------------------------------------------------------
# MCP OAuth — enabled by setting the MCP_CONNECT_SECRET environment variable.
# Connect your favorite AI apps and coding agents to a secure /mcp using OAuth.
# ---------------------------------------------------------------------------
MCP_CONNECT_SECRET = getenv("MCP_CONNECT_SECRET", "")

mcp_auth = None
if MCP_CONNECT_SECRET:
    from agno.os.mcp_auth_builtin import AgentOSBuiltinAuth

    mcp_auth = AgentOSBuiltinAuth(
        url=agentos_url,
        secret=MCP_CONNECT_SECRET,
        signing_key_material=getenv("AGENTOS_MCP_SIGNING_KEY"),
    )


# ---------------------------------------------------------------------------
# Lifespan — app-level startup / teardown.
#
# AgentOS handles the MCP lifecycle (connect on startup, close on shutdown)
# for agent-attached and registry tools. Keep this hook to plug in your own setup.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):  # type: ignore[no-untyped-def]
    log_info("AgentOS lifespan: startup")
    # Register schedules on startup. Idempotent and fail-soft.
    register_schedules()
    try:
        yield
    finally:
        log_info("AgentOS lifespan: shutdown")


# ---------------------------------------------------------------------------
# Create AgentOS
# ---------------------------------------------------------------------------
agent_os = AgentOS(
    name="AgentOS",
    tracing=True,
    scheduler=True,
    scheduler_base_url=agentos_url,
    authorization=runtime_env != "dev",
    authorization_config=AuthorizationConfig(user_isolation=True),
    # MCP clients can run agno directly
    mcp=MCPConfig(
        tools=[
            agno_team.as_tool(
                name="agno",
                title="Agno",
                description=(
                    "Talk to Agno, the platform lead. Send plain language. "
                    "Pass session_id back to continue the conversation."
                ),
            )
        ],
    ),
    mcp_auth=mcp_auth,
    lifespan=lifespan,
    db=get_postgres_db(),
    knowledge=[shared_knowledge, product_knowledge],
    agents=[platform_builder, platform_manager, platform_engineer],
    teams=[agno_team],
    workflows=[deployment_check, run_evals],
    interfaces=interfaces,
    registry=registry,
    config=str(Path(__file__).parent / "config.yaml"),
)
app = agent_os.get_app()


if __name__ == "__main__":
    agent_os.serve(app="app.main:app", reload=False)
