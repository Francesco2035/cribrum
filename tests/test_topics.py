import json

import numpy as np
import pytest

from core.topics import (
    OUTLIER,
    TopicParams,
    center_by_language,
    fit_topics,
    guess_language,
    load_stop_words,
    load_topic_params,
    params_hash,
    summarize,
    topics_markdown,
)
from core.window_embeddings import (
    chat_and_hash,
    embeddings_dir,
    is_current,
    load_embeddings,
    save_embeddings,
    window_text,
)
from tests.test_windows import msg


def test_window_text_uses_member_bodies_only():
    by_id = {1: msg(1, 0, text="first line"), 2: msg(2, 10, text="  "), 3: msg(3, 20, text="third"),
             9: msg(9, -10, text="overlap from before")}
    window = {"window_id": "1-1", "message_ids": [1, 2, 3], "overlap_ids": [9]}
    assert window_text(window, by_id) == "first line\nthird"          # no author, no empty line, no overlap


def test_embeddings_round_trip_and_cache_check(tmp_path):
    windows_dir = tmp_path / "windows" / "MAS" / "abc123"
    out = embeddings_dir(windows_dir, root=tmp_path / "emb")
    assert chat_and_hash(windows_dir) == ("MAS", "abc123") and out == tmp_path / "emb" / "MAS" / "abc123"
    vectors = np.eye(3, dtype=np.float32)
    save_embeddings(out, ["a", "b", "c"], vectors, {"model": "m"})
    ids, loaded, meta = load_embeddings(out)
    assert ids == ["a", "b", "c"] and np.array_equal(loaded, vectors) and meta["dim"] == 3
    assert is_current(out, "m", ["a", "b", "c"])
    assert not is_current(out, "other-model", ["a", "b", "c"])
    assert not is_current(out, "m", ["a", "b"])                      # windows changed


def test_guess_language():
    assert guess_language("qualcuno sa quando è l'esame di giugno?") == "it"
    assert guess_language("does someone know when the exam is?") == "en"


def test_center_by_language_removes_the_language_offset():
    rng = np.random.default_rng(0)
    topic_a, topic_b, lang_it = rng.normal(size=(3, 16))
    it = [topic_a + 3 * lang_it, topic_b + 3 * lang_it]
    en = [topic_a, topic_b]
    vecs = np.array(it + en)
    centred = center_by_language(vecs, ["it", "it", "en", "en"], min_group=2)
    sim = centred @ centred.T
    assert sim[0, 2] > 0.99 and sim[1, 3] > 0.99                    # same topic across languages
    assert np.allclose(np.linalg.norm(centred, axis=1), 1.0)


def test_topic_params_reject_unknown_keys_and_hash_follows_stop_words(tmp_path):
    cfg = tmp_path / "t.yaml"
    cfg.write_text("min_topic_size: 7\n")
    params = load_topic_params(cfg, {"n_neighbors": 9, "min_samples": None})
    assert params.min_topic_size == 7 and params.n_neighbors == 9
    cfg.write_text("min_topic_sise: 7\n")
    with pytest.raises(ValueError):
        load_topic_params(cfg)
    assert params_hash(params, ["a"]) != params_hash(params, ["a", "b"])
    assert params_hash(params, ["b", "a"]) == params_hash(params, ["a", "b"])


def test_stop_words_merge_sklearn_and_yaml(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text("italian: [della, Esame]\nchat: [ciao]\n")
    words = load_stop_words(path)
    assert {"the", "della", "esame", "ciao"} <= set(words)


class _FakeModel:
    def get_topic(self, t):
        return [("coalition", 0.5), ("core", 0.25)] if t == 0 else False


def test_summarize_and_markdown():
    vectors = np.array([[1, 0], [0.9, 0.1], [0, 1]], dtype=float)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    summary = summarize(_FakeModel(), [0, 0, OUTLIER], ["w1", "w2", "w3"], vectors, n_examples=1)
    by_topic = {r["topic"]: r for r in summary}
    assert by_topic[0]["size"] == 2 and by_topic[0]["keywords"][0] == ["coalition", 0.5]
    assert by_topic[OUTLIER]["keywords"] == []
    text = topics_markdown(summary, {"w1": "core of the game", "w2": "x", "w3": "y"}, "MAS")
    assert text.index("Topic 0") < text.index("Outliers")             # outliers listed last
    assert "**Keywords:** coalition, core" in text
    json.dumps(summary)                                               # serialisable as saved


def test_fit_topics_finds_separated_groups():
    rng = np.random.default_rng(1)
    groups = {"coalition core payoff game": 0, "lecture recording webeep online": 1, "exam grade february results": 2}
    centres = rng.normal(size=(3, 32)) * 5
    texts, vecs = [], []
    for words, g in groups.items():
        for i in range(25):
            texts.append(f"{words} {i}")
            vecs.append(centres[g] + rng.normal(size=32) * 0.2)
    vectors = np.array(vecs, dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    params = TopicParams(min_topic_size=10, cluster_selection="eom", min_df=1)
    _, topics = fit_topics(texts, vectors, params, ["the"])
    found = {t for t in topics if t != OUTLIER}
    assert len(found) == 3
    for g in range(3):                                                 # each group mostly in one topic
        block = topics[g * 25:(g + 1) * 25]
        assert max(block.count(t) for t in found) >= 20


def test_center_by_language_leaves_small_groups_alone():
    vecs = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    out = center_by_language(vecs, ["it", "en", "en"], min_group=2)
    assert np.allclose(out[0], [1.0, 0.0])                       # a lone Italian window is not zeroed
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
