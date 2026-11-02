import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cli.annotate import print_progress, run_review
from core.annotation import (
    LABELS,
    Candidate,
    ChatData,
    build_queue,
    candidate_pairs,
    drop_blocked_labels,
    labelled_keys,
    load_chat,
    load_labels,
)
from core.assisted_labels import (
    agreement,
    binary_agreement,
    assistant_queue,
    batch_text,
    calibration_batch,
    import_answers,
    next_batch,
    parse_answers,
    to_review,
)
from core.config import blocked_ids, export_paths
from core.window_config import WindowParams, load_window_params

HUMAN_LABELS = Path("data/labels/merge_pairs.jsonl")
ASSISTANT_LABELS = Path("data/labels/claude_pairs.jsonl")
BATCH_DIR = Path("data/labels/batches")          # contains chat text: git-ignored
HUMAN_TARGET, HUMAN_SEED = 300, 42
ASSISTANT_TARGET, ASSISTANT_SEED = 3000, 7
WINDOWS_CONFIG = Path("config/windows.yaml")

labels_app = typer.Typer(help="Assistant-proposed labels: export batches, import answers, review, status.")
console = Console()


@dataclass
class LabelSetup:
    chats: dict[str, ChatData]
    candidates: dict[str, list[Candidate]]
    human_queue: list[Candidate]
    params: WindowParams

    def by_key(self) -> dict[tuple[int, int], Candidate]:
        return {c.key: c for cands in self.candidates.values() for c in cands}

    def by_stem_id(self) -> dict[tuple[str, int], Candidate]:
        return {(c.chat, c.message_id): c for cands in self.candidates.values() for c in cands}


def load_setup(
    ctx: typer.Context,
    windows_config: Path = WINDOWS_CONFIG,
    chat: list[str] | None = None,
    label_files: tuple[Path, ...] = (HUMAN_LABELS, ASSISTANT_LABELS),
    human_target: int = HUMAN_TARGET,
    human_seed: int = HUMAN_SEED,
) -> LabelSetup:
    """Loads the exports, drops labels of blocked accounts and builds the candidate pairs."""
    cfg = ctx.obj["config"]
    if not ctx.obj["verbose"]:
        logging.getLogger("cribrum.ingest").setLevel(logging.WARNING)
    dates = cfg.get("dates", {})
    params, _ = load_window_params(windows_config, {"min_date": dates.get("min_date"),
                                                    "max_date": dates.get("max_date"),
                                                    "blocked_ids": blocked_ids(cfg)})
    paths = [p for p in export_paths(cfg) if not chat or p.stem in chat]
    if not paths:
        typer.echo("Error: no exports selected", err=True)
        raise typer.Exit(code=1)

    chats = {p.stem: load_chat(p, params) for p in paths}
    for path in label_files:
        dropped = drop_blocked_labels(path, chats, params.blocked_ids)
        if dropped:
            console.print(f"Removed {len(dropped)} labels involving blocked accounts from {path}")
    candidates = {stem: candidate_pairs(stem, c.included, params) for stem, c in chats.items()}
    return LabelSetup(chats, candidates, build_queue(candidates, human_target, human_seed), params)


@labels_app.command("export")
def export(
    ctx: typer.Context,
    size: Annotated[int, typer.Option(help="Pairs per batch")] = 100,
    batches: Annotated[int, typer.Option(help="How many batch files to write")] = 1,
    calibration: Annotated[bool, typer.Option(help="Export the pairs you already labelled (labels hidden)")] = False,
    target: Annotated[int, typer.Option(help="Size of the assistant queue")] = ASSISTANT_TARGET,
    seed: Annotated[int, typer.Option(help="Seed of the assistant queue")] = ASSISTANT_SEED,
    before: Annotated[int, typer.Option(help="Context messages before the pair")] = 5,
    after: Annotated[int, typer.Option(help="Messages after the pair")] = 2,
):
    """Writes batches of unlabelled pairs as text, for the assistant to label."""
    s = load_setup(ctx)
    done = labelled_keys(load_labels(ASSISTANT_LABELS))
    human = load_labels(HUMAN_LABELS)
    if calibration:
        items = calibration_batch(human, done, s.by_key(), size * batches)
    else:
        reserved = {c.key for c in s.human_queue} | labelled_keys(human)
        items = next_batch(assistant_queue(s.candidates, reserved, target, seed), done, size * batches)
    if not items:
        console.print("Nothing left to export.")
        return

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    first = len(list(BATCH_DIR.glob("batch_*.md"))) + 1
    kind = "calibration" if calibration else "pairs"
    for i in range(0, len(items), size):
        n = first + i // size
        path = BATCH_DIR / f"batch_{n:03d}_{kind}.md"
        path.write_text(batch_text(items[i:i + size], s.chats, before, after, f"Batch {n:03d} ({kind})"),
                        encoding="utf-8")
        console.print(f"{path}  ({len(items[i:i + size])} pairs) → answers in {path.with_suffix('.answers.txt')}")


