import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from core.config import (
    blocked_ids, blocklist_path, export_paths, load_blocklist, load_config, match_accounts, save_blocklist,
)
from core.ingest.telegram import parse_telegram_export
from core.chunking import build_all_qa_messages, looks_like_question
from core.debug import dump_messages_to_json
from core.vectorstore import get_collection, add_messages
from core.search import search as run_search
from core.ingest.telegram import parse_telegram_chat
from core.tokens import get_token_counter
from core.window_config import load_window_params
from core.windows import build_windows
from core.merge_decider import decider_for, load_model
from core.window_report import (
    sample_windows, window_stats, windows_markdown, write_jsonl, write_meta,
)
from cli.annotate import run_session
from cli.labels import ASSISTANT_LABELS, labels_app, load_setup, print_status
from cli.merge import merge_app
from cli.topics import discover, embed
from cli.vault import export
from cli.facets import facets

app = typer.Typer(help="Local semantic search over university course group chats.")
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    config: Annotated[Path, typer.Option(help="Path to config.yaml")] = Path("config.yaml"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug output")] = False,
):
    if not config.exists():
        typer.echo(f"Error: config not found at {config}", err=True)
        raise typer.Exit(code=1)

    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    logger = logging.getLogger("cribrum")

    cfg = load_config(config)

    ctx.obj = {
        "config": cfg,
        "verbose": verbose,
        "logger": logger,
    }

    if verbose:
        logger.debug(f"Config loaded from: {config}")
        logger.debug(f"Config content: {cfg}")

    if ctx.invoked_subcommand is None:
        print("TODO: start the REPL here")


@app.command()
def ingest(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="result.json file or export folder")],
    source: Annotated[str, typer.Option(help="Chat source")] = "telegram",
    reset: Annotated[bool, typer.Option(help="Wipe the index before re-indexing")] = False,
    dump_json: Annotated[Path | None, typer.Option(help="Writes the resulting messages to a debug JSON file")] = None,
    course: Annotated[str | None, typer.Option(help="Course this export belongs to (e.g. \"Analisi 1\")")] = None,
):
    """Indexes one or more chat exports."""
    logger = ctx.obj["logger"]
    cfg = ctx.obj["config"]
    verbose = ctx.obj["verbose"]
    min_text_length = cfg["ingest"]["min_text_length"]

    if verbose:
        logger.debug(f"Starting ingest of: {path}")
        logger.debug(f"Source: {source}")
        logger.debug(f"Reset: {reset}")
        logger.debug(f"Course: {course}")
        logger.debug(f"min_text_length (from config): {min_text_length}")

    all_messages = parse_telegram_export(path, logger)
    synthetic = build_all_qa_messages(all_messages, logger)
    standalone = [m for m in all_messages if len(m.text.strip()) >= min_text_length]

    # Dedup: a standalone message already "absorbed" into a synthetic chunk
    # (part of an explicit thread or an implicit adjacent pair) must not be
    # indexed again on its own, otherwise its content ends up duplicated in
    # the index (once isolated, once inside the full thread context).
    absorbed_ids = {sid for s in synthetic for sid in s.source_ids}
    before = len(standalone)
    standalone = [m for m in standalone if m.id not in absorbed_ids]

    if verbose:
        logger.debug(f"Standalone before dedup: {before}, after: {len(standalone)} "
                      f"({before - len(standalone)} absorbed into synthetic threads)")

    # A standalone question that survived the dedup was never absorbed into
    # any thread, so nobody answered it in the group.
    unanswered_ids = {m.id for m in standalone if looks_like_question(m.text)}

    if verbose:
        logger.debug(f"Unanswered questions among standalone: {len(unanswered_ids)}")

    to_index = standalone + synthetic

    # Tag every message (synthetic included, since chunking doesn't copy the
    # course field) so multiple exports can share one collection.
    for m in to_index:
        m.course = course

    logger.info(f"Ready to index: {len(standalone)} standalone + {len(synthetic)} synthetic = {len(to_index)}")

    if dump_json is not None:
        dump_messages_to_json(to_index, dump_json)
        logger.info(f"Dumped {len(to_index)} messages to {dump_json}")

    collection = get_collection(
        db_path=cfg["paths"]["chroma_db"],
        collection_name=cfg["vectorstore"]["collection_name"],
        reset=reset,
        logger=logger,
    )

    add_messages(
        collection=collection,
        messages=to_index,
        model_name=cfg["embedding"]["model_name"],
        batch_size=cfg["embedding"]["batch_size"],
        passage_prefix=cfg["embedding"]["passage_prefix"],
        unanswered_ids=unanswered_ids,
        logger=logger,
    )


