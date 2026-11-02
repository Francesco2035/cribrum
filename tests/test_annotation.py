from collections import Counter
from io import StringIO

from rich.console import Console

from cli.annotate import run_session
from core.annotation import (
    ChatData,
    append_label,
    band_of,
    build_queue,
    candidate_pairs,
    label_record,
    load_labels,
    progress,
    remove_last_label,
)
from tests.test_windows import PARAMS, msg


def test_candidates_skip_reply_burst_and_dependent():
    ms = [
        msg(1, 0, "a"),
        msg(2, 400, "b", reply_to_id=1),        # reply → skipped
        msg(3, 450, "b"),                        # burst of b → skipped
        msg(4, 500, "c", text="grazie"),         # dependent → skipped
        msg(5, 900, "d"),                        # gap 400 s → candidate
        msg(6, 900 + 4 * 3600, "e"),             # gap beyond last band → skipped
    ]
    cands = candidate_pairs("x", ms, PARAMS)
    assert [(c.message_id, c.prev_id, c.band) for c in cands] == [(5, 4, "300-600")]


def test_stale_reply_is_a_candidate():
    ms = [msg(1, 0, "a"), msg(2, 3000, "b"), msg(3, 3000 + 700, "c", reply_to_id=1)]
    cands = candidate_pairs("x", ms, PARAMS)    # reply_max_gap is 3600 s
    assert [c.message_id for c in cands] == [2, 3]


def test_band_edges():
    assert band_of(0) == "0-120"
    assert band_of(120) == "0-120"
    assert band_of(121) == "120-300"
    assert band_of(20000) is None


def _many(chat_id, n, step=200):
    return [msg(i, i * step, author=f"u{i % 2}", chat_id=chat_id) for i in range(n)]


def test_queue_is_deterministic_and_covers_every_chat():
    cands = {
        "big": candidate_pairs("big", _many(1, 400), PARAMS),
        "small": candidate_pairs("small", _many(2, 30), PARAMS),
    }
    q1, q2 = build_queue(cands, 60, seed=1), build_queue(cands, 60, seed=1)
    assert q1 == q2
    per_chat = Counter(c.chat for c in q1)
    assert per_chat["small"] >= 15 and per_chat["big"] > per_chat["small"]
    assert len({c.key for c in q1}) == len(q1)


def test_label_file_append_load_undo(tmp_path):
    path = tmp_path / "labels.jsonl"
    c1, c2 = candidate_pairs("x", _many(1, 3), PARAMS)
    append_label(path, label_record(c1, "same"))
    append_label(path, label_record(c2, "new"))
    assert [r["label"] for r in load_labels(path)] == ["same", "new"]
    assert remove_last_label(path)["message_id"] == c2.message_id
    assert [r["message_id"] for r in load_labels(path)] == [c1.message_id]


def _chat_data(ms):
    return ChatData("x", "Chat X", ms, {m.id: m for m in ms}, {m.id: i for i, m in enumerate(ms)})


def test_session_labels_undoes_and_resumes(tmp_path):
    ms = _many(1, 5)
    queue = candidate_pairs("x", ms, PARAMS)
    chats = {"x": _chat_data(ms)}
    path = tmp_path / "labels.jsonl"
    console = Console(file=StringIO())

    keys = iter("yuznq")                         # same, undo, (ignored key), new, quit
    run_session(queue, chats, path, console, getchar=lambda: next(keys))
    assert [(r["message_id"], r["label"]) for r in load_labels(path)] == [(queue[0].message_id, "new")]

    keys = iter("e?y")                           # resumes from the second pair
    run_session(queue, chats, path, console, getchar=lambda: next(keys))
    assert [r["label"] for r in load_labels(path)] == ["new", "earlier", "unsure", "same"]


def test_progress_counts_queue_and_labels_per_chat(tmp_path):
    a = candidate_pairs("a", _many(1, 4), PARAMS)
    b = candidate_pairs("b", _many(2, 3), PARAMS)
    queue = a + b
    records = [label_record(a[0], "same"), label_record(a[1], "new"), label_record(b[0], "same")]
    prog = progress(queue, records)
    assert (prog["a"]["done"], prog["a"]["queue"]) == (2, 3)
    assert (prog["b"]["done"], prog["b"]["queue"]) == (1, 2)
    assert prog["a"]["labels"] == Counter(same=1, new=1)
