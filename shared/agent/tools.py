"""
KK群組 - Agent 工具實作
========================
包含所有工具的具體執行邏輯、路徑安全防護、日誌掃描。
設計為可獨立 import、無 Discord 依賴。
"""

import asyncio
import json
import logging
import os
import re
import shlex
import subprocess
import shutil
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── 路徑安全防護 ────────────────────────────────────────────────────
WORK_DIR = Path(os.getenv("CLAUDE_WORK_DIR", "/home/e193752468/kkgroup")).resolve()

BLOCKED_PATHS = {
    "/etc", "/root", "/home", "/var", "/usr", "/bin", "/sbin",
    "/lib", "/lib64", "/boot", "/sys", "/proc", "/dev", "/run",
    "/tmp", "/srv", "/opt", "/mnt", "/media",
}

BLOCKED_FILES = {".env", ".ssh", "id_rsa", "id_ed25519", "authorized_keys", "config"}
BLOCKED_PREFIXES = [".git/", ".github/", "__pycache__/", "venv/", ".venv/", "node_modules/"]


def secure_path(path: str) -> Path:
    """
    解析並驗證路徑安全性。
    - 必須在 WORK_DIR 內
    - 不得存取敏感系統路徑
    - 不得存取敏感檔案
    """
    # 正規化路徑
    target = (WORK_DIR / path).resolve()

    # 必須在工作目錄內
    try:
        target.relative_to(WORK_DIR)
    except ValueError:
        raise PermissionError(f"路徑超出工作目錄範圍: {path}")

    # 檢查敏感路徑前綴
    for prefix in BLOCKED_PREFIXES:
        if prefix in str(target.relative_to(WORK_DIR)):
            raise PermissionError(f"禁止存取路徑: {path} (匹配 {prefix})")

    # 檢查敏感檔名
    for blocked in BLOCKED_FILES:
        if blocked in target.name:
            raise PermissionError(f"禁止存取敏感檔案: {target.name}")

    return target


