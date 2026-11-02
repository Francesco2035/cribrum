import os
from pathlib import Path

import numpy as np
import pytest

from core import facet_vault as fv
from core.facets import (
    Facet,
    FacetParams,
    TopicRef,
    assign_windows,
    build_facets,
    cluster_topics,
    eligible_windows,
    facet_keywords,
    facets_hash,
    latest_facets_dir,
    load_facet_params,
    load_facets,
    save_facets,
    shared_space,
    topic_refs,
    unit,
)
from core.topic_results import ChatResult
from core.vault import VaultParams
from tests.test_windows import msg

AXES = np.eye(4)


def _result(chat, vectors, texts, assignments, min_words=0):
    windows = {wid: {"window_id": wid, "message_ids": [i], "first_ts": f"2024-01-1{i}T10:00:00",
                     "last_ts": f"2024-01-1{i}T10:05:00", "n_messages": 1} for i, wid in enumerate(vectors)}
    by_id = {i: msg(i, i * 60, text=texts[wid]) for i, wid in enumerate(vectors)}
    return ChatResult(chat, chat.upper(), Path("x"), {"params": {"min_words": min_words}}, [], assignments,
                      windows, by_id, texts, {k: np.asarray(v, dtype=float) for k, v in vectors.items()})


def _facet(fid, kind, chats, members, proto, threshold=0.5):
    return Facet(fid, kind, [(c, 0) for c in chats], members, unit(np.asarray(proto, dtype=float)), threshold=threshold)


def test_params_reject_unknown_keys(tmp_path):
    cfg = tmp_path / "f.yaml"
    cfg.write_text("min_chats: 3\n")
    assert load_facet_params(cfg, {"merge_similarity": 0.3}).min_chats == 3
    cfg.write_text("min_chat: 3\n")
    with pytest.raises(ValueError):
        load_facet_params(cfg)


def test_shared_space_covers_every_chat_and_is_unit_length():
    a = _result("a", {"w1": AXES[0], "w2": AXES[1]}, {"w1": "the exam is", "w2": "il corso è"}, {})
    b = _result("b", {"w3": AXES[2]}, {"w3": "the lecture is"}, {})
    space = shared_space([a, b])
    assert set(space) == {("a", "w1"), ("a", "w2"), ("b", "w3")}
    assert np.allclose([np.linalg.norm(v) for v in space.values()], 1.0)


def test_topic_refs_skip_outliers():
    r = _result("a", {"w1": AXES[0], "w2": AXES[0], "w3": AXES[1]}, dict.fromkeys(["w1", "w2", "w3"], "x"),
                {"w1": 0, "w2": 0, "w3": -1})
    space = {("a", w): v for w, v in r.vectors.items()}
    refs = topic_refs([r], space)
    assert [(ref.chat, ref.topic, len(ref.members)) for ref in refs] == [("a", 0, 2)]
    assert np.allclose(refs[0].centroid, AXES[0])


def test_cluster_topics_follows_the_threshold():
    cents = np.array([unit(AXES[0] + 0.1 * AXES[1]), AXES[0], AXES[2]])
    labels = cluster_topics(cents, merge_similarity=0.8)
    assert labels[0] == labels[1] != labels[2]
    assert cluster_topics(cents, merge_similarity=0.99) != [labels[0]] * 3
    assert cluster_topics(cents[:1], 0.5) == [0]


def test_build_facets_kind_threshold_and_order():
    space = {("a", "w1"): AXES[0], ("a", "w2"): unit(AXES[0] + 0.2 * AXES[1]), ("b", "w3"): AXES[0],
             ("a", "w4"): AXES[2]}
    refs = [TopicRef("a", 0, [("a", "w1"), ("a", "w2")], AXES[0]), TopicRef("b", 0, [("b", "w3")], AXES[0]),
            TopicRef("a", 1, [("a", "w4")], AXES[2])]
    facets = build_facets(refs, [0, 0, 1], space, FacetParams(min_chats=2, member_percentile=0, n_examples=1))
    assert [(f.id, f.kind, f.topic_chats) for f in facets] == [("F000", "shared", ["a", "b"]), ("F001", "local", ["a"])]
    assert facets[0].threshold == pytest.approx(min(space[k] @ facets[0].prototype for k in facets[0].members))
    assert facets[0].examples[0] in (("a", "w1"), ("b", "w3"))      # the most central member


def test_facet_keywords_are_distinctive():
    facets = [_facet("F0", "shared", ["a"], [("a", "1"), ("a", "2")], AXES[0]),
              _facet("F1", "shared", ["a"], [("a", "3")], AXES[1])]
    texts = {("a", "1"): "exam grades exam", ("a", "2"): "grades course", ("a", "3"): "lecture recording course"}
    facet_keywords(facets, texts, stop_words=["the"], top_n=2)
    assert facets[0].keywords[0] in ("exam", "grades") and "course" not in facets[0].keywords[:1]
    assert facets[1].keywords[0] in ("lecture", "recording", "lecture recording")


