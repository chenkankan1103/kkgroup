"""本地知識語意索引。"""

from __future__ import annotations

import logging
import math
import pickle
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    _SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover
    TfidfVectorizer = None  # type: ignore
    cosine_similarity = None  # type: ignore
    _SKLEARN_AVAILABLE = False

from shared.db.ai_memory import KnowledgeBase, ensure_db_exists

logger = logging.getLogger(__name__)

INDEX_FILE = Path(__file__).resolve().parent / "data" / "knowledge_vector_index.pkl"


class KnowledgeVectorIndex:
    """使用 TF-IDF 建立本地語意檢索索引。"""

    def __init__(self, index_path: Optional[Path] = None):
        self.index_path = index_path or INDEX_FILE

    def rebuild_from_database(self, category: Optional[str] = None) -> int:
        items = KnowledgeBase.get_all_items(category=category)
        return self.rebuild(items)

    def rebuild(self, items: List[Dict[str, Any]]) -> int:
        ensure_db_exists()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        records: List[Dict[str, Any]] = []
        corpus: List[str] = []
        for item in items:
            document = self._compose_document(item)
            if not document.strip():
                continue
            corpus.append(document)
            records.append(item)

        if not corpus:
            self._save_payload(
                {"engine": "empty", "vectorizer": None, "matrix": None, "records": []}
            )
            return 0

        if _SKLEARN_AVAILABLE:
            vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 4),
                min_df=1,
                max_features=12000,
                sublinear_tf=True,
            )
            matrix = vectorizer.fit_transform(corpus)
            self._save_payload(
                {
                    "engine": "sklearn",
                    "vectorizer": vectorizer,
                    "matrix": matrix,
                    "records": records,
                }
            )
        else:
            vectors = [self._build_sparse_vector(text) for text in corpus]
            norms = [self._vector_norm(vector) for vector in vectors]
            self._save_payload(
                {
                    "engine": "fallback",
                    "vectors": vectors,
                    "norms": norms,
                    "records": records,
                }
            )
        logger.info("✅ 已重建知識語意索引，共 %s 筆", len(records))
        return len(records)

    def semantic_search(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None,
        min_score: float = 0.05,
    ) -> List[Dict[str, Any]]:
        if not query.strip():
            return []

        payload = self._load_payload()
        if not payload:
            self.rebuild_from_database(category=category)
            payload = self._load_payload()
            if not payload:
                return []

        records = payload["records"]
        scores = self._score_query(payload, query)

        ranked: List[Dict[str, Any]] = []
        ranked_indexes = sorted(
            range(len(scores)), key=lambda index: float(scores[index]), reverse=True
        )
        for idx in ranked_indexes:
            score = float(scores[idx])
            if score < min_score:
                break
            item = dict(records[idx])
            if category and item.get("category") != category:
                continue
            item["score"] = round(score, 4)
            ranked.append(item)
            if len(ranked) >= limit:
                break
        return ranked

    def hybrid_search(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        keyword_items = KnowledgeBase.search_knowledge_items(
            query, limit=max(limit * 2, 10)
        )
        semantic_items = self.semantic_search(
            query, limit=max(limit * 2, 10), category=category
        )

        merged: Dict[str, Dict[str, Any]] = {}

        for item in semantic_items:
            key = self._make_key(item)
            merged[key] = dict(item)
            merged[key]["match_mode"] = "semantic"
            merged[key]["score"] = float(item.get("score", 0.0))

        for item in keyword_items:
            if category and item.get("category") != category:
                continue
            key = self._make_key(item)
            existing = merged.get(key)
            if existing:
                existing["match_mode"] = "hybrid"
                existing["score"] = round(float(existing.get("score", 0.0)) + 0.25, 4)
            else:
                merged[key] = dict(item)
                merged[key]["match_mode"] = "keyword"
                merged[key]["score"] = 0.25

        ranked = sorted(
            merged.values(),
            key=lambda item: (
                float(item.get("score", 0.0)),
                item.get("updated_at", ""),
            ),
            reverse=True,
        )
        return ranked[:limit]

    def _compose_document(self, item: Dict[str, Any]) -> str:
        related_topics = " ".join(item.get("related_topics", []))
        metadata = item.get("metadata", {}) or {}
        metadata_text = " ".join(f"{key}:{value}" for key, value in metadata.items())
        return "\n".join(
            [
                item.get("topic", ""),
                item.get("category", ""),
                related_topics,
                metadata_text,
                item.get("content", ""),
            ]
        )

    def _load_payload(self) -> Optional[Dict[str, Any]]:
        if not self.index_path.exists():
            return None
        try:
            with self.index_path.open("rb") as handle:
                return pickle.load(handle)
        except Exception as exc:
            logger.warning("⚠️ 載入知識語意索引失敗: %s", exc)
            return None

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        with self.index_path.open("wb") as handle:
            pickle.dump(payload, handle)

    def _make_key(self, item: Dict[str, Any]) -> str:
        return f"{item.get('topic', '')}::{item.get('source_path', '')}::{item.get('category', '')}"

    def _score_query(self, payload: Dict[str, Any], query: str):
        engine = payload.get("engine")
        if (
            engine == "sklearn"
            and payload.get("vectorizer") is not None
            and payload.get("matrix") is not None
        ):
            query_vector = payload["vectorizer"].transform([query])
            return cosine_similarity(query_vector, payload["matrix"]).ravel()

        query_vector = self._build_sparse_vector(query)
        query_norm = self._vector_norm(query_vector)
        scores: List[float] = []
        for vector, norm in zip(payload.get("vectors", []), payload.get("norms", [])):
            scores.append(self._cosine_sparse(query_vector, query_norm, vector, norm))
        return scores

    def _build_sparse_vector(self, text: str) -> Dict[str, float]:
        normalized = " ".join((text or "").lower().split())
        counts: Counter[str] = Counter()
        for size in range(2, 5):
            if len(normalized) < size:
                continue
            for index in range(len(normalized) - size + 1):
                gram = normalized[index : index + size]
                counts[gram] += 1
        return dict(counts)

    def _vector_norm(self, vector: Dict[str, float]) -> float:
        return math.sqrt(sum(value * value for value in vector.values()))

    def _cosine_sparse(
        self,
        query_vector: Dict[str, float],
        query_norm: float,
        doc_vector: Dict[str, float],
        doc_norm: float,
    ) -> float:
        if query_norm == 0 or doc_norm == 0:
            return 0.0
        overlap = set(query_vector.keys()) & set(doc_vector.keys())
        dot = sum(query_vector[key] * doc_vector[key] for key in overlap)
        return dot / (query_norm * doc_norm)
