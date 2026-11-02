"""Compares candidate window configurations on every export and writes a
markdown report: per-chat stats for each config, plus "boundary" message
pairs whose gap falls between two candidate thresholds (the only decisions
that change between configs), to be judged by reading them.

Usage: HF_HUB_OFFLINE=1 uv run python scripts/tune_windows.py [--out data/windows/tuning/report.md]
"""
import argparse
import logging
import random
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_blocklist, load_config
from core.ingest.telegram import parse_telegram_chat
from core.tokens import get_token_counter
from core.window_config import apply_overrides, load_window_params
from core.window_report import window_stats
from core.windows import (
    _gap, build_windows, exclusion_reason, in_date_range, is_dependent, normalize_phrase, render_body,
)

CANDIDATES = {
    "tight": {"gap_course": 300, "gap_general": 600, "reply_max_gap": 3 * 3600, "burst_gap": 60},
    "default": {},
    "loose": {"gap_course": 900, "gap_general": 1200, "reply_max_gap": 12 * 3600, "burst_gap": 180},
    "very_loose": {"gap_course": 1800, "gap_general": 2400, "reply_max_gap": 24 * 3600, "burst_gap": 300},
    "proposed": {"gap_course": 1200, "gap_general": 1800, "reply_max_gap": 24 * 3600, "burst_gap": 300},
}
GAP_BANDS = [(300, 600), (600, 900), (900, 1800), (1800, 3600)]
REPLY_BANDS = [(3 * 3600, 6 * 3600), (6 * 3600, 12 * 3600), (12 * 3600, 24 * 3600)]
BURST_BANDS = [(60, 120), (120, 300)]
PAIRS_PER_BAND = 3
TEXT_CHARS = 140


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=Path("data/exports"))
    ap.add_argument("--windows-config", type=Path, default=Path("config/windows.yaml"))
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--out", type=Path, default=Path("data/windows/tuning/report.md"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    cfg = load_config(args.config)
    dates = cfg.get("dates", {})
    blocked = tuple(load_blocklist(Path(cfg["paths"].get("blocklist", "config/blocklist.yaml"))))
    base, _ = load_window_params(args.windows_config, {"min_date": dates.get("min_date"),
                                                        "max_date": dates.get("max_date"),
                                                        "blocked_ids": blocked})
    count, tokenizer_name = get_token_counter(base.tokenizer_model)
    count = lru_cache(maxsize=None)(count)
    rng = random.Random(args.seed)

    sections = [_header(base)]
    for path in sorted(args.exports.glob("*.json"), key=lambda p: p.stem.lower()):
        chat_info, messages = parse_telegram_chat(path)
        print(f"{path.stem}: {len(messages)} messages", file=sys.stderr)
        sections.append(_chat_section(path.stem, chat_info, messages, base, count, tokenizer_name, rng))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(sections), encoding="utf-8")
    print(f"Report written to {args.out}", file=sys.stderr)


def _header(base) -> str:
    rows = "\n".join(f"| {name} | {_describe(apply_overrides(base, o))} |" for name, o in CANDIDATES.items())
    return (f"# Window tuning report\n\nDate range: {base.min_date} → {base.max_date or 'end'}\n\n"
            f"| config | params |\n|---|---|\n{rows}\n")


def _describe(p) -> str:
    return (f"gap course/general {p.gap['course']}/{p.gap['general']} s, reply ≤ {p.reply_max_gap // 3600} h, "
            f"burst {p.burst_gap} s")


def _chat_section(stem, chat_info, messages, base, count, tokenizer_name, rng) -> str:
    names = {chat_info["id"]: chat_info["name"]}
    lines = [f"\n## {stem} — {chat_info['name']} ({base.chat_type_for(chat_info['id'])})\n"]
    lines.append("| config | windows | single % | msgs p50/p90/max | tok mean | capped | reply | burst | dep | mention | gap | cap |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    gap_pct = None
    for name, overrides in CANDIDATES.items():
        params = apply_overrides(base, overrides)
        windows, [report] = build_windows(messages, params, count, names, tokenizer_name)
        s = window_stats(windows, report)
        gap_pct = s["gap_percentiles_s"]
        mpw, m = s["messages_per_window"], s["merges"]
        lines.append(
            f"| {name} | {s['n_windows']} | {s['single_message_pct']} | {mpw.get('p50')}/{mpw.get('p90')}/{mpw.get('max')} "
            f"| {s['tokens_per_window'].get('mean')} | {s['capped_windows']} | {m['reply']} | {m['burst']} "
            f"| {m['dependent']} | {m['mention']} | {m['gap']} | {m['cap']} |"
        )
    lines.append(f"\nIncluded messages: {report.n_included} · gap percentiles (s): {gap_pct} · "
                 f"orphan/stale replies: {report.orphan_replies}/{report.stale_replies} · "
                 f"unresolved mentions: {report.unresolved_mentions}\n")
    lines.extend(_boundary_pairs(messages, base, rng))
    return "\n".join(lines)


def _boundary_pairs(messages, params, rng) -> list[str]:
    """Consecutive pairs where the given rule is the deciding one, grouped by gap band."""
    included = sorted((m for m in messages if in_date_range(m, params) and not exclusion_reason(m, params)),
                      key=lambda m: (m.timestamp, m.id))
    by_id = {m.id: m for m in included}
    phrases = {normalize_phrase(p) for p in params.dependent_phrases}

    gap_pairs, burst_pairs, reply_pairs = [], [], []
    for prev, m in zip(included, included[1:]):
        gap = _gap(prev, m)
        has_reply = m.reply_to_id in by_id
        if prev.from_id == m.from_id and not has_reply:
            burst_pairs.append((gap, prev, m))
        elif not has_reply and not is_dependent(m.text, phrases):
            gap_pairs.append((gap, prev, m))
        if has_reply:
            parent = by_id[m.reply_to_id]
            reply_pairs.append((_gap(parent, m), parent, m))

    out = []
    for title, pairs, bands in (("Gap (different authors, no reply)", gap_pairs, GAP_BANDS),
                                ("Same-author burst", burst_pairs, BURST_BANDS),
                                ("Reply distance (parent → reply)", reply_pairs, REPLY_BANDS)):
        out.append(f"### {title}\n")
        for lo, hi in bands:
            in_band = [p for p in pairs if lo < p[0] <= hi]
            out.append(f"**{_fmt(lo)}–{_fmt(hi)}** ({len(in_band)} pairs)\n")
            for gap, a, b in rng.sample(in_band, min(PAIRS_PER_BAND, len(in_band))):
                out.append(f"- [{_fmt(gap)}] {_short(a)}\n  → {_short(b)}")
            out.append("")
    return out


def _short(m) -> str:
    text = render_body(m).replace("\n", " ")
    if len(text) > TEXT_CHARS:
        text = text[:TEXT_CHARS] + "…"
    return f"**{m.author}**: {text}"


def _fmt(seconds: float) -> str:
    return f"{seconds / 3600:g}h" if seconds >= 3600 else f"{seconds / 60:g}m"


if __name__ == "__main__":
    main()
