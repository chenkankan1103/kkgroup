#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動錯誤檢測器
監控系統日誌，檢測特定錯誤並自動觸發 GitHub Actions 修復
"""

import os
import asyncio
import aiohttp
import subprocess
from datetime import datetime, timedelta
import re
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _normalize_incident_signature(text):
    normalized = " ".join(str(text or "").strip().split())
    return normalized[:160] or "unknown-incident"


def _artifact_key_from_signature(signature):
    safe = []
    for ch in str(signature or "").lower():
        safe.append(ch if ch.isalnum() else "-")
    compact = "".join(safe).strip("-")
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact[:80] or "unknown-incident"


def _safe_stamp(value):
    text = str(value or datetime.now().isoformat())
    safe = []
    for ch in text:
        safe.append(ch if ch.isalnum() else "-")
    compact = "".join(safe).strip("-")
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact[:48] or "unknown-time"

class AutoErrorDetector:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo_owner = "chenkankan1103"
        self.repo_name = "kkgroup"
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK")
        self.last_error_time = {}
        self.last_incident_time = {}
        self.http_timeout = aiohttp.ClientTimeout(total=15)
        self.journal_services = [
            "bot.service",
            "shopbot.service",
            "uibot.service",
        ]
        self.journal_lines = int(os.getenv("AUTO_DEBUG_JOURNAL_LINES", "200"))
        self.max_log_age_seconds = int(os.getenv("AUTO_DEBUG_MAX_LOG_AGE_SECONDS", "600"))
        self.error_patterns = {
            "name_self_error": r"name\s*['\"]\s*self\s*['\"]\s*is\s*not\s*defined",
            "syntax_error": r"SyntaxError",
            "import_error": r"ImportError",
            "attribute_error": r"AttributeError",
            "traceback": r"Traceback \(most recent call last\):",
            "http_exception": r"discord\.errors\.HTTPException|HTTPException",
        }

    def _is_benign_unknown_interaction(self, lines, index):
        current_line = str(lines[index] or "")
        if re.search(r"Unknown interaction|error code:\s*10062", current_line, re.IGNORECASE):
            return True

        if "Traceback (most recent call last):" not in current_line:
            return False

        window = "\n".join(str(line or "") for line in lines[index:index + 12])
        return bool(re.search(r"Unknown interaction|error code:\s*10062", window, re.IGNORECASE))

    def _collect_errors_from_lines(self, lines, source_name):
        errors_found = []

        for index, line in enumerate(lines):
            if not line:
                continue

            # 跳過 detector 自己的輸出，避免自我回音
            if re.search(r'auto-debug|auto_error_detector', line, re.IGNORECASE):
                continue

            if self._is_benign_unknown_interaction(lines, index):
                continue

            for error_name, pattern in self.error_patterns.items():
                if not re.search(pattern, line, re.IGNORECASE):
                    continue

                timestamp = self.extract_timestamp(line)
                if not self.should_trigger_error(error_name, timestamp):
                    continue

                errors_found.append({
                    "type": error_name,
                    "message": line.strip(),
                    "timestamp": timestamp,
                    "file": source_name,
                })

        return errors_found

    def _read_journal_lines(self, service_name):
        cmd = [
            "/usr/bin/journalctl",
            "-u",
            service_name,
            "-n",
            str(self.journal_lines),
            "--no-pager",
            "-o",
            "short-iso",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"journalctl failed for {service_name}")
        return result.stdout.splitlines()
        
    async def check_system_logs(self):
        """檢查系統日誌中的錯誤"""
        errors_found = []
        journal_available = False

        try:
            for service_name in self.journal_services:
                try:
                    print(f"🔍 檢查 systemd journal: {service_name}")
                    journal_available = True
                    lines = self._read_journal_lines(service_name)
                    errors_found.extend(self._collect_errors_from_lines(lines, service_name))
                except FileNotFoundError:
                    print("❌ 找不到 /usr/bin/journalctl，回退到文件日誌模式")
                    break
                except Exception as e:
                    print(f"❌ 讀取 systemd journal 失敗 {service_name}: {e}")

            if journal_available:
                return errors_found

            log_files = [
                "/var/log/syslog",
                "/var/log/kern.log",
                "/home/e193752468/.local/share/logs/discord_bot.log"
            ]

            for log_file in log_files:
                if not os.path.exists(log_file):
                    continue

                print(f"🔍 檢查日誌文件: {log_file}")
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()[-1000:]
                    errors_found.extend(self._collect_errors_from_lines(lines, log_file))
                except Exception as e:
                    print(f"❌ 讀取日誌文件失敗 {log_file}: {e}")

        except Exception as e:
            print(f"❌ 檢查系統日誌失敗: {e}")
            
        return errors_found
    
    def extract_timestamp(self, log_line):
        """從日誌行中提取時間戳"""
        # 嘗試匹配常見的時間戳格式
        timestamp_patterns = [
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{4})',  # YYYY-MM-DDTHH:MM:SS+0800
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',  # YYYY-MM-DD HH:MM:SS
            r'(\w{3}\s+\d{2}\s+\d{2}:\d{2}:\d{2})',   # Mon DD HH:MM:SS
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})',  # MM/DD/YYYY HH:MM:SS
        ]
        
        for pattern in timestamp_patterns:
            match = re.search(pattern, log_line)
            if match:
                return match.group(1)
        
        return datetime.now().isoformat()

    def normalize_timestamp(self, timestamp):
        """標準化時間戳，避免非 ISO 格式導致冷卻判斷失敗"""
        if isinstance(timestamp, datetime):
            return timestamp

        if not isinstance(timestamp, str):
            return datetime.now()

        candidates = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%b %d %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
        ]

        for fmt in candidates:
            try:
                parsed = datetime.strptime(timestamp, fmt)
                if fmt == "%b %d %H:%M:%S":
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(timestamp)
        except ValueError:
            return datetime.now()
    
    def should_trigger_error(self, error_type, timestamp):
        """判斷是否應該觸發錯誤處理"""
        current_time = self.normalize_timestamp(timestamp)

        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=datetime.now().astimezone().tzinfo)

        now = datetime.now(current_time.tzinfo)
        if (now - current_time).total_seconds() > self.max_log_age_seconds:
            return False

        # 檢查冷卻時間（避免重複觸發）
        if error_type in self.last_error_time:
            last_time = self.last_error_time[error_type]
            
            # 如果同一類型錯誤在 10 分鐘內已經觸發過，則跳過
            if current_time - last_time < timedelta(minutes=10):
                return False
        
        # 更新最後觸發時間
        self.last_error_time[error_type] = current_time
        return True

    def _build_incident_signature(self, error_data):
        base = f"{error_data.get('type', 'unknown')}|{error_data.get('file', 'log')}|{error_data.get('message', '')}"
        return _normalize_incident_signature(base)

    def should_trigger_incident(self, error_data):
        signature = self._build_incident_signature(error_data)
        current_time = self.normalize_timestamp(error_data.get("timestamp"))

        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=datetime.now().astimezone().tzinfo)

        previous_time = self.last_incident_time.get(signature)
        if previous_time and current_time - previous_time < timedelta(minutes=30):
            return False

        self.last_incident_time[signature] = current_time
        return True

    def _infer_service_hint(self, error_data):
        source = str(error_data.get("file") or "").lower()
        message = str(error_data.get("message") or "").lower()
        combined = f"{source} {message}"

        if "shopbot" in combined:
            return "shopbot.service"
        if "uibot" in combined:
            return "uibot.service"
        if "bot" in combined:
            return "bot.service"
        return ""
    
    async def trigger_github_action(self, error_data):
        """觸發 GitHub Actions 進行分析、修復與推送。"""
        try:
            if not self.github_token:
                print("❌ 未設置 GITHUB_TOKEN，無法觸發 GitHub Actions")
                return False

            normalized_timestamp = self.normalize_timestamp(error_data.get("timestamp")).isoformat()

            # 準備觸發數據
            payload = {
                "event_type": "system_debug",
                "client_payload": {
                    "timestamp": normalized_timestamp,
                    "severity": "high",
                    "error_logs": {
                        error_data.get("file", "log"): error_data.get("message", "")
                    },
                    "error_data": error_data,
                    "source": "auto_error_detector",
                    "service_hint": self._infer_service_hint(error_data),
                    "incident_signature": self._build_incident_signature(error_data),
                }
            }
            payload["client_payload"]["incident_key"] = _artifact_key_from_signature(
                payload["client_payload"]["incident_signature"]
            )
            
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json"
            }
            
            # 觸發 repository_dispatch 事件
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/dispatches"
            
            async with aiohttp.ClientSession(timeout=self.http_timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 204:
                        print("✅ 成功觸發 GitHub Actions 自動修復")
                        return True
                    else:
                        error_text = await response.text()
                        print(f"❌ 觸發 GitHub Actions 失敗: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            print(f"❌ 觸發 GitHub Actions 時發生異常: {e}")
            return False
    
    async def send_discord_notification(self, error_data, dispatch_success):
        """發送簡化流程通知。"""
        if not self.webhook_url:
            return
        
        try:
            status_text = "已送交 GitHub 分析 / debug / push" if dispatch_success else "觸發 GitHub 失敗"
            webhook_data = {
                "content": f"🚨 **自動錯誤檢測**",
                "embeds": [{
                    "title": "檢測到系統錯誤",
                    "description": f"流程：分析問題 -> debug -> push",
                    "color": 0x57F287 if dispatch_success else 0xED4245,
                    "fields": [
                        {"name": "🔍 錯誤類型", "value": error_data.get("type", "未知"), "inline": True},
                        {"name": "📁 錯誤文件", "value": error_data.get("file", "未知"), "inline": True},
                        {"name": "⏰ 檢測時間", "value": error_data.get("timestamp", datetime.now().isoformat()), "inline": True},
                        {"name": "🤖 處理狀態", "value": status_text, "inline": False}
                    ]
                }]
            }
            
            async with aiohttp.ClientSession(timeout=self.http_timeout) as session:
                async with session.post(self.webhook_url, json=webhook_data) as response:
                    if response.status == 204:
                        print("✅ Discord 通知發送成功")
                    else:
                        print(f"❌ Discord 通知發送失敗: {response.status}")
                        
        except Exception as e:
            print(f"❌ 發送 Discord 通知失敗: {e}")

    async def monitor_loop(self):
        """監控循環"""
        print("🚀 自動錯誤檢測器啟動")
        
        while True:
            try:
                print("🔍 開始檢查系統日誌...")
                
                # 檢查系統日誌
                errors = await self.check_system_logs()
                
                if errors:
                    print(f"🚨 檢測到 {len(errors)} 個錯誤")
                    
                    for error in errors:
                        print(f"🔍 錯誤詳情: {error}")
                        if not self.should_trigger_incident(error):
                            print("ℹ️ 相同 incident 仍在冷卻中，跳過")
                            continue
                        dispatch_success = await self.trigger_github_action(error)
                        await self.send_discord_notification(error, dispatch_success)
                        
                        # 等待一段時間避免重複觸發
                        await asyncio.sleep(30)
                else:
                    print("✅ 未檢測到錯誤")
                
                # 等待下次檢查（每 2 分鐘檢查一次）
                await asyncio.sleep(120)
                
            except Exception as e:
                print(f"❌ 監控循環發生異常: {e}")
                await asyncio.sleep(30)  # 異常時等待 30 秒後重試

    async def run_once(self):
        """單次檢查，適合 GitHub Actions 或一次性任務。"""
        print("🔍 執行單次錯誤檢測")
        errors = await self.check_system_logs()
        if not errors:
            print("✅ 單次檢查未檢測到錯誤")
            return 0

        print(f"🚨 單次檢查檢測到 {len(errors)} 個錯誤")
        for error in errors:
            print(f"🔍 錯誤詳情: {error}")
            if not self.should_trigger_incident(error):
                print("ℹ️ 相同 incident 仍在冷卻中，跳過")
                continue
            dispatch_success = await self.trigger_github_action(error)
            await self.send_discord_notification(error, dispatch_success)
        return len(errors)

async def main():
    """主函數"""
    print("🚀 啟動自動錯誤檢測器")
    
    detector = AutoErrorDetector()
    if not detector.github_token:
        print("ℹ️ 未設置 GITHUB_TOKEN，將只能檢測錯誤，無法送出分析 / debug / push 流程")
    run_once = os.getenv("AUTO_ERROR_DETECTOR_RUN_ONCE", "").strip().lower() in ("1", "true", "yes")
    if run_once:
        await detector.run_once()
    else:
        await detector.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())
