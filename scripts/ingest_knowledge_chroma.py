#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
將 knowledge wiki、VM 掃描報告、程式碼庫匯入 Chroma 向量資料庫。
支援：
- Markdown 文件（wiki、掃描報告）
- Python 程式碼（函式/類別級切分）
- 一般文字檔
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Optional

# 專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge" / "_wiki"
DEFAULT_SCAN_REPORT = PROJECT_ROOT / "knowledge" / "_wiki" / "Inbox" / "vm-scan-latest.md"
DEFAULT_CODE_ROOTS = [
    PROJECT_ROOT / "bots",
    PROJECT_ROOT / "cogs",
    PROJECT_ROOT / "shared",
    PROJECT_ROOT / "web",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "scheduled_tasks",
    PROJECT_ROOT / "utils",
]

# Chroma 持久化目錄
CHROMA_PERSIST_DIR = PROJECT_ROOT / "chroma_db"
CHROMA_COLLECTION_NAME = "kkgroup_knowledge"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
except ImportError:
    print("❌ 請先安裝 chromadb: pip install chromadb")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("❌ 請先安裝 sentence-transformers: pip install sentence-transformers")
    sys.exit(1)


@dataclass
class KnowledgeChunk:
    """知識片段"""
    id: str
    text: str
    metadata: Dict[str, object]


# ==================== 文件發現 ====================

