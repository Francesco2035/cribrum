import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.ingest.telegram import parse_telegram_chat
from core.models import ChatMessage
from core.topics import TOPICS_ROOT
from core.window_embeddings import embeddings_dir, load_embeddings, load_windows, window_text


@dataclass
class ChatResult:
    """Everything later steps need from one chat's `discover` result."""
    chat: str                           # export stem
    title: str
    topics_dir: Path
    meta: dict
    summary: list[dict]                 # topics.json
    assignments: dict[str, int]         # window id -> topic (-1 = outlier), fitted windows only
    windows: dict[str, dict]            # every window of the windows folder
    by_id: dict[int, ChatMessage]
    texts: dict[str, str]
    vectors: dict[str, np.ndarray]      # raw E5 vectors of every embedded window

    @property
    def min_words(self) -> int:
        return int(self.meta["params"].get("min_words", 0))


def latest_topics_dirs(root: Path = TOPICS_ROOT) -> list[Path]:
    """For each chat, the most recently written `discover` result."""
    out = []
    for chat_dir in sorted(p for p in root.glob("*") if p.is_dir()):
        results = [m.parent for m in chat_dir.glob("*/*/meta.json")]
        if results:
            out.append(max(results, key=lambda p: (p / "meta.json").stat().st_mtime))
    return out


def load_chat_result(topics_dir: Path, raw_data_dir: Path) -> ChatResult:
    meta = json.loads((topics_dir / "meta.json").read_text(encoding="utf-8"))
    summary = json.loads((topics_dir / "topics.json").read_text(encoding="utf-8"))
    with open(topics_dir / "assignments.jsonl", encoding="utf-8") as f:
        assignments = {r["window_id"]: r["topic"] for r in map(json.loads, f)}
    windows_dir = Path(meta["windows_dir"])
    windows = {w["window_id"]: w for w in load_windows(windows_dir)}
    info, messages = parse_telegram_chat(raw_data_dir / f"{meta['chat']}.json")
    by_id = {m.id: m for m in messages}
    ids, vectors, _ = load_embeddings(embeddings_dir(windows_dir))
    return ChatResult(meta["chat"], info["name"], topics_dir, meta, summary, assignments, windows, by_id,
                      {wid: window_text(w, by_id) for wid, w in windows.items()},
                      {wid: vectors[i] for i, wid in enumerate(ids)})
