from agno.agent import Agent
from agno.learn import LearningMachine, LearningMode, UserMemoryConfig, UserProfileConfig
from agno.skills import LocalSkills, Skills
from agno.tools.slack import SlackTools

from app.settings import default_model, get_settings
from app.utils import select_llms_txt_sources
from db import get_postgres_db

settings = get_settings()

llm_txt_sources = select_llms_txt_sources(selected_names=["Slack"], selected_tags=["ai_models"])

learning = LearningMachine(
    user_profile=UserProfileConfig(
        mode=LearningMode.AGENTIC,
    ),
    user_memory=UserMemoryConfig(
        mode=LearningMode.AGENTIC,
    ),
)
slack_assistant = Agent(
    id="slack-assistant",
    name="Slack Assistant",
    model=default_model(),
    db=get_postgres_db(),
    tools=[
        SlackTools(
            settings.slack.bot_token.get_secret_value(),
            enable_get_channel_info=True,
            enable_get_user_info=True,
            enable_list_users=True,
        ),
        *llm_txt_sources,
    ],
    skills=Skills(loaders=[LocalSkills(path=str(settings.codebase_dir / ".agents" / "slack" / ".agents" / "skills"))]),
    instructions=[
        "You are the Slack Assistant.",
        "agentos-code-intelligence is your Slack bot identity, not a documentation source.",
        "The following documentation indexes are configured:",
        f"{[sources.allowed_hosts for sources in llm_txt_sources]}",
        "When asked about documentation, select the relevant configured URL.",
        "Call get_llms_txt_index to discover documentation pages.",
        "Call read_llms_txt_url to retrieve relevant pages.",
        "Do not ask the user for a URL that is already configured.",
    ],
    add_history_to_context=True,
    num_history_runs=10,
)
