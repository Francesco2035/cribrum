"""Labels proposed by an assistant (Claude) in batches, kept apart from the
human ones: they can be used for training, never for measuring a model."""
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from core.annotation import (
    LABELS,
    Candidate,
    ChatData,
    build_queue,
    label_record,
    labelled_keys,
    load_labels,
    pair_context,
    write_labels,
)
from core.models import ChatMessage
from core.windows import render_body

CONFIDENCES = ("high", "low")
ANSWER_RE = re.compile(r"^(?P<chat>[\w.-]+):(?P<mid>\d+)\s+(?P<label>\w+)\s+(?P<conf>\w+)\s*$")
TEXT_CHARS = 500


def assistant_queue(
    candidates: dict[str, list[Candidate]], reserved: set[tuple[int, int]], total: int, seed: int,
) -> list[Candidate]:
    """Like the human queue, but without the `reserved` pairs (the human
    random sample), which must stay human-only to serve as the test set."""
    free = {chat: [c for c in cands if c.key not in reserved] for chat, cands in candidates.items()}
    return build_queue(free, total, seed)


def next_batch(queue: list[Candidate], done: set[tuple[int, int]], size: int) -> list[Candidate]:
    return [c for c in queue if c.key not in done][:size]


def calibration_batch(
    human: list[dict], done: set[tuple[int, int]], by_key: dict[tuple[int, int], Candidate], size: int,
) -> list[Candidate]:
    """Human-labelled pairs not yet labelled by the assistant (labels hidden)."""
    out = []
    for r in human:
        key = (r["chat_id"], r["message_id"])
        if key not in done and key in by_key and len(out) < size:
            out.append(by_key[key])
    return out


def batch_text(items: list[Candidate], chats: dict[str, ChatData], before: int, after: int, title: str) -> str:
    parts = [
        f"# {title} · {len(items)} pairs\n",
        "Question for each pair: does the T message continue the conversation of the P message?",
        "Context lines are plain, P = previous message, T = message to decide, + = messages after (not seen by the model).",
        f"Answer one line per pair: `<key> <{'|'.join(LABELS)}> <{'|'.join(CONFIDENCES)}>`\n",
    ]
    for c in items:
        chat = chats[c.chat]
        ctx, target, nxt = pair_context(chat, c, before, after)
        parts.append(f"## {c.chat}:{c.message_id}  ({chat.title}, {target.timestamp:%Y-%m-%d}, gap {c.gap_s // 60} min)")
        parts.extend(_line(m, chat, "P " if m.id == c.prev_id else "  ") for m in ctx)
        parts.append(_line(target, chat, "T "))
        parts.extend(_line(m, chat, "+ ") for m in nxt)
        parts.append("")
    return "\n".join(parts)


def _line(m: ChatMessage, chat: ChatData, mark: str) -> str:
    text = render_body(m).replace("\n", " ⏎ ")
    text = text if len(text) <= TEXT_CHARS else text[:TEXT_CHARS] + "…"
    reply = ""
    parent = chat.by_id.get(m.reply_to_id) if m.reply_to_id is not None else None
    if parent is not None:
        reply = f" [reply to {parent.author}: “{render_body(parent).replace(chr(10), ' ')[:60]}”]"
    return f"{mark}{m.timestamp:%H:%M} {m.author}:{reply} {text}"


def parse_answers(text: str) -> tuple[list[tuple[str, int, str, str]], list[str]]:
    """Returns (answers, errors). Blank lines and lines starting with # are skipped."""
    answers, errors = [], []
    for n, line in enumerate(text.splitlines(), start=1):
        line = line.strip().strip("`")
        if not line or line.startswith("#"):
            continue
        m = ANSWER_RE.match(line)
        if not m or m["label"] not in LABELS or m["conf"] not in CONFIDENCES:
            errors.append(f"line {n}: {line}")
            continue
        answers.append((m["chat"], int(m["mid"]), m["label"], m["conf"]))
    return answers, errors


def import_answers(
    answers: list[tuple[str, int, str, str]], by_stem_id: dict[tuple[str, int], Candidate], path: Path,
) -> tuple[int, list[str]]:
    """Appends the answers to the assistant labels file; a pair already there is replaced."""
    records = {(r["chat_id"], r["message_id"]): r for r in load_labels(path)}
    unknown = []
    for chat, mid, label, conf in answers:
        c = by_stem_id.get((chat, mid))
        if c is None:
            unknown.append(f"{chat}:{mid}")
            continue
        records[c.key] = label_record(c, label, source="claude", confidence=conf)
    write_labels(path, list(records.values()))
    return len(answers) - len(unknown), unknown


def to_review(records: list[dict], human_keys: set[tuple[int, int]]) -> list[dict]:
    """Low-confidence assistant labels not yet reviewed, skipping pairs the human already labelled."""
    return [r for r in records if r.get("confidence") == "low" and r["source"] == "claude"
            and (r["chat_id"], r["message_id"]) not in human_keys]


def review_record(record: dict, label: str) -> dict:
    return {**record, "label": label, "claude_label": record["label"], "source": "claude_reviewed",
            "reviewed_at": datetime.now().isoformat(timespec="seconds")}


def replace_record(path: Path, record: dict) -> None:
    key = (record["chat_id"], record["message_id"])
    write_labels(path, [record if (r["chat_id"], r["message_id"]) == key else r for r in load_labels(path)])


def agreement(human: list[dict], assistant: list[dict]) -> tuple[int, int, Counter]:
    """On the pairs labelled by both: (n, n agreeing, confusion of (human, assistant))."""
    by_key = {(r["chat_id"], r["message_id"]): r for r in assistant}
    confusion = Counter()
    for r in human:
        other = by_key.get((r["chat_id"], r["message_id"]))
        if other is not None:
            confusion[(r["label"], other.get("claude_label", other["label"]))] += 1
    n = confusion.total()
    return n, sum(v for (h, a), v in confusion.items() if h == a), confusion


def binary_agreement(confusion: Counter) -> tuple[int, int]:
    """The decision the model takes: merge (same) or not (new, earlier). Pairs
    where either side is unsure are left out."""
    merge = lambda label: label == "same"
    pairs = {k: v for k, v in confusion.items() if "unsure" not in k}
    return sum(pairs.values()), sum(v for (h, a), v in pairs.items() if merge(h) == merge(a))


def done_keys(path: Path) -> set[tuple[int, int]]:
    return labelled_keys(load_labels(path))
