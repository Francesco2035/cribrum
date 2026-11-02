import logging

import numpy as np
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def _get_model(
    model_name: str,
    logger: logging.Logger | None = None,
) -> SentenceTransformer:
    global _model

    if logger is None:
        logger = logging.getLogger("cribrum.embeddings")

    if _model is None:
        logger.debug(f"Loading embedding model: {model_name}")
        try:
            # First try the local Hugging Face cache only, with no network requests
            _model = SentenceTransformer(model_name, local_files_only=True)
        except OSError:
            # Model not cached yet: download it (it will be cached for next runs)
            logger.info(f"Model '{model_name}' not found in local cache, downloading it")
            _model = SentenceTransformer(model_name)

    return _model


def encode_passages(
    texts: list[str],
    model_name: str,
    batch_size: int,
    passage_prefix: str = "passage: ",
    logger: logging.Logger | None = None,
) -> np.ndarray:
    if logger is None:
        logger = logging.getLogger("cribrum.embeddings")

    logger.debug(f"Prefixing {len(texts)} messages")
    prefixed_texts = [f"{passage_prefix}{t}" for t in texts]

    model = _get_model(model_name=model_name, logger=logger)

    try:
        embeddings = model.encode(
            prefixed_texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=logger.isEnabledFor(logging.DEBUG),
        )
    except Exception:
        logger.error(f"Failed to encode {len(texts)} passages with model '{model_name}'")
        raise

    logger.info(f"Encoded {len(texts)} passages, shape={embeddings.shape}")
    return embeddings



def encode_query(
    text: str,
    model_name: str,
    query_prefix: str = "query: ",
    logger: logging.Logger | None = None,
) -> np.ndarray:
    if logger is None:
        logger = logging.getLogger("cribrum.embeddings")

    prefixed_text = f"{query_prefix}{text}"

    model = _get_model(model_name=model_name, logger=logger)

    try:
        embedding = model.encode(
            prefixed_text,
            normalize_embeddings=True,
        )
    except Exception:
        logger.error(f"Failed to encode query with model '{model_name}'")
        raise

    logger.debug(f"Encoded query, shape={embedding.shape}")
    return embedding