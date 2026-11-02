from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Message:
    id: int
    text: str
    author: str
    timestamp: datetime
    reply_to_id: Optional[int] = None
    has_media: bool = False
    source: str = "telegram"
    course: Optional[str] = None
    is_synthetic: bool = False
    source_ids: list[int] = field(default_factory=list)   # id dei messaggi originali combinati

@dataclass
class ChatMessage:
    """Raw-faithful message used to build windows. Identified by (chat_id, id)."""
    chat_id: int
    id: int
    timestamp: datetime
    author: str
    from_id: str | None
    text: str
    kind: str = "text"          # text | media | poll | service
    reply_to_id: Optional[int] = None
    is_forwarded: bool = False
    is_edited: bool = False
    n_reactions: int = 0
    service_action: Optional[str] = None
    mentioned_user_ids: list[str] = field(default_factory=list)
    mentioned_usernames: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, int]:
        return (self.chat_id, self.id)


@dataclass
class WindowLink:
    """Why a message joined its window: the rule and the message it was linked to."""
    message_id: int
    rule: Optional[str]          # None for the first message of a window
    linked_to: Optional[int] = None
    capped_rule: Optional[str] = None   # with rule="cap": the rule the cap prevented


@dataclass
class Window:
    window_id: str
    chat_id: int
    chat_name: str
    chat_type: str
    config_hash: str
    message_ids: list[int]
    links: list[WindowLink]
    first_ts: datetime
    last_ts: datetime
    authors: list[str]
    n_messages: int
    n_tokens: int
    overlap_ids: list[int] = field(default_factory=list)
    is_short: bool = False
    has_forwarded: bool = False
    has_media: bool = False
    hit_cap: bool = False
