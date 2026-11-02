import dataclasses
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from core.topic_results import ChatResult
from core.topics import OUTLIER, center_by_language, guess_language

FACETS_ROOT = Path("data/facets")
Key = tuple[str, str]                   # (chat, window id)


@dataclass(frozen=True)
class FacetParams:
    merge_similarity: float = 0.45      # topics this similar (average linkage on centroids) form one facet
    min_chats: int = 2                  # a facet whose topics span at least this many chats is "shared"
    member_percentile: float = 25.0     # a window joins a facet if as close as this percentile of its members
    top_n_words: int = 10
    n_examples: int = 3
    stop_words_file: str = "config/topic_stopwords.yaml"


def load_facet_params(path: Path, overrides: dict | None = None) -> FacetParams:
    raw = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    unknown = set(raw) - {f.name for f in dataclasses.fields(FacetParams)}
    if unknown:
        raise ValueError(f"Unknown facet config keys in {path}: {sorted(unknown)}")
    raw.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return FacetParams(**raw)


@dataclass
class TopicRef:
    chat: str
    topic: int
    members: list[Key]
    centroid: np.ndarray


@dataclass
class Facet:
    id: str
    kind: str                           # "shared" (spans >= min_chats chats) or "local"
    topics: list[tuple[str, int]]
    members: list[Key]                  # windows of its topics
    prototype: np.ndarray
    keywords: list[str] = field(default_factory=list)
    threshold: float = 0.0
    examples: list[Key] = field(default_factory=list)

    @property
    def topic_chats(self) -> list[str]:
        return sorted({chat for chat, _ in self.topics})


def unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n else v


def shared_space(results: list[ChatResult]) -> dict[Key, np.ndarray]:
    """Every embedded window of every chat, language-centred all together: one space for all chats."""
    keys = [(r.chat, wid) for r in results for wid in r.vectors]
    by_chat = {r.chat: r for r in results}
    vecs = np.stack([by_chat[c].vectors[w] for c, w in keys])
    langs = [guess_language(by_chat[c].texts.get(w, "")) for c, w in keys]
    return dict(zip(keys, center_by_language(vecs, langs)))


def topic_refs(results: list[ChatResult], space: dict[Key, np.ndarray]) -> list[TopicRef]:
    """One reference per topic (outliers excluded), with its centroid in the shared space."""
    refs = []
    for r in sorted(results, key=lambda r: r.chat):
        members: dict[int, list[Key]] = {}
        for wid, t in r.assignments.items():
            if t != OUTLIER and (r.chat, wid) in space:
                members.setdefault(t, []).append((r.chat, wid))
        for t in sorted(members):
            refs.append(TopicRef(r.chat, t, members[t], unit(np.mean([space[k] for k in members[t]], axis=0))))
    return refs


def cluster_topics(centroids: np.ndarray, merge_similarity: float) -> list[int]:
    """Average-linkage clustering on cosine distance: the number of clusters follows from the threshold."""
    if len(centroids) < 2:
        return [0] * len(centroids)
    from sklearn.cluster import AgglomerativeClustering
    model = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                    distance_threshold=1.0 - merge_similarity)
    return model.fit_predict(centroids).tolist()


def build_facets(refs: list[TopicRef], labels: list[int], space: dict[Key, np.ndarray], params: FacetParams) -> list[Facet]:
    groups: dict[int, list[TopicRef]] = {}
    for ref, label in zip(refs, labels):
        groups.setdefault(label, []).append(ref)
    facets = []
    for group in groups.values():
        members = [k for ref in group for k in ref.members]
        proto = unit(np.mean([space[k] for k in members], axis=0))
        n_chats = len({ref.chat for ref in group})
        sims = np.array([space[k] @ proto for k in members])
        facets.append(Facet("", "shared" if n_chats >= params.min_chats else "local",
                            [(ref.chat, ref.topic) for ref in group], members, proto,
                            threshold=float(np.percentile(sims, params.member_percentile)),
                            examples=[members[i] for i in np.argsort(-sims)[:params.n_examples]]))
    # Stable, readable ids: biggest facet first; ties broken by the first topic so the order is deterministic.
    facets.sort(key=lambda f: (-len(f.members), f.topics[0]))
    for i, f in enumerate(facets):
        f.id = f"F{i:03d}"
    return facets


