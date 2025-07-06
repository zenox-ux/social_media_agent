# FILE: src/models.py

from typing import TypedDict, Optional

class AgentState(TypedDict):
    """
    Represents the state of an agent processing a URL posting request.
    """
    generated_text: str
    url: Optional[str]
    scraped_content: Optional[str]

