import logging
import statistics
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise

from core.ingest.telegram import SKIN_TONE_PATTERN
from core.models import ChatMessage, Window, WindowLink
from core.window_config import WindowParams, config_hash

# (included messages of one chat, chat type) -> {message id: merge with the previous message?}
MergeDecider = Callable[[list[ChatMessage], str], dict[int, bool]]

RULES = ("reply", "burst", "dependent", "mention", "model", "gap", "cap")
PERCENTILES = (50, 75, 90, 95)


@dataclass
class BuildReport:
    chat_id: int
    chat_name: str
    chat_type: str
    config_hash: str
    tokenizer: str
    n_raw: int = 0
    n_included: int = 0
    excluded: Counter = field(default_factory=Counter)
    service_actions: Counter = field(default_factory=Counter)
    merges: Counter = field(default_factory=Counter)
    orphan_replies: int = 0
    stale_replies: int = 0
    replies_to_excluded: int = 0
    unresolved_mentions: int = 0
    gap_percentiles: dict[int, float] = field(default_factory=dict)


@dataclass
class _Draft:
    members: list[ChatMessage] = field(default_factory=list)
    links: list[WindowLink] = field(default_factory=list)
    overlap: list[ChatMessage] = field(default_factory=list)
    n_tokens: int = 0
    successor: int | None = None
    hit_cap: bool = False


@dataclass
class _ChatState:
    """What the linking rules can look at while scanning a chat in time order."""
    all_ids: set[int]
    placed: dict[int, ChatMessage] = field(default_factory=dict)
    window_of: dict[int, int] = field(default_factory=dict)
    last_by_author: dict[str, ChatMessage] = field(default_factory=dict)


def build_windows(
    messages: list[ChatMessage],
    params: WindowParams,
    count_tokens: Callable[[str], int],
    chat_names: dict[int, str] | None = None,
    tokenizer_name: str = "",
    logger: logging.Logger | None = None,
    merge_decider: MergeDecider | None = None,
) -> tuple[list[Window], list[BuildReport]]:
    """Builds windows chat by chat: messages of different chats never share a window.
    With `merge_decider` (and `params.merge_model` set to its id) a trained model
    replaces the gap rule: it gets the chat's included messages and type and
    returns, per message id, whether to merge it with the previous message."""
    if logger is None:
        logger = logging.getLogger("cribrum.windows")
    if bool(params.merge_model) != (merge_decider is not None):
        raise ValueError("params.merge_model and merge_decider must be given together")

    by_chat: dict[int, list[ChatMessage]] = defaultdict(list)
    for m in messages:
        by_chat[m.chat_id].append(m)

    windows: list[Window] = []
    reports: list[BuildReport] = []
    for chat_id, chat_messages in by_chat.items():
        name = (chat_names or {}).get(chat_id, str(chat_id))
        w, r = _build_chat_windows(chat_messages, name, params, count_tokens, tokenizer_name, merge_decider)
        logger.info(f"Chat {name}: {len(w)} windows from {r.n_included} messages (config {r.config_hash})")
        windows.extend(w)
        reports.append(r)
    return windows, reports


