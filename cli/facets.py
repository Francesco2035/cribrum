import dataclasses
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from core.facets import (
    FACETS_ROOT,
    assign_windows,
    build_facets,
    cluster_topics,
    eligible_windows,
    facet_keywords,
    facets_hash,
    load_facet_params,
    save_facets,
    shared_space,
    topic_refs,
)
from core.topic_results import latest_topics_dirs, load_chat_result
from core.topics import load_stop_words
from core.vault import topic_label

FACETS_CONFIG = Path("config/facets.yaml")
console = Console()


def facets(
    ctx: typer.Context,
    topics_dirs: Annotated[list[Path] | None, typer.Argument(help="Results of `discover`; default: the latest per chat")] = None,
    facets_config: Annotated[Path, typer.Option(help="Facet parameters file")] = FACETS_CONFIG,
    merge_similarity: Annotated[float | None, typer.Option(help="Topics at least this similar form one facet")] = None,
    min_chats: Annotated[int | None, typer.Option(help="Chats a facet must span to be 'shared'")] = None,
    member_percentile: Annotated[float | None, typer.Option(help="Assignment threshold: percentile of member similarity")] = None,
):
    """Groups the topics of all chats into facets, names them and assigns every window to its nearest facet."""
    if not ctx.obj["verbose"]:
        logging.getLogger("cribrum.ingest").setLevel(logging.WARNING)
    params = load_facet_params(facets_config, {"merge_similarity": merge_similarity, "min_chats": min_chats,
                                               "member_percentile": member_percentile})
    dirs = topics_dirs or latest_topics_dirs()
    if not dirs:
        typer.echo("Error: no topic results found; run `discover` first", err=True)
        raise typer.Exit(code=1)
    raw_dir = Path(ctx.obj["config"]["paths"]["raw_data"])
    results = [load_chat_result(d, raw_dir) for d in dirs]
    for r in results:
        console.print(f"{escape(r.chat)}: {len(set(r.assignments.values()) - {-1})} topics from {escape(str(r.topics_dir))}")

    space = shared_space(results)
    refs = topic_refs(results, space)
    found = build_facets(refs, cluster_topics([ref.centroid for ref in refs], params.merge_similarity), space, params)
    stop_words = load_stop_words(Path(params.stop_words_file))
    texts = {(r.chat, wid): t for r in results for wid, t in r.texts.items()}
    facet_keywords(found, texts, stop_words, params.top_n_words)
    eligible = eligible_windows(results, space)
    assignments = assign_windows(space, eligible, found)

    out = FACETS_ROOT / facets_hash(params, dirs, stop_words)
    n_by_source = {s: sum(src == s for _, _, src in assignments.values()) for s in ("topic", "nearest", "none")}
    meta = {"params": dataclasses.asdict(params), "topics_dirs": [str(d) for d in dirs],
            "chats": [r.chat for r in results], "n_topics": len(refs), "n_facets": len(found),
            "n_shared": sum(f.kind == "shared" for f in found), "n_eligible": len(eligible), "by_source": n_by_source}
    save_facets(out, found, assignments, meta)
    _print_facets(found, assignments)
    console.print(f"\n{len(refs)} topics → {len(found)} facets ({meta['n_shared']} shared across ≥{params.min_chats} chats). "
                  f"Windows with a facet: {n_by_source['topic']} via their topic + {n_by_source['nearest']} nearest; "
                  f"{n_by_source['none']} of {len(eligible)} without.")
    console.print(f"Written to [cyan]{escape(str(out))}[/cyan]: facets.json, prototypes.npy, assignments.jsonl, meta.json")


def _print_facets(found, assignments) -> None:
    n_assigned = {}
    for fid, _, _ in assignments.values():
        if fid:
            n_assigned[fid] = n_assigned.get(fid, 0) + 1
    table = Table(title="Facets (shared first, then by size)")
    for col in ("id", "kind", "chats", "windows", "label"):
        table.add_column(col, justify="right" if col in ("chats", "windows") else "left")
    for f in sorted(found, key=lambda f: (f.kind != "shared", -len(f.topic_chats), -len(f.members))):
        table.add_row(f.id, f.kind, str(len(f.topic_chats)), str(n_assigned.get(f.id, 0)),
                      escape(topic_label(f.keywords, 4)))
    console.print(table)