OUTCOME_BADGES = {
    "found": "[bold black on green] FOUND [/]",
    "question_found_no_answer": "[bold black on yellow] QUESTION FOUND, NO ANSWER [/]",
    "not_found": "[bold white on red] NOT FOUND [/]",
}


@app.command()
def search(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Question to search for")],
    k: Annotated[int, typer.Option(help="Number of results")] = None,
    course: Annotated[str | None, typer.Option(help="Only search messages of this course")] = None,
):
    """Single (non-interactive) search."""
    logger = ctx.obj["logger"]
    cfg = ctx.obj["config"]
    k = k or cfg["search"]["default_k"]

    collection = get_collection(
        db_path=cfg["paths"]["chroma_db"],
        collection_name=cfg["vectorstore"]["collection_name"],
        logger=logger,
    )

    outcome, results = run_search(
        collection=collection,
        query_text=query,
        model_name=cfg["embedding"]["model_name"],
        k=k,
        query_prefix=cfg["embedding"]["query_prefix"],
        min_similarity=cfg["search"]["min_similarity"],
        course=course,
        logger=logger,
    )

    # escape(): user/chat strings may contain [brackets] that rich would parse as markup
    scope = f" in [cyan]{escape(course)}[/cyan]" if course else ""
    console.print(f"\n{OUTCOME_BADGES[outcome]}  {escape(repr(query))}{scope}\n")

    for i, r in enumerate(results, start=1):
        kind = "thread" if r.is_synthetic else "message"
        header = f"[bold]{i}. {r.similarity:.3f}[/bold]  [dim]{kind} · {escape(r.author)} · {r.timestamp[:10]}"
        if r.course:
            header += f" · {escape(r.course)}"
        header += "[/dim]"
        if r.is_unanswered_question:
            header += "  [yellow](unanswered)[/yellow]"
        console.print(header)
        console.print(r.text, markup=False)
        console.print()