def _build_chat_windows(
    messages: list[ChatMessage],
    chat_name: str,
    params: WindowParams,
    count_tokens: Callable[[str], int],
    tokenizer_name: str,
    merge_decider: MergeDecider | None = None,
) -> tuple[list[Window], BuildReport]:
    chat_id = messages[0].chat_id
    chat_type = params.chat_type_for(chat_id)
    report = BuildReport(
        chat_id, chat_name, chat_type, config_hash(params, chat_type), tokenizer_name, n_raw=len(messages),
    )

    included = []
    for m in messages:
        if not in_date_range(m, params):
            report.excluded["out_of_date_range"] += 1
            continue
        if m.kind == "service":
            report.service_actions[m.service_action or "unknown"] += 1
        reason = exclusion_reason(m, params)
        if reason:
            report.excluded[reason] += 1
        else:
            included.append(m)
    included.sort(key=lambda m: (m.timestamp, m.id))
    report.n_included = len(included)
    report.gap_percentiles = gap_percentiles(included)

    resolve_username = _username_resolver(messages, params.mention_aliases)
    phrases = {normalize_phrase(p) for p in params.dependent_phrases}
    chat_gap = params.gap_for(chat_type)
    decisions = merge_decider(included, chat_type) if merge_decider is not None else None
    state = _ChatState(all_ids={m.id for m in messages})
    drafts: list[_Draft] = []

    for i, m in enumerate(included):
        prev = included[i - 1] if i > 0 else None
        mentioned = list(m.mentioned_user_ids)
        for username in m.mentioned_usernames:
            uid = resolve_username(username)
            if uid is None:
                report.unresolved_mentions += 1
            else:
                mentioned.append(uid)

        target, rule = _find_link(m, prev, state, mentioned, phrases, chat_gap, params, report, decisions)
        line_tokens = count_tokens(render_message(m))

        if target is None:
            drafts.append(_Draft())
            idx = len(drafts) - 1
            link = WindowLink(m.id, None)
        else:
            idx = _current(drafts, state.window_of[target.id])
            draft = drafts[idx]
            if len(draft.members) >= params.max_messages or draft.n_tokens + line_tokens > params.max_tokens:
                idx = _open_continuation(drafts, idx, params.overlap)
                link = WindowLink(m.id, "cap", target.id, capped_rule=rule)
                report.merges["cap"] += 1
            else:
                link = WindowLink(m.id, rule, target.id)
                report.merges[rule] += 1

        draft = drafts[idx]
        draft.members.append(m)
        draft.links.append(link)
        draft.n_tokens += line_tokens
        state.placed[m.id] = m
        state.window_of[m.id] = idx
        if m.from_id:
            state.last_by_author[m.from_id] = m

    windows = [_to_window(d, chat_name, chat_type, report.config_hash, params) for d in drafts]
    windows.sort(key=lambda w: (w.first_ts, w.message_ids[0]))
    return windows, report


def _find_link(
    m: ChatMessage,
    prev: ChatMessage | None,
    state: _ChatState,
    mentioned: list[str],
    phrases: set[str],
    chat_gap: int,
    params: WindowParams,
    report: BuildReport,
    decisions: dict[int, bool] | None = None,
) -> tuple[ChatMessage | None, str | None]:
    """First rule that fires, in priority order. Each message gets at most one
    link and existing windows are never fused, so a reply plus a temporal
    neighbour can't glue two separate conversations together."""
    if m.reply_to_id is not None:
        parent = state.placed.get(m.reply_to_id)
        if m.reply_to_id not in state.all_ids:
            report.orphan_replies += 1
        elif parent is None:
            report.replies_to_excluded += 1
        elif _gap(parent, m) <= params.reply_max_gap:
            return parent, "reply"
        else:
            report.stale_replies += 1

    if prev is None:
        return None, None
    gap = _gap(prev, m)

    if m.from_id and prev.from_id == m.from_id and gap <= params.burst_gap:
        return prev, "burst"

    if gap <= params.dependent_gap and is_dependent(m.text, phrases):
        return prev, "dependent"

    for uid in mentioned:
        last = state.last_by_author.get(uid)
        if last is not None and uid != m.from_id and _gap(last, m) <= params.mention_gap:
            return last, "mention"

    if decisions is not None:
        return (prev, "model") if decisions.get(m.id) else (None, None)
    if gap <= chat_gap:
        return prev, "gap"
    return None, None


def _current(drafts: list[_Draft], idx: int) -> int:
    """A window closed by the cap forwards new links to its continuation."""
    while drafts[idx].successor is not None:
        idx = drafts[idx].successor
    return idx


def _open_continuation(drafts: list[_Draft], idx: int, overlap: int) -> int:
    full = drafts[idx]
    full.hit_cap = True
    tail = full.members[-overlap:] if overlap else []
    drafts.append(_Draft(overlap=list(tail)))
    full.successor = len(drafts) - 1
    return full.successor


