"""
Semantic deduplication of topics using ChromaDB + paraphrase-multilingual-MiniLM-L12-v2.

Each account has its own persistent collection. A new topic is rejected as duplicate
if cosine similarity with any existing topic exceeds SIMILARITY_THRESHOLD.

Usage:
    from modules.topic_store import add_topic, is_duplicate, migrate_from_list, count

First run downloads the multilingual model (~270MB) to ~/.cache/huggingface/hub.
"""
import hashlib
import re
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

CHROMA_DIR = Path(__file__).parent.parent / "chroma"
SIMILARITY_THRESHOLD = 0.85
_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_client: chromadb.PersistentClient = None
_ef: SentenceTransformerEmbeddingFunction = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _get_ef() -> SentenceTransformerEmbeddingFunction:
    global _ef
    if _ef is None:
        _ef = SentenceTransformerEmbeddingFunction(model_name=_MODEL)
    return _ef


def _safe_name(account_name: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', account_name.lower())
    safe = re.sub(r'_+', '_', safe).strip('_')
    return safe or "default"


def _col(account_name: str):
    return _get_client().get_or_create_collection(
        name=_safe_name(account_name),
        embedding_function=_get_ef(),
        metadata={"hnsw:space": "cosine"},
    )


def _doc_id(topic: str) -> str:
    return hashlib.md5(topic.encode()).hexdigest()


def add_topic(account_name: str, topic: str) -> None:
    col = _col(account_name)
    doc_id = _doc_id(topic)
    if not col.get(ids=[doc_id])["ids"]:
        col.add(documents=[topic], ids=[doc_id])


def is_duplicate(account_name: str, topic: str,
                 threshold: float = SIMILARITY_THRESHOLD) -> tuple[bool, str, float]:
    """
    Returns (is_dup, closest_existing_topic, similarity_score).
    similarity_score in [0.0, 1.0]. Duplicate if >= threshold.
    """
    col = _col(account_name)
    if col.count() == 0:
        return False, "", 0.0
    try:
        results = col.query(query_texts=[topic], n_results=1)
    except chromadb.errors.InternalError as e:
        # Índice HNSW no persistido tras un crash previo ("Nothing found on disk").
        # No abortar la ejecución: tratar como no-duplicado y avisar.
        print(f"  [TopicStore] WARN query falló ({e}); se omite dedup para '{topic[:50]}'")
        return False, "", 0.0
    if not results["distances"][0]:
        return False, "", 0.0
    # ChromaDB cosine space: distance = 1 - cosine_similarity
    similarity = 1.0 - results["distances"][0][0]
    closest = results["documents"][0][0]
    return similarity >= threshold, closest, round(similarity, 3)


def migrate_from_list(account_name: str, topics: list) -> int:
    """Add topics not already in the store. Returns count added."""
    added = 0
    for topic in topics:
        col = _col(account_name)
        doc_id = _doc_id(topic)
        if not col.get(ids=[doc_id])["ids"]:
            col.add(documents=[topic], ids=[doc_id])
            added += 1
    return added


def count(account_name: str) -> int:
    return _col(account_name).count()
