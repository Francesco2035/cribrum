from collections import defaultdict
from collections.abc import Callable

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from core.annotation import GAP_BANDS, Candidate, labelled_keys
from core.merge_features import ChatFeatures, pair_features

TARGET = {"same": 1, "new": 0, "earlier": 0}       # unsure has no target: left out


def model_factories(seed: int = 0) -> dict[str, Callable]:
    # class_weight="balanced": "same" is the majority, the models should not win by always merging.
    return {
        "tree_d3": lambda: DecisionTreeClassifier(max_depth=3, min_samples_leaf=10, class_weight="balanced", random_state=seed),
        "tree_d5": lambda: DecisionTreeClassifier(max_depth=5, min_samples_leaf=10, class_weight="balanced", random_state=seed),
        "forest": lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced",
                                                 random_state=seed, n_jobs=-1),
        "boosting": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                           class_weight="balanced", random_state=seed),
        "logreg": lambda: make_pipeline(SimpleImputer(), StandardScaler(),
                                        LogisticRegression(max_iter=2000, class_weight="balanced")),
    }


def training_records(human: list[dict], assistant: list[dict]) -> list[dict]:
    """Assistant labels of pairs you did not label: for a pair labelled by both, yours wins."""
    mine = labelled_keys(human)
    return [r for r in assistant if (r["chat_id"], r["message_id"]) not in mine]


def build_rows(records: list[dict], by_key: dict[tuple[int, int], Candidate],
               chat_features: dict[str, ChatFeatures], gap_threshold: Callable[[str], int]) -> list[dict]:
    """One row per labelled pair with a target: identifiers, label, source and features."""
    rows = []
    for r in records:
        c = by_key.get((r["chat_id"], r["message_id"]))
        y = TARGET.get(r["label"])
        if c is None or y is None or c.chat not in chat_features:
            continue
        rows.append({"chat": c.chat, "message_id": c.message_id, "gap_s": c.gap_s, "band": c.band,
                     "source": r.get("source", "human"), "label": r["label"], "y": y,
                     "gap_threshold": gap_threshold(c.chat), **pair_features(chat_features[c.chat], c)})
    return rows


def matrix(rows: list[dict], features: tuple[str, ...]) -> np.ndarray:
    return np.array([[r[f] for f in features] for r in rows], dtype=float)


def targets(rows: list[dict]) -> np.ndarray:
    return np.array([r["y"] for r in rows], dtype=int)


def gap_rule(rows: list[dict]) -> np.ndarray:
    """Today's rule: merge when the gap is within the threshold of the chat type."""
    return np.array([int(r["gap_s"] <= r["gap_threshold"]) for r in rows])


def with_floor(rows: list[dict], pred: np.ndarray, seconds: int) -> np.ndarray:
    """Hybrid: always merge within `seconds`, the model decides above."""
    return np.array([1 if r["gap_s"] <= seconds else int(p) for r, p in zip(rows, pred)])


def leave_one_chat_out(train: list[dict], test: list[dict], features: tuple[str, ...], factory: Callable) -> np.ndarray:
    """Each chat of `test` is predicted by a model that never saw that chat."""
    preds = np.zeros(len(test), dtype=int)
    for chat in sorted({r["chat"] for r in test}):
        fit_rows = [r for r in train if r["chat"] != chat]
        idx = [i for i, r in enumerate(test) if r["chat"] == chat]
        model = factory().fit(matrix(fit_rows, features), targets(fit_rows))
        preds[idx] = model.predict(matrix([test[i] for i in idx], features))
    return preds


def scores(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {"n": len(y), "accuracy": accuracy_score(y, pred), "balanced": balanced_accuracy_score(y, pred),
            "f1_merge": f1_score(y, pred, pos_label=1, zero_division=0),
            "f1_split": f1_score(y, pred, pos_label=0, zero_division=0)}


def accuracy_by_band(rows: list[dict], pred: np.ndarray) -> dict[str, tuple[int, float]]:
    hits: dict[str, list[int]] = defaultdict(list)
    for r, p in zip(rows, pred):
        hits[r["band"]].append(int(r["y"] == p))
    order = [f"{lo}-{hi}" for lo, hi in GAP_BANDS]
    return {b: (len(hits[b]), float(np.mean(hits[b]))) for b in order if hits[b]}


def tree_rules(rows: list[dict], features: tuple[str, ...], depth: int = 3) -> str:
    tree = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=10, class_weight="balanced", random_state=0)
    tree.fit(matrix(rows, features), targets(rows))
    return export_text(tree, feature_names=list(features), class_names=["split", "merge"], decimals=2)


def ablation_sets(base: tuple[str, ...], groups: dict[str, tuple[str, ...]], extra: tuple[str, ...] = ()) -> dict[str, tuple[str, ...]]:
    """base, base + each group alone, everything; plus everything + `extra` (embeddings) if given."""
    every = base + tuple(f for g in groups.values() for f in g)
    sets = {"base": base, **{f"base+{name}": base + g for name, g in groups.items()}, "all": every}
    if extra:
        sets["all+emb"] = every + extra
    return sets


def parse_feature_groups(spec: str, base: tuple[str, ...], groups: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """"all", "base" or a comma list of group names (base features are always included)."""
    names = [s.strip() for s in spec.split(",") if s.strip()]
    if names == ["all"]:
        names = list(groups)
    unknown = set(names) - set(groups) - {"base"}
    if unknown:
        raise ValueError(f"Unknown feature groups {sorted(unknown)}, expected 'all', 'base' or {sorted(groups)}")
    return base + tuple(f for name in groups if name in names for f in groups[name])
