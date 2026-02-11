#!/usr/bin/env python3
"""
檢查Discord消息ID是否在新頻道中有效
"""

import os
import sys
import discord
from dotenv import load_dotenv

# 添加當前目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Discord設定
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))
DASHBOARD_CHANNEL_ID = int(os.getenv("DASHBOARD_CHANNEL_ID", "1470272652429099125"))

# 硬編碼的消息ID
HARDCODED_MESSAGE_IDS = {
    "bot": {
        "dashboard": 1470781481071808614,
        "logs": 1470781481868591187
    },
    "shopbot": {
        "dashboard": 1470782649806098483,
        "logs": 1470782650716389648
    },
    "uibot": {
        "dashboard": 1470782658702344486,
        "logs": 1470782659843068032
    }
}

class TestClient(discord.Client):
    async def on_ready(self):
        print(f"✅ 已登入為 {self.user}")

        # 獲取頻道
        channel = self.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到頻道: {DASHBOARD_CHANNEL_ID}")
            await self.close()
            return

        print(f"✅ 找到頻道: {channel.name} ({channel.id})")

        # 檢查每個消息ID
        for bot_type, ids in HARDCODED_MESSAGE_IDS.items():
            for msg_type, msg_id in ids.items():
                try:
                    message = await channel.fetch_message(msg_id)
                    print(f"✅ {bot_type} {msg_type} 消息存在: {msg_id}")
                    print(f"   內容: {message.content[:50] if message.content else 'Embed消息'}")
                except discord.NotFound:
                    print(f"❌ {bot_type} {msg_type} 消息不存在: {msg_id}")
                except Exception as e:
                    print(f"⚠️ {bot_type} {msg_type} 檢查失敗: {e}")

        await self.close()

async def main():
    if not TOKEN:
        print("❌ 未找到 DISCORD_BOT_TOKEN")
        return

    client = TestClient(intents=discord.Intents.default())
    try:
        await client.start(TOKEN)
    except Exception as e:
        print(f"❌ 連接失敗: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())