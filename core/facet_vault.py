from dataclasses import dataclass, field

import numpy as np
import yaml

from core.topic_results import ChatResult
from core.vault import VaultParams, render_window, safe_name, topic_label


@dataclass
class FacetView:
    """A facet as the vault shows it."""
    id: str
    kind: str                                   # shared | local
    keywords: list[str]
    prototype: np.ndarray
    name: str = ""
    windows: dict[str, list[tuple[float, str, str]]] = field(default_factory=dict)  # chat -> [(sim, window id, source)]
    related: list[tuple[str, float]] = field(default_factory=list)

    @property
    def chats(self) -> list[str]:
        return sorted(self.windows, key=lambda c: -len(self.windows[c]))

    @property
    def n_windows(self) -> int:
        return sum(len(v) for v in self.windows.values())


def facet_views(records: list[dict], prototypes: np.ndarray, assignments: list[dict]) -> list[FacetView]:
    views = {r["id"]: FacetView(r["id"], r["kind"], r["keywords"], prototypes[i]) for i, r in enumerate(records)}
    for a in assignments:
        if a["facet"]:
            views[a["facet"]].windows.setdefault(a["chat"], []).append((a["similarity"], a["window_id"], a["source"]))
    for v in views.values():
        for items in v.windows.values():
            items.sort(reverse=True)                    # most central first
    return [v for v in views.values() if v.windows]


def name_facets(views: list[FacetView], label_words: int) -> None:
    """Shared facets are named by their keywords; local ones also carry their chat, since they are
    concepts of that chat. Collisions get the facet id."""
    seen: set[str] = set()
    for v in views:
        label = topic_label(v.keywords, label_words) or v.id
        base = safe_name(label if v.kind == "shared" else f"{v.chats[0]} - {label}")
        v.name = base if base not in seen else f"{base} ({v.id})"
        seen.add(v.name)


def chat_facet_name(chat: str, facet: FacetView) -> str:
    return safe_name(f"{chat} · {facet.name}")


def link_facets(views: list[FacetView], top_k: int, min_similarity: float) -> None:
    if len(views) < 2:
        return
    p = np.stack([v.prototype / (np.linalg.norm(v.prototype) or 1.0) for v in views])
    sims = p @ p.T
    np.fill_diagonal(sims, -1.0)
    for i, v in enumerate(views):
        v.related = [(views[j].name, float(sims[i, j])) for j in np.argsort(-sims[i])[:top_k] if sims[i, j] >= min_similarity]


def _front(data: dict) -> list[str]:
    return ["---", yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip(), "---", ""]


def _related(v: FacetView) -> list[str]:
    if not v.related:
        return []
    return ["## Related facets", "", *[f"- [[{name}]] ({sim:.2f})" for name, sim in v.related], ""]


def _windows(items: list[tuple[float, str, str]], result: ChatResult, params: VaultParams) -> list[str]:
    shown = items[:params.max_windows]
    hidden = len(items) - len(shown)
    windows = sorted((result.windows[wid] for _, wid, _ in shown if wid in result.windows), key=lambda w: w["first_ts"])
    nearest = {wid for _, wid, src in shown if src == "nearest"}
    head = f"## Windows ({len(windows)} shown" + (f", {hidden} less central left out)" if hidden else ")")
    out = [head, "", "_Windows marked ↳ joined the facet by similarity, not through a topic._", ""] if nearest else [head, ""]
    for w in windows:
        text = render_window(w, result.by_id, params.max_message_chars)
        out.append(text.replace("### ", "### ↳ ", 1) if w["window_id"] in nearest else text)
    return out


def _period(items: list[tuple[float, str, str]], result: ChatResult) -> str:
    ws = [result.windows[wid] for _, wid, _ in items if wid in result.windows]
    return f"{min(w['first_ts'] for w in ws)[:10]} → {max(w['last_ts'] for w in ws)[:10]}" if ws else ""


