"""Chroma 知識庫語意檢索（取代 KnowledgeVectorIndex TF-IDF 方案）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    _CHROMADB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CHROMADB_AVAILABLE = False

from shared.db.ai_memory import KnowledgeBase, ensure_db_exists

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_PERSIST_DIR = PROJECT_ROOT / "chroma_db"
CHROMA_COLLECTION_NAME = "kkgroup_knowledge"

# 與 ingest_knowledge.py 一致的嵌入模型
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class ChromaKnowledgeIndex:
    """使用 Chroma dense vector 進行語意檢索，支援 hybrid/keyword/semantic 模式。"""

    def __init__(self, persist_dir: Optional[Path] = None, collection_name: Optional[str] = None):
        self.persist_dir = persist_dir or CHROMA_PERSIST_DIR
        self.collection_name = collection_name or CHROMA_COLLECTION_NAME
        self._client = None
        self._collection = None

    def _get_client(self):
        if self._client is None:
            if not _CHROMADB_AVAILABLE:
                raise RuntimeError("chromadb 未安裝")
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL
            )
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    def semantic_search(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """純語意搜尋（dense vector cosine similarity）。"""
        if not query.strip():
            return []

        collection = self._get_collection()
        where = {"category": category} if category else None

        try:
            results = collection.query(
                query_texts=[query],
                n_results=limit,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.warning(f"Chroma semantic_search 失敗: {e}")
            return []

        return self._format_results(results, min_score)

    def keyword_search(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """關鍵字搜尋：委派給 KnowledgeBase（SQLite FTS）。"""
        items = KnowledgeBase.search_knowledge_items(query, limit=max(limit * 2, 10))
        if category:
            items = [item for item in items if item.get("category") == category]
        for item in items[:limit]:
            item["match_mode"] = "keyword"
            item["score"] = 0.5  # keyword 固定分數
        return items[:limit]

    def hybrid_search(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """混合搜尋：語意 + 關鍵字，去重並加權排序。"""
        semantic_items = self.semantic_search(query, limit=max(limit * 2, 10), category=category)
        keyword_items = self.keyword_search(query, limit=max(limit * 2, 10), category=category)

        merged: Dict[str, Dict[str, Any]] = {}

        # 語意結果優先，分數保留（cosine similarity 越高越相關，distance 越小越相關）
        for item in semantic_items:
            key = self._make_key(item)
            merged[key] = dict(item)
            merged[key]["match_mode"] = "semantic"
            # Chroma 回傳 distance（cosine distance），轉為 similarity
            merged[key]["score"] = round(1.0 - float(item.get("distance", 1.0)), 4)

        # 關鍵字結果補強
        for item in keyword_items:
            key = self._make_key(item)
            existing = merged.get(key)
            if existing:
                existing["match_mode"] = "hybrid"
                existing["score"] = round(existing["score"] + 0.25, 4)
            else:
                merged[key] = dict(item)
                merged[key]["match_mode"] = "keyword"
                merged[key]["score"] = 0.5

        # 排序：score 降序，updated_at 降序
        ranked = sorted(
            merged.values(),
            key=lambda x: (float(x.get("score", 0.0)), x.get("updated_at", "")),
            reverse=True
        )
        return ranked[:limit]

    def _format_results(self, results: Dict, min_score: float) -> List[Dict[str, Any]]:
        """統一格式化 Chroma 查詢結果。"""
        formatted = []
        if not results.get("documents") or not results["documents"][0]:
            return formatted

        docs = results["documents"][0]
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{} for _ in docs]
        distances = results["distances"][0] if results.get("distances") else [1.0 for _ in docs]

        for doc, metadata, distance in zip(docs, metadatas, distances):
            similarity = 1.0 - distance
            if similarity < min_score:
                continue
            item = dict(metadata)
            item["content"] = doc
            item["distance"] = round(distance, 4)
            item["score"] = round(similarity, 4)
            formatted.append(item)
        return formatted

    def _make_key(self, item: Dict[str, Any]) -> str:
        return f"{item.get('topic', '')}::{item.get('relative_path', '')}::{item.get('category', '')}"

    # 相容 KnowledgeVectorIndex 的介面
    def rebuild_from_database(self, category: Optional[str] = None) -> int:
        """重建索引：委派給 ingest_knowledge.py（這裡只確保 collection 存在）。"""
        ensure_db_exists()
        # 確保 collection 存在
        self._get_collection()
        count = self._collection.count()
        logger.info(f"✅ Chroma collection 就緒，現有 {count} 筆")
        return count


# 便利函數：保持向後相容
def get_chroma_index() -> ChromaKnowledgeIndex:
    return ChromaKnowledgeIndex()