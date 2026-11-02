import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from core.ingest.telegram import parse_telegram_chat
from core.topics import (
    OUTLIER,
    center_by_language,
    guess_language,
    fit_topics,
    load_stop_words,
    load_topic_params,
    params_hash,
    save_topics,
    summarize,
    topics_dir,
    topics_markdown,
)
from core.window_embeddings import (
    chat_and_hash,
    embed_texts,
    embeddings_dir,
    is_current,
    load_embeddings,
    load_windows,
    save_embeddings,
    window_text,
)

TOPICS_CONFIG = Path("config/topics.yaml")
console = Console()

WindowsDir = Annotated[Path, typer.Argument(help="A windows folder: data/windows/<chat>/<config_hash> (printed by `windows`)")]


def embed(
    ctx: typer.Context,
    windows_dir: WindowsDir,
    force: Annotated[bool, typer.Option(help="Recompute even if the cached vectors are current")] = False,
):
    """Computes one E5 vector per window and saves it in data/embeddings/<chat>/<config_hash>/."""
    _quiet(ctx)
    texts = _window_texts(ctx, windows_dir)
    out = embeddings_dir(windows_dir)
    emb_cfg = ctx.obj["config"]["embedding"]
    ids = [wid for wid, text in texts.items() if text]
    if not force and is_current(out, emb_cfg["model_name"], ids):
        console.print(f"Embeddings already current: {escape(str(out))} ({len(ids)} windows)")
        return
    console.print(f"Encoding {len(ids)} windows ({len(texts) - len(ids)} without text skipped)...")
    vectors = embed_texts([texts[i] for i in ids], emb_cfg)
    save_embeddings(out, ids, vectors, {"model": emb_cfg["model_name"], "prefix": emb_cfg.get("query_prefix", "query: "),
                                        "windows_dir": str(windows_dir)})
    console.print(f"Written to [cyan]{escape(str(out))}[/cyan]: vectors.npy {vectors.shape}, meta.json")


def discover(
    ctx: typer.Context,
    windows_dir: WindowsDir,
    topics_config: Annotated[Path, typer.Option(help="Topic parameters file")] = TOPICS_CONFIG,
    min_topic_size: Annotated[int | None, typer.Option(help="Smallest group that counts as a topic")] = None,
    min_samples: Annotated[int | None, typer.Option(help="HDBSCAN min_samples: higher = more outliers")] = None,
    n_neighbors: Annotated[int | None, typer.Option(help="UMAP neighbours: small = local structure")] = None,
    min_words: Annotated[int | None, typer.Option(help="Windows with fewer words are left out")] = None,
    center_languages: Annotated[bool | None, typer.Option(help="Remove the per-language mean from the vectors")] = None,
    cluster_selection: Annotated[str | None, typer.Option(help="HDBSCAN: eom (few large topics) or leaf (many small)")] = None,
):
    """Runs BERTopic on the window embeddings and saves topics, assignments and a readable report."""
    _quiet(ctx)
    params = load_topic_params(topics_config, {"min_topic_size": min_topic_size, "min_samples": min_samples,
                                               "n_neighbors": n_neighbors, "min_words": min_words,
                                               "center_languages": center_languages, "cluster_selection": cluster_selection})
    stop_words = load_stop_words(Path(params.stop_words_file))
    texts = _window_texts(ctx, windows_dir)
    emb_dir = embeddings_dir(windows_dir)
    if not (emb_dir / "meta.json").exists():
        typer.echo(f"Error: no embeddings for {windows_dir}; run `embed {windows_dir}` first", err=True)
        raise typer.Exit(code=1)
    ids, vectors, emb_meta = load_embeddings(emb_dir)
    keep = [i for i, wid in enumerate(ids) if len(texts.get(wid, "").split()) >= params.min_words]
    if len(keep) <= params.min_topic_size:
        typer.echo(f"Error: only {len(keep)} windows with ≥{params.min_words} words: too few for topics", err=True)
        raise typer.Exit(code=1)
    fit_ids, fit_vectors = [ids[i] for i in keep], vectors[keep]
    languages = [guess_language(texts[i]) for i in fit_ids]
    if params.center_languages:
        fit_vectors = center_by_language(fit_vectors, languages)
    console.print(f"Fitting BERTopic on {len(fit_ids)} windows "
                  f"({len(texts) - len(fit_ids)} left out: no text or < {params.min_words} words)...")
    model, topics = fit_topics([texts[i] for i in fit_ids], fit_vectors, params, stop_words)

    chat, windows_hash = chat_and_hash(windows_dir)
    out = topics_dir(chat, windows_hash, params_hash(params, stop_words))
    summary = summarize(model, topics, fit_ids, fit_vectors, params.n_examples)
    n_out = sum(t == OUTLIER for t in topics)
    meta = {"chat": chat, "windows_dir": str(windows_dir), "embedding_model": emb_meta["model"],
            "params": {**params.__dict__}, "n_windows": len(texts), "n_fitted": len(fit_ids),
            "n_topics": len({t for t in topics} - {OUTLIER}), "n_outliers": n_out,
            "languages": {lang: languages.count(lang) for lang in sorted(set(languages))},
            "created_at": datetime.now().isoformat(timespec="seconds")}
    save_topics(out, summary, dict(zip(fit_ids, topics)), meta)
    (out / "topics.md").write_text(topics_markdown(summary, texts, f"{chat} · {meta['n_topics']} topics"), encoding="utf-8")
    _print_topics(summary, len(fit_ids), n_out)
    console.print(f"\nWritten to [cyan]{escape(str(out))}[/cyan]: topics.md, topics.json, assignments.jsonl, meta.json")


def _window_texts(ctx: typer.Context, windows_dir: Path) -> dict[str, str]:
    if not (windows_dir / "windows.jsonl").exists():
        typer.echo(f"Error: {windows_dir}/windows.jsonl not found; build windows first with `windows`", err=True)
        raise typer.Exit(code=1)
    chat, _ = chat_and_hash(windows_dir)
    export = Path(ctx.obj["config"]["paths"]["raw_data"]) / f"{chat}.json"
    _, messages = parse_telegram_chat(export)
    by_id = {m.id: m for m in messages}
    return {w["window_id"]: window_text(w, by_id) for w in load_windows(windows_dir)}


def _quiet(ctx: typer.Context) -> None:
    if not ctx.obj["verbose"]:
        for name in ("cribrum.ingest", "cribrum.embeddings", "sentence_transformers", "BERTopic"):
            logging.getLogger(name).setLevel(logging.WARNING)


def _print_topics(summary: list[dict], n_fitted: int, n_outliers: int) -> None:
    table = Table(title=f"{len(summary) - (n_outliers > 0)} topics · outliers {n_outliers}/{n_fitted} "
                        f"({100 * n_outliers / n_fitted:.0f}%)")
    table.add_column("topic", justify="right")
    table.add_column("windows", justify="right")
    table.add_column("keywords")
    for rec in sorted(summary, key=lambda r: -r["size"]):
        if rec["topic"] != OUTLIER:
            table.add_row(str(rec["topic"]), str(rec["size"]), escape(", ".join(w for w, _ in rec["keywords"][:7])))
    console.print(table)