def render_facet_note(v: FacetView, results: dict[str, ChatResult], chat_notes: dict[str, str]) -> str:
    """Hub of a shared facet: the chats where it appears, its related facets, a few examples."""
    lines = _front({"type": "facet", "facet_id": v.id, "kind": v.kind, "chats": v.chats, "windows": v.n_windows,
                    "keywords": v.keywords, "tags": ["facet"]})
    lines += [f"# {v.name}", "", f"Shared facet · {len(v.chats)} chats · {v.n_windows} windows", "",
              f"**Keywords:** {', '.join(v.keywords)}", "", "## Chats", ""]
    lines += [f"- [[{chat_facet_name(c, v)}]] · {len(v.windows[c])} windows in [[{chat_notes[c]}]]" for c in v.chats]
    lines.append("")
    lines += _related(v)
    return "\n".join(lines)


def render_chat_facet_note(chat: str, v: FacetView, result: ChatResult, chat_note: str, params: VaultParams) -> str:
    """The windows of one chat about one shared facet."""
    items = v.windows[chat]
    lines = _front({"type": "chat_facet", "chat": chat, "facet_id": v.id, "windows": len(items),
                    "period": _period(items, result), "tags": ["chat_facet", f"chat/{chat}"]})
    lines += [f"# {chat_facet_name(chat, v)}", "", f"Facet: [[{v.name}]] · Chat: [[{chat_note}]] · "
              f"{len(items)} windows · {_period(items, result)}", ""]
    lines += _windows(items, result, params)
    return "\n".join(lines)


def render_concept_note(v: FacetView, result: ChatResult, chat_note: str, params: VaultParams) -> str:
    """A local facet: a concept found in one chat only."""
    chat = v.chats[0]
    items = v.windows[chat]
    lines = _front({"type": "concept", "chat": chat, "facet_id": v.id, "windows": len(items),
                    "period": _period(items, result), "keywords": v.keywords, "tags": ["concept", f"chat/{chat}"]})
    lines += [f"# {v.name}", "", f"Concept of [[{chat_note}]] · {len(items)} windows · {_period(items, result)}", "",
              f"**Keywords:** {', '.join(v.keywords)}", ""]
    lines += _related(v)
    lines += _windows(items, result, params)
    return "\n".join(lines)


def render_chat_note(result: ChatResult, views: list[FacetView], n_without: int) -> str:
    chat = result.chat
    shared = sorted((v for v in views if v.kind == "shared" and chat in v.windows), key=lambda v: -len(v.windows[chat]))
    local = sorted((v for v in views if v.kind == "local" and chat in v.windows), key=lambda v: -len(v.windows[chat]))
    total = sum(len(v.windows[chat]) for v in shared + local)
    lines = _front({"type": "chat", "chat": chat, "shared_facets": len(shared), "concepts": len(local),
                    "windows_with_facet": total, "windows_without_facet": n_without, "tags": ["chat", f"chat/{chat}"]})
    lines += [f"# {result.title}", "", f"{total} windows with a facet · {n_without} without", "",
              "## Shared facets", ""]
    lines += [f"- [[{chat_facet_name(chat, v)}]] · {len(v.windows[chat])} windows" for v in shared] or ["_none_"]
    lines += ["", "## Concepts of this chat", ""]
    lines += [f"- [[{v.name}]] · {len(v.windows[chat])} windows" for v in local] or ["_none_"]
    return "\n".join(lines) + "\n"


def render_index(chats: list[tuple[str, str]], views: list[FacetView], generated_at: str) -> str:
    """`chats` = (chat note name, title)."""
    shared = sorted((v for v in views if v.kind == "shared"), key=lambda v: (-len(v.chats), -v.n_windows))
    lines = ["# Cribrum", "", f"Generated by `cli.main export` on {generated_at}. Do not edit: it is rewritten.", "",
             "## Chats", "", *[f"- [[{name}]]" for name, _ in chats], "",
             "## Shared facets", "", *[f"- [[{v.name}]] · {len(v.chats)} chats · {v.n_windows} windows" for v in shared]]
    return "\n".join(lines) + "\n"
