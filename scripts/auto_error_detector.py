#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動錯誤檢測器
監控系統日誌，檢測特定錯誤並自動觸發 GitHub Actions 修復
"""

import os
import asyncio
import aiohttp
import json
import subprocess
from datetime import datetime, timedelta
import re
from typing import Dict


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
        self.http_timeout = aiohttp.ClientTimeout(total=15)
        self.github_mode = os.getenv("AUTO_DEBUG_GITHUB_MODE", "escalate").strip().lower()
        self.escalate_severity = os.getenv("AUTO_DEBUG_ESCALATE_SEVERITY", "high").strip().lower()
        self.error_patterns = {
            "name_self_error": r"name\s*['\"]\s*self\s*['\"]\s*is\s*not\s*defined",
            "syntax_error": r"SyntaxError",
            "import_error": r"ImportError",
            "attribute_error": r"AttributeError"
        }

    async def analyze_locally(self, error_data: Dict) -> Dict:
        """本地先做摘要分析，把 GitHub Actions 降級成第二層。"""
        log_text = str(error_data.get("message") or "")
        fallback = {
            "root_cause": f"檢測到 {error_data.get('type', 'unknown')} 類型錯誤",
            "impact": "需要檢查對應日誌與相關程式碼位置",
            "fix_steps": ["查看錯誤行附近代碼", "確認最近變更與部署內容"],
            "prevention": ["增加該錯誤類型的測試或防呆"],
            "confidence": 0.25,
            "analysis_source": "fallback",
            "analysis_status": "unavailable",
        }

        try:
            from utils.nvidia_ai import analyze_github_error

            system_info = (
                "local auto debug / source=auto_error_detector / "
                f"type={error_data.get('type', 'unknown')} / file={error_data.get('file', 'unknown')}"
            )
            analysis = await analyze_github_error(log_text[:4000], system_info)
            if isinstance(analysis, dict) and analysis:
                analysis.setdefault("analysis_source", "local_nvidia")
                analysis.setdefault("analysis_status", "completed")
                return analysis
        except Exception as exc:
            fallback["impact"] = str(exc)

        return fallback

    def should_escalate_to_github(self, error_data: Dict, local_analysis: Dict) -> bool:
        if self.github_mode == "off":
            return False
        if self.github_mode == "always":
            return bool(self.github_token)
        if str((local_analysis or {}).get("analysis_status") or "").lower() != "completed":
            return bool(self.github_token)
        severity = "high" if error_data.get("type") in {"syntax_error", "import_error"} else "medium"
        return severity == self.escalate_severity and bool(self.github_token)

    def save_local_artifact(self, error_data: Dict, local_analysis: Dict, escalated: bool) -> str:
        incident_signature = self._build_incident_signature(error_data)
        incident_key = _artifact_key_from_signature(incident_signature)
        timestamp = _safe_stamp(error_data.get("timestamp"))
        artifact_dir = os.path.join("archive", "auto_debug_reports")
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, f"{timestamp}-{incident_key}.json")
        payload = {
            "timestamp": error_data.get("timestamp"),
            "type": error_data.get("type"),
            "file": error_data.get("file"),
            "message": error_data.get("message"),
            "incident_signature": incident_signature,
            "incident_key": incident_key,
            "github_escalated": escalated,
            "local_analysis": local_analysis,
        }
        with open(artifact_path, "w", encoding="utf-8") as artifact_file:
            json.dump(payload, artifact_file, ensure_ascii=False, indent=2)
        return artifact_path
        
    async def check_system_logs(self):
        """檢查系統日誌中的錯誤"""
        errors_found = []
        
        # 檢查 Discord Bot 日誌
        try:
            # 獲取最近的系統日誌
            log_files = [
                "/var/log/syslog",
                "/var/log/kern.log",
                "/home/e193752468/.local/share/logs/discord_bot.log"
            ]
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    print(f"🔍 檢查日誌文件: {log_file}")
                    
                    # 讀取最近的日誌內容
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()[-1000:]  # 只讀取最後1000行
                            
                        for line in lines:
                            # 檢查各種錯誤模式
                            for error_name, pattern in self.error_patterns.items():
                                if re.search(pattern, line, re.IGNORECASE):
                                    timestamp = self.extract_timestamp(line)
                                    
                                    # 檢查是否需要觸發（避免重複觸發）
                                    if self.should_trigger_error(error_name, timestamp):
                                        errors_found.append({
                                            "type": error_name,
                                            "message": line.strip(),
                                            "timestamp": timestamp,
                                            "file": log_file
                                        })
                                        
                    except Exception as e:
                        print(f"❌ 讀取日誌文件失敗 {log_file}: {e}")
                        
        except Exception as e:
            print(f"❌ 檢查系統日誌失敗: {e}")
            
        return errors_found
    
    def extract_timestamp(self, log_line):
        """從日誌行中提取時間戳"""
        # 嘗試匹配常見的時間戳格式
        timestamp_patterns = [
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
    
    async def trigger_github_action(self, error_data):
        """觸發 GitHub Actions 進行自動修復"""
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
                    "service_hint": "bot.service" if "bot" in str(error_data.get("file", "")).lower() else "",
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
    
    async def send_discord_notification(self, error_data):
        """發送 Discord 通知"""
        if not self.webhook_url:
            return
        
        try:
            webhook_data = {
                "content": f"🚨 **自動錯誤檢測**",
                "embeds": [{
                    "title": "檢測到系統錯誤",
                    "description": f"已自動觸發 GitHub Actions 進行修復",
                    "color": 0xFF0000,
                    "fields": [
                        {"name": "🔍 錯誤類型", "value": error_data.get("type", "未知"), "inline": True},
                        {"name": "📁 錯誤文件", "value": error_data.get("file", "未知"), "inline": True},
                        {"name": "⏰ 檢測時間", "value": error_data.get("timestamp", datetime.now().isoformat()), "inline": True},
                        {"name": "🤖 處理狀態", "value": "已觸發自動修復", "inline": True}
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
    
    async def send_local_analysis_notification(self, error_data: Dict, local_analysis: Dict, escalated: bool, artifact_path: str):
        if not self.webhook_url:
            return

        try:
            status_text = "已完成本地分析"
            if escalated:
                status_text = "已完成本地分析，並升級至 GitHub Actions"

            webhook_data = {
                "content": "🚨 **自動錯誤檢測**",
                "embeds": [{
                    "title": "檢測到系統錯誤",
                    "description": (
                        f"錯誤訊息: {error_data.get('message', '未知')}\n\n"
                        f"本地分析: {json.dumps(local_analysis, ensure_ascii=False)}\n\n"
                        f"本地紀錄: {artifact_path}"
                    )[:4000],
                    "color": 0xFF0000,
                    "fields": [
                        {"name": "🔍 錯誤類型", "value": error_data.get("type", "未知"), "inline": True},
                        {"name": "📁 錯誤文件", "value": error_data.get("file", "未知"), "inline": True},
                        {"name": "🤖 處理狀態", "value": status_text, "inline": True},
                    ]
                }]
            }

            async with aiohttp.ClientSession(timeout=self.http_timeout) as session:
                await session.post(self.webhook_url, json=webhook_data)
        except Exception as e:
            print(f"❌ 發送本地分析通知失敗: {e}")

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
                        local_analysis = await self.analyze_locally(error)
                        should_escalate = self.should_escalate_to_github(error, local_analysis)
                        artifact_path = self.save_local_artifact(error, local_analysis, should_escalate)
                        await self.send_local_analysis_notification(error, local_analysis, should_escalate, artifact_path)
                        if should_escalate:
                            await self.trigger_github_action(error)
                        
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
            local_analysis = await self.analyze_locally(error)
            should_escalate = self.should_escalate_to_github(error, local_analysis)
            artifact_path = self.save_local_artifact(error, local_analysis, should_escalate)
            await self.send_local_analysis_notification(error, local_analysis, should_escalate, artifact_path)
            if should_escalate:
                await self.trigger_github_action(error)
        return len(errors)

async def main():
    """主函數"""
    print("🚀 啟動自動錯誤檢測器")
    
    detector = AutoErrorDetector()
    if not detector.github_token:
        print("ℹ️ 未設置 GITHUB_TOKEN，將只執行本地分析與 Discord 通知，不升級至 GitHub Actions")
    run_once = os.getenv("AUTO_ERROR_DETECTOR_RUN_ONCE", "").strip().lower() in ("1", "true", "yes")
    if run_once:
        await detector.run_once()
    else:
        await detector.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())
