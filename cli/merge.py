import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cli.labels import ASSISTANT_LABELS, HUMAN_LABELS, WINDOWS_CONFIG, LabelSetup, load_setup
from core.annotation import load_labels
from core.config import blocked_ids, export_paths
from core.ingest.telegram import parse_telegram_chat
from core.merge_decider import DEFAULT_MODEL_PATH, MergeModel, decider_for, load_model, save_model
from core.config import load_merge_cues, merge_cues_path
from core.merge_features import BASE_FEATURES, EMBEDDING_FEATURES, FEATURE_GROUPS, needed_ids, prepare_chat
from core.merge_model import (
    ablation_sets,
    accuracy_by_band,
    build_rows,
    gap_rule,
    leave_one_chat_out,
    matrix,
    model_factories,
    parse_feature_groups,
    scores,
    targets,
    training_records,
    tree_rules,
    with_floor,
)
from core.message_embeddings import message_vectors
from core.tokens import get_token_counter
from core.window_config import load_window_params
from core.window_report import window_stats
from core.windows import build_windows

DEFAULT_GROUPS = "base"    # the ablation found no gain from the other groups (see docs/it/code/cli/merge.md)

merge_app = typer.Typer(help="Merge model: evaluate, train, and compare its windows with the gap rule.")
console = Console()


@merge_app.command("evaluate")
def evaluate(
    ctx: typer.Context,
    embeddings: Annotated[bool, typer.Option(help="Also test the E5 embedding features (cached per chat)")] = True,
    csv_path: Annotated[Path | None, typer.Option("--csv", help="Also write the feature table (no chat text)")] = None,
    tree_depth: Annotated[int, typer.Option(help="Depth of the tree whose rules are printed")] = 3,
    always_merge_below: Annotated[int, typer.Option(help="Every model always merges within this gap (s); 0 = off")] = 120,
    test_on: Annotated[str, typer.Option("--test-on", help="human (default, the real measure) or assistant (more pairs, second opinion)")] = "human",
    errors: Annotated[bool, typer.Option(help="List the test pairs the best model gets wrong (prints chat text)")] = False,
):
    """Feature ablation and model comparison against today's gap rule, measured on your labels by default."""
    if test_on not in ("human", "assistant"):
        typer.echo("Error: --test-on must be 'human' or 'assistant'", err=True)
        raise typer.Exit(code=1)
    setup, rows = _labelled_rows(ctx, embeddings)
    test = [r for r in rows if (r["source"] == "human") == (test_on == "human")]
    console.print(f"Pairs with a target: {len(rows)}; test set: {len(test)} {test_on} labels "
                  f"(each chat predicted by a model trained on the other chats)")
    if csv_path:
        _write_csv(csv_path, rows)
        console.print(f"Feature table: {csv_path}")

    sets = ablation_sets(BASE_FEATURES, FEATURE_GROUPS, EMBEDDING_FEATURES if embeddings else ())
    rule = gap_rule(test)
    results, preds = _ablation(rows, test, sets, always_merge_below)
    _print_ablation(results, scores(targets(test), rule), len(test), test_on, always_merge_below)
    best = max(results, key=lambda k: (results[k]["balanced"], results[k]["accuracy"]))
    _print_best(best, results[best], scores(targets(test), rule))
    _print_bands(test, {"gap rule": rule, f"{best[1]} [{best[0]}]": preds[best]})
    if errors:
        _print_errors(setup, test, preds[best])
    console.print(f"\n[bold]Tree rules[/bold] (depth {tree_depth}, all labels, {escape(best[0])}):")
    console.print(tree_rules(rows, sets[best[0]], tree_depth), markup=False)


