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

from shared.utils.mutual_rescue import _attempt_local_service_heal, _decide_repair_action, _read_service_snapshot

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

_MONITORED_SERVICES = ("bot.service", "shopbot.service", "uibot.service")


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


def _safe_stamp(value: str) -> str:
    text = str(value or datetime.now().isoformat())
    safe = []
    for ch in text:
        safe.append(ch if ch.isalnum() else "-")
    compact = "".join(safe).strip("-")
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact[:48] or "unknown-time"

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
        self.github_mode = os.getenv("AUTO_DEBUG_GITHUB_MODE", "escalate").strip().lower()
        self.escalate_severity = os.getenv("AUTO_DEBUG_ESCALATE_SEVERITY", "critical").strip().lower()

    async def analyze_locally(self, error_data: Dict) -> Dict:
        """先在本地/VM 直接做 AI 分析，避免把 GitHub Actions 當成主路徑。"""
        errors = error_data.get("errors") or {}
        severity = str(error_data.get("severity") or "unknown").lower()
        joined_logs = "\n\n".join(f"[{service}]\n{message}" for service, message in errors.items())

        fallback = {
            "root_cause": "尚未取得 AI 分析結果",
            "impact": "已檢測到服務異常，需要人工確認或進一步升級處理",
            "fix_steps": ["檢查最近 journalctl/systemd 日誌", "必要時重啟異常服務"],
            "prevention": ["補充錯誤監控與本地分析紀錄"],
            "confidence": 0.2,
            "analysis_source": "fallback",
            "analysis_status": "unavailable",
        }

        try:
            from utils.nvidia_ai import analyze_github_error

            system_info = (
                "local auto debug / source=auto_debug_system / "
                f"severity={severity} / services={', '.join(errors.keys()) or 'unknown'}"
            )
            analysis = await analyze_github_error(joined_logs[:6000], system_info)
            if isinstance(analysis, dict) and analysis:
                analysis.setdefault("analysis_source", "local_nvidia")
                analysis.setdefault("analysis_status", "completed")
                return analysis
        except Exception as exc:
            logger.warning(f"本地 AI 分析失敗，將使用 fallback 摘要: {type(exc).__name__}: {exc}")
            fallback["impact"] = str(exc)

        return fallback

    def should_escalate_to_github(self, error_data: Dict, local_analysis: Optional[Dict]) -> bool:
        """GitHub Actions 只做升級處理，而不是主處理路徑。"""
        if self.github_mode == "off":
            return False
        if self.github_mode == "always":
            return bool(self.github_token)

        severity = str(error_data.get("severity") or "unknown").lower()
        analysis_status = str((local_analysis or {}).get("analysis_status") or "").lower()
        if analysis_status != "completed":
            return bool(self.github_token)
        return severity == self.escalate_severity and bool(self.github_token)

    def save_local_artifact(self, error_data: Dict, local_analysis: Dict, escalated: bool) -> str:
        """將本地分析結果寫入 archive，方便 VM 上直接追查。"""
        incident_signature = _build_incident_signature(error_data.get("errors") or {}, error_data.get("severity", "unknown"))
        incident_key = _artifact_key_from_signature(incident_signature)
        timestamp = _safe_stamp(error_data.get("timestamp"))
        artifact_dir = os.path.join("archive", "auto_debug_reports")
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, f"{timestamp}-{incident_key}.json")
        payload = {
            "timestamp": error_data.get("timestamp"),
            "severity": error_data.get("severity"),
            "errors": error_data.get("errors"),
            "incident_signature": incident_signature,
            "incident_key": incident_key,
            "github_escalated": escalated,
            "local_analysis": local_analysis,
        }
        with open(artifact_path, "w", encoding="utf-8") as artifact_file:
            json.dump(payload, artifact_file, ensure_ascii=False, indent=2)
        return artifact_path

    def _build_detection_message(self, result: Dict, local_analysis: Optional[Dict] = None, artifact_path: str = "") -> str:
        lines = []
        healed = result.get("healed") or {}
        errors = result.get("errors") or {}

        if healed:
            lines.append("已完成本地自癒:\n" + json.dumps(healed, ensure_ascii=False, indent=2))
        if errors:
            lines.append("待進一步處理的異常:\n" + json.dumps(errors, ensure_ascii=False, indent=2))
        if local_analysis:
            lines.append("本地分析:\n" + json.dumps(local_analysis, ensure_ascii=False, indent=2))
        if artifact_path:
            lines.append(f"本地紀錄: {artifact_path}")
        return "\n\n".join(lines)[:4000]

    async def _collect_detection_result(self) -> Optional[Dict]:
        """收集 systemd/journal 異常，並優先嘗試本地自癒。"""
        try:
            if os.name != "posix":
                logger.info("目前環境不是 Linux/systemd，跳過本地服務健康檢查")
                return None

            errors = {}
            healed = {}
            severity_rank = "low"

            for service in _MONITORED_SERVICES:
                snapshot = await asyncio.to_thread(_read_service_snapshot, service)
                action, reason = _decide_repair_action(snapshot)
                if action == "healthy":
                    continue

                if action == "local-heal":
                    heal_result = await asyncio.to_thread(_attempt_local_service_heal, service)
                    if heal_result.get("success"):
                        healed[service] = heal_result.get("summary", reason)
                        severity_rank = "medium" if severity_rank == "low" else severity_rank
                        continue

                    failed_snapshot = heal_result.get("snapshot") or snapshot
                    errors[service] = (
                        f"{reason}\n"
                        f"本地自癒失敗: {heal_result.get('summary', 'unknown')}\n"
                        f"{failed_snapshot.get('summary', '')}"
                    )[:2000]
                    severity_rank = "high"
                    continue

                errors[service] = f"{reason}\n{snapshot.get('summary', '')}"[:2000]
                severity_rank = "high"

            if not errors and not healed:
                return None

            return {
                "timestamp": datetime.now().isoformat(),
                "errors": errors,
                "healed": healed,
                "severity": severity_rank,
            }
        except Exception as e:
            logger.error(f"檢查系統錯誤時發生異常: {e}")
            return None

    async def _handle_detection_result(self, result: Dict) -> int:
        errors = result.get("errors") or {}
        healed = result.get("healed") or {}

        if not errors:
            await self.send_notification(
                self._build_detection_message(result),
                result.get("severity", "medium"),
                status_text="已完成本地自癒",
            )
            return len(healed)

        logger.warning(f"🔥 檢測到需升級處理的系統錯誤: {result}")
        local_analysis = await self.analyze_locally(result)
        should_escalate = self.should_escalate_to_github(result, local_analysis)
        artifact_path = self.save_local_artifact(result, local_analysis, should_escalate)
        status_text = "已完成本地分析"
        if should_escalate:
            status_text = "已完成本地分析，並升級至 GitHub Actions"

        await self.send_notification(
            self._build_detection_message(result, local_analysis=local_analysis, artifact_path=artifact_path),
            result["severity"],
            status_text=status_text,
        )

        if should_escalate:
            await self.trigger_github_action(result)
        return len(errors) + len(healed)
        
    async def check_system_errors(self) -> Optional[Dict]:
        """檢查系統錯誤"""
        return await self._collect_detection_result()
    
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
    
    async def send_notification(self, message: str, severity: str = "medium", status_text: str = "已完成本地分析"):
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
                    {"name": "🔄 處理狀態", "value": status_text, "inline": True}
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
                detection_result = await self.check_system_errors()

                if detection_result:
                    await self._handle_detection_result(detection_result)
                    await asyncio.sleep(300)  # 5分鐘
                else:
                    logger.info("✅ 系統運行正常")
                    await asyncio.sleep(60)  # 1分鐘後再次檢查
                    
            except Exception as e:
                logger.error(f"監控循環發生異常: {e}")
                await asyncio.sleep(30)  # 30秒後重試

    async def run_once(self) -> int:
        """單次執行檢查，供 VM 上的 one-shot probe 使用。"""
        logger.info("🔍 執行單次 VM 自動 Debug 檢查")
        detection_result = await self.check_system_errors()
        if not detection_result:
            logger.info("✅ 單次檢查未發現系統錯誤")
            return 0
        return await self._handle_detection_result(detection_result)

async def main():
    """主函數"""
    # 啟動監控系統
    debug_system = AutoDebugSystem()
    if not debug_system.github_token:
        logger.info("未設置 GitHub token，auto debug 將以本地分析模式運行，不升級至 GitHub Actions")
    run_once = os.getenv("AUTO_DEBUG_RUN_ONCE", "").strip().lower() in ("1", "true", "yes")
    if run_once:
        await debug_system.run_once()
    else:
        await debug_system.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())