def _to_window(d: _Draft, chat_name: str, chat_type: str, cfg_hash: str, params: WindowParams) -> Window:
    first = d.members[0]
    return Window(
        window_id=f"{first.chat_id}-{first.id}",
        chat_id=first.chat_id,
        chat_name=chat_name,
        chat_type=chat_type,
        config_hash=cfg_hash,
        message_ids=[m.id for m in d.members],
        links=d.links,
        first_ts=first.timestamp,
        last_ts=d.members[-1].timestamp,
        authors=list(dict.fromkeys(m.author for m in d.members)),
        n_messages=len(d.members),
        n_tokens=d.n_tokens,
        overlap_ids=[m.id for m in d.overlap],
        is_short=len(d.members) <= params.short_max_messages or d.n_tokens < params.short_min_tokens,
        has_forwarded=any(m.is_forwarded for m in d.members),
        has_media=any(m.kind == "media" for m in d.members),
        hit_cap=d.hit_cap,
    )


def in_date_range(m: ChatMessage, params: WindowParams) -> bool:
    if params.min_date and m.timestamp < datetime.fromisoformat(params.min_date):
        return False
    if params.max_date and m.timestamp >= datetime.fromisoformat(params.max_date):
        return False
    return True


def exclusion_reason(m: ChatMessage, params: WindowParams) -> str | None:
    if m.from_id in params.blocked_ids:
        return "blocked"
    if m.kind == "service":
        return None if params.include["service"] else "service"
    if m.kind == "media" and not params.include["media"]:
        return "media"
    if m.kind == "poll" and not params.include["poll"]:
        return "poll"
    if m.is_forwarded and not params.include["forwarded"]:
        return "forwarded"
    return None


def render_message(m: ChatMessage) -> str:
    """The line a message contributes to a window's text (and token count)."""
    return f"{m.author}: {render_body(m)}"


def render_body(m: ChatMessage) -> str:
    text = m.text.strip()
    if m.kind == "media":
        return f"[media] {text}".strip()
    if m.kind == "poll":
        return f"[poll] {text}"
    if m.kind == "service":
        return f"[{m.service_action}]"
    return text


def normalize_phrase(text: str) -> str:
    """Lowercase, no skin tones, no punctuation except '+' (for "+1"), single spaces."""
    text = SKIN_TONE_PATTERN.sub("", text.lower())
    text = "".join(c for c in text if c == "+" or not unicodedata.category(c).startswith("P"))
    return " ".join(text.split())


def is_dependent(text: str, phrases: set[str]) -> bool:
    norm = normalize_phrase(text)
    if not norm:
        return False
    # "grazie 🙏" should match "grazie": also try the text with emoji/symbols removed.
    no_symbols = " ".join("".join(c for c in norm if c == "+" or not unicodedata.category(c).startswith("S")).split())
    return norm in phrases or (bool(no_symbols) and no_symbols in phrases)


def _username_resolver(messages: list[ChatMessage], aliases: dict[str, str]) -> Callable[[str], str | None]:
    """The export has display names, not usernames: an @username resolves via
    the config aliases, or when exactly one author's normalized display name
    equals it."""
    by_name: dict[str, set[str]] = defaultdict(set)
    for m in messages:
        if m.from_id and m.kind != "service":
            by_name[_name_key(m.author)].add(m.from_id)

    def resolve(username: str) -> str | None:
        if username in aliases:
            return aliases[username]
        candidates = by_name.get(_name_key(username), set())
        return next(iter(candidates)) if len(candidates) == 1 else None

    return resolve


def _name_key(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _gap(a: ChatMessage, b: ChatMessage) -> float:
    return abs((b.timestamp - a.timestamp).total_seconds())


def gap_percentiles(messages: list[ChatMessage], percentiles: tuple[int, ...] = PERCENTILES) -> dict[int, float]:
    """Percentiles of the gaps between consecutive messages (already time-sorted)."""
    gaps = [_gap(a, b) for a, b in pairwise(messages)]
    if len(gaps) < 2:
        return {}
    # quantiles(n=100) returns the 99 cut points p1..p99
    cuts = statistics.quantiles(gaps, n=100, method="inclusive")
    return {p: cuts[p - 1] for p in percentiles}
