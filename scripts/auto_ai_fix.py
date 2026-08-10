#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動 AI 修復腳本
由 GitHub Actions 觸發，執行 AI 分析和修復代碼生成
"""

import os
import asyncio
import json
import re
import subprocess
from datetime import datetime


def _normalize_log_text(error_logs):
    if isinstance(error_logs, str):
        return error_logs
    return json.dumps(error_logs, ensure_ascii=False, indent=2)


def _normalize_repo_path(file_path: str) -> str:
    return os.path.normpath(file_path).replace("\\", "/")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _build_review_artifact_path(target_file_path: str, timestamp: str) -> str:
    safe_target = (
        (target_file_path or "unknown-target").replace("/", "__").replace("\\", "__")
    )
    safe_target = (
        re.sub(r"[^A-Za-z0-9_.-]+", "-", safe_target).strip("-") or "unknown-target"
    )
    return os.path.join("archive", "ai_fixes", f"{timestamp}_{safe_target}.md")


def should_allow_commit(event_data):
    payload = event_data.get("client_payload", {})
    source = (
        str(payload.get("source") or event_data.get("source") or "").strip().lower()
    )
    if source.startswith("manual_test"):
        return False, f"來源為 {source}，僅做閉環測試，禁止提交修復 commit"
    return True, "允許提交修復 commit"


def should_attempt_code_fix(event_data):
    """只對高危且偏程式碼層面的錯誤啟用自動修復。"""
    payload = event_data.get("client_payload", {})
    severity = (
        str(payload.get("severity") or event_data.get("severity") or "medium")
        .strip()
        .lower()
    )
    error_logs = (
        payload.get("error_logs")
        or payload.get("error_data")
        or payload.get("log_text")
        or event_data.get("error_logs")
        or ""
    )
    log_text = _normalize_log_text(error_logs)

    is_high = severity in ("high", "h", "高")
    has_code_failure_signal = bool(
        re.search(
            r"(Traceback|Exception|CRITICAL|Fatal|Unhandled|NameError|AttributeError|TypeError|ImportError|SyntaxError|object is not subscriptable|is not subscriptable|failed with result|status=\d+/FAILURE)",
            log_text,
            re.IGNORECASE,
        )
    )
    looks_external_or_infra = bool(
        re.search(
            r"(503 Service Unavailable|upstream connect error|remote connection failure|No such file or directory|connection reset by peer|temporarily unavailable|cloudflared|nginx)",
            log_text,
            re.IGNORECASE,
        )
    )

    # severity 若缺失、亂碼、或非標準值，回退用日誌內容推估
    if severity not in ("high", "h", "高", "medium", "m", "中", "low", "l", "低"):
        severity = "high" if has_code_failure_signal else "medium"

    is_high = severity in ("high", "h", "高")

    if looks_external_or_infra and not has_code_failure_signal:
        return False, "外部服務或基礎設施異常，跳過自動改碼"
    if not is_high:
        return False, f"緊急程度為 {severity}，未達自動改碼門檻"
    if not has_code_failure_signal:
        return False, "缺少明確程式碼錯誤訊號，跳過自動改碼"
    return True, "符合高危程式錯誤條件，允許自動改碼"


def _extract_payload(event_data):
    payload = event_data.get("client_payload", {})
    return payload if isinstance(payload, dict) else {}


def _extract_error_log_text(event_data):
    payload = _extract_payload(event_data)
    error_logs = (
        payload.get("error_logs")
        or payload.get("error_data")
        or payload.get("log_text")
        or event_data.get("error_logs")
        or ""
    )
    return _normalize_log_text(error_logs)


def _extract_incident_metadata(event_data):
    payload = _extract_payload(event_data)
    return {
        "incident_signature": str(payload.get("incident_signature") or "").strip(),
        "incident_key": str(payload.get("incident_key") or "").strip(),
        "source": str(
            payload.get("source") or event_data.get("source") or "auto-ai-fix"
        ).strip(),
        "severity": str(
            payload.get("severity") or event_data.get("severity") or "medium"
        ).strip(),
        "timestamp": str(
            payload.get("timestamp")
            or event_data.get("timestamp")
            or datetime.now().isoformat()
        ).strip(),
    }


async def analyze_and_fix(event_data, nvidia_api_key, discord_webhook):
    """AI 分析和生成修復代碼"""
    try:
        import sys

        workspace_path = os.getenv("GITHUB_WORKSPACE", ".")
        sys.path.insert(0, workspace_path)
        from utils.google_ai import GoogleAIClient
        from utils.nvidia_ai import NVIDIAAIClient

        client = NVIDIAAIClient()
        print("✅ NVIDIA AI 客戶端初始化成功")

        # 獲取錯誤日誌
        payload = event_data.get("client_payload", {})
        error_logs = (
            payload.get("error_logs")
            or payload.get("error_data")
            or payload.get("log_text")
            or event_data.get("error_logs")
            or {}
        )
        if isinstance(error_logs, str):
            error_logs = {"log": error_logs}
        timestamp = (
            payload.get("timestamp")
            or event_data.get("timestamp")
            or datetime.now().isoformat()
        )
        severity = payload.get("severity") or event_data.get("severity") or "medium"

        # 從 dispatch payload 取得 traceback 抽出的真實檔案路徑（mutual_rescue / self-heal daemon 已填入）
        target_file = payload.get("target_file", "") or event_data.get(
            "target_file", ""
        )
        if target_file:
            print(
                f"📁 dispatch payload 內含 traceback 抽出之真實檔案路徑: {target_file}"
            )

        # 構建分析提示
        analysis_prompt = f"""你是KKGroup Discord Bot系統的AI除錯和修復專家。

        系統環境：
        - GCP VM: e2-micro (1GB RAM + 4GB swap)
        - 三個Bot服務: bot.service, shopbot.service, uibot.service
        - 技術棧: Python 3.11 + Discord.py + systemd

        錯誤日誌：
        {json.dumps(error_logs, ensure_ascii=False, indent=2)}

        時間：{timestamp}
        緊急程度：{severity}

        請分析並生成修復代碼：
        1. 根本原因分析
        2. 具體修復代碼（Python）
        3. 修復後的驗證方法
        4. 預防措施

        請以JSON格式回覆：
        {{
            "root_cause": "技術根本原因",
            "fix_code": "具體修復代碼",
            "verification": "驗證方法",
            "prevention": "預防措施",
            "file_path": "修復文件路徑"
        }}"""

        # 調用 NVIDIA AI
        messages = [
            {
                "role": "system",
                "content": "你是KKGroup Discord Bot系統的AI除錯和修復專家，請生成可執行的修復代碼。",
            },
            {"role": "user", "content": analysis_prompt},
        ]

        response = await client.call_api(
            messages,
            model=os.getenv(
                "AUTO_AI_FIX_NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b"
            ),
            max_tokens=2000,
        )

        if not response:
            # 只有在緊急程度為高時才使用 Gemini 備援以節省配額
            sev_norm = str(severity).strip().lower()
            is_high = sev_norm in ("high", "h", "高")
            if is_high:
                # 先嘗試 Groq（免費額度充足）
                groq_key = os.getenv("GROQ_API_KEY", "")
                if groq_key:
                    print("⚠️ NVIDIA 無回應，改用 Groq 備援")
                    import aiohttp

                    groq_payload = {
                        "model": "llama-3.3-70b-versatile",
                        "messages": messages,
                        "temperature": 0.4,
                        "max_tokens": 2000,
                    }
                    groq_headers = {
                        "Authorization": f"Bearer {groq_key}",
                        "Content-Type": "application/json",
                    }
                    try:
                        async with aiohttp.ClientSession(
                            timeout=aiohttp.ClientTimeout(total=8)
                        ) as session:
                            async with session.post(
                                "https://api.groq.com/openai/v1/chat/completions",
                                json=groq_payload,
                                headers=groq_headers,
                            ) as groq_resp:
                                if groq_resp.status == 200:
                                    groq_data = await groq_resp.json()
                                    choices = groq_data.get("choices", [])
                                    if choices:
                                        response = (
                                            choices[0]
                                            .get("message", {})
                                            .get("content", "")
                                            or ""
                                        )
                    except Exception as groq_err:
                        print(f"Groq fallback failed: {groq_err}")

                # 如果 Groq 也失敗，才使用 Gemini
                if not response:
                    print("⚠️ Groq 也無回應，改用 Gemini 備援")
                    response = await GoogleAIClient().call_api(
                        messages,
                        temperature=0.2,
                        max_tokens=2000,
                    )
            else:
                print(
                    f"⚠️ NVIDIA 無回應且緊急程度為 {severity}，跳過 Gemini 備援以節省配額"
                )
                response = None

        if response:
            try:
                result = json.loads(response)
                print("✅ AI 分析和修復代碼生成成功")
                return result
            except json.JSONDecodeError:
                print("⚠️ AI 回應不是有效JSON，嘗試提取修復代碼")
                return {
                    "root_cause": "AI 分析完成",
                    "fix_code": response,
                    "verification": "手動驗證修復效果",
                    "prevention": "定期檢查系統狀態",
                    "file_path": "fixes/auto_fix.py",
                }
        else:
            print("❌ NVIDIA AI 調用失敗")
            return None

    except ImportError as e:
        print(f"❌ NVIDIA AI 導入失敗: {e}")
        return None
    except Exception as e:
        print(f"❌ AI 分析過程發生錯誤: {e}")
        return None


async def create_fix_file(fix_data, timestamp, severity, override_target_file=None):
    """創建修復文件並提交"""
    if not fix_data:
        return False

    try:
        # 獲取修復代碼和文件路徑
        fix_code = fix_data.get("fix_code", "")
        # 優先使用 dispatch payload 的 target_file（由 mutual_rescue/self-heal 的 traceback 抽出），
        # 避免 AI 猜錯 file_path 導致只產 .md 提案、從未真正修原始碼。
        if override_target_file:
            file_path = _normalize_repo_path(override_target_file)
        else:
            file_path = _normalize_repo_path(
                fix_data.get("file_path", "fixes/auto_fix.py")
            )
        artifact_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        review_artifact_path = _build_review_artifact_path(
            file_path, artifact_timestamp
        )
        direct_write_enabled = _bool_env("AUTO_AI_DIRECT_WRITE", default=False)

        print(f"📝 生成修復提案: {review_artifact_path}")

        if (
            os.path.isabs(file_path)
            or file_path.startswith("../")
            or "/../" in file_path
        ):
            print(f"❌ 拒絕不安全修復路徑: {file_path}")
            return False

        os.makedirs(os.path.dirname(review_artifact_path), exist_ok=True)
        with open(review_artifact_path, "w", encoding="utf-8") as f:
            f.write(
                f"# AI Auto Fix Proposal\n\n"
                f"- Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- Severity: {severity}\n"
                f"- Suggested Target: {file_path}\n"
                f"- Direct Write Enabled: {direct_write_enabled}\n\n"
                f"## Root Cause\n{fix_data.get('root_cause', 'N/A')}\n\n"
                f"## Verification\n{fix_data.get('verification', '手動驗證修復效果')}\n\n"
                f"## Prevention\n{fix_data.get('prevention', '定期檢查系統狀態')}\n\n"
                f"## Suggested Code\n```python\n{fix_code}\n```\n"
            )

        staged_paths = [review_artifact_path]

        if direct_write_enabled:
            if not os.path.exists(file_path):
                print(f"❌ 目標文件不存在，拒絕直接寫入: {file_path}")
                return False

            target_dir = os.path.dirname(file_path)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fix_code)
            staged_paths.append(file_path)
            print(f"⚠️ 已啟用 AUTO_AI_DIRECT_WRITE，直接寫入目標文件: {file_path}")
        else:
            print(
                "ℹ️ 預設僅產生修復提案，不直接覆寫原始碼；如需啟用請設置 AUTO_AI_DIRECT_WRITE=true"
            )

        # 配置 Git
        subprocess.run(["git", "config", "user.name", "AI Auto Fix Bot"], check=True)
        subprocess.run(
            ["git", "config", "user.email", "ai-fix@kkgroup.local"], check=True
        )

        # 添加文件到 Git
        subprocess.run(["git", "add", *staged_paths], check=True)

        staged_changes = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], check=False
        )
        if staged_changes.returncode == 0:
            print(f"ℹ️ 修復提案 {review_artifact_path} 沒有實際差異，跳過 commit/push")
            return True

        # 提交修復
        commit_message = f"""fix: AI 自動修復 - {fix_data.get('root_cause', '未知錯誤')}

