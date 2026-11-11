# -*- coding: utf-8 -*-
"""
批量刷新所有用戶置物櫃的 Cron 腳本（輕量觸發版）
排程設定：每週三固定時間執行
配置：0 3 * * 3 cd /home/e193752468/kkgroup && python3 scheduled_tasks/refresh_all_lockers_cron.py

流程：
  cron 腳本用 Bot Token 透過 REST API 將「靜音」觸發訊息貼進論壇頻道的
  固定同一篇觸發貼文（thread ID 存 .env 的 LOCKER_REFRESH_THREAD_ID，
  貼文被刪才自動重開一篇）；未設論壇頻道時退回系統/管理員等文字頻道
  → 線上 uibot 的 on_message 收到 → 執行 refresh_all_lockers()

優點：
  - 不開第二條 Discord gateway 連線，不會踢到線上常駐 uibot
  - 重活由已 warm 的 uibot 執行，沿用已驗證的更新邏輯
  - 腳本本身只發一個 HTTPS POST，最省 VM 資源
"""

import os
import sys
import logging
from pathlib import Path

# 添加路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

# 配置日誌
LOG_DIR = os.path.expanduser("~/kkgroup/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "locker_refresh.log")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
)
logger = logging.getLogger(__name__)

# 載入環境變數
from dotenv import load_dotenv

load_dotenv()

# Discord Message Flag: SUPPRESS_NOTIFICATIONS = 1 << 12 = 4096（靜音不推播通知）
SUPPRESS_NOTIFICATIONS = 4096

# 觸發訊息內容（必須與 uibot on_message 監聽的字串完全一致）
TRIGGER_CONTENT = "定時任務觸發：批量刷新置物櫃"

# 固定觸發貼文：論壇頻道內集中在同一篇 thread，thread ID 持久化到 .env
LOCKER_THREAD_ENV_KEY = "LOCKER_REFRESH_THREAD_ID"
LOCKER_THREAD_NAME = "批量刷新置物櫃"
ENV_FILE = Path(__file__).parent.parent / ".env"


def _load_saved_thread_id():
    """從 .env 重讀上次建立的觸發貼文 thread ID（讀檔而非 getenv，避免快取）"""
    try:
        from dotenv import dotenv_values

        val = dotenv_values(str(ENV_FILE)).get(LOCKER_THREAD_ENV_KEY)
        return int(val) if val else None
    except Exception:
        return None


def _save_thread_id(thread_id):
    """保存觸發貼文 thread ID 到 .env（與 status_dashboard / log_monitor 同一慣例）"""
    try:
        from dotenv import set_key

        set_key(str(ENV_FILE), LOCKER_THREAD_ENV_KEY, str(thread_id))
    except Exception as e:
        logger.error(f"保存觸發貼文 thread ID 失敗: {e}")


def trigger_locker_refresh() -> bool:
    """以 Bot Token 透過 REST API 發送靜音觸發貼文/訊息到論壇（或文字）頻道，由線上 uibot 接手執行更新。"""
    import requests

    bot_token = os.getenv("UI_DISCORD_BOT_TOKEN")
    if not bot_token:
        logger.error("❌ 缺少 UI_DISCORD_BOT_TOKEN")
        return False

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    # 優先發到論壇式頻道（集中在同一篇觸發貼文，不吵人）
    forum_id = os.getenv("DISCORD_FORUM_CHANNEL_ID")
    if forum_id:
        # 先試既有 thread：直接貼觸發訊息（進已歸檔貼文會自動重新開啟）
        saved_thread_id = _load_saved_thread_id()
        if saved_thread_id:
            url = f"https://discord.com/api/v10/channels/{saved_thread_id}/messages"
            payload = {
                "content": TRIGGER_CONTENT,
                "flags": SUPPRESS_NOTIFICATIONS,
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    logger.info(
                        f"✅ 靜音觸發訊息已貼進既有 thread (thread_id={saved_thread_id})，uibot 將接手執行置物櫃更新"
                    )
                    return True
                logger.warning(
                    f"⚠️ 既有 thread {saved_thread_id} 發送失敗：HTTP {response.status_code}，重開一篇觸發貼文..."
                )
            except Exception as e:
                logger.error(f"❌ 既有 thread 發送異常：{e}，重開一篇觸發貼文...")

        # 沒有既有 thread 或發送失敗：開新貼文並記住 ID，之後都貼同一篇
        url = f"https://discord.com/api/v10/channels/{forum_id}/threads"
        payload = {
            "name": LOCKER_THREAD_NAME,
            "message": {
                "content": TRIGGER_CONTENT,
                "flags": SUPPRESS_NOTIFICATIONS,
            },
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            # 建立 thread 成功回傳 201（偶有 200）
            if response.status_code in (200, 201):
                data = response.json()
                _save_thread_id(data.get("id"))
                logger.info(
                    f"✅ 靜音觸發貼文已建立於論壇頻道 (thread_id={data.get('id')})，之後每次觸發都貼同一篇，uibot 將接手執行置物櫃更新"
                )
                return True
            logger.warning(
                f"⚠️ 論壇頻道發送失敗：HTTP {response.status_code} - {response.text[:200]}，改用文字頻道候選..."
            )
        except Exception as e:
            logger.error(f"❌ 論壇頻道請求異常：{e}，改用文字頻道候選...")

    # Fallback：文字頻道候選（管理員 → 系統 → 歡迎 → 公告）
    # 皆為文字頻道，發送靜音訊息不跳通知
    candidate_env_keys = [
        "ADMIN_CHANNEL_ID",  # 🕴管理員 (文字頻道)
        "DISCORD_SYS_CHANNEL_ID",  # 原系統頻道 (可能無權限)
        "WELCOME_CHANNEL_ID",  # 🚪園區大門
        "ANNOUNCEMENT_CHANNEL_ID",  # 📢園區公告
        "STAFF_ID_CHANNEL_ID",  # 同 ADMIN_CHANNEL_ID
    ]

    for env_key in candidate_env_keys:
        channel_id = os.getenv(env_key)
        if not channel_id:
            continue
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        payload = {
            "content": TRIGGER_CONTENT,
            "flags": SUPPRESS_NOTIFICATIONS,
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"✅ 靜音觸發訊息已發送至 {env_key} (message_id={data.get('id')})，uibot 將接手執行置物櫃更新"
                )
                return True
            elif response.status_code == 404:
                logger.warning(
                    f"⚠️ {env_key} ({channel_id}) 該 token 無存取權 (404)，嘗試下一個頻道..."
                )
                continue
            elif response.status_code == 400:
                err = response.json()
                if err.get("code") == 50008:  # non-text channel
                    logger.warning(
                        f"⚠️ {env_key} ({channel_id}) 非文字頻道，嘗試下一個..."
                    )
                    continue
                logger.error(
                    f"❌ 發送觸發訊息失敗 ({env_key})：HTTP 400 - {err.get('message')}"
                )
            else:
                logger.error(
                    f"❌ 發送觸發訊息失敗 ({env_key})：HTTP {response.status_code} - {response.text[:200]}"
                )
        except Exception as e:
            logger.error(f"❌ 請求異常 ({env_key})：{e}")

    logger.error("❌ 所有候選頻道均發送失敗")
    return False


if __name__ == "__main__":
    logger.info("🚀 Cron 腳本開始執行（輕量觸發模式）")
    success = trigger_locker_refresh()
    exit_code = 0 if success else 1
    logger.info(f"✅ Cron 任務完成 (exit code: {exit_code})")
    sys.exit(exit_code)