def test_assign_windows_rules():
    shared = _facet("F0", "shared", ["a", "b"], [("a", "m1")], AXES[0], threshold=0.5)
    local = _facet("F1", "local", ["b"], [("b", "m2")], AXES[1], threshold=0.5)
    space = {("a", "m1"): AXES[0], ("b", "m2"): AXES[1],
             ("a", "near"): unit(AXES[0] + 0.3 * AXES[2]),     # close to F0, its chat has F0
             ("a", "far"): AXES[3],                               # close to nothing
             ("a", "local"): AXES[1],                             # close to F1, but F1 belongs to chat b
             ("c", "other"): AXES[0]}                             # chat c has no facet at all
    out = assign_windows(space, list(space), [shared, local])
    assert out[("a", "m1")][0::2] == ("F0", "topic")
    assert out[("a", "near")][0::2] == ("F0", "nearest")
    assert out[("a", "far")][0::2] == (None, "none")
    assert out[("a", "local")][0] != "F1"
    assert out[("c", "other")] == (None, 0.0, "none")


def test_eligible_windows_use_min_words():
    r = _result("a", {"w1": AXES[0], "w2": AXES[1]}, {"w1": "one two three", "w2": "ok"}, {}, min_words=2)
    space = {("a", w): v for w, v in r.vectors.items()}
    assert eligible_windows([r], space) == [("a", "w1")]


def test_hash_save_load_and_latest(tmp_path):
    p = FacetParams()
    assert facets_hash(p, [Path("x"), Path("y")], ["a"]) == facets_hash(p, [Path("y"), Path("x")], ["a"])
    assert facets_hash(p, [Path("x")], ["a"]) != facets_hash(FacetParams(min_chats=3), [Path("x")], ["a"])
    f = _facet("F000", "shared", ["a", "b"], [("a", "w1")], AXES[0])
    f.keywords = ["exam"]
    out = tmp_path / "facets" / "h1"
    save_facets(out, [f], {("a", "w1"): ("F000", 0.9, "topic"), ("b", "w2"): (None, 0.1, "none")}, {"n_facets": 1})
    records, protos, assignments, meta = load_facets(out)
    assert records[0]["windows_per_chat"] == {"a": 1} and records[0]["n_assigned"] == 1
    assert protos.shape == (1, 4) and len(assignments) == 2 and meta["n_facets"] == 1
    older = tmp_path / "facets" / "h0"
    save_facets(older, [f], {}, {})
    os.utime(older / "meta.json", (1, 1))
    assert latest_facets_dir(tmp_path / "facets") == out


def _views():
    records = [{"id": "F000", "kind": "shared", "keywords": ["exam", "grades", "exams"]},
               {"id": "F001", "kind": "local", "keywords": ["coalition", "core"]},
               {"id": "F002", "kind": "shared", "keywords": ["unused"]}]
    assignments = [{"chat": "a", "window_id": "w0", "facet": "F000", "similarity": 0.4, "source": "nearest"},
                   {"chat": "a", "window_id": "w1", "facet": "F000", "similarity": 0.9, "source": "topic"},
                   {"chat": "b", "window_id": "w2", "facet": "F000", "similarity": 0.8, "source": "topic"},
                   {"chat": "a", "window_id": "w3", "facet": "F001", "similarity": 0.7, "source": "topic"},
                   {"chat": "a", "window_id": "w4", "facet": None, "similarity": 0.1, "source": "none"}]
    views = fv.facet_views(records, np.stack([AXES[0], AXES[1], AXES[2]]), assignments)
    fv.name_facets(views, 3)
    return views


def test_facet_views_and_names():
    views = _views()
    assert [v.id for v in views] == ["F000", "F001"]                # F002 has no window: no note
    shared, local = views
    assert shared.name == "exam, grades" and local.name == "a - coalition, core"
    assert [wid for _, wid, _ in shared.windows["a"]] == ["w1", "w0"]  # most central first
    assert shared.chats == ["a", "b"] and shared.n_windows == 3


def test_facet_notes_link_the_graph():
    shared, local = _views()
    texts = {f"w{i}": f"text {i}" for i in range(5)}
    a = _result("a", {f"w{i}": AXES[0] for i in range(5)}, texts, {})
    b = _result("b", {f"w{i}": AXES[0] for i in range(5)}, texts, {})
    chat_notes = {"a": "A", "b": "B"}
    hub = fv.render_facet_note(shared, {"a": a, "b": b}, chat_notes)
    assert "- [[a · exam, grades]] · 2 windows in [[A]]" in hub and "type: facet" in hub
    note = fv.render_chat_facet_note("a", shared, a, "A", VaultParams())
    assert "Facet: [[exam, grades]] · Chat: [[A]]" in note and "### ↳ " in note   # the nearest window is marked
    concept = fv.render_concept_note(local, a, "A", VaultParams())
    assert "Concept of [[A]]" in concept and "type: concept" in concept
    chat = fv.render_chat_note(a, [shared, local], n_without=1)
    assert "[[a · exam, grades]] · 2 windows" in chat and "[[a - coalition, core]] · 1 windows" in chat
    index = fv.render_index([("A", "a"), ("B", "b")], [shared, local], "now")
    assert "- [[exam, grades]] · 2 chats · 3 windows" in index and "coalition" not in index
