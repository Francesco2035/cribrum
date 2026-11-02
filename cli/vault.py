import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from rich.console import Console
from rich.markup import escape

from core import facet_vault as fv
from core.facets import load_facets, latest_facets_dir, shared_space
from core.topic_results import ChatResult, latest_topics_dirs, load_chat_result
from core.topics import OUTLIER, center_by_language, guess_language
from core.vault import (
    TopicNote,
    VaultParams,
    assign_names,
    link_similar,
    load_vault_params,
    render_chat_note,
    render_index,
    render_topic_note,
    reset_generated,
    safe_name,
    topic_windows,
    write_graph_settings,
    write_note,
)

VAULT_CONFIG = Path("config/vault.yaml")
console = Console()


def export(
    ctx: typer.Context,
    topics_dirs: Annotated[list[Path] | None, typer.Argument(help="With --by topics: results of `discover` (default: the latest per chat)")] = None,
    by: Annotated[str, typer.Option(help="facets (default when `facets` has been run) or topics")] = "auto",
    facets_dir: Annotated[Path | None, typer.Option(help="With --by facets: a `facets` result (default: the latest)")] = None,
    vault: Annotated[Path, typer.Option(help="Obsidian vault folder (open it in Obsidian as a vault)")] = Path("vault"),
    vault_config: Annotated[Path, typer.Option(help="Export parameters")] = VAULT_CONFIG,
):
    """Writes an Obsidian vault, organised by facets (shared themes + concepts per chat) or by topics."""
    if not ctx.obj["verbose"]:
        logging.getLogger("cribrum.ingest").setLevel(logging.WARNING)
    params = load_vault_params(vault_config)
    facets_dir = facets_dir or latest_facets_dir()
    mode = ("facets" if facets_dir else "topics") if by == "auto" else by
    if mode not in ("facets", "topics"):
        typer.echo("Error: --by must be 'facets' or 'topics'", err=True)
        raise typer.Exit(code=1)
    if mode == "facets" and facets_dir is None:
        typer.echo("Error: no facets result found; run `facets` first or use --by topics", err=True)
        raise typer.Exit(code=1)
    raw_dir = Path(ctx.obj["config"]["paths"]["raw_data"])
    if mode == "facets":
        _export_facets(facets_dir, raw_dir, vault, params)
    else:
        dirs = topics_dirs or latest_topics_dirs()
        if not dirs:
            typer.echo("Error: no topic results found; run `discover` first", err=True)
            raise typer.Exit(code=1)
        _export_topics([load_chat_result(d, raw_dir) for d in dirs], vault, params)


def _export_facets(facets_dir: Path, raw_dir: Path, vault: Path, params: VaultParams) -> None:
    records, prototypes, assignments, meta = load_facets(facets_dir)
    console.print(f"Facets from {escape(str(facets_dir))} ({meta['n_facets']} facets, {len(meta['chats'])} chats)")
    results = {r.chat: r for r in (load_chat_result(Path(d), raw_dir) for d in meta["topics_dirs"])}
    views = fv.facet_views(records, prototypes, assignments)
    fv.name_facets(views, params.label_words)
    fv.link_facets(views, params.top_k, params.min_similarity)

    reset_generated(vault)
    chat_notes = {c: safe_name(r.title) for c, r in results.items()}
    without = {c: 0 for c in results}
    for a in assignments:
        if not a["facet"]:
            without[a["chat"]] += 1
    for v in views:
        if v.kind == "shared":
            write_note(vault / "facets" / f"{v.name}.md", fv.render_facet_note(v, results, chat_notes))
            for chat in v.chats:
                write_note(vault / "notes" / chat / f"{fv.chat_facet_name(chat, v)}.md",
                           fv.render_chat_facet_note(chat, v, results[chat], chat_notes[chat], params))
        else:
            chat = v.chats[0]
            write_note(vault / "concepts" / chat / f"{v.name}.md",
                       fv.render_concept_note(v, results[chat], chat_notes[chat], params))
    for chat, r in results.items():
        write_note(vault / "chats" / f"{chat_notes[chat]}.md", fv.render_chat_note(r, views, without[chat]))
    write_note(vault / "index.md", fv.render_index([(chat_notes[c], r.title) for c, r in results.items()], views,
                                                   datetime.now().isoformat(timespec="minutes")))
    shared = [v for v in views if v.kind == "shared"]
    _done(vault, f"{len(shared)} shared facets ({sum(len(v.chats) for v in shared)} chat·facet notes), "
                 f"{len(views) - len(shared)} concepts, {len(results)} chats")


def _export_topics(results: list[ChatResult], vault: Path, params: VaultParams) -> None:
    notes, centred_by_chat = [], {}
    for r in results:
        centred_by_chat[r.chat] = _chat_space(r)
        members = topic_windows(r.summary, r.assignments, r.windows, centred_by_chat[r.chat])
        notes += [TopicNote(r.chat, r.title, rec["topic"], [w for w, _ in rec["keywords"]],
                            np.array(rec["centroid"]), members.get(rec["topic"], []))
                  for rec in r.summary if rec["topic"] != OUTLIER]
        console.print(f"{escape(r.chat)}: topics from {escape(str(r.topics_dir))}")
    assign_names(notes, params.label_words)
    space = shared_space(results)
    for note in notes:                      # cross-chat links need one space for all chats
        vecs = [space[(note.chat, w["window_id"])] for w in note.windows if (note.chat, w["window_id"]) in space]
        if vecs:
            note.centroid = np.mean(vecs, axis=0)
    link_similar(notes, params.top_k, params.min_similarity)

    reset_generated(vault)
    chat_notes = {r.chat: safe_name(r.title) for r in results}
    by_chat = {r.chat: r for r in results}
    for note in notes:
        write_note(vault / "topics" / note.chat / f"{note.name}.md",
                   render_topic_note(note, by_chat[note.chat].by_id, params, chat_notes[note.chat]))
    for r in results:
        own = [n for n in notes if n.chat == r.chat]
        n_out = sum(t == OUTLIER for t in r.assignments.values())
        write_note(vault / "chats" / f"{chat_notes[r.chat]}.md", render_chat_note(r.chat, r.title, own, len(r.assignments), n_out))
    write_note(vault / "index.md", render_index([(chat_notes[r.chat], r.title, sum(n.chat == r.chat for n in notes))
                                                 for r in results], datetime.now().isoformat(timespec="minutes")))
    cross = sum(1 for n in notes for name, _ in n.related if not name.startswith(f"{n.chat} - "))
    _done(vault, f"{len(notes)} topic notes, {len(results)} chats, "
                 f"{sum(len(n.related) for n in notes)} similarity links ({cross} across chats)")


def _chat_space(r: ChatResult) -> dict:
    """Fitted windows in the space of this chat's topic centroids (language-centred if `discover` was)."""
    fitted = [w for w in r.assignments if w in r.vectors]
    vecs = np.stack([r.vectors[w] for w in fitted])
    if r.meta["params"].get("center_languages", False):
        vecs = center_by_language(vecs, [guess_language(r.texts.get(w, "")) for w in fitted])
    return dict(zip(fitted, vecs))


def _done(vault: Path, what: str) -> None:
    new_graph = write_graph_settings(vault)
    console.print(f"\nWrote {what} to [cyan]{escape(str(vault))}[/cyan]"
                  + (" · graph colours set in .obsidian/graph.json" if new_graph else ""))