🤖 由 NVIDIA deepseek-v4-pro 自動生成修復代碼
📊 錯誤時間: {timestamp}
🚨 緊急程度: {severity}
🔧 修復提案: {review_artifact_path}
🎯 建議目標: {file_path}
"""

        subprocess.run(["git", "commit", "-m", commit_message], check=True)

        # 推送到遠端
        subprocess.run(["git", "push", "origin", "main"], check=True)

        fix_data["file_path"] = review_artifact_path
        fix_data["target_file_path"] = file_path
        print(f"✅ 修復提案已提交並推送到: {review_artifact_path}")
        return True

    except Exception as e:
        print(f"❌ 創建修復文件失敗: {e}")
        return False


async def send_discord_notification(
    fix_data, success, discord_webhook, heal_result=None
):
    """發送 Discord 通知"""
    if not discord_webhook:
        return

    color = 0x00FF00 if success else 0xFF0000
    status = "✅ 修復成功" if success else "❌ 修復失敗"

    webhook_data = {
        "content": f"🤖 **AI 自動修復** - {status}",
        "embeds": [
            {
                "title": "🔧 自動修復報告",
                "description": "根據錯誤分析生成的修復代碼",
                "color": color,
                "fields": [
                    {
                        "name": "🤖 AI引擎",
                        "value": "NVIDIA deepseek-v4-pro",
                        "inline": True,
                    },
                    {
                        "name": "⏰ 修復時間",
                        "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "inline": True,
                    },
                    {
                        "name": "📁 修復文件",
                        "value": fix_data.get("file_path", "N/A"),
                        "inline": True,
                    },
                    {
                        "name": "🔍 根本原因",
                        "value": fix_data.get("root_cause", "N/A")[:100],
                        "inline": False,
                    },
                ],
            }
        ],
    }

    if heal_result and heal_result.get("attempted"):
        webhook_data["embeds"][0]["fields"].insert(
            0,
            {
                "name": "🩺 Agent 自癒",
                "value": heal_result.get("summary", "N/A")[:1000],
                "inline": False,
            },
        )

    try:
        import requests

        response = requests.post(discord_webhook, json=webhook_data)
        if response.status_code == 204:
            print("✅ Discord 通知發送成功")
        else:
            print(f"❌ Discord 通知發送失敗: {response.status_code}")
    except Exception as e:
        print(f"❌ 發送 Discord 通知失敗: {e}")


async def main():
    """主執行流程"""
    print("🚀 開始 AI 自動修復流程: 分析問題 -> debug -> push")

    # 獲取環境變數
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    discord_webhook = os.getenv("DISCORD_WEBHOOK")

    # 獲取觸發數據
    event_data_str = os.getenv("GITHUB_EVENT_DATA", "{}")
    event_data = json.loads(event_data_str)

    print(f"📊 事件數據: {event_data}")

    should_commit, commit_reason = should_allow_commit(event_data)
    print(f"🧾 提交判定: {commit_reason}")
    if not should_commit:
        return

    should_fix, reason = should_attempt_code_fix(event_data)
    print(f"🧭 自動修復判定: {reason}")
    if not should_fix:
        return

    # AI 分析和生成修復代碼
    fix_data = await analyze_and_fix(event_data, nvidia_api_key, discord_webhook)

    if fix_data:
        # 獲取錯誤信息
        payload = event_data.get("client_payload", {})
        timestamp = payload.get("timestamp", datetime.now().isoformat())
        severity = payload.get("severity", "medium")

        # 創建修復文件並提交
        # 優先使用 dispatch payload 的 target_file（traceback 抽出之真實路徑）
        target_file = payload.get("target_file", "") or event_data.get(
            "target_file", ""
        )
        success = await create_fix_file(
            fix_data, timestamp, severity, override_target_file=target_file
        )

        # 發送通知
        await send_discord_notification(fix_data, success, discord_webhook)
        if not success:
            raise SystemExit(1)
    else:
        print("❌ 無法生成修復代碼")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