def discover_markdown_files(roots: Sequence[Path]) -> List[Path]:
    files: List[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".md":
            files.append(root)
            continue
        if not root.exists():
            continue
        files.extend(sorted(path for path in root.rglob("*.md") if path.is_file()))
    return files


def discover_python_files(roots: Sequence[Path]) -> List[Path]:
    files: List[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(sorted(path for path in root.rglob("*.py") if path.is_file()))
    return files


# ==================== Markdown 解析 ====================

def parse_front_matter(raw_text: str) -> tuple[Dict[str, object], str]:
    if not raw_text.startswith("---\n"):
        return {}, raw_text
    end_index = raw_text.find("\n---\n", 4)
    if end_index == -1:
        return {}, raw_text
    meta_text = raw_text[4:end_index]
    body = raw_text[end_index + 5:]
    metadata: Dict[str, object] = {}
    for line in meta_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, body


def derive_topic(path: Path, body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").strip()


def derive_category(path: Path, knowledge_root: Path) -> str:
    if path.name.startswith("vm-scan"):
        return "vm_scan"
    try:
        relative_parts = path.relative_to(knowledge_root).parts
    except ValueError:
        return "knowledge"
    if not relative_parts:
        return "knowledge"
    first_part = relative_parts[0].lower()
    mapping = {
        "concepts": "wiki_concept",
        "entities": "wiki_entity",
        "sources": "wiki_source",
        "inbox": "wiki_inbox",
    }
    return mapping.get(first_part, "knowledge")


def extract_related_topics(body: str) -> List[str]:
    related: List[str] = []
    markdown_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", body)
    for label, target in markdown_links:
        if target.endswith(".md"):
            related.append(label.strip())
    wiki_links = re.findall(r"\[\[([^\]]+)\]\]", body)
    related.extend(item.strip() for item in wiki_links)
    seen = set()
    deduped = []
    for item in related:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped[:20]


# ==================== 程式碼切分 ====================

PYTHON_SPLIT_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<type>def|class|async def)\s+(?P<name>\w+)',
    re.MULTILINE
)

def split_python_code(file_path: Path, content: str, max_chunk_chars: int = 2000) -> List[KnowledgeChunk]:
    """將 Python 檔案按函式/類別切分，過大則再細分"""
    chunks: List[KnowledgeChunk] = []
    matches = list(PYTHON_SPLIT_PATTERN.finditer(content))
    
    if not matches:
        # 沒有函式/類別，整個檔案當一個 chunk
        return [KnowledgeChunk(
            id=f"{file_path.as_posix()}::full",
            text=content[:max_chunk_chars],
            metadata={
                "source_path": file_path.as_posix(),
                "source_type": "python",
                "chunk_type": "full_file",
                "symbol": file_path.stem,
            }
        )]
    
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        chunk_text = content[start:end].strip()
        
        if not chunk_text:
            continue
            
        # 如果太大，按行切分
        if len(chunk_text) > max_chunk_chars:
            lines = chunk_text.splitlines()
            sub_chunk = []
            sub_len = 0
            for line in lines:
                if sub_len + len(line) > max_chunk_chars and sub_chunk:
                    chunks.append(KnowledgeChunk(
                        id=f"{file_path.as_posix()}::{match.group('name')}::{len(chunks)}",
                        text="\n".join(sub_chunk),
                        metadata={
                            "source_path": file_path.as_posix(),
                            "source_type": "python",
                            "chunk_type": "symbol_part",
                            "symbol": match.group('name'),
                            "symbol_type": match.group('type'),
                        }
                    ))
                    sub_chunk = [line]
                    sub_len = len(line)
                else:
                    sub_chunk.append(line)
                    sub_len += len(line)
            if sub_chunk:
                chunks.append(KnowledgeChunk(
                    id=f"{file_path.as_posix()}::{match.group('name')}::{len(chunks)}",
                    text="\n".join(sub_chunk),
                    metadata={
                        "source_path": file_path.as_posix(),
                        "source_type": "python",
                        "chunk_type": "symbol_part",
                        "symbol": match.group('name'),
                        "symbol_type": match.group('type'),
                    }
                ))
        else:
            chunks.append(KnowledgeChunk(
                id=f"{file_path.as_posix()}::{match.group('name')}",
                text=chunk_text,
                metadata={
                    "source_path": file_path.as_posix(),
                    "source_type": "python",
                    "chunk_type": "symbol",
                    "symbol": match.group('name'),
                    "symbol_type": match.group('type'),
                }
            ))
    
    return chunks


def split_markdown(content: str, max_chunk_chars: int = 2000) -> List[str]:
    """按標題層級切分 Markdown"""
    # 先按二級標題切分
    sections = re.split(r'\n## ', content)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_chunk_chars:
            chunks.append(section)
        else:
            # 再按三級標題切
            sub_sections = re.split(r'\n### ', section)
            for sub in sub_sections:
                sub = sub.strip()
                if not sub:
                    continue
                if len(sub) <= max_chunk_chars:
                    chunks.append(sub)
                else:
                    # 硬切
                    for i in range(0, len(sub), max_chunk_chars):
                        chunks.append(sub[i:i + max_chunk_chars])
    return chunks


# ==================== 文件建構 ====================

def build_markdown_chunks(path: Path, knowledge_root: Path) -> List[KnowledgeChunk]:
    raw_text = path.read_text(encoding="utf-8")
    front_matter, body = parse_front_matter(raw_text)
    topic = derive_topic(path, body)
    category = derive_category(path, knowledge_root)
    related_topics = extract_related_topics(body)
    relative_path = path.relative_to(PROJECT_ROOT).as_posix()
    
    base_metadata = {
        "sha1": hashlib.sha1(raw_text.encode("utf-8")).hexdigest(),
        "relative_path": relative_path,
        "line_count": len(body.splitlines()),
        "front_matter": front_matter,
        "category": category,
        "related_topics": related_topics,
        "source_type": "markdown",
    }
    
    chunks = split_markdown(body)
    result = []
    for i, chunk_text in enumerate(chunks):
        result.append(KnowledgeChunk(
            id=f"{relative_path}::chunk::{i}",
            text=f"# {topic}\n\n{chunk_text}",
            metadata={**base_metadata, "chunk_index": i, "topic": topic}
        ))
    return result


def build_python_chunks(path: Path) -> List[KnowledgeChunk]:
    content = path.read_text(encoding="utf-8")
    relative_path = path.relative_to(PROJECT_ROOT).as_posix()
    return split_python_code(path, content)


# ==================== Chroma 客戶端 ====================

def get_chroma_client() -> chromadb.PersistentClient:
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(CHROMA_PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False)
    )


def get_embedding_function():
    """使用 sentence-transformers 的嵌入函數"""
    # 使用多語言模型，支援中文
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )


def get_or_create_collection(client: chromadb.PersistentClient):
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"}
    )


# ==================== 匯入邏輯 ====================

