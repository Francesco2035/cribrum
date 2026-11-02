from datetime import datetime, timedelta

import pytest

from core.ingest.telegram import normalize_text
from core.models import ChatMessage
from core.window_config import WindowParams, apply_overrides, config_hash
from core.windows import build_windows

T0 = datetime(2024, 1, 10, 10, 0, 0)
PARAMS = WindowParams(
    chat_types={"2": "general"},
    gap={"course": 600, "general": 900},
    reply_max_gap=3600,
    burst_gap=120,
    dependent_gap=300,
    mention_gap=1800,
    max_messages=40,
    max_tokens=10_000,
    dependent_phrases=("ok", "grazie", "+1"),
)


def word_count(text: str) -> int:
    return len(text.split())


def msg(mid, seconds, author="a", text="some message here", chat_id=1, **kw) -> ChatMessage:
    return ChatMessage(chat_id=chat_id, id=mid, timestamp=T0 + timedelta(seconds=seconds),
                       author=author, from_id=f"user_{author}", text=text, **kw)


def build(messages, params=PARAMS):
    windows, reports = build_windows(messages, params, word_count)
    return windows, reports


def groups(windows):
    return [w.message_ids for w in windows]


def rule_of(windows, mid):
    for w in windows:
        for link in w.links:
            if link.message_id == mid:
                return link.rule
    raise KeyError(mid)


def test_reply_chain_stays_together_despite_large_gaps():
    ms = [msg(1, 0, "a"), msg(2, 1000, "b", reply_to_id=1), msg(3, 2000, "c", reply_to_id=2)]
    windows, _ = build(ms)
    assert groups(windows) == [[1, 2, 3]]
    assert rule_of(windows, 3) == "reply"


def test_reply_too_old_is_not_followed_and_counted():
    ms = [msg(1, 0, "a"), msg(2, 5000, "b", reply_to_id=1)]
    windows, [report] = build(ms)
    assert groups(windows) == [[1], [2]]
    assert report.stale_replies == 1


def test_same_author_burst():
    ms = [msg(1, 0, "a"), msg(2, 60, "a"), msg(3, 2000, "a")]
    windows, _ = build(ms)
    assert groups(windows) == [[1, 2], [3]]
    assert rule_of(windows, 2) == "burst"


def test_dependent_message_attaches_to_previous():
    ms = [msg(1, 0, "a"), msg(2, 250, "b", text="Grazie!")]
    windows, _ = build(ms, apply_overrides(PARAMS, {"gap_course": 60}))
    assert groups(windows) == [[1, 2]]
    assert rule_of(windows, 2) == "dependent"


def test_mention_links_to_last_message_of_that_user():
    ms = [
        msg(1, 0, "marco"),
        msg(2, 700, "b"),
        msg(3, 1400, "c", mentioned_usernames=["marco"]),
    ]
    windows, _ = build(ms)
    assert groups(windows) == [[1, 3], [2]]
    assert rule_of(windows, 3) == "mention"


def test_gap_threshold_depends_on_chat_type():
    course = [msg(1, 0, "a"), msg(2, 700, "b")]
    general = [msg(1, 0, "a", chat_id=2), msg(2, 700, "b", chat_id=2)]
    assert groups(build(course)[0]) == [[1], [2]]
    windows, _ = build(general)
    assert groups(windows) == [[1, 2]]
    assert rule_of(windows, 2) == "gap"


def test_message_cap_splits_and_redirects_links():
    ms = [msg(i, i * 10, "a" if i % 2 else "b") for i in range(1, 8)]
    windows, [report] = build(ms, apply_overrides(PARAMS, {"max_messages": 3}))
    assert groups(windows) == [[1, 2, 3], [4, 5, 6], [7]]
    assert windows[0].hit_cap and rule_of(windows, 4) == "cap"
    assert rule_of(windows, 5) == "gap"
    assert report.merges["cap"] == 2


def test_token_cap_and_overlap():
    ms = [msg(i, i * 10, "a" if i % 2 else "b", text="one two three") for i in range(1, 5)]
    windows, _ = build(ms, apply_overrides(PARAMS, {"max_tokens": 9, "overlap": 1}))
    # each rendered line is "a: one two three" = 4 words
    assert groups(windows) == [[1, 2], [3, 4]]
    assert windows[1].overlap_ids == [2]


def test_orphan_reply_treated_as_normal_message():
    ms = [msg(1, 0, "a"), msg(2, 100, "b", reply_to_id=999)]
    windows, [report] = build(ms)
    assert report.orphan_replies == 1
    assert groups(windows) == [[1, 2]]
    assert rule_of(windows, 2) == "gap"


def test_service_messages_excluded_but_counted():
    ms = [msg(1, 0, "a"), msg(2, 10, "x", kind="service", service_action="join_group_by_link"), msg(3, 20, "b")]
    windows, [report] = build(ms)
    assert groups(windows) == [[1, 3]]
    assert report.excluded["service"] == 1
    assert report.service_actions["join_group_by_link"] == 1


def test_chats_never_mix():
    ms = [msg(1, 0, "a", chat_id=1), msg(1, 10, "a", chat_id=2), msg(2, 20, "b", chat_id=1, reply_to_id=1)]
    windows, reports = build(ms)
    assert len(reports) == 2
    assert {(w.chat_id, tuple(w.message_ids)) for w in windows} == {(1, (1, 2)), (2, (1,))}


def test_short_windows_are_flagged_not_dropped():
    windows, _ = build([msg(1, 0, "a"), msg(2, 5000, "b")])
    assert len(windows) == 2 and all(w.is_short for w in windows)


@pytest.mark.parametrize("text", ["ciao mondo", ["ciao ", {"type": "bold", "text": "mondo"}]])
def test_text_normalization(text):
    assert normalize_text({"text": text, "text_entities": []}) == "ciao mondo"


def test_config_hash_tracks_parameters():
    assert config_hash(PARAMS, "course") == config_hash(PARAMS, "course")
    assert config_hash(PARAMS, "course") != config_hash(PARAMS, "general")
    assert config_hash(PARAMS, "course") != config_hash(apply_overrides(PARAMS, {"burst_gap": 60}), "course")


def test_date_range_excludes_and_counts():
    ms = [msg(1, 0, "a"), msg(2, 86400 * 2, "b"), msg(3, 86400 * 4, "c")]
    params = apply_overrides(PARAMS, {"min_date": "2024-01-11", "max_date": "2024-01-13"})
    windows, [report] = build(ms, params)
    assert groups(windows) == [[2]]
    assert report.excluded["out_of_date_range"] == 2
    assert config_hash(params, "course") != config_hash(PARAMS, "course")