@labels_app.command("import")
def import_cmd(
    ctx: typer.Context,
    answers: Annotated[list[Path], typer.Argument(help="Answer files (<key> <label> <high|low> per line)")],
):
    """Adds the assistant's answers to data/labels/claude_pairs.jsonl."""
    s = load_setup(ctx)
    by_stem_id = s.by_stem_id()
    for path in answers:
        parsed, errors = parse_answers(path.read_text(encoding="utf-8"))
        n, unknown = import_answers(parsed, by_stem_id, ASSISTANT_LABELS)
        console.print(f"{path}: imported {n}" + (f", {len(errors)} malformed lines" if errors else "")
                      + (f", {len(unknown)} unknown pairs" if unknown else ""))
        for line in errors[:10] + unknown[:10]:
            console.print(f"  [red]{escape(line)}[/red]")


@labels_app.command("review")
def review(
    ctx: typer.Context,
    before: Annotated[int, typer.Option(help="Context messages before the pair")] = 5,
    after: Annotated[int, typer.Option(help="Messages after the pair")] = 2,
):
    """Shows the pairs the assistant was unsure about: accept or correct them."""
    s = load_setup(ctx)
    pending = to_review(load_labels(ASSISTANT_LABELS), labelled_keys(load_labels(HUMAN_LABELS)))
    if not pending:
        console.print("Nothing to review.")
    else:
        stats = run_review(pending, s.chats, s.by_key(), ASSISTANT_LABELS, console, before, after)
        console.print(f"\nThis session: {dict(stats) or 'nothing reviewed'}")
    print_status(s, HUMAN_LABELS)


@labels_app.command("status")
def status(ctx: typer.Context):
    """Progress of your labels, the assistant's labels and how often you agree."""
    print_status(load_setup(ctx), HUMAN_LABELS)


def print_status(s: LabelSetup, human_path: Path) -> None:
    human = load_labels(human_path)
    print_progress(console, s.human_queue, human)
    assistant = load_labels(ASSISTANT_LABELS)
    if assistant:
        _print_assistant_table(assistant, labelled_keys(human))
    n, agree, confusion = agreement(human, assistant)
    if n:
        console.print(f"\nAgreement with your labels: [bold]{agree}/{n} ({100 * agree / n:.0f}%)[/bold]")
        b_n, b_agree = binary_agreement(confusion)
        if b_n:
            console.print(f"Merge / don't merge (new = earlier, unsure left out): "
                          f"[bold]{b_agree}/{b_n} ({100 * b_agree / b_n:.0f}%)[/bold]")
        for (h, a), v in sorted(confusion.items(), key=lambda kv: -kv[1]):
            if h != a:
                console.print(f"  you {h}, Claude {a}: {v}")
    console.print(f"[dim]your labels: {human_path} · Claude's: {ASSISTANT_LABELS}[/dim]")


def _print_assistant_table(records: list[dict], human_keys: set[tuple[int, int]]) -> None:
    table = Table(title="Claude's labels")
    for col in ("chat", *LABELS, "low", "reviewed", "to review", "total"):
        table.add_column(col, justify="left" if col == "chat" else "right")
    pending = {(r["chat_id"], r["message_id"]) for r in to_review(records, human_keys)}
    rows: dict[str, dict] = {}
    for r in records:
        row = rows.setdefault(r["chat"], {lb: 0 for lb in (*LABELS, "low", "reviewed", "pending", "total")})
        row[r["label"]] += 1
        row["low"] += r.get("confidence") == "low"
        row["reviewed"] += r["source"] == "claude_reviewed"
        row["pending"] += (r["chat_id"], r["message_id"]) in pending
        row["total"] += 1
    totals = {k: sum(row[k] for row in rows.values()) for k in (*LABELS, "low", "reviewed", "pending", "total")}
    for chat in sorted(rows, key=str.lower):
        table.add_row(escape(chat), *(str(v) for v in rows[chat].values()))
    table.add_section()
    table.add_row("[bold]total[/bold]", *(f"[bold]{v}[/bold]" for v in totals.values()))
    console.print(table)
