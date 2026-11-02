import logging
from core.models import Message

MAX_CHAIN_DEPTH = 50


def build_qa_messages(
    messages: list[Message],
    logger: logging.Logger | None = None,
) -> list[Message]:
    """For each leaf message (one nobody replied to) that is part of an explicit
    reply chain, walks back to the root and builds a synthetic Message containing
    the whole thread as a single searchable unit."""

    if logger is None:
        logger = logging.getLogger("cribrum.chunking")

    messages_by_id = {m.id: m for m in messages}
    replied_to_ids = {m.reply_to_id for m in messages if m.reply_to_id is not None}

    synthetic_messages: list[Message] = []

    for msg in messages:
        if msg.reply_to_id is None:
            continue

        if msg.id in replied_to_ids:
            continue   # not a leaf: someone already replied to this message

        thread: list[Message] = [msg]
        current = msg
        depth = 0

        while current.reply_to_id is not None and depth < MAX_CHAIN_DEPTH:
            parent = messages_by_id.get(current.reply_to_id)
            if parent is None:
                logger.debug(f"Thread id={msg.id}: missing parent id={current.reply_to_id}")
                break
            thread.append(parent)
            current = parent
            depth += 1

        if len(thread) < 2:
            continue   # parent not found immediately: no real thread to build

        thread.reverse()   # root -> ... -> leaf, chronological order

        combined_text = "\n".join(f"{m.author}: {m.text}" for m in thread)

        synthetic_messages.append(Message(
            id=msg.id,
            text=combined_text,
            author=" / ".join(dict.fromkeys(m.author for m in thread)),
            timestamp=msg.timestamp,
            is_synthetic=True,
            source_ids=[m.id for m in thread],
        ))

    logger.info(f"Built {len(synthetic_messages)} synthetic thread messages from explicit replies")
    return synthetic_messages


def build_implicit_qa_messages(
    messages: list[Message],
    logger: logging.Logger | None = None,
) -> list[Message]:
    """For each question-like message immediately followed by a message from
    a different author with no explicit reply link, builds a synthetic Message
    treating that adjacent message as an implicit answer.

    Assumes `messages` is already in chronological order (as produced by the
    Telegram export parser)."""

    if logger is None:
        logger = logging.getLogger("cribrum.chunking")

    synthetic_messages: list[Message] = []

    for i in range(len(messages) - 1):
        question = messages[i]
        answer = messages[i + 1]

        if not looks_like_question(question.text):
            continue

        if answer.reply_to_id is not None:
            continue   # already handled explicitly by build_qa_messages

        if answer.author == question.author:
            continue   # same person continuing their own message, not an answer

        combined_text = f"{question.author}: {question.text}\n{answer.author}: {answer.text}"

        synthetic_messages.append(Message(
            id=answer.id,
            text=combined_text,
            author=f"{question.author} / {answer.author}",
            timestamp=answer.timestamp,
            is_synthetic=True,
            source_ids=[question.id, answer.id],
        ))

    logger.info(f"Built {len(synthetic_messages)} synthetic implicit Q&A messages")
    return synthetic_messages


def looks_like_question(text: str) -> bool:
    """Very simple heuristic: a message counts as a question if it ends with '?'.
    Misses questions phrased without punctuation (common in casual chat) —
    a future refinement can replace this with proper question detection
    (e.g. a small local LLM classification step)."""
    return text.strip().endswith("?")


def build_all_qa_messages(
    messages: list[Message],
    logger: logging.Logger | None = None,
) -> list[Message]:
    """Runs both explicit (reply-based) and implicit (adjacency-based) Q&A
    chunking and returns the combined list of synthetic messages.

    The two functions operate on disjoint subsets of messages (explicit replies
    vs. messages with no reply_to_id), so there is no overlap between their
    results."""

    if logger is None:
        logger = logging.getLogger("cribrum.chunking")

    explicit = build_qa_messages(messages, logger)
    implicit = build_implicit_qa_messages(messages, logger)

    logger.info(
        f"Total synthetic messages: {len(explicit)} explicit + {len(implicit)} implicit "
        f"= {len(explicit) + len(implicit)}"
    )

    return explicit + implicit