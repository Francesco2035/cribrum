import dataclasses
import json
import math

import numpy as np
import pytest

import core.message_embeddings as me
from core.annotation import ChatData, candidate_pairs, label_record
from core.merge_decider import MergeModel, decide_pairs, decider_for, load_model, save_model
from core.config import load_merge_cues
from core.merge_features import (
    BASE_FEATURES, EMBEDDING_FEATURES, FEATURE_GROUPS, compile_cues, needed_ids, pair_features, prepare_chat, shrink,
)
from core.merge_model import (
    ablation_sets, build_rows, gap_rule, leave_one_chat_out, parse_feature_groups, training_records,
)
from core.window_config import config_hash
from core.windows import build_windows
from tests.test_windows import PARAMS, msg


def _chat(texts, step=700, stem="x", chat_id=1):
    ms = [msg(i, i * step, author=f"u{i % 2}", text=t, chat_id=chat_id) for i, t in enumerate(texts)]
    return ChatData(stem, "Chat", ms, {m.id: m for m in ms}, {m.id: i for i, m in enumerate(ms)})


def _unit(*xs):
    v = np.array(xs, dtype=float)
    return v / np.linalg.norm(v)


def test_shrink_pulls_short_texts_towards_the_chat_mean():
    assert math.isclose(shrink(0.9, 0, 0.5), 0.5)
    assert abs(shrink(0.9, 200, 0.5) - 0.9) < 0.02
    assert 0.5 < shrink(0.9, 5, 0.5) < 0.9


def test_pair_features_text_signals():
    chat = _chat(["exam room for the networks exam", "ciao, which room is the networks exam?"])
    c = candidate_pairs("x", chat.included, PARAMS)[0]
    f = pair_features(prepare_chat(chat, general=False), c)
    assert f["cur_question"] == 1 and f["cur_opener"] == 1 and f["same_author"] == 0
    assert f["tfidf_prev"] > 0.3
    assert math.isnan(f["emb_prev"])          # no vectors: embedding features are missing, not 0


def test_embedding_features_use_the_vectors():
    chat = _chat(["first message text", "second message text", "third message text"])
    vectors = {0: _unit(1, 0), 1: _unit(1, 1), 2: _unit(1, 0)}
    c = candidate_pairs("x", chat.included, PARAMS)[-1]
    f = pair_features(prepare_chat(chat, False, vectors), c)
    assert math.isclose(f["emb_prev"], 1 / math.sqrt(2), rel_tol=1e-6)
    assert math.isclose(f["emb_max_recent"], 1.0, rel_tol=1e-6)


def test_needed_ids_cover_the_recent_context():
    chat = _chat([f"message number {i}" for i in range(10)])
    c = [x for x in candidate_pairs("x", chat.included, PARAMS) if x.message_id == 8][0]
    assert needed_ids(chat, [c]) == {3, 4, 5, 6, 7, 8}


def test_build_rows_skips_unsure_and_unknown_pairs_and_human_wins():
    chat = _chat(["a question here?", "an answer here", "another thing", "more text"])
    cands = candidate_pairs("x", chat.included, PARAMS)
    human = [label_record(cands[0], "new"), label_record(cands[1], "unsure")]
    assistant = [label_record(cands[0], "same", source="claude"), label_record(cands[2], "same", source="claude")]
    records = human + training_records(human, assistant)
    rows = build_rows(records, {c.key: c for c in cands}, {"x": prepare_chat(chat, False)}, lambda _: 600)
    assert [(r["message_id"], r["y"], r["source"]) for r in rows] == [(1, 0, "human"), (3, 1, "claude")]
    assert gap_rule(rows).tolist() == [0, 0]          # 700 s > 600 s threshold


class _Recorder:
    seen: list = []

    def fit(self, X, y):
        _Recorder.seen.append(set(X[:, 0].tolist()))
        return self

    def predict(self, X):
        return np.ones(len(X), dtype=int)


