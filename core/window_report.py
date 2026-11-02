import dataclasses
import json
import random
import statistics
from pathlib import Path

from core.models import ChatMessage, Window
from core.window_config import WindowParams
from core.windows import RULES, BuildReport, render_body


def window_stats(windows: list[Window], report: BuildReport, top: int = 5) -> dict:
    n = len(windows)
    lengths = [w.n_messages for w in windows]
    tokens = [w.n_tokens for w in windows]
    longest = sorted(windows, key=lambda w: (-w.n_messages, -w.n_tokens))[:top]
    return {
        "chat_id": report.chat_id,
        "chat_name": report.chat_name,
        "chat_type": report.chat_type,
        "config_hash": report.config_hash,
        "tokenizer": report.tokenizer,
        "n_raw_messages": report.n_raw,
        "n_included_messages": report.n_included,
        "excluded": dict(report.excluded),
        "service_actions": dict(report.service_actions),
        "gap_percentiles_s": {f"p{p}": round(v) for p, v in report.gap_percentiles.items()},
        "n_windows": n,
        "messages_per_window": _distribution(lengths),
        "tokens_per_window": _distribution(tokens),
        "single_message_pct": round(100 * sum(1 for x in lengths if x == 1) / n, 1) if n else 0.0,
        "short_windows": sum(w.is_short for w in windows),
        "capped_windows": sum(w.hit_cap for w in windows),
        "merges": {rule: report.merges.get(rule, 0) for rule in RULES},
        "orphan_replies": report.orphan_replies,
        "stale_replies": report.stale_replies,
        "replies_to_excluded": report.replies_to_excluded,
        "unresolved_mentions": report.unresolved_mentions,
        "longest_windows": [
            {"window_id": w.window_id, "n_messages": w.n_messages, "n_tokens": w.n_tokens,
             "first_ts": w.first_ts.isoformat(), "last_ts": w.last_ts.isoformat()}
            for w in longest
        ],
    }


def _distribution(values: list[int]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]
    return {"min": ordered[0], "p50": pick(0.5), "p90": pick(0.9), "max": ordered[-1],
            "mean": round(statistics.fmean(ordered), 2)}


def sample_windows(windows: list[Window], n: int, seed: int) -> list[Window]:
    """Reproducible: same windows, n and seed give the same sample."""
    rng = random.Random(seed)
    picked = rng.sample(windows, min(n, len(windows)))
    return sorted(picked, key=lambda w: w.first_ts)


def window_to_dict(w: Window) -> dict:
    d = dataclasses.asdict(w)
    d["first_ts"] = w.first_ts.isoformat()
    d["last_ts"] = w.last_ts.isoformat()
    return d


def write_jsonl(windows: list[Window], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for w in windows:
            f.write(json.dumps(window_to_dict(w), ensure_ascii=False) + "\n")


def write_meta(params: WindowParams, stats: dict, path: Path) -> None:
    meta = {"config_hash": stats["config_hash"], "params": dataclasses.asdict(params), "stats": stats}
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def windows_markdown(windows: list[Window], messages: dict[int, ChatMessage], title: str) -> str:
    parts = [f"# {title}\n"]
    for w in windows:
        parts.append(_window_markdown(w, messages))
    return "\n".join(parts)


def _window_markdown(w: Window, messages: dict[int, ChatMessage]) -> str:
    flags = [name for name in ("is_short", "has_forwarded", "has_media", "hit_cap") if getattr(w, name)]
    lines = [
        f"## {w.window_id}",
        f"{w.first_ts:%Y-%m-%d %H:%M} → {w.last_ts:%Y-%m-%d %H:%M} · {w.n_messages} msg · "
        f"{w.n_tokens} tok · {len(w.authors)} authors" + (f" · {', '.join(flags)}" if flags else ""),
        "",
    ]
    for mid in w.overlap_ids:
        lines.append(f"- _(overlap)_ {_message_line(messages[mid])}")
    for link in w.links:
        lines.append(f"- {_rule_label(link)} {_message_line(messages[link.message_id])}")
    lines.append("")
    return "\n".join(lines)


def _rule_label(link) -> str:
    if link.rule is None:
        return "`start`"
    rule = f"cap after {link.capped_rule}" if link.rule == "cap" else link.rule
    return f"`{rule} ← #{link.linked_to}`"


def _message_line(m: ChatMessage) -> str:
    extras = [x for x, on in (("fwd", m.is_forwarded), ("edited", m.is_edited)) if on]
    if m.n_reactions:
        extras.append(f"{m.n_reactions} reactions")
    suffix = f" _({', '.join(extras)})_" if extras else ""
    text = render_body(m).replace("\n", " ⏎ ")
    return f"**{m.author}** {m.timestamp:%H:%M} #{m.id}: {text}{suffix}"
