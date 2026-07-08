# -*- coding: utf-8 -*-
"""
批量刷新所有用戶置物櫃的 Cron 腳本
排程設定：每週三固定時間執行
配置：0 3 * * 3 cd /home/e193752468/kkgroup && python3 scheduled_tasks/refresh_all_lockers_cron.py

直接調用核心置物櫃更新邏輯（不經由 Discord 訊息觸發）
"""

import asyncio
import os
import sys
import logging
import discord
from pathlib import Path
from datetime import datetime

# 添加路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

# 配置日誌
LOG_DIR = os.path.expanduser("~/kkgroup/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "locker_refresh.log")

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)

# 載入環境變數
from dotenv import load_dotenv
load_dotenv()


async def main():
    """建立臨時 Discord 客戶端，載入所需 Cog 並直接執行置物櫃更新"""
    bot_token = os.getenv('UI_DISCORD_BOT_TOKEN')
    if not bot_token:
        logger.error("❌ 缺少 UI_DISCORD_BOT_TOKEN 環境變數")
        return False

    # 必要的意圖：我們需要獲取頻道和使用者資訊
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    # 預先載入 Cog
    try:
        from cogs.ui.uibody import UserPanel
        from cogs.ui.admin_locker_commands import AdminLockerCommands
    except Exception as e:
        logger.exception(f"❌ 載入 Cog 失敗: {e}")
        return False

    # 將 Cog 加入 Bot（會在 bot 就緒時自動呼叫 cog_load）
    try:
        if 'UserPanel' not in bot.cogs:
            bot.add_cog(UserPanel(bot))
            logger.info("📦 已加載 UserPanel Cog")
        if 'AdminLockerCommands' not in bot.cogs:
            bot.add_cog(AdminLockerCommands(bot))
            logger.info("📦 已加載 AdminLockerCommands Cog")
    except Exception as e:
        logger.exception(f"❌ 加載 Cog 到 Bot 失敗: {e}")
        return False

    @bot.event
    async def on_ready():
        logger.info(f"✅ 已登入為 {bot.user} (ID: {bot.user.id})")
        # 等待所有 Cog 的 cog_load 完成（它們內部會 await bot.wait_until_ready()）
        await asyncio.sleep(1)  # 給予初始化時間

        # 取得 AdminLockerCommands 實例
        admin_cog = bot.get_cog('AdminLockerCommands')
        if admin_cog is None:
            logger.error("❌ 無法取得 AdminLockerCommands Cog 實例")
            await bot.close()
            return

        # 直接執行置物櫃更新核心邏輯
        try:
            logger.info("🔄 開始執行批量置物櫃更新...")
            success_count, fail_count, total = await admin_cog.refresh_all_lockers()
            success_rate = (success_count / total * 100) if total > 0 else 0
            logger.info(
                f"✅ 批量更新完成：{success_count}/{total} 成功 "
                f"({success_rate:.1f}% 成功率), {fail_count} 失敗"
            )
        except Exception as e:
            logger.exception(f"❌ 執行置物櫃更新時發生錯誤: {e}")
        finally:
            await bot.close()

    try:
        await bot.start(bot_token)
    except Exception as e:
        logger.exception(f"❌ 啟動 Discord 客戶端失敗: {e}")
        return False
    return True


if __name__ == '__main__':
    # 直接運行該腳本
    logger.info("🚀 Cron 腳本開始執行")
    success = asyncio.run(main())
    exit_code = 0 if success else 1
    logger.info(f"✅ Cron 任務完成 (exit code: {exit_code})")
    sys.exit(exit_code)