import logging
from collections.abc import Callable

WORDS_TO_TOKENS = 1.3   # rough subword/word ratio for Italian/English text


def get_token_counter(
    model_name: str,
    logger: logging.Logger | None = None,
) -> tuple[Callable[[str], int], str]:
    """Returns (count_tokens, description). Uses only the tokenizer of the
    embedding model (no weights loaded); falls back to a word-based estimate
    when the tokenizer isn't available offline."""
    if logger is None:
        logger = logging.getLogger("cribrum.tokens")

    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    except Exception as e:
        logger.warning(f"Tokenizer for '{model_name}' unavailable ({e}); using word-based estimate")
        return approx_token_count, f"approx (words x {WORDS_TO_TOKENS})"

    # We only count tokens, never feed the model here: silence the >512 length warning.
    tokenizer.model_max_length = 10**9

    def count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return count, f"tokenizer:{model_name}"


def approx_token_count(text: str) -> int:
    return round(len(text.split()) * WORDS_TO_TOKENS)