def test_leave_one_chat_out_never_trains_on_the_test_chat():
    rows = [{"chat": ch, "flag": float(i), "y": i % 2} for i, ch in enumerate("aabbcc")]
    _Recorder.seen = []
    preds = leave_one_chat_out(rows, rows, ("flag",), _Recorder)
    assert preds.tolist() == [1] * 6
    assert _Recorder.seen == [{2.0, 3.0, 4.0, 5.0}, {0.0, 1.0, 4.0, 5.0}, {0.0, 1.0, 2.0, 3.0}]


def test_message_vectors_encode_only_missing_messages(tmp_path, monkeypatch):
    chat = _chat(["hello there", "[media]", "general kenobi"])
    calls = []

    def fake_encode(texts, *args, **kwargs):
        calls.append(list(texts))
        return np.ones((len(texts), 3))

    monkeypatch.setattr(me, "encode_passages", fake_encode)
    cfg = {"model_name": "m"}
    first = me.message_vectors(chat, {0, 1, 2}, cfg, tmp_path)
    second = me.message_vectors(chat, {0, 2}, cfg, tmp_path)
    assert set(first) == {0, 2} and set(second) == {0, 2}     # media gets no vector
    assert calls == [["hello there", "general kenobi"]]       # second call served from the cache


class _Constant:
    """Picklable stand-in estimator that always answers `value`."""

    def __init__(self, value):
        self.value = value

    def predict(self, X):
        return np.full(len(X), self.value)


def _model(value=0, floor=120, max_gap=3000):
    return MergeModel(_Constant(value), BASE_FEATURES, "const", floor, max_gap)


def test_decide_pairs_applies_floor_model_and_max_gap():
    gaps = [0, 60, 700, 5000]          # pair gaps: 60 (floor), 640 (model), 4300 (above max_gap)
    ms = [msg(i, s, author=f"u{i}", text=f"text number {i}") for i, s in enumerate(gaps)]
    assert decide_pairs(_model(value=0), ms, general=False) == {1: True, 2: False}
    assert decide_pairs(_model(value=1), ms, general=False) == {1: True, 2: True}


def test_save_and_load_model_round_trip(tmp_path):
    path = tmp_path / "m.pkl"
    mid = save_model(_model(value=1), path)
    loaded, loaded_id = load_model(path)
    assert loaded_id == mid and loaded.always_merge_below == 120
    assert json.loads(path.with_suffix(".json").read_text())["model_id"] == mid
    assert save_model(_model(value=0), path) != mid          # new content, new id
    with pytest.raises(ValueError):
        save_model(MergeModel(_Constant(1), EMBEDDING_FEATURES, "emb"), tmp_path / "e.pkl")


def test_windows_use_the_model_instead_of_the_gap_rule():
    ms = [msg(i, i * 700, author=f"u{i}", text=f"text number {i}") for i in range(3)]   # 700 s > 600 s gap rule
    counter = lambda t: len(t.split())
    rule_windows, _ = build_windows(ms, PARAMS, counter)
    assert len(rule_windows) == 3
    params = dataclasses.replace(PARAMS, merge_model="abc")
    model_windows, reports = build_windows(ms, params, counter, merge_decider=decider_for(_model(value=1)))
    assert [w.message_ids for w in model_windows] == [[0, 1, 2]]
    assert reports[0].merges["model"] == 2 and reports[0].merges["gap"] == 0
    assert config_hash(params, "course") != config_hash(PARAMS, "course")
    with pytest.raises(ValueError):
        build_windows(ms, params, counter)                     # model id without a decider


CUES = {"group_request": ("qualcuno", "a tutti"), "answer_start": ("yes", "i think"), "anaphora_start": ("he",)}


def test_cues_match_whole_words_on_normalised_text():
    rx = compile_cues({"group_request": ("c'è qualcuno",), "answer_start": ("no",)})
    assert rx["group_request"].search("ciao cè qualcuno che")            # apostrophe removed on both sides
    assert rx["answer_start"].search("no non credo")
    assert not rx["answer_start"].search("nobody knows")                  # whole words only
    assert not rx["answer_start"].search("i say no")                      # start-only list
    assert rx["anaphora_start"] is None                                   # empty list never matches


