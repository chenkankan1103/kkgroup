# -*- coding: utf-8 -*-
"""
批量刷新所有用戶置物櫃的 Cron 腳本
排程設定：每三天執行一次
配置：*/72 * * * * cd /home/e193752468/kkgroup && python3 scheduled_tasks/refresh_all_lockers_cron.py

使用 Discord bot 通過 webhook 觸發置物櫃批量刷新
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# 添加路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/kkgroup_locker_refresh.log')
    ]
)
logger = logging.getLogger(__name__)

from db_adapter import get_all_users

async def refresh_all_user_lockers_via_webhook():
    """
    通過 Discord webhook 觸發置物櫃批量刷新
    
    方案說明：
    1. 通過 webhook 向 Discord 頻道發送請求
    2. UIBot 接收到觸發信號
    3. 執行置物櫃批量刷新
    
    優勢：無需直接訪問 bot 實例，完全獨立
    """
    try:
        import requests
        import json
        
        all_users = get_all_users()
        total = len(all_users)
        
        logger.info("=" * 60)
        logger.info("🔄 【定時任務】開始批量刷新置物櫃")
        logger.info(f"📊 總用戶數：{total}")
        logger.info(f"⏱️ 執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        # 取得 webhook URL
        webhook_url = os.getenv('ADMIN_WEBHOOK_URL')
        if not webhook_url:
            logger.error("❌ 未設定 ADMIN_WEBHOOK_URL 環境變量")
            logger.info("💡 提示：需要在 .env 中設定 ADMIN_WEBHOOK_URL")
            return False
        
        # 構建 webhook 訊息
        embed_data = {
            "title": "🔄 定時置物櫃批量刷新已觸發",
            "description": f"系統每三天自動執行一次置物櫃批量刷新\n\n📊 待刷新用戶數：**{total}**",
            "color": 0xFFA500,
            "footer": {
                "text": "系統排程任務"
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        payload = {
            "content": "定時任務觸發：批量刷新置物櫃",
            "embeds": [embed_data]
        }
        
        # 發送 webhook
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 204:
            logger.info("✅ Webhook 已發送，置物櫃批量刷新已觸發")
            logger.info("=" * 60)
            return True
        else:
            logger.error(f"❌ Webhook 發送失敗：HTTP {response.status_code}")
            logger.error(f"   Response：{response.text[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 刷新失敗：{e}", exc_info=True)
        return False

if __name__ == '__main__':
    # 直接運行該腳本
    success = asyncio.run(refresh_all_user_lockers_via_webhook())
    exit_code = 0 if success else 1
    logger.info(f"✅ Cron 任務完成 (exit code: {exit_code})")
    sys.exit(exit_code)
