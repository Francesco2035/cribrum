import logging
from dataclasses import dataclass

import chromadb

from core.vectorstore import query_similar


@dataclass
class SearchResult:
    doc_id: str
    text: str
    author: str
    is_synthetic: bool
    similarity: float
    timestamp: str                 # ISO format, as stored in ChromaDB metadata
    course: str                    # "" if the message was ingested without --course
    is_unanswered_question: bool
    source_ids: list[int]          # ids of the original messages (synthetic only)


def search(
    collection: chromadb.Collection,
    query_text: str,
    model_name: str,
    k: int,
    query_prefix: str,
    min_similarity: float,
    course: str | None = None,
    logger: logging.Logger | None = None,
) -> tuple[str, list[SearchResult]]:
    """Runs a semantic search and returns (outcome, results above threshold).

    outcome is one of:
    - "question_found_no_answer": the best match is above threshold and is a
      question nobody answered in the group
    - "found": at least one result is above min_similarity
    - "not_found": nothing is above min_similarity
    """
    if logger is None:
        logger = logging.getLogger("cribrum.search")

    where = {"course": course} if course else None

    raw = query_similar(
        collection=collection,
        query_text=query_text,
        model_name=model_name,
        k=k,
        query_prefix=query_prefix,
        where=where,
        logger=logger,
    )

    all_results: list[SearchResult] = []
    for doc_id, doc, dist, meta in zip(
        raw["ids"][0], raw["documents"][0], raw["distances"][0], raw["metadatas"][0]
    ):
        source_ids = meta.get("source_ids", "")
        all_results.append(SearchResult(
            doc_id=doc_id,
            text=doc,
            author=meta.get("author", ""),
            is_synthetic=meta.get("is_synthetic", False),
            # ChromaDB cosine distance is exactly 1 - cosine similarity
            similarity=1 - dist,
            timestamp=meta.get("timestamp", ""),
            course=meta.get("course", ""),
            # .get() keeps documents indexed before this field existed readable
            is_unanswered_question=meta.get("is_unanswered_question", False),
            source_ids=[int(i) for i in source_ids.split(",")] if source_ids else [],
        ))

    # ChromaDB already returns results sorted by distance (best first)
    results = [r for r in all_results if r.similarity >= min_similarity]

    logger.debug(
        f"{len(all_results)} raw results, {len(results)} above min_similarity={min_similarity}"
    )

    if results and results[0].is_unanswered_question:
        outcome = "question_found_no_answer"
    elif results:
        outcome = "found"
    else:
        outcome = "not_found"

    return outcome, results