def facet_keywords(facets: list[Facet], texts: dict[Key, str], stop_words: list[str], top_n: int) -> None:
    """Class-based TF-IDF: one document per facet, so a word scores high if it is frequent in this
    facet and rare in the others. The same formula BERTopic uses for topics, applied to facets."""
    from sklearn.feature_extraction.text import CountVectorizer
    docs = [" ".join(texts.get(k, "") for k in f.members) for f in facets]
    vec = CountVectorizer(stop_words=stop_words, ngram_range=(1, 2), token_pattern=r"(?u)\b[^\W\d_]{2,}\b")
    try:
        counts = vec.fit_transform(docs).toarray().astype(float)
    except ValueError:                                  # nothing left after stop words
        return
    words = vec.get_feature_names_out()
    tf = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
    avg_words = counts.sum() / len(facets)
    idf = np.log(1 + avg_words / np.maximum(counts.sum(axis=0), 1))
    scores = tf * idf
    for f, row in zip(facets, scores):
        f.keywords = [str(words[j]) for j in np.argsort(-row)[:top_n] if row[j] > 0]


def assign_windows(space: dict[Key, np.ndarray], eligible: list[Key], facets: list[Facet]) -> dict[Key, tuple[str | None, float, str]]:
    """Members keep their facet ("topic"). Any other window goes to the nearest facet among those its
    own chat already has through its topics ("nearest"), if at least as close as that facet's
    threshold; otherwise to no facet. So which chats share a facet is decided by topics only, and
    this step recovers the windows left out of the topics inside their chat's own themes."""
    member_of = {k: f for f in facets for k in f.members}
    protos = np.stack([f.prototype for f in facets])
    chats_of = [set(f.topic_chats) for f in facets]
    out = {}
    for k in eligible:
        if k in member_of:
            f = member_of[k]
            out[k] = (f.id, float(f.prototype @ space[k]), "topic")
            continue
        allowed = [k[0] in c for c in chats_of]
        if not any(allowed):
            out[k] = (None, 0.0, "none")
            continue
        sims = np.where(allowed, protos @ space[k], -np.inf)
        best = int(np.argmax(sims))
        hit = sims[best] >= facets[best].threshold
        out[k] = (facets[best].id if hit else None, float(sims[best]), "nearest" if hit else "none")
    return out


def eligible_windows(results: list[ChatResult], space: dict[Key, np.ndarray]) -> list[Key]:
    """Windows that can get a facet: embedded and with the minimum number of words used by `discover`."""
    return [(r.chat, wid) for r in results for wid in r.vectors
            if (r.chat, wid) in space and len(r.texts.get(wid, "").split()) >= r.min_words]


def facets_hash(params: FacetParams, topics_dirs: list[Path], stop_words: list[str]) -> str:
    data = dataclasses.asdict(params)
    data.pop("stop_words_file")
    data["stop_words"] = sorted(stop_words)
    data["inputs"] = sorted(str(p) for p in topics_dirs)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def save_facets(out_dir: Path, facets: list[Facet], assignments: dict, meta: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    assigned = Counter(fid for fid, _, _ in assignments.values() if fid)
    per_chat: dict[str, Counter] = {}
    for (chat, _), (fid, _, _) in assignments.items():
        if fid:
            per_chat.setdefault(fid, Counter())[chat] += 1
    records = [{"id": f.id, "kind": f.kind, "keywords": f.keywords, "topic_chats": f.topic_chats,
                "topics": [list(t) for t in f.topics], "n_members": len(f.members), "n_assigned": assigned[f.id],
                "windows_per_chat": dict(sorted(per_chat.get(f.id, {}).items())),
                "threshold": round(f.threshold, 4), "examples": [list(k) for k in f.examples]} for f in facets]
    (out_dir / "facets.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    np.save(out_dir / "prototypes.npy", np.stack([f.prototype for f in facets]).astype(np.float32))
    with open(out_dir / "assignments.jsonl", "w", encoding="utf-8") as fh:
        for (chat, wid), (fid, sim, source) in assignments.items():
            fh.write(json.dumps({"chat": chat, "window_id": wid, "facet": fid,
                                 "similarity": round(sim, 4), "source": source}) + "\n")
    (out_dir / "meta.json").write_text(json.dumps({**meta, "created_at": datetime.now().isoformat(timespec="seconds")},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")


def load_facets(out_dir: Path) -> tuple[list[dict], np.ndarray, list[dict], dict]:
    records = json.loads((out_dir / "facets.json").read_text(encoding="utf-8"))
    with open(out_dir / "assignments.jsonl", encoding="utf-8") as f:
        assignments = [json.loads(line) for line in f]
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    return records, np.load(out_dir / "prototypes.npy"), assignments, meta


def latest_facets_dir(root: Path = FACETS_ROOT) -> Path | None:
    results = [m.parent for m in root.glob("*/meta.json")]
    return max(results, key=lambda p: (p / "meta.json").stat().st_mtime) if results else None
