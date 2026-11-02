import json
import os

import numpy as np
import pytest

from core.topic_results import latest_topics_dirs
from core.vault import (
    GENERATED,
    TopicNote,
    assign_names,
    clean_text,
    link_similar,
    load_vault_params,
    render_chat_note,
    render_topic_note,
    render_window,
    reset_generated,
    safe_name,
    topic_label,
    topic_windows,
    write_graph_settings,
    VaultParams,
)
from tests.test_windows import msg


def _note(chat, topic, keywords, centroid, windows=()):
    return TopicNote(chat, chat.upper(), topic, list(keywords), np.array(centroid, dtype=float), list(windows))


def _window(wid, ids, first="2024-01-10T10:00:00", last="2024-01-10T10:05:00"):
    return {"window_id": wid, "message_ids": ids, "first_ts": first, "last_ts": last, "n_messages": len(ids)}


def test_safe_name_and_label():
    assert safe_name('MAS - a/b: c? [x] #y') == "MAS - a b c x y"
    assert topic_label(["coalition", "grand coalition", "core", "nash"], 3) == "coalition, core, nash"


def test_names_are_unique():
    notes = [_note("mas", 0, ["exam"], [1, 0]), _note("mas", 1, ["exam"], [0, 1])]
    assign_names(notes, 3)
    assert [n.name for n in notes] == ["mas - exam", "mas - exam (1)"]


def test_link_similar_keeps_top_k_above_threshold():
    notes = [_note("a", 0, ["x"], [1, 0, 0]), _note("b", 0, ["y"], [0.9, 0.1, 0]), _note("c", 0, ["z"], [0, 0, 1])]
    assign_names(notes, 3)
    link_similar(notes, top_k=2, min_similarity=0.5)
    assert [name for name, _ in notes[0].related] == ["b - y"]          # c is orthogonal: below the threshold
    assert notes[2].related == []


def test_clean_text_neutralises_tags_and_links():
    assert clean_text("see #exam and [[note]]\nnow", 100) == "see \\#exam and \\[\\[note\\]\\] now"
    assert clean_text("abcdef", 3) == "abc…"


def test_render_window_quotes_each_message():
    by_id = {1: msg(1, 0, author="Ann", text="question?"), 2: msg(2, 60, author="Bob", text="")}
    text = render_window(_window("w", [1, 2]), by_id, 100)
    assert "### 2024-01-10 10:00 · 2 messages" in text
    assert "> **Ann** 10:00 · question?" in text and "> **Bob** 10:01 · _[media]_" in text
    assert not text.rstrip().endswith(">")


def test_topic_and_chat_notes_link_each_other():
    by_id = {1: msg(1, 0, text="core of the game")}
    note = _note("mas", 2, ["coalition", "core"], [1, 0], [_window("w1", [1])])
    note.name, note.related = "mas - coalition, core", [("dm - itemset", 0.44)]
    text = render_topic_note(note, by_id, VaultParams(), "MULTIAGENT SYSTEMS")
    assert text.startswith("---\ntype: topic") and "chat/mas" in text
    assert "Chat: [[MULTIAGENT SYSTEMS]]" in text and "- [[dm - itemset]] (0.44)" in text
    chat = render_chat_note("mas", "MULTIAGENT SYSTEMS", [note], n_windows=10, n_outliers=4)
    assert "- [[mas - coalition, core]] (1 windows)" in chat and "windows_without_topic: 4" in chat


def test_topic_note_caps_windows():
    windows = [_window(f"w{i}", [1], first=f"2024-01-1{i}T10:00:00") for i in range(5)]
    note = _note("mas", 0, ["x"], [1, 0], windows)
    note.name = "mas - x"
    text = render_topic_note(note, {1: msg(1, 0)}, VaultParams(max_windows=2), "MAS")
    assert "## Windows (2 shown, 3 less central left out)" in text
    assert text.index("2024-01-10") < text.index("2024-01-11")          # shown by date


def test_topic_windows_orders_by_centrality_and_drops_outliers():
    summary = [{"topic": 0, "centroid": [1.0, 0.0]}, {"topic": -1, "centroid": [0.0, 1.0]}]
    assignments = {"a": 0, "b": 0, "c": -1}
    windows = {k: _window(k, [1]) for k in "abc"}
    vectors = {"a": np.array([0.6, 0.8]), "b": np.array([1.0, 0.0]), "c": np.array([0.0, 1.0])}
    out = topic_windows(summary, assignments, windows, vectors)
    assert list(out) == [0] and [w["window_id"] for w in out[0]] == ["b", "a"]


def test_reset_keeps_obsidian_settings_and_hand_written_notes(tmp_path):
    for name in ("chats/x.md", "topics/a/y.md", "index.md", "mine.md", ".obsidian/app.json"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")
    reset_generated(tmp_path)
    assert not any((tmp_path / g).exists() for g in GENERATED)
    assert (tmp_path / "mine.md").exists() and (tmp_path / ".obsidian/app.json").exists()


def test_graph_settings_written_once(tmp_path):
    assert write_graph_settings(tmp_path)
    (tmp_path / ".obsidian/graph.json").write_text("{}")             # the user changed it in Obsidian
    assert not write_graph_settings(tmp_path)
    assert json.loads((tmp_path / ".obsidian/graph.json").read_text()) == {}


def test_vault_params_and_latest_topics(tmp_path):
    cfg = tmp_path / "v.yaml"
    cfg.write_text("top_k: 5\n")
    assert load_vault_params(cfg).top_k == 5
    cfg.write_text("topk: 5\n")
    with pytest.raises(ValueError):
        load_vault_params(cfg)
    old, new = tmp_path / "t/mas/h1/old", tmp_path / "t/mas/h2/new"
    for d in (old, new):
        d.mkdir(parents=True)
        (d / "meta.json").write_text("{}")
    os.utime(old / "meta.json", (1, 1))
    assert latest_topics_dirs(tmp_path / "t") == [new]
