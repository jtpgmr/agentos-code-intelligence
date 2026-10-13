from typing import Any
from urllib.parse import urlparse

from agno.agent import Agent
from agno.learn import LearningMachine, LearningMode, UserMemoryConfig, UserProfileConfig
from agno.tools import tool
from agno.tools.duckduckgo import DuckDuckGoTools

# from agno.tools.clickup import ClickUpTools
# from agno.tools.google.drive import GoogleDriveTools
# from agno.tools.reasoning import ReasoningTools
from agno.tools.youtube import YouTubeTools
from yt_dlp import YoutubeDL

from app.settings import default_model, get_settings
from db import get_postgres_db

settings = get_settings()

# llm_txt_sources = select_llms_txt_sources(selected_names=["Slack"], selected_tags=["ai_models"])

learning = LearningMachine(
    user_profile=UserProfileConfig(
        mode=LearningMode.AGENTIC,
    ),
    user_memory=UserMemoryConfig(
        mode=LearningMode.AGENTIC,
    ),
)


@tool
def get_youtube_playlist(url: str) -> list[dict]:
    """Get all publicly accessible videos in a YouTube playlist."""
    if urlparse(url).hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        raise ValueError("Expected a YouTube URL")
    params: Any = {
        "extract_flat": True,
        # "skip_download": True,
        "quiet": True,
        "ignoreerrors": True,
    }
    ydl = YoutubeDL(params=params)
    playlist = ydl.extract_info(url, download=False)

    return [
        {
            "title": video.get("title"),
            "video_id": video["id"],
            "url": f"https://www.youtube.com/watch?v={video['id']}",
        }
        for video in playlist.get("entries", [])
        if video and video.get("id")
    ]


learning_coach = Agent(
    id="learning-coach",
    name="Learning Coach",
    model=default_model(),
    db=get_postgres_db(),
    tools=[
        # ClickUpTools(),
        # GoogleDriveTools(),
        # FileGenerationTools(enable_csv_generation=True),
        # ReasoningTools(),
        YouTubeTools(),
        DuckDuckGoTools(modifier="(site:youtube.com OR site:github.com)", enable_news=False),
        get_youtube_playlist,
    ],
    # skills=Skills(loaders=[LocalSkills(path=str(settings.codebase_dir / ".agents" / "slack" / ".agents" / "skills"))]),
    instructions=[],
    add_history_to_context=True,
    num_history_runs=10,
)
