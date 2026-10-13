from pathlib import Path

import yaml
from agno.tools.llms_txt import LLMsTxtTools


def select_llms_txt_sources(
    path: Path | str = Path(".agents/llms_txt.yaml"), selected_names: list[str] = [], selected_tags: list[str] = []
) -> list[LLMsTxtTools]:
    llms_txt_sources: list[dict[str, str]] = yaml.safe_load(Path(path).read_text())

    if not selected_names:
        return []

    selected: dict[str, str] = {}
    selected = {
        source["name"].lower().replace(" ", "_").replace("-", "_"): source.get("host", "").lower()
        for source in llms_txt_sources
        if source["name"] in selected_names
    }

    selected = {
        **selected,
        **{
            source["name"].lower().replace(" ", "_").replace("-", "_"): source.get("host", "").lower()
            for source in llms_txt_sources
            if any(tag in selected_tags for tag in source.get("tags", []))
        },
    }

    tools = [
        LLMsTxtTools(
            id="llms-txt",
            allowed_hosts=[source_url for source_url in selected.values()],
        )
    ]

    return tools
