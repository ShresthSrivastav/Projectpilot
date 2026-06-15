"""RAG Service — document upload, chunking, embedding, and retrieval."""
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MAX_CHUNKS_PER_DOC = 200

_rag_client: Optional[chromadb.EphemeralClient] = None


def _get_client() -> chromadb.EphemeralClient:
    global _rag_client
    if _rag_client is None:
        _rag_client = chromadb.EphemeralClient(
            settings=Settings(anonymized_telemetry=False),
        )
    return _rag_client


def _col(name: str):
    return _get_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )


def _embed(n: int = 1) -> List[List[float]]:
    return [[0.0]] * n


def _chunk_text(text: str, source: str) -> List[Dict[str, Any]]:
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    buffer = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(buffer) + len(para) < CHUNK_SIZE:
            buffer = (buffer + "\n\n" + para).strip()
        else:
            if buffer:
                chunks.append({"text": buffer, "source": source})
            buffer = para
    if buffer:
        chunks.append({"text": buffer, "source": source})

    if len(chunks) == 0 and text.strip():
        for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
            chunk_text = text[i:i + CHUNK_SIZE]
            if chunk_text.strip():
                chunks.append({"text": chunk_text, "source": source})
                if len(chunks) >= MAX_CHUNKS_PER_DOC:
                    break

    return chunks


def _extract_text_from_file(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".txt":
        return file_path.read_text(encoding="utf-8", errors="replace")
    elif ext == ".md":
        return file_path.read_text(encoding="utf-8", errors="replace")
    elif ext == ".py":
        return file_path.read_text(encoding="utf-8", errors="replace")
    elif ext == ".json":
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        return json.dumps(json.loads(raw), indent=2)
    elif ext == ".csv":
        return file_path.read_text(encoding="utf-8", errors="replace")
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            logger.warning("pypdf not installed, cannot parse PDF: %s", file_path)
            return f"[PDF file: {file_path.name} — install pypdf to extract text]"
        except Exception as exc:
            logger.warning("Failed to parse PDF %s: %s", file_path, exc)
            return f"[PDF file: {file_path.name} — parse error: {exc}]"
    else:
        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return f"[Unsupported file: {file_path.name}]"


def upload_document(
    file_path: Path,
    tags: Optional[List[str]] = None,
    doc_id: Optional[str] = None,
) -> Dict[str, Any]:
    doc_id = doc_id or str(uuid.uuid4())
    text = _extract_text_from_file(file_path)
    chunks = _chunk_text(text, file_path.name)

    if not chunks:
        return {"doc_id": doc_id, "status": "empty", "chunks": 0}

    metadata = {
        "source": file_path.name,
        "doc_id": doc_id,
        "tags": json.dumps(tags or []),
        "total_chunks": len(chunks),
    }

    _col("rag_docs").upsert(
        ids=[doc_id],
        embeddings=_embed(1),
        documents=[json.dumps({"source": file_path.name, "tags": tags or [], "text_length": len(text)})],
        metadatas=[metadata],
    )

    chunk_ids = []
    for i, chunk in enumerate(chunks):
        cid = f"{doc_id}_chunk_{i:04d}"
        chunk_ids.append(cid)
        _col("rag_chunks").upsert(
            ids=[cid],
            embeddings=_embed(1),
            documents=[chunk["text"]],
            metadatas=[{
                "doc_id": doc_id,
                "source": chunk["source"],
                "chunk_index": i,
                "tags": json.dumps(tags or []),
            }],
        )

    logger.info("RAG: uploaded %s (%d chunks)", file_path.name, len(chunks))
    return {"doc_id": doc_id, "status": "ok", "chunks": len(chunks), "source": file_path.name}


def list_documents() -> List[Dict[str, Any]]:
    try:
        r = _col("rag_docs").get(include=["documents", "metadatas"])
        docs = []
        for doc, meta in zip(r["documents"], r["metadatas"]):
            parsed = json.loads(doc) if doc else {}
            docs.append({
                "doc_id": meta.get("doc_id", ""),
                "source": meta.get("source", ""),
                "tags": json.loads(meta.get("tags", "[]")),
                "total_chunks": meta.get("total_chunks", 0),
                "text_length": parsed.get("text_length", 0),
            })
        return docs
    except Exception as exc:
        logger.warning("RAG list failed: %s", exc)
        return []


def query(query_text: str, top_k: int = 5, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    try:
        where = {}
        if tags:
            tag_set = set(tags)
            r_chunks = _col("rag_chunks").get(include=["documents", "metadatas"])
            scored = []
            for doc_text, meta in zip(r_chunks["documents"], r_chunks["metadatas"]):
                chunk_tags = json.loads(meta.get("tags", "[]"))
                if tags and not tag_set.intersection(chunk_tags):
                    continue
                if doc_text:
                    score = len(set(query_text.lower().split()) & set(doc_text.lower().split()))
                    scored.append((score, doc_text, meta))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = []
            for score, doc_text, meta in scored[:top_k]:
                results.append({
                    "text": doc_text[:1000],
                    "source": meta.get("source", ""),
                    "score": score,
                    "doc_id": meta.get("doc_id", ""),
                })
            return results
        else:
            r = _col("rag_chunks").get(include=["documents", "metadatas"])
            scored = []
            for doc_text, meta in zip(r["documents"], r["metadatas"]):
                if doc_text:
                    score = len(set(query_text.lower().split()) & set(doc_text.lower().split()))
                    scored.append((score, doc_text, meta))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = []
            for score, doc_text, meta in scored[:top_k]:
                results.append({
                    "text": doc_text[:1000],
                    "source": meta.get("source", ""),
                    "score": score,
                    "doc_id": meta.get("doc_id", ""),
                })
            return results
    except Exception as exc:
        logger.warning("RAG query failed: %s", exc)
        return []


def delete_document(doc_id: str) -> bool:
    try:
        _col("rag_docs").delete(ids=[doc_id])
        r = _col("rag_chunks").get()
        chunk_ids = [cid for cid in r["ids"] if cid.startswith(f"{doc_id}_chunk_")]
        if chunk_ids:
            _col("rag_chunks").delete(ids=chunk_ids)
        return True
    except Exception as exc:
        logger.warning("RAG delete failed: %s", exc)
        return False