@merge_app.command("train")
def train(
    ctx: typer.Context,
    model: Annotated[str, typer.Option(help="One of: tree_d3, tree_d5, forest, boosting, logreg")] = "tree_d5",
    features: Annotated[str, typer.Option(help=f"'all', 'base' or a comma list of {', '.join(FEATURE_GROUPS)}")] = DEFAULT_GROUPS,
    always_merge_below: Annotated[int, typer.Option(help="Always merge within this gap (s), the model decides above")] = 120,
    out: Annotated[Path, typer.Option(help="Where to save the model (a .json with its metadata goes next to it)")] = DEFAULT_MODEL_PATH,
):
    """Trains the chosen model on all labels (yours + assistant) and saves it for `windows --merge-model`."""
    factories = model_factories()
    if model not in factories:
        typer.echo(f"Error: unknown model '{model}', expected one of {sorted(factories)}", err=True)
        raise typer.Exit(code=1)
    try:
        chosen = parse_feature_groups(features, BASE_FEATURES, FEATURE_GROUPS)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    _, rows = _labelled_rows(ctx, embeddings=False)
    estimator = factories[model]().fit(matrix(rows, chosen), targets(rows))
    sources = {src: sum(r["source"] == src for r in rows) for src in sorted({r["source"] for r in rows})}
    meta = {"trained_at": datetime.now().isoformat(timespec="seconds"), "feature_groups": features,
            "n_pairs": len(rows), "pairs_by_source": sources, "merge_share": round(float(targets(rows).mean()), 3),
            "label_files": [str(HUMAN_LABELS), str(ASSISTANT_LABELS)]}
    cues = load_merge_cues(merge_cues_path(ctx.obj["config"]))
    mid = save_model(MergeModel(estimator, chosen, model, always_merge_below, meta=meta, cue_lists=cues), out)
    console.print(f"Trained [bold]{model}[/bold] ({escape(features)}, {len(chosen)} features) on {len(rows)} pairs "
                  f"{sources}; always merge ≤{always_merge_below}s")
    console.print(f"Saved {escape(str(out))} (model id [bold]{mid}[/bold]) and {escape(str(out.with_suffix('.json')))}")
    if model.startswith("tree"):
        console.print("\n[bold]Rules (depth 3 view)[/bold]:")
        console.print(tree_rules(rows, chosen, 3), markup=False)


@merge_app.command("compare")
def compare(
    ctx: typer.Context,
    chat: Annotated[list[str] | None, typer.Option(help="Export name (repeatable); default: all exports")] = None,
    merge_model: Annotated[Path, typer.Option(help="Trained merge model")] = DEFAULT_MODEL_PATH,
    windows_config: Annotated[Path, typer.Option(help="Window parameters file")] = WINDOWS_CONFIG,
):
    """Builds the windows of each chat with the gap rule and with the model, and compares them. Writes nothing."""
    cfg = ctx.obj["config"]
    if not merge_model.exists():
        typer.echo(f"Error: {merge_model} not found, run `merge train` first", err=True)
        raise typer.Exit(code=1)
    if not ctx.obj["verbose"]:
        for name in ("cribrum.ingest", "cribrum.windows", "cribrum.tokens"):
            logging.getLogger(name).setLevel(logging.WARNING)
    model, mid = load_model(merge_model)
    dates = cfg.get("dates", {})
    base = {"min_date": dates.get("min_date"), "max_date": dates.get("max_date"), "blocked_ids": blocked_ids(cfg)}
    rule_params, _ = load_window_params(windows_config, base)
    model_params, _ = load_window_params(windows_config, {**base, "merge_model": mid})
    count_tokens, _ = get_token_counter(rule_params.tokenizer_model)

    rows = []
    for path in export_paths(cfg):
        if chat and path.stem not in chat:
            continue
        info, messages = parse_telegram_chat(path)
        names = {info["id"]: info["name"]}
        r_w, r_rep = build_windows(messages, rule_params, count_tokens, names)
        m_w, m_rep = build_windows(messages, model_params, count_tokens, names, merge_decider=decider_for(model))
        rows.append((path.stem, window_stats(r_w, r_rep[0]), window_stats(m_w, m_rep[0])))
    _print_comparison(rows, mid)


def _labelled_rows(ctx: typer.Context, embeddings: bool) -> tuple[LabelSetup, list[dict]]:
    s = load_setup(ctx)
    human, assistant = load_labels(HUMAN_LABELS), load_labels(ASSISTANT_LABELS)
    records = human + training_records(human, assistant)
    if not ctx.obj["verbose"]:
        logging.getLogger("cribrum.embeddings").setLevel(logging.WARNING)
    cues = load_merge_cues(merge_cues_path(ctx.obj["config"]))
    chat_features = _chat_features(s, records, ctx.obj["config"].get("embedding", {}) if embeddings else None, cues)
    rows = build_rows(records, s.by_key(), chat_features,
                      lambda stem: s.params.gap_for(s.params.chat_type_for(s.chats[stem].included[0].chat_id)))
    return s, rows


def _chat_features(s: LabelSetup, records: list[dict], emb_cfg: dict | None, cue_lists: dict) -> dict:
    by_key = s.by_key()
    per_chat: dict[str, list] = {}
    for r in records:
        c = by_key.get((r["chat_id"], r["message_id"]))
        if c is not None:
            per_chat.setdefault(c.chat, []).append(c)
    out = {}
    for stem, cands in per_chat.items():
        chat = s.chats[stem]
        vectors = message_vectors(chat, needed_ids(chat, cands), emb_cfg) if emb_cfg is not None else None
        general = s.params.chat_type_for(chat.included[0].chat_id) == "general"
        out[stem] = prepare_chat(chat, general, vectors, cue_lists)
    return out


