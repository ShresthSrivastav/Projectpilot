import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-minilm:l6-v2")


def ollama_embedding_function(texts: List[str]) -> List[List[float]]:
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": texts},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings", [])
        if embeddings:
            return embeddings
    except Exception as exc:
        logger.warning("Ollama embedding failed, using fallback: %s", exc)
    return _fallback_embed(texts)


def _fallback_embed(texts: List[str]) -> List[List[float]]:
    dim = 384
    return [[0.0] * dim for _ in texts]


def get_embedding_dimension() -> int:
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": ["test"]},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        embeds = data.get("embeddings", [])
        if embeds:
            return len(embeds[0])
    except Exception:
        pass
    return 384


class ChromaEmbeddingFunction:
    def __call__(self, input):
        if isinstance(input, str):
            input = [input]
        return ollama_embedding_function(input)
