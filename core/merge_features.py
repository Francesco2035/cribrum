import math
import re
import statistics
from bisect import bisect_left
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from core.annotation import Candidate, ChatData
from core.windows import normalize_phrase

RECENT = 5           # messages before the candidate looked at by the "recent" features
SHORT_WINDOW = 1800  # s: "last 30 minutes" of the density and author features
LONG_WINDOW = 3600   # s: "last hour" for the number of active authors
SHRINK_K = 5         # words at which the raw cosine and the chat mean weigh the same

QUESTION_RE = re.compile(r"\?|^(chi|come|cosa|dove|quando|quanto|perch|qual|does|do|is|are|can|how|what|when|where|why|which|who)\b", re.I)
OPENER_RE = re.compile(
    r"^(ciao|salve|buongiorno|buonasera|hey|hi|hello|raga|ragazzi|guys|scusate|scusa|qualcuno|"
    r"does any|do you|anyone|someone|somebody|has anyone|is there|domanda|question)\b", re.I)
THANKS_RE = re.compile(r"\b(grazie|thanks?|thx|ty|tnx)\b", re.I)
WORD_RE = re.compile(r"\w+")

BASE_FEATURES = (
    "log_gap", "gap_rel", "same_author", "author_in_recent",
    "prev_question", "cur_question", "cur_opener", "cur_thanks",
    "log_prev_words", "log_cur_words", "prev_media", "cur_media",
    "cur_has_reply", "prev_has_reply", "tfidf_prev", "tfidf_max_recent", "general_chat",
)
FEATURE_GROUPS = {
    "density": ("log_msgs_30m", "log_authors_60m"),
    "author": ("log_author_msgs_30m", "prev_replies_to_cur_author", "cur_author_replied_30m"),
    "group_request": ("cur_group_request",),
    "continuity": ("cur_answer_start", "cur_anaphora_start"),
}
ALL_FEATURES = BASE_FEATURES + tuple(f for group in FEATURE_GROUPS.values() for f in group)
EMBEDDING_FEATURES = ("emb_prev", "emb_prev_shrunk", "emb_max_recent", "emb_recent_mean")

# Cue list (config/merge_cues.yaml) -> where the phrase must appear in the normalised text.
CUE_MODES = {"group_request": "anywhere", "answer_start": "start", "anaphora_start": "start"}


@dataclass
class ChatFeatures:
    """Per-chat state shared by the pairs of that chat."""
    chat: ChatData
    general: bool
    median_gap: float
    tfidf: object                                    # sparse matrix, rows aligned with chat.included
    vectors: dict[int, np.ndarray] = field(default_factory=dict)   # message id -> unit embedding
    mean_cos: float = 0.0
    cues: dict[str, re.Pattern | None] = field(default_factory=dict)
    times: list[float] = field(default_factory=list)               # epoch seconds, aligned with chat.included


def prepare_chat(chat: ChatData, general: bool, vectors: dict[int, np.ndarray] | None = None,
                 cue_lists: dict[str, tuple[str, ...]] | None = None) -> ChatFeatures:
    vectors = vectors or {}
    return ChatFeatures(chat, general, median_gap(chat), tfidf_matrix(chat), vectors,
                        mean_consecutive_cos(chat, vectors), compile_cues(cue_lists or {}),
                        [m.timestamp.timestamp() for m in chat.included])


def compile_cues(cue_lists: dict[str, tuple[str, ...]]) -> dict[str, re.Pattern | None]:
    """One regex per list, on whole words of the normalised text; an empty list never matches."""
    out = {}
    for name, mode in CUE_MODES.items():
        phrases = sorted({normalize_phrase(p) for p in cue_lists.get(name, ())} - {""}, key=len, reverse=True)
        alts = "|".join(re.escape(p) for p in phrases)
        prefix = "^" if mode == "start" else "(?:^| )"
        out[name] = re.compile(rf"{prefix}(?:{alts})(?: |$)") if phrases else None
    return out


def cue_hit(cf: ChatFeatures, name: str, text: str) -> float:
    rx = cf.cues.get(name)
    return float(rx is not None and rx.search(normalize_phrase(text or "")) is not None)


def median_gap(chat: ChatData) -> float:
    gaps = [(b.timestamp - a.timestamp).total_seconds() for a, b in pairwise(chat.included)]
    return max(1.0, statistics.median(gaps)) if gaps else 1.0


def tfidf_matrix(chat: ChatData):
    texts = [m.text or "" for m in chat.included]
    vec = TfidfVectorizer(lowercase=True, sublinear_tf=True, token_pattern=r"(?u)\b\w\w+\b")
    try:
        return vec.fit_transform(texts)
    except ValueError:                               # empty vocabulary
        return None


def mean_consecutive_cos(chat: ChatData, vectors: dict[int, np.ndarray]) -> float:
    sims = [float(vectors[a.id] @ vectors[b.id]) for a, b in pairwise(chat.included)
            if a.id in vectors and b.id in vectors]
    return statistics.fmean(sims) if sims else 0.0