def _ablation(rows: list[dict], test: list[dict], sets: dict, floor: int) -> tuple[dict, dict]:
    """Scores and predictions keyed by (feature set, model)."""
    y = targets(test)
    preds = {}
    for set_name, features in sets.items():
        for name, factory in model_factories().items():
            pred = leave_one_chat_out(rows, test, features, factory)
            preds[(set_name, name)] = with_floor(test, pred, floor) if floor else pred
    return {key: scores(y, p) for key, p in preds.items()}, preds


def _print_ablation(results: dict, rule: dict, n: int, test_on: str, floor: int) -> None:
    models = list(model_factories())
    floor_note = f", always merge ≤{floor}s" if floor else ""
    who = "your" if test_on == "human" else "the assistant's"
    table = Table(title=f"Balanced accuracy, leave-one-chat-out on {who} {n} labels{floor_note}. Gap rule: {rule['balanced']:.2f}")
    table.add_column("features")
    for m in models:
        table.add_column(m, justify="right")
    best = max(r["balanced"] for r in results.values())
    for set_name in dict.fromkeys(k[0] for k in results):
        cells = []
        for m in models:
            v = results[(set_name, m)]["balanced"]
            cells.append(f"[bold]{v:.2f}[/bold]" if v == best else f"{v:.2f}")
        table.add_row(escape(set_name), *cells)
    console.print(table)


def _print_errors(s: LabelSetup, test: list[dict], pred) -> None:
    console.print("\n[bold]Pairs the best model gets wrong[/bold] (P = previous message, T = message to decide):")
    for r, p in zip(test, pred):
        if r["y"] == p:
            continue
        chat = s.chats[r["chat"]]
        cur = chat.by_id[r["message_id"]]
        prev = chat.included[chat.position[r["message_id"]] - 1]
        verdict = "split" if r["y"] == 0 else "merge"
        console.print(f"\n{escape(r['chat'])}:{r['message_id']}  gap {r['gap_s'] // 60} min · label {r['label']} "
                      f"→ should {verdict}, model says {'merge' if p else 'split'}")
        for mark, m in (("P", prev), ("T", cur)):
            console.print(f"  {mark} {escape(m.author)}: {escape((m.text or '').replace(chr(10), ' ')[:160])}")


def _print_best(best: tuple[str, str], sc: dict, rule: dict) -> None:
    table = Table(title=f"Best: {best[1]} on {best[0]} vs gap rule")
    for col in ("", "accuracy", "balanced acc.", "F1 merge", "F1 split"):
        table.add_column(col, justify="right" if col else "left")
    for name, row in ((f"{best[1]} [{best[0]}]", sc), ("gap rule", rule)):
        table.add_row(escape(name), *(f"{row[k]:.2f}" for k in ("accuracy", "balanced", "f1_merge", "f1_split")))
    console.print(table)


def _print_bands(test: list[dict], preds: dict) -> None:
    table = Table(title="Accuracy by gap band (test labels)")
    table.add_column("gap band (s)")
    table.add_column("pairs", justify="right")
    by_band = {name: accuracy_by_band(test, p) for name, p in preds.items()}
    for name in preds:
        table.add_column(escape(name), justify="right")
    for band, (n, _) in next(iter(by_band.values())).items():
        table.add_row(band, str(n), *(f"{by_band[name][band][1]:.2f}" for name in preds))
    console.print(table)


def _print_comparison(rows: list[tuple[str, dict, dict]], mid: str) -> None:
    table = Table(title=f"Windows built with the gap rule → with model {mid} (len = messages per window)")
    for col in ("chat", "msgs", "windows", "1-msg %", "mean len", "p90 len", "capped", "gap/model merges"):
        table.add_column(col, justify="left" if col == "chat" else "right")
    for stem, r, m in rows:
        arrow = lambda key: f"{r[key]} → {m[key]}"
        dist = lambda key: f"{r['messages_per_window'].get(key, 0)} → {m['messages_per_window'].get(key, 0)}"
        table.add_row(escape(stem), str(r["n_included_messages"]), arrow("n_windows"), arrow("single_message_pct"),
                      dist("mean"), dist("p90"), arrow("capped_windows"),
                      f"{r['merges']['gap']} → {m['merges']['model']}")
    console.print(table)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
