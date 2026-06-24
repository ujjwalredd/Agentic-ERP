"""Local embeddings (sentence-transformers) + pgvector similarity search.

Anthropic has no embeddings endpoint, so the Categorizer's "learn from history"
memory uses a local MiniLM model. When the model can't load (CI / mock mode), we
fall back to a deterministic hashed embedding so the pipeline still runs.
"""
from __future__ import annotations

import hashlib
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import VectorDoc

_model = None
_model_failed = False


def _hashed_embedding(text: str) -> list[float]:
    """Deterministic fallback embedding. Not semantic, but stable and unit-norm."""
    dim = settings.embedding_dim
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float]:
    global _model, _model_failed
    if settings.use_mock_llm or _model_failed:
        return _hashed_embedding(text)
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(settings.embedding_model)
        except Exception:
            _model_failed = True
            return _hashed_embedding(text)
    return _model.encode(text, normalize_embeddings=True).tolist()


def add_doc(db: Session, text: str, meta: dict, kind: str = "txn_category") -> VectorDoc:
    doc = VectorDoc(kind=kind, text=text, embedding=embed(text), meta=meta)
    db.add(doc)
    db.flush()
    return doc


def similar(db: Session, text: str, k: int = 3, kind: str = "txn_category") -> list[VectorDoc]:
    """Top-k nearest past docs by cosine distance (pgvector `<=>`)."""
    query_vec = embed(text)
    stmt = (
        select(VectorDoc)
        .where(VectorDoc.kind == kind)
        .order_by(VectorDoc.embedding.cosine_distance(query_vec))
        .limit(k)
    )
    return list(db.scalars(stmt))