def test_cue_features_follow_the_lists():
    chat = _chat(["exam is tomorrow", "Ciao a tutti, someone knows?", "Yes, I think so", "He said so"])
    cf = prepare_chat(chat, False, cue_lists=CUES)
    f = {c.message_id: pair_features(cf, c) for c in candidate_pairs("x", chat.included, PARAMS)}
    assert f[1]["cur_group_request"] == 1 and f[1]["cur_answer_start"] == 0
    assert f[2]["cur_answer_start"] == 1 and f[2]["cur_group_request"] == 0
    assert f[3]["cur_anaphora_start"] == 1
    assert pair_features(prepare_chat(chat, False), candidate_pairs("x", chat.included, PARAMS)[0])["cur_group_request"] == 0


def test_activity_features_count_recent_messages_and_replies():
    ms = [msg(0, 0, author="a", text="question about the exam"),
          msg(1, 100, author="b", text="answer for you", reply_to_id=0),
          msg(2, 200, author="c", text="unrelated chatter here"),
          msg(3, 900, author="a", text="thanks that helps"),
          msg(4, 5000, author="d", text="late message here")]
    chat = ChatData("x", "Chat", ms, {m.id: m for m in ms}, {m.id: i for i, m in enumerate(ms)})
    cf = prepare_chat(chat, False)
    f = pair_features(cf, [c for c in candidate_pairs("x", ms, PARAMS) if c.message_id == 3][0])
    assert f["log_msgs_30m"] == pytest.approx(math.log1p(3))
    assert f["log_authors_60m"] == pytest.approx(math.log1p(3))
    assert f["log_author_msgs_30m"] == pytest.approx(math.log1p(1))
    assert f["cur_author_replied_30m"] == 1 and f["prev_replies_to_cur_author"] == 0
    late = pair_features(cf, [c for c in candidate_pairs("x", ms, PARAMS) if c.message_id == 4][0])
    assert late["log_msgs_30m"] == 0 and late["cur_author_replied_30m"] == 0


def test_prev_replies_to_cur_author():
    ms = [msg(0, 0, author="a", text="question about the exam"),
          msg(1, 100, author="b", text="answer for you", reply_to_id=0),
          msg(2, 800, author="a", text="ok and the oral part")]
    chat = ChatData("x", "Chat", ms, {m.id: m for m in ms}, {m.id: i for i, m in enumerate(ms)})
    c = [c for c in candidate_pairs("x", ms, PARAMS) if c.message_id == 2][0]
    assert pair_features(prepare_chat(chat, False), c)["prev_replies_to_cur_author"] == 1


def test_feature_sets_for_ablation_and_training():
    sets = ablation_sets(("a",), {"g1": ("b",), "g2": ("c", "d")}, ("e",))
    assert sets == {"base": ("a",), "base+g1": ("a", "b"), "base+g2": ("a", "c", "d"),
                    "all": ("a", "b", "c", "d"), "all+emb": ("a", "b", "c", "d", "e")}
    groups = {"g1": ("b",), "g2": ("c",)}
    assert parse_feature_groups("all", ("a",), groups) == ("a", "b", "c")
    assert parse_feature_groups("base", ("a",), groups) == ("a",)
    assert parse_feature_groups("g2, g1", ("a",), groups) == ("a", "b", "c")      # order follows the groups
    with pytest.raises(ValueError):
        parse_feature_groups("nope", ("a",), groups)


def test_shipped_cue_file_loads_and_rejects_unknown_lists(tmp_path):
    from pathlib import Path
    cues = load_merge_cues(Path("config/merge_cues.yaml"))
    assert all(cues[name] for name in ("group_request", "answer_start", "anaphora_start"))
    bad = tmp_path / "c.yaml"
    bad.write_text("typo_list: [a]\n")
    with pytest.raises(ValueError):
        load_merge_cues(bad)
    assert load_merge_cues(tmp_path / "missing.yaml")["group_request"] == ()


def test_saved_model_carries_its_cue_lists(tmp_path):
    model = MergeModel(_Constant(1), BASE_FEATURES + FEATURE_GROUPS["group_request"], "c", cue_lists=CUES)
    save_model(model, tmp_path / "m.pkl")
    loaded, _ = load_model(tmp_path / "m.pkl")
    assert loaded.cue_lists == CUES
    assert json.loads((tmp_path / "m.json").read_text())["cue_lists"]["group_request"] == ["qualcuno", "a tutti"]
