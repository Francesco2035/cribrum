import hashlib
import json
import pickle
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import numpy as np

from core.annotation import Candidate, ChatData, band_of
from core.merge_features import EMBEDDING_FEATURES, pair_features, prepare_chat
from core.models import ChatMessage

DEFAULT_MODEL_PATH = Path("data/models/merge_model.pkl")
MAX_GAP = 10800      # pairs above this gap were never labelled: the model does not decide them


@dataclass
class MergeModel:
    """A trained classifier plus everything needed to apply it the same way it was trained."""
    estimator: object
    features: tuple[str, ...]
    name: str
    always_merge_below: int = 0
    max_gap: int = MAX_GAP
    meta: dict = field(default_factory=dict)
    cue_lists: dict[str, tuple[str, ...]] = field(default_factory=dict)   # config/merge_cues.yaml at training time


def save_model(model: MergeModel, path: Path) -> str:
    """Pickles the model, writes `<name>.json` with its metadata next to it and returns the model id."""
    if set(model.features) & set(EMBEDDING_FEATURES):
        raise ValueError("Embedding features are not supported in windows: train on base features")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)
    mid = model_id(path)
    meta = {"model_id": mid, "name": model.name, "features": list(model.features),
            "always_merge_below": model.always_merge_below, "max_gap": model.max_gap, **model.meta,
            "cue_lists": {k: list(v) for k, v in model.cue_lists.items()}}
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return mid


def load_model(path: Path) -> tuple[MergeModel, str]:
    with open(path, "rb") as f:
        return pickle.load(f), model_id(path)


def model_id(path: Path) -> str:
    """Content hash: it goes into the window config hash, so a retrained model gives a new folder."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def decide_pairs(model: MergeModel, included: list[ChatMessage], general: bool) -> dict[int, bool]:
    """Merge decision for every consecutive pair of one chat, keyed by the later message id.
    The features only look at the messages, not at the windows, so all pairs are
    decided in one batch before the windows are built. Pairs above `max_gap` are missing."""
    chat = ChatData("", "", included, {m.id: m for m in included}, {m.id: i for i, m in enumerate(included)})
    cf = prepare_chat(chat, general, cue_lists=model.cue_lists)
    out: dict[int, bool] = {}
    pending: list[Candidate] = []
    for prev, m in pairwise(included):
        gap = round((m.timestamp - prev.timestamp).total_seconds())
        if gap <= model.always_merge_below:
            out[m.id] = True
        elif gap <= model.max_gap:
            pending.append(Candidate("", m.chat_id, m.id, prev.id, gap, band_of(gap) or ""))
    if pending:
        X = np.array([[pair_features(cf, c)[f] for f in model.features] for c in pending], dtype=float)
        out.update(zip((c.message_id for c in pending), model.estimator.predict(X).astype(bool).tolist()))
    return out


def decider_for(model: MergeModel):
    """Adapter to the `MergeDecider` signature expected by `build_windows`."""
    return lambda included, chat_type: decide_pairs(model, included, chat_type == "general")
