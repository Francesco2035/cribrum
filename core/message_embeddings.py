import logging
from pathlib import Path

import numpy as np

from core.annotation import ChatData
from core.embeddings import encode_passages
from core.merge_features import is_media

CACHE_DIR = Path("data/cache/message_embeddings")
logger = logging.getLogger("cribrum.message_embeddings")


def load_cache(path: Path) -> dict[int, np.ndarray]:
    if not path.exists():
        return {}
    data = np.load(path)
    return dict(zip(data["ids"].tolist(), data["vectors"]))


def save_cache(path: Path, vectors: dict[int, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = np.array(sorted(vectors), dtype=np.int64)
    np.savez_compressed(path, ids=ids, vectors=np.stack([vectors[i] for i in ids]))


def message_vectors(chat: ChatData, ids: set[int], emb_cfg: dict, cache_dir: Path = CACHE_DIR) -> dict[int, np.ndarray]:
    """E5 vectors of the given messages, computed only for those missing from
    the per-chat cache. Media-only and empty messages get no vector."""
    path = cache_dir / f"{chat.stem}.npz"
    cache = load_cache(path)
    todo = sorted(i for i in ids if i not in cache and not is_media(chat.by_id[i]))
    if todo:
        logger.info(f"{chat.stem}: encoding {len(todo)} messages")
        # Message-to-message comparison is symmetric: E5 wants the "query: " prefix on both sides.
        vecs = encode_passages([chat.by_id[i].text for i in todo], emb_cfg["model_name"],
                               emb_cfg.get("batch_size", 32), passage_prefix=emb_cfg.get("query_prefix", "query: "))
        cache.update(zip(todo, np.asarray(vecs, dtype=np.float32)))
        save_cache(path, cache)
    return {i: cache[i] for i in ids if i in cache}
