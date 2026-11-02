from collections import Counter
from collections.abc import Callable
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from core.annotation import (
    LABELS,
    Candidate,
    ChatData,
    append_label,
    label_record,
    labelled_keys,
    load_labels,
    pair_context,
    progress,
    remove_last_label,
)
from core.assisted_labels import replace_record, review_record
from core.models import ChatMessage
from core.windows import render_body

KEYS = {"y": "same", "s": "same", "n": "new", "e": "earlier", "?": "unsure"}
HELP = ("[bold]y[/] same conversation   [bold]n[/] new topic   [bold]e[/] continues an earlier message   "
        "[bold]?[/] unsure   [bold]u[/] undo   [bold]q[/] quit")
REVIEW_HELP = ("[bold]Enter[/] accept   [bold]y n e ?[/] change to same / new / earlier / unsure   "
               "[bold]k[/] skip   [bold]q[/] quit")
TEXT_CHARS = 400
PREVIEW_CHARS = 80


def run_session(
    queue: list[Candidate],
    chats: dict[str, ChatData],
    labels_path: Path,
    console: Console,
    before: int = 5,
    after: int = 2,
    getchar: Callable[[], str] = click.getchar,
) -> Counter:
    """Shows one pair at a time until the queue is done or the user quits.
    The labels file is re-read every step, so undo and resume need no state."""
    session = Counter()
    while True:
        records = load_labels(labels_path)
        done = labelled_keys(records)
        pending = [c for c in queue if c.key not in done]
        if not pending:
            console.print("\n[green]Queue complete.[/green]")
            return session

        c = pending[0]
        console.clear()
        console.print(_header(queue, pending, c), highlight=False)
        _show_pair(console, chats[c.chat], c, before, after)
        key = _read_key(getchar)
        if key == "q":
            return session
        if key == "u":
            undone = remove_last_label(labels_path)
            if undone:
                session[undone["label"]] -= 1
            continue
        append_label(labels_path, label_record(c, KEYS[key]))
        session[KEYS[key]] += 1


def _read_key(getchar: Callable[[], str]) -> str:
    while True:
        try:
            key = getchar().lower()
        except (KeyboardInterrupt, EOFError):
            return "q"
        if key in KEYS or key in ("u", "q"):
            return key


def _header(queue: list[Candidate], pending: list[Candidate], c: Candidate) -> str:
    n_chat = sum(x.chat == c.chat for x in queue)
    left_chat = sum(x.chat == c.chat for x in pending)
    return (f"[bold]{len(queue) - len(pending)}/{len(queue)}[/bold] labelled overall · "
            f"[cyan]{escape(c.chat)}[/cyan] {n_chat - left_chat}/{n_chat}")


def run_review(
    pending: list[dict],
    chats: dict[str, ChatData],
    by_key: dict[tuple[int, int], Candidate],
    labels_path: Path,
    console: Console,
    before: int = 5,
    after: int = 2,
    getchar: Callable[[], str] = click.getchar,
) -> Counter:
    """Walks the assistant's low-confidence labels: Enter keeps the proposal,
    a label key replaces it. Each decision is saved at once."""
    stats = Counter()
    for i, r in enumerate(pending, start=1):
        c = by_key.get((r["chat_id"], r["message_id"]))
        if c is None:
            continue
        console.clear()
        console.print(f"[bold]review {i}/{len(pending)}[/bold] · [cyan]{escape(c.chat)}[/cyan] · "
                      f"Claude proposes: [bold magenta]{r['label']}[/bold magenta]", highlight=False)
        _show_pair(console, chats[c.chat], c, before, after, REVIEW_HELP)
        key = _read_review_key(getchar)
        if key == "q":
            break
        if key == "k":
            stats["skipped"] += 1
            continue
        label = r["label"] if key == "enter" else KEYS[key]
        replace_record(labels_path, review_record(r, label))
        stats["accepted" if label == r["label"] else "changed"] += 1
    return stats


def _read_review_key(getchar: Callable[[], str]) -> str:
    while True:
        try:
            key = getchar().lower()
        except (KeyboardInterrupt, EOFError):
            return "q"
        if key in ("\r", "\n"):
            return "enter"
        if key in KEYS or key in ("k", "q"):
            return key


def print_progress(console: Console, queue: list[Candidate], records: list[dict], title: str = "Your labels") -> None:
    table = Table(title=title)
    table.add_column("chat")
    table.add_column("queue", justify="right")
    for label in LABELS:
        table.add_column(label, justify="right")
    table.add_column("labels", justify="right")
    totals = {"queue": 0, "done": 0, "labels": Counter()}
    for chat, row in progress(queue, records).items():
        table.add_row(escape(chat), f"{row['done']}/{row['queue']}",
                      *(str(row["labels"][lb]) for lb in LABELS), str(row["labels"].total()))
        totals["queue"] += row["queue"]
        totals["done"] += row["done"]
        totals["labels"] += row["labels"]
    table.add_section()
    table.add_row("[bold]total[/bold]", f"[bold]{totals['done']}/{totals['queue']}[/bold]",
                  *(str(totals["labels"][lb]) for lb in LABELS), f"[bold]{totals['labels'].total()}[/bold]")
    console.print(table)


def _show_pair(console: Console, chat: ChatData, c: Candidate, before: int, after: int, help_text: str = HELP) -> None:
    ctx, target, nxt = pair_context(chat, c, before, after)
    console.print(f"[dim]{escape(chat.title)} · {target.timestamp:%Y-%m-%d}[/dim]\n")
    for m in ctx:
        style = "bold" if m.id == c.prev_id else "dim"
        console.print(_line(m, chat), style=style, markup=False, highlight=False)
    console.rule(style="yellow")
    console.print(_line(target, chat), style="bold yellow", markup=False, highlight=False)
    console.rule(style="yellow")
    for m in nxt:
        console.print(_line(m, chat), style="dim italic", markup=False, highlight=False)
    console.print("\nDoes the [yellow]yellow[/yellow] message continue the conversation of the [bold]bold[/bold] one?")
    console.print(help_text)


def _line(m: ChatMessage, chat: ChatData) -> str:
    text = _clip(render_body(m).replace("\n", " ⏎ "), TEXT_CHARS)
    line = f"{m.timestamp:%H:%M}  {m.author}: {text}"
    parent = chat.by_id.get(m.reply_to_id) if m.reply_to_id is not None else None
    if parent is None:
        return line
    preview = _clip(render_body(parent).replace("\n", " "), PREVIEW_CHARS)
    return f"       ↪ reply to {parent.author}: “{preview}”\n{line}"


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"