def shrink(cos: float, n_words: int, mean: float, k: int = SHRINK_K) -> float:
    """Short texts give unreliable cosines: pull them towards the chat mean, not towards 0."""
    w = n_words / (n_words + k)
    return w * cos + (1 - w) * mean


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def is_media(m) -> bool:
    return m.kind != "text" or (m.text or "").strip() in ("", "[media]")


def pair_features(cf: ChatFeatures, c: Candidate) -> dict[str, float]:
    i = cf.chat.position[c.message_id]
    cur, prev = cf.chat.included[i], cf.chat.included[i - 1]
    recent = cf.chat.included[max(0, i - RECENT):i]
    feats = {
        "log_gap": math.log1p(c.gap_s),
        "gap_rel": c.gap_s / cf.median_gap,
        "same_author": float(cur.from_id is not None and cur.from_id == prev.from_id),
        "author_in_recent": float(any(m.from_id == cur.from_id for m in recent[:-1])),
        "prev_question": float(bool(QUESTION_RE.search(prev.text or ""))),
        "cur_question": float(bool(QUESTION_RE.search(cur.text or ""))),
        "cur_opener": float(bool(OPENER_RE.match((cur.text or "").strip()))),
        "cur_thanks": float(bool(THANKS_RE.search(cur.text or ""))),
        "log_prev_words": math.log1p(word_count(prev.text)),
        "log_cur_words": math.log1p(word_count(cur.text)),
        "prev_media": float(is_media(prev)),
        "cur_media": float(is_media(cur)),
        "cur_has_reply": float(cur.reply_to_id is not None),
        "prev_has_reply": float(prev.reply_to_id is not None),
        "general_chat": float(cf.general),
    }
    feats.update(_activity_features(cf, i, cur, prev))
    feats.update({name: cue_hit(cf, cue, cur.text) for name, cue in
                  (("cur_group_request", "group_request"), ("cur_answer_start", "answer_start"),
                   ("cur_anaphora_start", "anaphora_start"))})
    feats.update(_tfidf_features(cf, i, len(recent)))
    feats.update(_embedding_features(cf, cur, prev, recent))
    return feats


def _activity_features(cf: ChatFeatures, i: int, cur, prev) -> dict[str, float]:
    """How busy the chat is right before T, and how involved T's author already is."""
    t = cf.times[i]
    last_30 = cf.chat.included[bisect_left(cf.times, t - SHORT_WINDOW):i]
    last_60 = cf.chat.included[bisect_left(cf.times, t - LONG_WINDOW):i]
    author = cur.from_id
    parent_of = lambda m: cf.chat.by_id.get(m.reply_to_id) if m.reply_to_id is not None else None
    replied = any(m.from_id != author and (p := parent_of(m)) is not None and p.from_id == author for m in last_30)
    prev_parent = parent_of(prev)
    return {
        "log_msgs_30m": math.log1p(len(last_30)),
        "log_authors_60m": math.log1p(len({m.from_id for m in last_60})),
        "log_author_msgs_30m": math.log1p(sum(m.from_id == author for m in last_30)) if author else 0.0,
        "prev_replies_to_cur_author": float(author is not None and prev_parent is not None and prev_parent.from_id == author),
        "cur_author_replied_30m": float(author is not None and replied),
    }


def _tfidf_features(cf: ChatFeatures, i: int, n_recent: int) -> dict[str, float]:
    if cf.tfidf is None:
        return {"tfidf_prev": 0.0, "tfidf_max_recent": 0.0}
    sims = (cf.tfidf[i - n_recent:i] @ cf.tfidf[i].T).toarray().ravel()   # rows are L2-normalised
    return {"tfidf_prev": float(sims[-1]), "tfidf_max_recent": float(sims.max())}


def _embedding_features(cf: ChatFeatures, cur, prev, recent) -> dict[str, float]:
    nan = {name: math.nan for name in EMBEDDING_FEATURES}
    v = cf.vectors.get(cur.id)
    if v is None:
        return nan
    others = [cf.vectors[m.id] for m in recent if m.id in cf.vectors]
    out = dict(nan)
    if prev.id in cf.vectors:
        cos = float(v @ cf.vectors[prev.id])
        out["emb_prev"] = cos
        out["emb_prev_shrunk"] = shrink(cos, min(word_count(cur.text), word_count(prev.text)), cf.mean_cos)
    if others:
        sims = np.stack(others) @ v
        centroid = np.mean(others, axis=0)
        out["emb_max_recent"] = float(sims.max())
        out["emb_recent_mean"] = float(centroid @ v / (np.linalg.norm(centroid) or 1.0))
    return out


def needed_ids(chat: ChatData, cands: list[Candidate]) -> set[int]:
    """Messages whose embedding the features of `cands` need: each pair and its recent context."""
    ids = set()
    for c in cands:
        i = chat.position[c.message_id]
        ids.update(m.id for m in chat.included[max(0, i - RECENT):i + 1])
    return ids
