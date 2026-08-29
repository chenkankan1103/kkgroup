# -*- coding: utf-8 -*-
"""
批量刷新所有用戶置物櫃的 Cron 腳本（輕量觸發版）
排程設定：每週三固定時間執行
配置：0 3 * * 3 cd /home/e193752468/kkgroup && python3 scheduled_tasks/refresh_all_lockers_cron.py

流程：
  cron 腳本用 Bot Token 透過 REST API 發送一條「靜音」觸發訊息到系統頻道
  → 線上 uibot 的 on_message 收到 → 執行 refresh_all_lockers() → 30 分鐘後刪除觸發訊息

優點：
  - 不開第二條 Discord gateway 連線，不會踢到線上常駐 uibot
  - 重活由已 warm 的 uibot 執行，沿用已驗證的更新邏輯
  - 腳本本身只發一個 HTTPS POST，最省 VM 資源
"""

import logging
import os
import sys
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


def trigger_locker_refresh() -> bool:
    """以 Bot Token 透過 REST API 發送靜音觸發訊息到管理員/系統頻道，由線上 uibot 接手執行更新。"""
    import requests

    bot_token = os.getenv("UI_DISCORD_BOT_TOKEN")
    if not bot_token:
        logger.error("❌ 缺少 UI_DISCORD_BOT_TOKEN")
        return False

    # 優先順序：管理員頻道 → 系統頻道 → 歡迎頻道 → 公告頻道
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
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }
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
