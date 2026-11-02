import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

TOPICS_ROOT = Path("data/topics")
OUTLIER = -1


@dataclass(frozen=True)
class TopicParams:
    min_words: int = 5                  # windows with fewer words are left out of the fit (greetings, "ok")
    min_topic_size: int = 10            # HDBSCAN min_cluster_size: smallest group that counts as a topic
    min_samples: int | None = None      # HDBSCAN: higher = more conservative, more outliers (None = min_topic_size)
    cluster_selection: str = "leaf"     # HDBSCAN: "eom" = few large topics, "leaf" = many small, specific ones
    n_neighbors: int = 15               # UMAP: local (small) vs global (large) structure
    n_components: int = 5               # UMAP: dimensions given to HDBSCAN
    random_state: int = 42              # UMAP seed: same input and params give the same topics
    ngram_max: int = 2                  # keywords: single words and pairs of words
    min_df: int = 2                     # a keyword must appear in at least this many windows
    top_n_words: int = 10
    n_examples: int = 3                 # representative windows saved per topic
    center_languages: bool = True       # remove the per-language mean from the vectors (see docs/it/code/config/topics.md)
    stop_words_file: str = "config/topic_stopwords.yaml"


def load_topic_params(path: Path, overrides: dict | None = None) -> TopicParams:
    raw = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    known = {f.name for f in dataclasses.fields(TopicParams)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Unknown topic config keys in {path}: {sorted(unknown)}")
    raw.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return TopicParams(**raw)


def load_stop_words(path: Path) -> list[str]:
    """English list of scikit-learn plus the Italian and chat-specific words of the YAML file."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    words = set(ENGLISH_STOP_WORDS)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        for group in raw.values():
            words.update(str(w).lower() for w in group or ())
    return sorted(words)


IT_MARKERS = frozenset("il lo la gli le di del della che non per con una sono è ho hai anche ma come perché più se qualcuno esame grazie".split())
EN_MARKERS = frozenset("the is are of to and that for with you it this have has not but what how if someone exam thanks".split())


def guess_language(text: str) -> str:
    """'it' or 'en' by counting very common words; ties and empty texts count as 'en'."""
    words = text.lower().split()
    it = sum(w in IT_MARKERS for w in words)
    en = sum(w in EN_MARKERS for w in words)
    return "it" if it > en else "en"


MIN_LANGUAGE_GROUP = 10     # below this many windows a language mean is unreliable: those vectors stay as they are


def center_by_language(vectors: np.ndarray, languages: list[str], min_group: int = MIN_LANGUAGE_GROUP) -> np.ndarray:
    """Subtract each language's mean vector and renormalise: what is left is mostly the topic,
    so an Italian and an English window about the same thing end up close to each other.
    A language with fewer than `min_group` windows is not centred (one window would become zero)."""
    out = vectors.astype(np.float32).copy()
    langs = np.array(languages)
    for lang in set(languages):
        idx = langs == lang
        if idx.sum() >= min_group:
            out[idx] -= out[idx].mean(axis=0)
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1.0, norms)


def params_hash(params: TopicParams, stop_words: list[str]) -> str:
    """Topic results depend on the params and on the stop word list, not on the file name."""
    data = dataclasses.asdict(params)
    data.pop("stop_words_file")
    data["stop_words"] = sorted(stop_words)
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def fit_topics(texts: list[str], vectors: np.ndarray, params: TopicParams, stop_words: list[str]):
    """BERTopic on precomputed embeddings: nothing is downloaded or re-encoded."""
    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    umap_model = UMAP(n_neighbors=min(params.n_neighbors, len(texts) - 1), n_components=params.n_components,
                      min_dist=0.0, metric="cosine", random_state=params.random_state)
    hdbscan_model = HDBSCAN(min_cluster_size=params.min_topic_size, min_samples=params.min_samples,
                            metric="euclidean", cluster_selection_method=params.cluster_selection, prediction_data=True)
    vectorizer = CountVectorizer(stop_words=stop_words, ngram_range=(1, params.ngram_max),
                                 min_df=min(params.min_df, len(texts)), token_pattern=r"(?u)\b[^\W\d_]{2,}\b")
    # language="multilingual": with "english" BERTopic strips every non-ASCII character before
    # computing keywords ("perché" -> "perch"); embeddings are ours, so the setting only affects that.
    model = BERTopic(embedding_model=None, language="multilingual", umap_model=umap_model, hdbscan_model=hdbscan_model,
                     vectorizer_model=vectorizer, top_n_words=params.top_n_words, verbose=False)
    topics, _ = model.fit_transform(texts, embeddings=vectors)
    return model, [int(t) for t in topics]


def summarize(model, topics: list[int], ids: list[str], vectors: np.ndarray, n_examples: int) -> list[dict]:
    """One record per topic (outliers included): size, keywords, centroid and the members closest to it."""
    out = []
    labels = np.array(topics)
    for t in sorted(set(topics)):
        idx = np.flatnonzero(labels == t)
        centroid = vectors[idx].mean(axis=0)
        centroid /= np.linalg.norm(centroid) or 1.0
        closest = idx[np.argsort(-(vectors[idx] @ centroid))][:n_examples]
        words = (model.get_topic(t) or []) if t != OUTLIER else []
        out.append({"topic": t, "size": int(len(idx)),
                    "keywords": [[w, round(float(s), 4)] for w, s in words],
                    "examples": [ids[i] for i in closest], "centroid": [round(float(x), 6) for x in centroid]})
    return out


def topics_dir(chat: str, windows_hash: str, topics_hash: str, root: Path = TOPICS_ROOT) -> Path:
    return root / chat / windows_hash / topics_hash


def save_topics(out_dir: Path, summary: list[dict], assignments: dict[str, int], meta: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "topics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out_dir / "assignments.jsonl", "w", encoding="utf-8") as f:
        for wid, t in assignments.items():
            f.write(json.dumps({"window_id": wid, "topic": t}) + "\n")
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def topics_markdown(summary: list[dict], texts: dict[str, str], title: str, max_chars: int = 600) -> str:
    """Readable report: each topic with its keywords and its most central windows."""
    parts = [f"# {title}\n"]
    for rec in sorted(summary, key=lambda r: (r["topic"] == OUTLIER, -r["size"])):
        name = "Outliers (no topic)" if rec["topic"] == OUTLIER else f"Topic {rec['topic']}"
        keywords = ", ".join(w for w, _ in rec["keywords"][:10])
        parts.append(f"## {name} · {rec['size']} windows\n")
        if keywords:
            parts.append(f"**Keywords:** {keywords}\n")
        for wid in rec["examples"]:
            body = texts.get(wid, "").replace("\n", " ⏎ ")
            parts.append(f"- `{wid}` {body[:max_chars]}{'…' if len(body) > max_chars else ''}")
        parts.append("")
    return "\n".join(parts)
