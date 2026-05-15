#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""將 knowledge wiki 與 VM 掃描報告匯入 AI 知識庫。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge" / "_wiki"
DEFAULT_SCAN_REPORT = PROJECT_ROOT / "knowledge" / "_wiki" / "Inbox" / "vm-scan-latest.md"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.db.ai_memory import KnowledgeBase, PersonalityMemory, initialize_memory_system


@dataclass
class KnowledgeDocument:
    topic: str
    content: str
    category: str
    source_path: str
    metadata: Dict[str, object]
    related_topics: List[str]


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


def parse_front_matter(raw_text: str) -> tuple[Dict[str, object], str]:
    if not raw_text.startswith("---\n"):
        return {}, raw_text

    end_index = raw_text.find("\n---\n", 4)
    if end_index == -1:
        return {}, raw_text

    meta_text = raw_text[4:end_index]
    body = raw_text[end_index + 5 :]
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


def derive_category(path: Path) -> str:
    if path.name.startswith("vm-scan"):
        return "vm_scan"

    relative_parts = path.relative_to(DEFAULT_KNOWLEDGE_ROOT).parts
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


def summarize_body(body: str, limit: int = 2400) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def build_document(path: Path) -> KnowledgeDocument:
    raw_text = path.read_text(encoding="utf-8")
    front_matter, body = parse_front_matter(raw_text)
    topic = derive_topic(path, body)
    related_topics = extract_related_topics(body)
    relative_path = path.relative_to(PROJECT_ROOT).as_posix()
    metadata = {
        "sha1": hashlib.sha1(raw_text.encode("utf-8")).hexdigest(),
        "relative_path": relative_path,
        "line_count": len(body.splitlines()),
        "front_matter": front_matter,
    }
    return KnowledgeDocument(
        topic=topic,
        content=summarize_body(body),
        category=derive_category(path),
        source_path=relative_path,
        metadata=metadata,
        related_topics=related_topics,
    )


def bootstrap_personality() -> None:
    PersonalityMemory.set_personality(
        "身份",
        "你是 KK 詐騙園區中控室 NPC『干部』，能結合 repo、知識庫與 VM 掃描結果回報現況。",
    )
    PersonalityMemory.set_personality(
        "任務",
        "每天更新自己的知識庫，回答 VM 狀態、維運入口、功能缺口與可拓展方向。",
    )
    PersonalityMemory.set_personality(
        "回覆風格",
        "先講已知事實，再講推論；若要建議新功能，指出對應檔案或模組。",
    )


def ingest_documents(paths: Sequence[Path], dry_run: bool = False) -> Dict[str, int]:
    stats = {"processed": 0, "ingested": 0}
    for path in paths:
        document = build_document(path)
        stats["processed"] += 1
        if dry_run:
            print(f"[DRY-RUN] {document.topic} <- {document.source_path}")
            continue
        KnowledgeBase.delete_by_source_path(document.source_path)
        KnowledgeBase.add_knowledge(
            topic=document.topic,
            content=document.content,
            category=document.category,
            source_path=document.source_path,
            source_type="markdown",
            metadata=document.metadata,
            related_topics=document.related_topics,
        )
        stats["ingested"] += 1
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="匯入 knowledge wiki 到 AI 知識庫")
    parser.add_argument(
        "paths",
        nargs="*",
        help="要匯入的檔案或資料夾，預設為 knowledge/_wiki 與最新 VM 掃描報告",
    )
    parser.add_argument("--dry-run", action="store_true", help="只顯示要匯入的文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    initialize_memory_system()
    bootstrap_personality()

    roots = [Path(path).resolve() for path in args.paths] if args.paths else [DEFAULT_KNOWLEDGE_ROOT]
    if DEFAULT_SCAN_REPORT.exists() and DEFAULT_SCAN_REPORT not in roots:
        roots.append(DEFAULT_SCAN_REPORT)

    files = discover_markdown_files(roots)
    if not files:
        print("⚠️ 沒有找到可匯入的 Markdown 文件")
        return 1

    stats = ingest_documents(files, dry_run=args.dry_run)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())