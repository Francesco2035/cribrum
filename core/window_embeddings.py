import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from core.embeddings import encode_passages
from core.models import ChatMessage

EMBEDDINGS_ROOT = Path("data/embeddings")
logger = logging.getLogger("cribrum.window_embeddings")


def load_windows(windows_dir: Path) -> list[dict]:
    with open(windows_dir / "windows.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def chat_and_hash(windows_dir: Path) -> tuple[str, str]:
    """`data/windows/<chat>/<config_hash>` -> (chat, config_hash)."""
    return windows_dir.parent.name, windows_dir.name


def message_body(m: ChatMessage) -> str:
    """Text a message contributes to its window's document: no author name, no media marker."""
    return (m.text or "").strip()


def window_text(window: dict, by_id: dict[int, ChatMessage]) -> str:
    """Member messages only (overlap messages belong to the previous window), one per line."""
    lines = (message_body(by_id[mid]) for mid in window["message_ids"] if mid in by_id)
    return "\n".join(line for line in lines if line)


def embeddings_dir(windows_dir: Path, root: Path = EMBEDDINGS_ROOT) -> Path:
    chat, cfg_hash = chat_and_hash(windows_dir)
    return root / chat / cfg_hash


def embed_texts(texts: list[str], emb_cfg: dict) -> np.ndarray:
    # Clustering is a symmetric task: E5 wants the "query: " prefix on every text.
    return np.asarray(encode_passages(texts, emb_cfg["model_name"], emb_cfg.get("batch_size", 32),
                                      passage_prefix=emb_cfg.get("query_prefix", "query: ")), dtype=np.float32)


def save_embeddings(out_dir: Path, ids: list[str], vectors: np.ndarray, meta: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "vectors.npy", vectors)
    full = {**meta, "window_ids": ids, "dim": int(vectors.shape[1]) if len(vectors) else 0,
            "created_at": datetime.now().isoformat(timespec="seconds")}
    (out_dir / "meta.json").write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")


def load_embeddings(out_dir: Path) -> tuple[list[str], np.ndarray, dict]:
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    return meta["window_ids"], np.load(out_dir / "vectors.npy"), meta


def is_current(out_dir: Path, model_name: str, ids: list[str]) -> bool:
    """Cached vectors are reusable only for the same model and the same windows."""
    if not (out_dir / "meta.json").exists() or not (out_dir / "vectors.npy").exists():
        return False
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    return meta.get("model") == model_name and meta.get("window_ids") == ids
