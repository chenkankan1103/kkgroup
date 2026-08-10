#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知識檢索 API。"""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from shared.db.ai_memory import KnowledgeBase
from shared.db.chroma_knowledge_index import ChromaKnowledgeIndex

knowledge_api_bp = Blueprint("knowledge_api", __name__, url_prefix="/api/knowledge")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = PROJECT_ROOT / "status" / "knowledge_refresh_status.json"


@knowledge_api_bp.route("/search", methods=["GET"])
def search_knowledge():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"status": "error", "error": "缺少 q 參數"}), 400

    mode = (request.args.get("mode") or "hybrid").strip().lower()
    category = (request.args.get("category") or "").strip() or None
    limit = min(max(int(request.args.get("limit", 5)), 1), 20)

    vector_index = ChromaKnowledgeIndex()
    if mode == "semantic":
        items = vector_index.semantic_search(query, limit=limit, category=category)
    elif mode == "keyword":
        items = vector_index.keyword_search(query, limit=limit, category=category)
    else:
        items = vector_index.hybrid_search(query, limit=limit, category=category)

    return jsonify(
        {
            "status": "success",
            "data": {
                "query": query,
                "mode": mode,
                "category": category,
                "count": len(items),
                "items": items,
            },
        }
    ), 200


@knowledge_api_bp.route("/recent", methods=["GET"])
def recent_knowledge():
    category = (request.args.get("category") or "").strip() or None
    limit = min(max(int(request.args.get("limit", 10)), 1), 50)
    items = KnowledgeBase.get_recent_items(limit=limit, category=category)
    return jsonify(
        {"status": "success", "data": {"count": len(items), "items": items}}
    ), 200


@knowledge_api_bp.route("/status", methods=["GET"])
def knowledge_status():
    if not STATUS_FILE.exists():
        return jsonify(
            {
                "status": "success",
                "data": {"status": "unknown", "message": "尚未產生刷新狀態"},
            }
        ), 200

    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return jsonify({"status": "error", "error": f"讀取狀態失敗: {exc}"}), 500

    return jsonify({"status": "success", "data": data}), 200