# ─── 工具實作類別 ────────────────────────────────────────────────────
class ToolImpl:
    """所有工具的具體實作"""

    def __init__(self, work_dir: Path):
        self.work_dir = work_dir

    # ----- 檔案讀寫 -----
    async def read(self, path: str, offset: int = 0, limit: Optional[int] = None) -> str:
        """讀取檔案（支援行號範圍）"""
        target = secure_path(path)
        if not target.exists():
            raise FileNotFoundError(f"檔案不存在: {path}")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # 嘗試其他編碼
            content = target.read_text(encoding="utf-8", errors="replace")

        lines = content.splitlines()
        if offset or limit:
            end = offset + limit if limit else None
            lines = lines[offset:end]
        return "\n".join(lines)

    async def write(self, path: str, content: str) -> str:
        """寫入檔案（建立父目錄）"""
        target = secure_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"✅ 已寫入: {path} ({len(content)} 字元)"

    async def edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """編輯檔案（精確替換）"""
        target = secure_path(path)
        if not target.exists():
            raise FileNotFoundError(f"檔案不存在: {path}")

        content = target.read_text(encoding="utf-8")

        if replace_all:
            if old_string not in content:
                raise ValueError(f"找不到要替換的字串: {old_string[:50]}...")
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            if content.count(old_string) != 1:
                raise ValueError(f"匹配不唯一 (找到 {content.count(old_string)} 處)，談確指定或用 replace_all=true")
            new_content = content.replace(old_string, new_string)
            count = 1

        target.write_text(new_content, encoding="utf-8")
        return f"✅ 已編輯: {path} ({count} 處替換)"

    # ----- 目錄/搜尋 -----
    async def list(self, path: str = ".") -> str:
        """列出目錄內容"""
        target = secure_path(path)
        if not target.exists():
            raise FileNotFoundError(f"目錄不存在: {path}")
        if not target.is_dir():
            raise NotADirectoryError(f"非目錄: {path}")

        items = []
        for item in sorted(target.iterdir()):
            rel = item.relative_to(self.work_dir)
            if item.is_dir():
                items.append(f"📁 {rel}/")
            else:
                size = item.stat().st_size
                items.append(f"📄 {rel} ({size} bytes)")
        return "\n".join(items) if items else "(空目錄)"

    async def glob(self, pattern: str, path: str = ".") -> str:
        """Glob 模式搜尋檔案"""
        target = secure_path(path)
        if not target.exists():
            raise FileNotFoundError(f"目錄不存在: {path}")

        matches = list(target.glob(pattern))
        matches.sort()
        return "\n".join(str(m.relative_to(self.work_dir)) for m in matches) if matches else "(無匹配)"

    # ----- 命令執行 -----
    async def bash(self, command: str, timeout: int = 60) -> str:
        """執行 shell 命令（安全模式：僅允許白名單命令）"""
        # 解析命令
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"❌ 命令解析失敗: {e}"

        if not parts:
            return "❌ 空命令"

        # 命令白名單（防止任意命令執行）
        ALLOWED_COMMANDS = {
            "python3", "python", "pip", "pytest", "ruff", "black", "mypy",
            "git", "grep", "rg", "find", "cat", "head", "tail", "wc",
            "ls", "stat", "file", "which", "ps", "free", "df",
            "journalctl", "systemctl", "systemd-analyze",
            "curl", "wget", "jq", "awk", "sed", "sort", "uniq",
        }
        if parts[0] not in ALLOWED_COMMANDS:
            return f"❌ 命令不在白名單: {parts[0]}"

        # 執行
        try:
            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.work_dir),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")

            result = f"Exit code: {proc.returncode}\n"
            if out:
                result += f"STDOUT:\n{out}"
            if err:
                result += f"STDERR:\n{err}"
            return result.strip()

        except asyncio.TimeoutError:
            return f"❌ 命令超時 ({timeout}s)"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

    # ----- 代碼搜尋 -----
    async def search_code(self, pattern: str, path: str = ".", glob: str = "") -> str:
        """使用 ripgrep 搜尋代碼"""
        target = secure_path(path)
        if not target.exists():
            raise FileNotFoundError(f"路徑不存在: {path}")

        cmd = ["rg", "--no-heading", "--line-number", "--color=never"]
        if glob:
            cmd.extend(["--glob", glob])
        cmd.append(pattern)
        cmd.append(str(target))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            out = stdout.decode("utf-8", errors="replace")
            return out if out else "(無匹配)"
        except FileNotFoundError:
            # fallback to grep
            cmd = ["grep", "-r", "-n", pattern, str(target)]
            if glob:
                cmd.extend(["--include", glob])
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode("utf-8", errors="replace") or "(無匹配)"
        except Exception as e:
            return f"❌ 搜尋失敗: {e}"

    # ----- 系統日誌掃描 -----
    async def scan_journalctl(
        self,
        service: str = "all",
        since_minutes: int = 15,
        level: str = "error",
        pattern: str = "",
        limit: int = 50,
    ) -> str:
        """
        掃描 systemd journal 錯誤日誌。
        回傳結構化摘要：錯誤統計、高頻錯誤、疑似根因。
        """
        services = {
            "bot": "bot.service",
            "shopbot": "shopbot.service",
            "uibot": "uibot.service",
            "kkgroup-api": "kkgroup-api.service",
            "cloudflared": "cloudflared.service",
            "all": None,  # 所有以上服務
        }

        if service not in services:
            return f"❌ 未知服務: {service}"

        since = f"-{since_minutes}min"
        target_services = [services[service]] if service != "all" else list(services.values())[:-1]

        all_entries = []
        for svc in target_services:
            cmd = ["journalctl", "-u", svc, "--since", since, "--no-pager", "-o", "json"]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                lines = stdout.decode("utf-8", errors="replace").strip().split("\n")

                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        msg = entry.get("MESSAGE", "")
                        pri = entry.get("PRIORITY", "6")  # 0=emerg, 3=err, 4=warning, 6=info

                        # 級別過濾
                        if level == "error" and pri not in ("0", "1", "2", "3"):
                            continue
                        if level == "warning" and pri not in ("0", "1", "2", "3", "4"):
                            continue

                        # 模式過濾
                        if pattern and pattern.lower() not in msg.lower():
                            continue

                        all_entries.append({
                            "service": svc.replace(".service", ""),
                            "priority": pri,
                            "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                            "message": msg[:500],  # 截斷過長訊息
                        })
                    except json.JSONDecodeError:
                        continue

            except Exception as e:
                logger.warning(f"journalctl {svc} failed: {e}")

        if not all_entries:
            return f"📭 近 {since_minutes} 分鐘無符合條件的日誌 ({service})"

        # 統計分析
        from collections import Counter
        by_service = Counter(e["service"] for e in all_entries)
        by_priority = Counter(e["priority"] for e in all_entries)

        # 簡單錯誤指紋：取前 80 字元
        fingerprints = Counter(e["message"][:80] for e in all_entries)
        top_fingerprints = fingerprints.most_common(5)

        # 構建回報
        lines = [
            f"📊 Journal 掃描報告 (近 {since_minutes} 分鐘, {service})",
            f"總計: {len(all_entries)} 筆",
            f"服務分佈: {dict(by_service)}",
            f"優先級分佈: {dict(by_priority)}",
            "",
            "🔥 高頻錯誤模式:",
        ]
        for fp, count in top_fingerprints:
            lines.append(f"  ×{count}: {fp}")

        lines.append("")
        lines.append(f"📋 最近 {min(limit, len(all_entries))} 筆原始日誌:")
        for e in all_entries[-limit:]:
            ts = e["timestamp"][:19] if e["timestamp"] else "??"
            pri_mark = "🔴" if e["priority"] in ("0","1","2","3") else "🟡"
            lines.append(f"  {pri_mark} [{e['service']}] {ts} {e['message'][:200]}")

        return "\n".join(lines)


# ─── 匯出實例（供 agent_core 延遲載入） ───────────────────────────
def create_tool_impl(work_dir: Path) -> ToolImpl:
    return ToolImpl(work_dir)