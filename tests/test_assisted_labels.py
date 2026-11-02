from io import StringIO

from rich.console import Console

from cli.annotate import run_review
from core.annotation import ChatData, candidate_pairs, label_record, load_labels, write_labels
from core.assisted_labels import (
    agreement,
    assistant_queue,
    batch_text,
    calibration_batch,
    import_answers,
    parse_answers,
    to_review,
)
from tests.test_windows import PARAMS, msg


def _chat(n=6, chat_id=1, step=400):
    ms = [msg(i, i * step, author=f"u{i % 2}", chat_id=chat_id) for i in range(n)]
    return ChatData("x", "Chat X", ms, {m.id: m for m in ms}, {m.id: i for i, m in enumerate(ms)})


def test_parse_answers_accepts_valid_lines_and_reports_bad_ones():
    text = "# comment\nanndl:12 same high\n`UAI:7 new low`\n\nanndl:13 maybe high\ngarbage\n"
    answers, errors = parse_answers(text)
    assert answers == [("anndl", 12, "same", "high"), ("UAI", 7, "new", "low")]
    assert len(errors) == 2


def test_assistant_queue_never_contains_reserved_pairs():
    cands = {"x": candidate_pairs("x", _chat(40).included, PARAMS)}
    reserved = {c.key for c in cands["x"][:10]}
    queue = assistant_queue(cands, reserved, 100, seed=3)
    assert queue and not reserved & {c.key for c in queue}


def test_import_writes_claude_records_and_replaces_duplicates(tmp_path):
    chat = _chat()
    cands = candidate_pairs("x", chat.included, PARAMS)
    by_stem_id = {(c.chat, c.message_id): c for c in cands}
    path = tmp_path / "claude.jsonl"
    n, unknown = import_answers([("x", 1, "same", "high"), ("x", 99, "new", "low")], by_stem_id, path)
    assert (n, unknown) == (1, ["x:99"])
    import_answers([("x", 1, "new", "low")], by_stem_id, path)
    [r] = load_labels(path)
    assert (r["label"], r["confidence"], r["source"]) == ("new", "low", "claude")


def test_calibration_batch_uses_human_pairs_once():
    cands = candidate_pairs("x", _chat().included, PARAMS)
    by_key = {c.key: c for c in cands}
    human = [label_record(c, "same") for c in cands[:3]]
    assert calibration_batch(human, {cands[0].key}, by_key, 10) == cands[1:3]


def test_review_queue_skips_high_reviewed_and_human_pairs():
    cands = candidate_pairs("x", _chat().included, PARAMS)
    records = [
        label_record(cands[0], "same", source="claude", confidence="low"),
        label_record(cands[1], "same", source="claude", confidence="high"),
        label_record(cands[2], "new", source="claude_reviewed", confidence="low"),
        label_record(cands[3], "new", source="claude", confidence="low"),
    ]
    assert [r["message_id"] for r in to_review(records, {cands[3].key})] == [cands[0].message_id]


def test_agreement_uses_claude_original_label_after_review():
    cands = candidate_pairs("x", _chat().included, PARAMS)
    human = [label_record(cands[0], "same"), label_record(cands[1], "new")]
    claude = [label_record(cands[0], "same", source="claude"),
              {**label_record(cands[1], "new", source="claude_reviewed"), "claude_label": "same"}]
    n, agree, confusion = agreement(human, claude)
    assert (n, agree) == (2, 1)
    assert confusion[("new", "same")] == 1


def test_review_session_accepts_changes_and_skips(tmp_path):
    chat = _chat()
    cands = candidate_pairs("x", chat.included, PARAMS)
    path = tmp_path / "claude.jsonl"
    write_labels(path, [label_record(c, "same", source="claude", confidence="low") for c in cands[:3]])
    keys = iter(["\r", "n", "k"])
    stats = run_review(load_labels(path), {"x": chat}, {c.key: c for c in cands}, path,
                       Console(file=StringIO()), getchar=lambda: next(keys))
    assert stats == {"accepted": 1, "changed": 1, "skipped": 1}
    records = load_labels(path)
    assert [(r["label"], r["source"]) for r in records] == [
        ("same", "claude_reviewed"), ("new", "claude_reviewed"), ("same", "claude")]
    assert records[1]["claude_label"] == "same"


def test_batch_text_marks_previous_and_target():
    chat = _chat()
    c = candidate_pairs("x", chat.included, PARAMS)[2]
    text = batch_text([c], {"x": chat}, 2, 1, "Batch")
    assert f"## x:{c.message_id}" in text
    assert any(line.startswith("P ") for line in text.splitlines())
    assert any(line.startswith("T ") for line in text.splitlines())


def test_binary_agreement_merges_new_and_earlier_and_skips_unsure():
    from collections import Counter

    from core.assisted_labels import binary_agreement
    confusion = Counter({("same", "same"): 3, ("new", "earlier"): 2, ("same", "new"): 1, ("unsure", "same"): 4})
    assert binary_agreement(confusion) == (6, 5)