@app.command()
def windows(
    ctx: typer.Context,
    chat: Annotated[str, typer.Argument(help="Export JSON path, or its name in data/exports (e.g. datamining)")],
    windows_config: Annotated[Path, typer.Option(help="Window parameters file")] = Path("config/windows.yaml"),
    out: Annotated[Path, typer.Option(help="Output root; files go to <out>/<chat>/<config_hash>/")] = Path("data/windows"),
    chat_type: Annotated[str | None, typer.Option(help="Force chat type: course | general")] = None,
    gap_course: Annotated[int | None, typer.Option(help="Temporal gap for course chats (s)")] = None,
    gap_general: Annotated[int | None, typer.Option(help="Temporal gap for general chats (s)")] = None,
    reply_max_gap: Annotated[int | None, typer.Option(help="Max reply distance (s)")] = None,
    burst_gap: Annotated[int | None, typer.Option(help="Same-author burst gap (s)")] = None,
    dependent_gap: Annotated[int | None, typer.Option(help="Dependent-message gap (s)")] = None,
    mention_gap: Annotated[int | None, typer.Option(help="Mention gap (s)")] = None,
    max_messages: Annotated[int | None, typer.Option(help="Window cap in messages")] = None,
    max_tokens: Annotated[int | None, typer.Option(help="Window cap in tokens")] = None,
    overlap: Annotated[int | None, typer.Option(help="Messages repeated after a cap split")] = None,
    min_date: Annotated[str | None, typer.Option(help="Ignore messages before this ISO date (default: config.yaml dates)")] = None,
    max_date: Annotated[str | None, typer.Option(help="Ignore messages from this ISO date on (default: config.yaml dates)")] = None,
    sample: Annotated[int | None, typer.Option(help="Number of random windows for sample.md")] = None,
    seed: Annotated[int | None, typer.Option(help="Seed for the random sample")] = None,
    top: Annotated[int | None, typer.Option(help="How many of the longest windows to list")] = None,
    merge_model: Annotated[Path | None, typer.Option(help="Trained merge model (merge train) replacing the gap rule")] = None,
):
    """Builds conversation windows for one chat and prints inspection stats."""
    logger = ctx.obj["logger"]
    cfg = ctx.obj["config"]

    path = Path(chat)
    if not path.exists():
        path = Path(cfg["paths"]["raw_data"]) / f"{chat}.json"
    if not path.exists():
        typer.echo(f"Error: chat export not found: {chat}", err=True)
        raise typer.Exit(code=1)

    chat_info, messages = parse_telegram_chat(path, logger)
    overrides = {
        "gap_course": gap_course, "gap_general": gap_general, "reply_max_gap": reply_max_gap,
        "burst_gap": burst_gap, "dependent_gap": dependent_gap, "mention_gap": mention_gap,
        "max_messages": max_messages, "max_tokens": max_tokens, "overlap": overlap,
        "min_date": min_date or cfg.get("dates", {}).get("min_date"),
        "max_date": max_date or cfg.get("dates", {}).get("max_date"),
        "blocked_ids": blocked_ids(cfg),
    }
    if chat_type is not None:
        overrides["chat_types"] = {str(chat_info["id"]): chat_type}
    decider = None
    if merge_model is not None:
        model, overrides["merge_model"] = load_model(merge_model)
        decider = decider_for(model)
    params, inspect = load_window_params(windows_config, overrides)

    count_tokens, tokenizer_name = get_token_counter(params.tokenizer_model, logger)
    built, reports = build_windows(
        messages, params, count_tokens, {chat_info["id"]: chat_info["name"]}, tokenizer_name, logger, decider,
    )
    report = reports[0]
    stats = window_stats(built, report, top=top or inspect.get("top_longest", 5))

    out_dir = out / path.stem / report.config_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    by_id = {m.id: m for m in messages}
    write_jsonl(built, out_dir / "windows.jsonl")
    write_meta(params, stats, out_dir / "meta.json")
    (out_dir / "windows.md").write_text(
        windows_markdown(built, by_id, f"{chat_info['name']} · config {report.config_hash}"), encoding="utf-8",
    )

    n_sample = sample if sample is not None else inspect.get("sample_size", 20)
    seed = seed if seed is not None else inspect.get("seed", 42)
    picked = sample_windows(built, n_sample, seed)
    (out_dir / "sample.md").write_text(
        windows_markdown(picked, by_id, f"{chat_info['name']} · sample of {len(picked)} (seed {seed})"),
        encoding="utf-8",
    )

    _print_window_stats(stats)
    console.print(f"\nWritten to [cyan]{escape(str(out_dir))}[/cyan]: windows.jsonl, windows.md, sample.md, meta.json")


@app.command()
def annotate(
    ctx: typer.Context,
    labels: Annotated[Path, typer.Option(help="Labels file (JSONL, appended)")] = Path("data/labels/merge_pairs.jsonl"),
    target: Annotated[int, typer.Option(help="Pairs in the queue, over all chats")] = 300,
    seed: Annotated[int, typer.Option(help="Seed of the queue: keep it fixed to resume")] = 42,
    chat: Annotated[list[str] | None, typer.Option(help="Only these exports (name in data/exports); repeatable")] = None,
    before: Annotated[int, typer.Option(help="Context messages shown before the pair")] = 5,
    after: Annotated[int, typer.Option(help="Messages shown after the pair")] = 2,
    windows_config: Annotated[Path, typer.Option(help="Window parameters file")] = Path("config/windows.yaml"),
    status: Annotated[bool, typer.Option("--status", help="Only print the progress per chat, then exit")] = False,
):
    """Labels message pairs (same conversation or not) to train the merge model.
    Resumes where the last session stopped, as long as --target and --seed are unchanged."""
    setup = load_setup(ctx, windows_config, chat, (labels, ASSISTANT_LABELS), target, seed)
    if not status:
        session = run_session(setup.human_queue, setup.chats, labels, console, before, after)
        console.print(f"\nThis session: {dict(+session) or 'nothing labelled'}")
    print_status(setup, labels)
    console.print(f"[dim]queue: {len(setup.human_queue)} pairs (target {target}, seed {seed})[/dim]")


def _quiet_parser(ctx: typer.Context) -> None:
    """Per-export "Read N messages" lines are noise in interactive commands."""
    if not ctx.obj["verbose"]:
        logging.getLogger("cribrum.ingest").setLevel(logging.WARNING)


blocklist_app = typer.Typer(help="Accounts whose messages are dropped from windows and annotation.")
app.add_typer(blocklist_app, name="blocklist")
app.add_typer(labels_app, name="labels")
app.add_typer(merge_app, name="merge")
app.command()(embed)
app.command()(discover)
app.command()(export)
app.command()(facets)


