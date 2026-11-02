import dataclasses

from core.annotation import ChatData, append_label, candidate_pairs, drop_blocked_labels, label_record, load_labels
from core.config import load_blocklist, match_accounts, save_blocklist
from core.window_config import config_hash
from tests.test_windows import PARAMS, build, groups, msg

BLOCKED = dataclasses.replace(PARAMS, blocked_ids=("user_bot",))


def test_blocklist_round_trip_and_missing_file(tmp_path):
    path = tmp_path / "blocklist.yaml"
    assert load_blocklist(path) == {}
    save_blocklist(path, {"user2": "PoliNetwork Bot 🤖", "user1": "Bot 3"})
    assert load_blocklist(path) == {"user1": "Bot 3", "user2": "PoliNetwork Bot 🤖"}


def test_match_accounts_by_id_or_name():
    authors = {"user1": "PoliNetwork Bot 3", "user2": "PoliNetwork Bot 🤖", "user3": "Mario Rossi"}
    assert match_accounts(authors, "user3") == {"user3": "Mario Rossi"}
    assert set(match_accounts(authors, "polinetwork")) == {"user1", "user2"}
    assert match_accounts(authors, "nobody") == {}


def test_blocked_messages_are_excluded_and_counted():
    ms = [msg(1, 0, "a"), msg(2, 60, "bot"), msg(3, 120, "b")]
    windows, [report] = build(ms, BLOCKED)
    assert groups(windows) == [[1, 3]]
    assert report.excluded["blocked"] == 1


def test_blocklist_changes_the_hash():
    assert config_hash(PARAMS, "course") != config_hash(BLOCKED, "course")


def test_labels_touching_blocked_accounts_are_dropped(tmp_path):
    ms = [msg(1, 0, "a"), msg(2, 400, "bot"), msg(3, 800, "b"), msg(4, 1200, "c")]
    chat = ChatData("x", "X", ms, {m.id: m for m in ms}, {m.id: i for i, m in enumerate(ms)})
    path = tmp_path / "labels.jsonl"
    for c in candidate_pairs("x", ms, PARAMS):       # pairs (2,1), (3,2), (4,3)
        append_label(path, label_record(c, "same"))
    dropped = drop_blocked_labels(path, {"x": chat}, ("user_bot",))
    assert [r["message_id"] for r in dropped] == [2, 3]
    assert [r["message_id"] for r in load_labels(path)] == [4]
