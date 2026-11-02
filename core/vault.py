import dataclasses
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from core.models import ChatMessage
from core.topics import OUTLIER

GENERATED = ("chats", "topics", "facets", "notes", "concepts", "index.md")   # owned by `export`; everything else is kept
UNSAFE_NAME = re.compile(r'[\\/:*?"<>|#^\[\]]')


@dataclass(frozen=True)
class VaultParams:
    top_k: int = 3                  # links to the most similar topics per note
    min_similarity: float = 0.4     # ... only above this centroid cosine
    label_words: int = 3            # keywords in a note's title
    max_windows: int = 40           # windows quoted per topic note (most central first, then shown by date)
    max_message_chars: int = 500


def load_vault_params(path: Path) -> VaultParams:
    raw = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    unknown = set(raw) - {f.name for f in dataclasses.fields(VaultParams)}
    if unknown:
        raise ValueError(f"Unknown vault config keys in {path}: {sorted(unknown)}")
    return VaultParams(**raw)


@dataclass
class TopicNote:
    chat: str                       # export stem
    chat_title: str
    topic: int
    keywords: list[str]
    centroid: np.ndarray
    windows: list[dict]             # windows.jsonl records, most central first
    name: str = ""
    related: list[tuple[str, float]] = field(default_factory=list)


def safe_name(text: str) -> str:
    """A file name Obsidian can link to: no path or link characters, single spaces."""
    return " ".join(UNSAFE_NAME.sub(" ", text).split()).strip(" .") or "untitled"


def topic_label(keywords: list[str], n: int) -> str:
    """First n keywords, skipping those already contained in a previous one ("grand coalition" after "coalition")."""
    picked: list[str] = []
    for w in keywords:
        if not any(w in p or p in w for p in picked):
            picked.append(w)
        if len(picked) == n:
            break
    return ", ".join(picked)


def assign_names(notes: list[TopicNote], label_words: int) -> None:
    """`<chat> - <keywords>`, with the topic id appended only when two notes would collide."""
    seen: dict[str, int] = {}
    for note in notes:
        base = safe_name(f"{note.chat} - {topic_label(note.keywords, label_words)}")
        seen[base] = seen.get(base, 0) + 1
        note.name = base if seen[base] == 1 else f"{base} ({note.topic})"


def link_similar(notes: list[TopicNote], top_k: int, min_similarity: float) -> None:
    """Each note links its top_k most similar topics (any chat) above the threshold, by centroid cosine."""
    if len(notes) < 2:
        return
    c = np.stack([n.centroid / (np.linalg.norm(n.centroid) or 1.0) for n in notes])
    sims = c @ c.T
    np.fill_diagonal(sims, -1.0)
    for i, note in enumerate(notes):
        order = np.argsort(-sims[i])[:top_k]
        note.related = [(notes[j].name, float(sims[i, j])) for j in order if sims[i, j] >= min_similarity]


def clean_text(text: str, limit: int) -> str:
    """Message text safe inside a quote: no tags (#), no wikilinks, one line."""
    text = " ".join((text or "").split())
    text = text.replace("#", "\\#").replace("[[", "\\[\\[").replace("]]", "\\]\\]")
    return text[:limit] + ("…" if len(text) > limit else "")


def render_window(w: dict, by_id: dict[int, ChatMessage], limit: int) -> str:
    first = datetime.fromisoformat(w["first_ts"])
    n = w["n_messages"]
    lines = [f"### {first:%Y-%m-%d %H:%M} · {n} message{'s' if n != 1 else ''}", ""]
    for mid in w["message_ids"]:
        m = by_id.get(mid)
        if m is None:
            continue
        body = clean_text(m.text, limit) or "_[media]_"
        lines.append(f"> **{clean_text(m.author, 80)}** {m.timestamp:%H:%M} · {body}")
        lines.append(">")
    if lines[-1] == ">":
        lines.pop()
    return "\n".join(lines) + "\n"


