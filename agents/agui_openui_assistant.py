from agno.agent import Agent

from app.settings import default_model, get_settings
from db import get_postgres_db

settings = get_settings()
OPENUI_PROMPT_PATH = settings.codebase_dir / "frontend" / "openui" / "src" / "generated" / "system-prompt.txt"

if not OPENUI_PROMPT_PATH.is_file():
    raise RuntimeError(
        "OpenUI system prompt is missing. Run `npm install` and "
        "`npm run generate:prompt` in "
        "cookbook/05_agent_os/16_agui/openui/frontend before starting the server."
    )

openui_system_prompt = OPENUI_PROMPT_PATH.read_text(encoding="utf-8")

agui_openui_assistant = Agent(
    id="agui-openui-assistant",
    name="OpenUI Assistant",
    model=default_model(),
    db=get_postgres_db(),
    tools=[],
    instructions=[
        openui_system_prompt,
    ],
    add_history_to_context=True,
    num_history_runs=10,
)
