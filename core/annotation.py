import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path

from core.ingest.telegram import parse_telegram_chat
from core.models import ChatMessage
from core.window_config import WindowParams
from core.windows import exclusion_reason, in_date_range, is_dependent, normalize_phrase

LABELS = ("same", "new", "earlier", "unsure")
# Gap bands (seconds) used to stratify the sample: every band gets about the
# same number of pairs, so the rare long gaps are represented too.
GAP_BANDS = ((0, 120), (120, 300), (300, 600), (600, 1200), (1200, 2400), (2400, 5400), (5400, 10800))
MIN_PER_CHAT = 15


@dataclass(frozen=True)
class Candidate:
    """A decision to label: does `message_id` continue the conversation of `prev_id`?"""
    chat: str
    chat_id: int
    message_id: int
    prev_id: int
    gap_s: int
    band: str

    @property
    def key(self) -> tuple[int, int]:
        return (self.chat_id, self.message_id)


@dataclass
class ChatData:
    stem: str
    title: str
    included: list[ChatMessage]
    by_id: dict[int, ChatMessage]       # every message, excluded ones too (for reply previews)
    position: dict[int, int]            # message id -> index in `included`


def load_chat(path: Path, params: WindowParams) -> ChatData:
    chat_info, messages = parse_telegram_chat(path)
    included = included_messages(messages, params)
    return ChatData(
        stem=path.stem,
        title=chat_info["name"],
        included=included,
        by_id={m.id: m for m in messages},
        position={m.id: i for i, m in enumerate(included)},
    )


def included_messages(messages: list[ChatMessage], params: WindowParams) -> list[ChatMessage]:
    kept = [m for m in messages if in_date_range(m, params) and not exclusion_reason(m, params)]
    return sorted(kept, key=lambda m: (m.timestamp, m.id))


def band_of(gap_s: float) -> str | None:
    for lo, hi in GAP_BANDS:
        if lo < gap_s <= hi or (lo == 0 and gap_s == 0):
            return f"{lo}-{hi}"
    return None


def candidate_pairs(stem: str, included: list[ChatMessage], params: WindowParams) -> list[Candidate]:
    """Consecutive pairs that reach the gap rule. Pairs decided by reply, burst
    or dependent are left out: those rules stay as they are."""
    by_id = {m.id: m for m in included}
    phrases = {normalize_phrase(p) for p in params.dependent_phrases}
    out = []
    for prev, m in pairwise(included):
        gap = _seconds(prev, m)
        parent = by_id.get(m.reply_to_id) if m.reply_to_id is not None else None
        if parent is not None and _seconds(parent, m) <= params.reply_max_gap:
            continue
        if m.from_id and m.from_id == prev.from_id and gap <= params.burst_gap:
            continue
        if gap <= params.dependent_gap and is_dependent(m.text, phrases):
            continue
        band = band_of(gap)
        if band is not None:
            out.append(Candidate(stem, m.chat_id, m.id, prev.id, round(gap), band))
    return out


def allocate(sizes: dict[str, int], total: int, floor: int = MIN_PER_CHAT) -> dict[str, int]:
    """Pairs per chat, proportional to sqrt(size): big chats get more, but
    small ones are not drowned out."""
    weights = {chat: math.sqrt(n) for chat, n in sizes.items() if n}
    norm = sum(weights.values()) or 1.0
    return {chat: min(sizes[chat], max(floor, round(total * w / norm))) for chat, w in weights.items()}


def build_queue(candidates: dict[str, list[Candidate]], total: int, seed: int) -> list[Candidate]:
    """Deterministic: same candidates, total and seed give the same queue, so
    a session can be resumed by skipping what is already labelled."""
    rng = random.Random(seed)
    quotas = allocate({chat: len(c) for chat, c in candidates.items()}, total)
    queue = []
    for chat in sorted(quotas):
        queue.extend(_stratified(candidates[chat], quotas[chat], rng))
    rng.shuffle(queue)
    return queue


def _stratified(cands: list[Candidate], n: int, rng: random.Random) -> list[Candidate]:
    """Round-robin over gap bands, random order inside each band."""
    by_band: dict[str, list[Candidate]] = defaultdict(list)
    for c in cands:
        by_band[c.band].append(c)
    pools = []
    for lo, hi in GAP_BANDS:
        pool = by_band.get(f"{lo}-{hi}", [])
        rng.shuffle(pool)
        pools.append(pool)
    picked = []
    while len(picked) < n and any(pools):
        for pool in pools:
            if pool and len(picked) < n:
                picked.append(pool.pop())
    return picked


def pair_context(chat: ChatData, c: Candidate, before: int, after: int) -> tuple[list[ChatMessage], ChatMessage, list[ChatMessage]]:
    i = chat.position[c.message_id]
    return chat.included[max(0, i - before):i], chat.included[i], chat.included[i + 1:i + 1 + after]


def progress(queue: list[Candidate], records: list[dict]) -> dict[str, dict]:
    """Per chat: pairs in the queue, how many of them are labelled, and the
    label counts of every record of that chat (in the queue or not)."""
    done = labelled_keys(records)
    out: dict[str, dict] = {}

    def row(chat: str) -> dict:
        return out.setdefault(chat, {"queue": 0, "done": 0, "labels": Counter()})

    for c in queue:
        row(c.chat)["queue"] += 1
        row(c.chat)["done"] += c.key in done
    for r in records:
        row(r["chat"])["labels"][r["label"]] += 1
    return dict(sorted(out.items(), key=lambda kv: kv[0].lower()))


def load_labels(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def labelled_keys(records: list[dict]) -> set[tuple[int, int]]:
    return {(r["chat_id"], r["message_id"]) for r in records}


def label_record(c: Candidate, label: str, source: str = "human", **extra) -> dict:
    """`source` says who labelled the pair: only human labels are used to
    measure models. Records written before the field existed are human."""
    if label not in LABELS:
        raise ValueError(f"Unknown label: {label}")
    return {**asdict(c), "label": label, "source": source, **extra,
            "labelled_at": datetime.now().isoformat(timespec="seconds")}


def append_label(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def remove_last_label(path: Path) -> dict | None:
    records = load_labels(path)
    if not records:
        return None
    last = records.pop()
    write_labels(path, records)
    return last


def drop_blocked_labels(path: Path, chats: dict[str, ChatData], blocked_ids: tuple[str, ...]) -> list[dict]:
    """Removes the labels whose pair involves a blocked account; returns them.
    Labels of chats that are not loaded are kept."""
    blocked = set(blocked_ids)
    keep, dropped = [], []
    for r in load_labels(path):
        chat = chats.get(r["chat"])
        ids = (r["message_id"], r["prev_id"])
        hit = chat is not None and any(chat.by_id[i].from_id in blocked for i in ids if i in chat.by_id)
        (dropped if hit else keep).append(r)
    if dropped:
        write_labels(path, keep)
    return dropped


def write_labels(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def _seconds(a: ChatMessage, b: ChatMessage) -> float:
    return abs((b.timestamp - a.timestamp).total_seconds())
