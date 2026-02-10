"""
統一的啟動資訊 Webhook 發送器
所有三個機器人都使用此模塊統一格式發送啟動訊息
"""

import discord
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

STARTUP_WEBHOOK_CHANNEL_ID = int(os.getenv("STARTUP_WEBHOOK_CHANNEL_ID", "0"))
BOT_NAME_MAP = {
    "bot": "🤖 Main Bot",
    "shopbot": "🛍️ Shop Bot", 
    "uibot": "🎨 UI Bot"
}

async def send_startup_info(bot_type: str, bot: discord.Client):
    """
    發送統一格式的機器人啟動資訊到頻道（不使用 Webhook）
    
    Args:
        bot_type: "bot", "shopbot", "uibot"
        bot: Discord bot instance
    """
    try:
        if not STARTUP_WEBHOOK_CHANNEL_ID or STARTUP_WEBHOOK_CHANNEL_ID == 0:
            print(f"⚠️ 未配置 STARTUP_WEBHOOK_CHANNEL_ID，跳過啟動日誌")
            return
        
        channel = bot.get_channel(STARTUP_WEBHOOK_CHANNEL_ID)
        if not channel:
            print(f"⚠️ 找不到啟動日誌頻道 {STARTUP_WEBHOOK_CHANNEL_ID}")
            return
        
        # 建立 embed
        bot_name = BOT_NAME_MAP.get(bot_type, bot_type)
        embed = discord.Embed(
            title=f"{bot_name} 已啟動",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="🟢 狀態",
            value="在線 Online",
            inline=True
        )
        
        embed.add_field(
            name="⏰ 時間",
            value=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            inline=True
        )
        
        embed.add_field(
            name="🔧 配置",
            value="已檢查完成 ✅",
            inline=True
        )
        
        embed.set_footer(text=f"機器人類型: {bot_type.upper()}")
        
        # 直接發送到頻道
        await channel.send(embed=embed)
        
        print(f"✅ 啟動資訊已發送到頻道: {bot_name}")
        
    except Exception as e:
        print(f"⚠️ 發送啟動資訊失敗: {e}")
