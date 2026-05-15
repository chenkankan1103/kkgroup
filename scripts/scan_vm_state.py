#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收集目前主機與 repo 狀態，輸出成可匯入 knowledge wiki 的 Markdown。"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "knowledge" / "_wiki" / "Inbox" / "vm-scan-latest.md"
SERVICE_NAMES = ["bot.service", "shopbot.service", "uibot.service", "kkgroup-api.service", "cloudflared.service"]


def run_command(command: List[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=PROJECT_ROOT)
        return (result.stdout or result.stderr).strip()
    except Exception as exc:
        return f"command failed: {exc}"


def get_systemctl_statuses() -> Dict[str, str]:
    if shutil.which("systemctl") is None:
        return {name: "systemctl unavailable on this host" for name in SERVICE_NAMES}
    statuses = {}
    for service_name in SERVICE_NAMES:
        statuses[service_name] = run_command(["systemctl", "is-active", service_name]) or "unknown"
    return statuses


def get_disk_summary() -> str:
    usage = shutil.disk_usage(PROJECT_ROOT)
    used_gb = usage.used / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    return f"used={used_gb:.2f}GB / total={total_gb:.2f}GB"


def get_recent_commits(limit: int = 5) -> List[str]:
    output = run_command(["git", "log", f"--max-count={limit}", "--pretty=format:%h %s"])
    return [line for line in output.splitlines() if line.strip()]


def get_git_status() -> str:
    output = run_command(["git", "status", "--short"])
    return output or "clean"


def get_repo_hotspots() -> Dict[str, int]:
    hotspots = {}
    for relative in ["bots", "cogs/common", "cogs/shop", "cogs/ui", "shared", "web", "scheduled_tasks", "knowledge/_wiki"]:
        path = PROJECT_ROOT / relative
        if path.exists():
            hotspots[relative] = sum(1 for _ in path.rglob("*") if _.is_file())
    return hotspots


def derive_expansion_suggestions() -> List[str]:
    suggestions: List[str] = []
    memory_manager = PROJECT_ROOT / "cogs" / "common" / "memory_manager.py"
    if memory_manager.exists() and "# ==================== 知識庫管理指令 ====================" in memory_manager.read_text(encoding="utf-8"):
        suggestions.append("`cogs/common/memory_manager.py` 仍是骨架，下一步可補管理員 slash commands 管理知識庫。")

    api_index = PROJECT_ROOT / "api_index.json"
    if api_index.exists() and "knowledge" not in api_index.read_text(encoding="utf-8").lower():
        suggestions.append("`api_index.json` 尚未列出 knowledge search endpoint，可補 `/api/knowledge/search` 供外部查詢。")

    kb_pipeline_doc = PROJECT_ROOT / "knowledge" / "_wiki" / "concepts" / "ai-memory-and-vm-knowledge-pipeline.md"
    if not kb_pipeline_doc.exists():
        suggestions.append("缺少 AI 記憶管線說明頁，建議把掃描與 ingest 流程寫進 knowledge wiki。")

    return suggestions


def render_markdown() -> str:
    timestamp = datetime.now(timezone.utc).astimezone().isoformat()
    statuses = get_systemctl_statuses()
    commits = get_recent_commits()
    repo_hotspots = get_repo_hotspots()
    suggestions = derive_expansion_suggestions()

    lines = [
        "# VM 掃描快照",
        "",
        f"- 掃描時間: {timestamp}",
        f"- 主機名稱: {platform.node() or 'unknown'}",
        f"- 平台: {platform.platform()}",
        f"- Python: {platform.python_version()}",
        f"- 專案根目錄: {PROJECT_ROOT.as_posix()}",
        f"- 磁碟摘要: {get_disk_summary()}",
        "",
        "## systemd 服務狀態",
        "",
    ]

    for service_name, status in statuses.items():
        lines.append(f"- {service_name}: {status}")

    lines.extend([
        "",
        "## Git 狀態",
        "",
        "```text",
        get_git_status(),
        "```",
        "",
        "## 最近 Commit",
        "",
    ])

    for commit in commits or ["(無 commit 資訊)"]:
        lines.append(f"- {commit}")

    lines.extend([
        "",
        "## Repo 熱區檔案數",
        "",
    ])
    for relative, count in repo_hotspots.items():
        lines.append(f"- {relative}: {count} files")

    lines.extend([
        "",
        "## 可拓展功能建議",
        "",
    ])
    for suggestion in suggestions or ["- 目前未偵測到新的結構性缺口。"]:
        if suggestion.startswith("-"):
            lines.append(suggestion)
        else:
            lines.append(f"- {suggestion}")

    lines.extend([
        "",
        "## 相關知識頁",
        "",
        "- [AI Fast Read](../concepts/ai-fast-read.md)",
        "- [Command Registry](../entities/command-registry.md)",
        "- [Bot Services](../entities/bot-services.md)",
        "- [AI 記憶與 VM 知識更新流程](../concepts/ai-memory-and-vm-knowledge-pipeline.md)",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="產生 VM 掃描 Markdown 報告")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="輸出 Markdown 路徑")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(), encoding="utf-8")
    print(json.dumps({"output": output_path.relative_to(PROJECT_ROOT).as_posix()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())