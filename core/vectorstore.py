import logging

import chromadb

from core.models import Message
from core.embeddings import encode_passages, encode_query



def _build_doc_id(m: Message) -> str:
    """Builds a unique document id for ChromaDB, combining source, kind and id.

    Prevents collisions between a standalone message and the synthetic thread
    that contains it, since both could otherwise share the same numeric id
    (e.g. collection.upsert(ids=["telegram-msg-176"], documents=["no"])
    vs. collection.upsert(ids=["telegram-qa-176"], documents=["Anna: ...\\nMarco: no"])).
    """
    kind = "qa" if m.is_synthetic else "msg"
    # Telegram ids are only unique within one chat: the course keeps ids from
    # different exports (one per course) from overwriting each other on upsert
    course = m.course or ""
    return f"{m.source}-{course}-{kind}-{m.id}"


def get_collection(
    db_path: str,
    collection_name: str,
    reset: bool = False,
    logger: logging.Logger | None = None,
) -> chromadb.Collection:
    if logger is None:
        logger = logging.getLogger("cribrum.vectorstore")

    try:
        client = chromadb.PersistentClient(path=db_path)

        if reset:
            try:
                client.delete_collection(name=collection_name)
                logger.info(f"Collection '{collection_name}' deleted (--reset)")
            except Exception:
                logger.debug(f"No existing collection '{collection_name}' to delete")

        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        logger.error(f"Failed to open/create collection '{collection_name}' at '{db_path}'")
        raise

    logger.debug(f"Collection '{collection_name}' ready, {collection.count()} documents present")
    return collection


def add_messages(
    collection: chromadb.Collection,
    messages: list[Message],
    model_name: str,
    batch_size: int,
    passage_prefix: str,
    unanswered_ids: set[int] | None = None,
    logger: logging.Logger | None = None,
) -> None:
    if logger is None:
        logger = logging.getLogger("cribrum.vectorstore")

    if unanswered_ids is None:
        unanswered_ids = set()

    documents = [t.text for t in messages]
    ids = [_build_doc_id(m) for m in messages]   # fixed: no leading underscore

    embeddings = encode_passages(
        texts=documents,
        model_name=model_name,
        batch_size=batch_size,
        passage_prefix=passage_prefix,
        logger=logger,
    )

    metadatas = [
        {
            "author": m.author,
            "timestamp": m.timestamp.isoformat(), #necessary for chromadb 
            "is_synthetic": m.is_synthetic,
            "source_ids": ",".join(str(i) for i in m.source_ids) if m.source_ids else "", #necessary for chromadb 
            "course": m.course or "", # chromadb metadata values can't be None
            # synthetic messages always contain an answer, so they are never unanswered
            "is_unanswered_question": not m.is_synthetic and m.id in unanswered_ids,
        }
        for m in messages
    ]

    # ChromaDB caps how many items a single upsert can take (unrelated to the
    # embedding batch_size). _client is a private attribute, so fall back to
    # a conservative fixed size if a future chromadb version removes it.
    try:
        max_batch = collection._client.get_max_batch_size()
    except AttributeError:
        max_batch = 4000

    embeddings_list = embeddings.tolist()
    n_batches = (len(ids) + max_batch - 1) // max_batch   # ceiling division

    try:
        for b, start in enumerate(range(0, len(ids), max_batch), start=1):
            end = start + max_batch
            collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings_list[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )
            logger.debug(f"Upserted batch {b}/{n_batches}, {len(ids[start:end])} documents")
    except Exception:
        logger.error(f"Failed to upsert {len(messages)} messages into collection '{collection.name}'")
        raise

    logger.info(f"Indexed {len(messages)} messages into collection '{collection.name}'")



def query_similar(
    collection: chromadb.Collection,
    query_text: str,
    model_name: str,
    k: int,
    query_prefix: str,
    where: dict | None = None,
    logger: logging.Logger | None = None,
):
    if logger is None:
        logger = logging.getLogger("cribrum.vectorstore")

    query_embedding = encode_query(
        text=query_text,
        model_name=model_name,
        query_prefix=query_prefix,
        logger=logger,
    )

    try:
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        logger.error(f"Failed to query collection '{collection.name}' with text: {query_text!r}")
        raise

    logger.debug(f"Query returned {len(results['ids'][0])} results for: {query_text!r}")
    return results