def render_topic_note(note: TopicNote, by_id: dict[int, ChatMessage], params: VaultParams, chat_note: str) -> str:
    shown = sorted(note.windows[:params.max_windows], key=lambda w: w["first_ts"])
    first = min((w["first_ts"] for w in note.windows), default="")[:10]
    last = max((w["last_ts"] for w in note.windows), default="")[:10]
    front = {"type": "topic", "chat": note.chat, "topic_id": note.topic, "windows": len(note.windows),
             "period": f"{first} → {last}", "keywords": note.keywords, "tags": ["topic", f"chat/{note.chat}"]}
    parts = ["---", yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip(), "---", "",
             f"# {note.name}", "", f"Chat: [[{chat_note}]] · {len(note.windows)} windows · {first} → {last}", "",
             f"**Keywords:** {', '.join(note.keywords)}", ""]
    if note.related:
        parts += ["## Related topics", ""]
        parts += [f"- [[{name}]] ({sim:.2f})" for name, sim in note.related]
        parts.append("")
    hidden = len(note.windows) - len(shown)
    parts += [f"## Windows ({len(shown)} shown" + (f", {hidden} less central left out)" if hidden else ")"), ""]
    parts += [render_window(w, by_id, params.max_message_chars) for w in shown]
    return "\n".join(parts)


def render_chat_note(chat: str, title: str, notes: list[TopicNote], n_windows: int, n_outliers: int) -> str:
    front = {"type": "chat", "chat": chat, "topics": len(notes), "windows": n_windows,
             "windows_without_topic": n_outliers, "tags": ["chat", f"chat/{chat}"]}
    parts = ["---", yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip(), "---", "",
             f"# {title}", "", f"{len(notes)} topics · {n_windows} windows · {n_outliers} without a topic", "",
             "## Topics", ""]
    parts += [f"- [[{n.name}]] ({len(n.windows)} windows)" for n in sorted(notes, key=lambda n: -len(n.windows))]
    return "\n".join(parts) + "\n"


def render_index(chats: list[tuple[str, str, int]], generated_at: str) -> str:
    """`chats` = (chat note name, title, number of topics)."""
    parts = ["# Cribrum", "", f"Generated by `cli.main export` on {generated_at}. Do not edit: it is rewritten.", "",
             "## Chats", ""]
    parts += [f"- [[{name}]] · {n} topics" for name, _, n in chats]
    return "\n".join(parts) + "\n"


def graph_settings() -> dict:
    """Obsidian graph view colours by folder. Written only if the vault has none yet."""
    def group(query: str, rgb: int) -> dict:
        return {"query": query, "color": {"a": 1, "rgb": rgb}}
    return {"colorGroups": [group("path:chats", 0xE8590C), group("path:facets", 0x2F9E44), group("path:notes", 0x1C7ED6),
                            group("path:concepts", 0x868E96), group("path:topics", 0x1C7ED6)], "showTags": False}


def reset_generated(vault: Path) -> None:
    """Removes only what a previous export wrote, so notes and settings added by hand survive."""
    for name in GENERATED:
        target = vault / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def write_note(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_graph_settings(vault: Path) -> bool:
    path = vault / ".obsidian" / "graph.json"
    if path.exists():
        return False
    write_note(path, json.dumps(graph_settings(), indent=2))
    return True


def topic_windows(summary: list[dict], assignments: dict[str, int], windows: dict[str, dict],
                  vectors: dict[str, np.ndarray]) -> dict[int, list[dict]]:
    """Windows of each topic (outliers excluded), most central first."""
    out: dict[int, list[dict]] = {}
    for rec in summary:
        t = rec["topic"]
        if t == OUTLIER:
            continue
        centroid = np.array(rec["centroid"])
        members = [wid for wid, topic in assignments.items() if topic == t and wid in windows]
        members.sort(key=lambda wid: -float(vectors[wid] @ centroid) if wid in vectors else 0.0)
        out[t] = [windows[wid] for wid in members]
    return out
