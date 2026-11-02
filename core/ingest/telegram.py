import json
import logging
import re
from pathlib import Path
from datetime import datetime
from core.models import ChatMessage, Message

SKIN_TONE_PATTERN = re.compile(r"[\U0001F3FB-\U0001F3FF]")

STICKER_EMOJI_MAP = {
    "👍": "sì",
    "👎": "no",
    "✅": "sì",
    "👌": "sì",
    "❌": "no",
}


def parse_telegram_export(
    path: Path,
    logger: logging.Logger | None = None,
) -> list[Message]:
    """Reads a Telegram result.json export and returns a list of cleaned Message objects.
    No length filtering here — that happens later, after reply-based Q&A chunks are built,
    so short standalone replies (e.g. "sì") aren't lost before they can be linked."""

    if logger is None:
        logger = logging.getLogger("cribrum.ingest")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    raw_messages = raw["messages"]
    logger.info(f"Read {len(raw_messages)} raw messages from {path}")

    messages: list[Message] = []
    skipped_type = 0

    for msg in raw_messages:
        if msg["type"] != "message":
            skipped_type += 1
            continue

        text = _extract_text(msg)
        author = msg.get("from") or "Unknown user"
        timestamp = datetime.fromisoformat(msg["date"])
        has_media = any(k in msg for k in ("photo", "file", "media_type"))

        messages.append(Message(
            id=msg["id"],
            text=text,
            author=author,
            timestamp=timestamp,
            reply_to_id=msg.get("reply_to_message_id"),
            has_media=has_media,
        ))

    logger.info(f"Skipped {skipped_type} service messages. Valid messages: {len(messages)}")
    return messages


def _extract_text(msg: dict) -> str:
    """Builds the full text by concatenating text_entities, falling back to the
    sticker's emoji meaning when the message has no real text."""
    entities = msg.get("text_entities", [])
    text = "".join(entity.get("text", "") for entity in entities)

    if not text.strip() and msg.get("media_type") == "sticker":
        emoji = _normalize_emoji(msg.get("sticker_emoji", ""))
        return STICKER_EMOJI_MAP.get(emoji, "")

    return text


def _normalize_emoji(emoji: str) -> str:
    """Strips skin-tone modifiers so every color variant maps to the same base emoji."""
    return SKIN_TONE_PATTERN.sub("", emoji)


MEDIA_KEYS = ("photo", "file", "media_type", "location_information", "contact_information")


def parse_telegram_chat(
    path: Path,
    logger: logging.Logger | None = None,
) -> tuple[dict, list[ChatMessage]]:
    """Reads a Telegram export keeping every message (service ones included,
    marked by kind) plus the metadata needed to build conversation windows."""

    if logger is None:
        logger = logging.getLogger("cribrum.ingest")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    chat_info = {"id": raw.get("id", 0), "name": raw.get("name") or path.stem, "type": raw.get("type")}
    messages = [_to_chat_message(msg, chat_info["id"]) for msg in raw["messages"]]
    logger.info(f"Read {len(messages)} raw messages from {path} (chat id={chat_info['id']})")
    return chat_info, messages


def _to_chat_message(msg: dict, chat_id: int) -> ChatMessage:
    is_service = msg["type"] != "message"
    text = normalize_text(msg)

    if is_service:
        kind = "service"
    elif "poll" in msg:
        kind = "poll"
        text = text or msg["poll"].get("question", "")
    elif any(k in msg for k in MEDIA_KEYS) and not text.strip():
        kind = "media"
    else:
        kind = "text"

    user_ids, usernames = _extract_mentions(msg)

    return ChatMessage(
        chat_id=chat_id,
        id=msg["id"],
        timestamp=datetime.fromisoformat(msg["date"]),
        author=(msg.get("actor") if is_service else msg.get("from")) or "Unknown user",
        from_id=msg.get("actor_id") if is_service else msg.get("from_id"),
        text=text,
        kind=kind,
        reply_to_id=msg.get("reply_to_message_id"),
        is_forwarded="forwarded_from" in msg,
        is_edited="edited" in msg,
        n_reactions=sum(r.get("count", 0) for r in msg.get("reactions", [])),
        service_action=msg.get("action") if is_service else None,
        mentioned_user_ids=user_ids,
        mentioned_usernames=usernames,
    )


def normalize_text(msg: dict) -> str:
    """`text` is either a plain string or a list mixing strings and entity
    dicts ({"type": "link", "text": ...}); both become a single string."""
    text = msg.get("text", "")
    if isinstance(text, list):
        text = "".join(p if isinstance(p, str) else p.get("text", "") for p in text)
    if not text.strip():
        text = _extract_text(msg)
    return text


def _extract_mentions(msg: dict) -> tuple[list[str], list[str]]:
    """mention_name entities carry a numeric user_id (matches from_id "user<id>");
    plain @mentions only carry a username, which the export never maps to a user."""
    user_ids, usernames = [], []
    for e in msg.get("text_entities", []):
        if e.get("type") == "mention_name" and "user_id" in e:
            user_ids.append(f"user{e['user_id']}")
        elif e.get("type") == "mention":
            usernames.append(e.get("text", "").lstrip("@").lower())
    return user_ids, usernames
