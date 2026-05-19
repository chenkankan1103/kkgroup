"""
自動 Debug 系統
監控系統錯誤，自動觸發 GitHub Actions 進行 AI 分析和修復
"""

import os
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
import subprocess
import logging
from typing import Optional, Dict, List

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _normalize_incident_signature(text: str) -> str:
    normalized = " ".join((text or "").strip().split())
    return normalized[:160] or "unknown-incident"


def _build_incident_signature(error_logs: Dict[str, str], severity: str) -> str:
    first_line = ""
    for key, value in (error_logs or {}).items():
        text = f"{key}: {value}".strip()
        if text:
            first_line = text.splitlines()[0]
            break
    return f"{severity}|{_normalize_incident_signature(first_line)}"


def _artifact_key_from_signature(signature: str) -> str:
    safe = []
    for ch in signature.lower():
        safe.append(ch if ch.isalnum() else "-")
    compact = "".join(safe).strip("-")
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact[:80] or "unknown-incident"


def _infer_service_hint(error_logs: Dict[str, str]) -> str:
    for service in (error_logs or {}).keys():
        if service in {"bot.service", "shopbot.service", "uibot.service"}:
            return service
    return ""

class AutoDebugSystem:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN") or os.getenv("DISCORD_GITHUB_TOKEN")
        self.repo_owner = "chenkankan1103"
        self.repo_name = "kkgroup"
        self.webhook_url = (
            os.getenv("DISCORD_WEBHOOK_URL")
            or os.getenv("DISCORD_WEBHOOK")
            or os.getenv("GITHUB_WEBHOOK_URL", "")
        )
        self.last_error_time = {}
        self.error_threshold = 3  # 同類型錯誤觸發閾值
        self.http_timeout = aiohttp.ClientTimeout(total=15)
        
    async def check_system_errors(self) -> Optional[Dict]:
        """檢查系統錯誤"""
        try:
            if os.name != "posix":
                logger.info("目前環境不是 Linux/systemd，跳過本地服務健康檢查")
                return None

            # 檢查服務狀態
            services = ["bot.service", "shopbot.service", "uibot.service"]
            error_logs = {}
            has_errors = False
            
            for service in services:
                try:
                    # 檢查服務狀態
                    status_result = subprocess.run(
                        ['sudo', 'systemctl', 'is-active', service], 
                        capture_output=True, text=True, timeout=10
                    )
                    status = status_result.stdout.strip()
                    
                    if status in ["inactive", "failed"]:
                        has_errors = True
                        error_logs[service] = f"服務狀態異常: {status}"
                    
                    # 檢查最近錯誤日誌
                    log_result = subprocess.run(
                        ['sudo', 'journalctl', '-u', service, '--since', '1 hour ago', '--no-pager', '-n', '10'],
                        capture_output=True, text=True, timeout=10
                    )
                    logs = log_result.stdout
                    
                    # 檢查錯誤關鍵字
                    error_keywords = ["error", "exception", "failed", "traceback", "critical"]
                    error_count = sum(1 for keyword in error_keywords if keyword.lower() in logs.lower())
                    
                    if error_count >= 2:  # 1小時內有2個以上錯誤
                        has_errors = True
                        error_logs[service] = f"檢測到 {error_count} 個錯誤:\n{logs[-500:]}"
                        
                except subprocess.TimeoutExpired:
                    error_logs[service] = "檢查超時"
                    has_errors = True
                except Exception as e:
                    error_logs[service] = f"檢查失敗: {str(e)}"
                    has_errors = True
            
            if has_errors:
                return {
                    "timestamp": datetime.now().isoformat(),
                    "errors": error_logs,
                    "severity": "high" if len(error_logs) >= 2 else "medium"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"檢查系統錯誤時發生異常: {e}")
            return None
    
    async def trigger_github_action(self, error_data: Dict) -> bool:
        """觸發 GitHub Actions 進行 AI 分析"""
        try:
            if not self.github_token:
                logger.error("未設置 GITHUB_TOKEN，無法觸發 GitHub Actions")
                return False
            
            # 準備觸發數據
            payload = {
                "event_type": "system_debug",
                "client_payload": {
                    "timestamp": error_data["timestamp"],
                    "severity": error_data["severity"],
                    "error_logs": error_data["errors"],
                    "error_data": error_data,
                    "source": "auto_debug_system",
                    "service_hint": _infer_service_hint(error_data["errors"]),
                    "incident_signature": _build_incident_signature(error_data["errors"], error_data["severity"]),
                }
            }
            payload["client_payload"]["incident_key"] = _artifact_key_from_signature(
                payload["client_payload"]["incident_signature"]
            )
            
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json"
            }
            
            # 觸發 repository_dispatch 事件
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/dispatches"
            
            async with aiohttp.ClientSession(timeout=self.http_timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 204:
                        logger.info("✅ 成功觸發 GitHub Actions")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ 觸發 GitHub Actions 失敗: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"觸發 GitHub Actions 時發生異常: {e}")
            return False
    
    async def send_notification(self, message: str, severity: str = "medium"):
        """發送通知到 Discord"""
        if not self.webhook_url:
            return
        
        webhook_data = {
            "content": f"🤖 **自動 Debug 系統**",
            "embeds": [{
                "title": "🔍 系統錯誤檢測",
                "description": message,
                "color": 0xFF0000 if severity == "high" else 0xFFFF00,
                "fields": [
                    {"name": "⏰ 檢測時間", "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "inline": True},
                    {"name": "🚨 嚴重程度", "value": severity.upper(), "inline": True},
                    {"name": "🔄 處理狀態", "value": "已觸發 GitHub Actions", "inline": True}
                ]
            }]
        }
        
        try:
            async with aiohttp.ClientSession(timeout=self.http_timeout) as session:
                async with session.post(self.webhook_url, json=webhook_data) as response:
                    if response.status == 204:
                        logger.info("✅ Discord 通知發送成功")
                    else:
                        logger.error(f"❌ Discord 通知發送失敗: {response.status}")
        except Exception as e:
            logger.error(f"發送 Discord 通知時發生異常: {e}")
    
    async def monitor_loop(self):
        """監控循環"""
        logger.info("🚀 自動 Debug 系統啟動")
        
        while True:
            try:
                # 檢查系統錯誤
                error_data = await self.check_system_errors()
                
                if error_data:
                    logger.warning(f"🔥 檢測到系統錯誤: {error_data}")
                    
                    # 發送通知
                    await self.send_notification(
                        f"檢測到系統錯誤，已自動觸發 GitHub Actions 進行 AI 分析和修復\n\n錯誤詳情:\n{json.dumps(error_data['errors'], ensure_ascii=False, indent=2)}",
                        error_data["severity"]
                    )
                    
                    # 觸發 GitHub Actions
                    await self.trigger_github_action(error_data)
                    
                    # 等待一段時間避免重複觸發
                    await asyncio.sleep(300)  # 5分鐘
                else:
                    logger.info("✅ 系統運行正常")
                    await asyncio.sleep(60)  # 1分鐘後再次檢查
                    
            except Exception as e:
                logger.error(f"監控循環發生異常: {e}")
                await asyncio.sleep(30)  # 30秒後重試

async def main():
    """主函數"""
    # 檢查環境變數
    required_vars = ["GITHUB_TOKEN 或 DISCORD_GITHUB_TOKEN"]
    has_github_token = bool(os.getenv("GITHUB_TOKEN") or os.getenv("DISCORD_GITHUB_TOKEN"))
    missing_vars = [] if has_github_token else required_vars
    
    if missing_vars:
        logger.error(f"❌ 缺少必要環境變數: {', '.join(missing_vars)}")
        logger.error("請設置以下環境變數:")
        for var in missing_vars:
            logger.error(f"  export {var}=your_token_here")
        return
    
    # 啟動監控系統
    debug_system = AutoDebugSystem()
    await debug_system.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())