@blocklist_app.command("list")
def blocklist_list(ctx: typer.Context):
    """Shows the blocked accounts."""
    accounts = load_blocklist(blocklist_path(ctx.obj["config"]))
    if not accounts:
        console.print("Blocklist is empty.")
    for fid, name in accounts.items():
        console.print(f"{fid}  {escape(name)}")


@blocklist_app.command("add")
def blocklist_add(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="from_id (e.g. user386048772) or part of the display name")],
    all_matches: Annotated[bool, typer.Option("--all", help="Block every account matching the name")] = False,
):
    """Blocks an account, looked up among the authors of the exports."""
    cfg = ctx.obj["config"]
    _quiet_parser(ctx)
    authors = {}
    for p in export_paths(cfg):
        _, messages = parse_telegram_chat(p)
        authors.update({m.from_id: m.author for m in messages if m.from_id and m.kind != "service"})
    matches = match_accounts(authors, query)
    if not matches:
        typer.echo(f"Error: no author matches '{query}'", err=True)
        raise typer.Exit(code=1)
    if len(matches) > 1 and not all_matches:
        for fid, name in sorted(matches.items(), key=lambda kv: kv[1]):
            console.print(f"{fid}  {escape(name)}")
        typer.echo(f"{len(matches)} accounts match: pass a from_id, or --all to block them all", err=True)
        raise typer.Exit(code=1)
    path = blocklist_path(cfg)
    accounts = load_blocklist(path) | matches
    save_blocklist(path, accounts)
    for fid, name in matches.items():
        console.print(f"Blocked {fid}  {escape(name)}")


@blocklist_app.command("remove")
def blocklist_remove(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="from_id or part of the name of a blocked account")],
):
    """Unblocks an account."""
    path = blocklist_path(ctx.obj["config"])
    accounts = load_blocklist(path)
    matches = match_accounts(accounts, query)
    if len(matches) != 1:
        typer.echo(f"Error: '{query}' matches {len(matches)} blocked accounts, expected 1", err=True)
        raise typer.Exit(code=1)
    (fid, name), = matches.items()
    del accounts[fid]
    save_blocklist(path, accounts)
    console.print(f"Unblocked {fid}  {escape(name)}")


def _print_window_stats(stats: dict) -> None:
    console.print(f"\n[bold]{escape(stats['chat_name'])}[/bold] [dim]({stats['chat_type']}, "
                  f"config {stats['config_hash']}, {escape(stats['tokenizer'])})[/dim]\n")

    overview = Table(show_header=False, box=None)
    overview.add_row("raw messages", str(stats["n_raw_messages"]))
    overview.add_row("in windows", str(stats["n_included_messages"]))
    overview.add_row("excluded", escape(str(stats["excluded"] or "none")))
    overview.add_row("service actions", escape(str(stats["service_actions"] or "none")))
    overview.add_row("gap percentiles (s)", str(stats["gap_percentiles_s"]))
    overview.add_row("windows", str(stats["n_windows"]))
    overview.add_row("messages / window", str(stats["messages_per_window"]))
    overview.add_row("tokens / window", str(stats["tokens_per_window"]))
    overview.add_row("single-message windows", f"{stats['single_message_pct']}%")
    overview.add_row("short windows", str(stats["short_windows"]))
    overview.add_row("windows closed by cap", str(stats["capped_windows"]))
    overview.add_row("orphan / stale replies", f"{stats['orphan_replies']} / {stats['stale_replies']}")
    overview.add_row("replies to excluded", str(stats["replies_to_excluded"]))
    overview.add_row("unresolved @mentions", str(stats["unresolved_mentions"]))
    console.print(overview)

    merges = Table(title="Merges by rule")
    merges.add_column("rule")
    merges.add_column("count", justify="right")
    for rule, count in stats["merges"].items():
        merges.add_row(rule, str(count))
    console.print(merges)

    longest = Table(title="Longest windows")
    for col in ("window", "messages", "tokens", "from", "to"):
        longest.add_column(col)
    for w in stats["longest_windows"]:
        longest.add_row(w["window_id"], str(w["n_messages"]), str(w["n_tokens"]), w["first_ts"], w["last_ts"])
    console.print(longest)


if __name__ == "__main__":
    app()