def ingest_markdown_files(paths: Sequence[Path], dry_run: bool = False) -> Dict[str, int]:
    stats = {"processed": 0, "chunks": 0}
    client = get_chroma_client()
    collection = get_or_create_collection(client)
    
    for path in paths:
        chunks = build_markdown_chunks(path, DEFAULT_KNOWLEDGE_ROOT)
        stats["processed"] += 1
        
        if dry_run:
            for chunk in chunks:
                print(f"[DRY-RUN] {chunk.id} <- {chunk.metadata['relative_path']}")
            continue
        
        # 刪除舊資料（按 source_path）
        try:
            collection.delete(where={"relative_path": path.relative_to(PROJECT_ROOT).as_posix()})
        except Exception:
            pass
        
        # 批次新增
        ids = [c.id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]
        
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        stats["chunks"] += len(chunks)
        print(f"✅ {path.relative_to(PROJECT_ROOT)} -> {len(chunks)} chunks")
    
    return stats


def ingest_python_files(paths: Sequence[Path], dry_run: bool = False) -> Dict[str, int]:
    stats = {"processed": 0, "chunks": 0}
    client = get_chroma_client()
    collection = get_or_create_collection(client)
    
    for path in paths:
        chunks = build_python_chunks(path)
        stats["processed"] += 1
        
        if dry_run:
            for chunk in chunks:
                print(f"[DRY-RUN] {chunk.id} <- {chunk.metadata['source_path']}")
            continue
        
        # 刪除舊資料
        try:
            collection.delete(where={"source_path": path.relative_to(PROJECT_ROOT).as_posix()})
        except Exception:
            pass
        
        ids = [c.id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]
        
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        stats["chunks"] += len(chunks)
        print(f"✅ {path.relative_to(PROJECT_ROOT)} -> {len(chunks)} chunks")
    
    return stats


# ==================== 查詢介面（供 AI 使用） ====================

def query_knowledge(query: str, n_results: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict]:
    """查詢知識庫，回傳格式化結果"""
    client = get_chroma_client()
    collection = get_or_create_collection(client)
    
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=filter_dict,
        include=["documents", "metadatas", "distances"]
    )
    
    formatted = []
    if results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            formatted.append({
                "text": doc,
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else None
            })
    return formatted


# ==================== CLI ====================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="匯入 knowledge wiki、程式碼到 Chroma 向量資料庫")
    parser.add_argument(
        "paths",
        nargs="*",
        help="要匯入的檔案或資料夾，預設為 knowledge/_wiki、VM 掃描報告、主要程式碼目錄",
    )
    parser.add_argument("--dry-run", action="store_true", help="只顯示要匯入的文件")
    parser.add_argument("--no-code", action="store_true", help="不匯入程式碼")
    parser.add_argument("--query", type=str, help="測試查詢（不匯入，只查詢）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    
    # 測試查詢模式
    if args.query:
        results = query_knowledge(args.query, n_results=5)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    
    # 決定要匯入的路徑
    if args.paths:
        roots = [Path(path).resolve() for path in args.paths]
    else:
        roots = [DEFAULT_KNOWLEDGE_ROOT]
        if DEFAULT_SCAN_REPORT.exists():
            roots.append(DEFAULT_SCAN_REPORT)
    
    # 匯入 Markdown
    md_files = discover_markdown_files(roots)
    if md_files:
        print(f"📄 發現 {len(md_files)} 個 Markdown 檔案")
        stats = ingest_markdown_files(md_files, dry_run=args.dry_run)
        print(f"   處理: {stats['processed']} 檔, 切分: {stats['chunks']} chunks")
    
    # 匯入 Python 程式碼
    if not args.no_code:
        code_roots = DEFAULT_CODE_ROOTS
        py_files = discover_python_files(code_roots)
        if py_files:
            print(f"🐍 發現 {len(py_files)} 個 Python 檔案")
            stats = ingest_python_files(py_files, dry_run=args.dry_run)
            print(f"   處理: {stats['processed']} 檔, 切分: {stats['chunks']} chunks")
    
    if args.dry_run:
        print("\n🔍 Dry-run 完成，未實際寫入")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())