"""
統一的啟動資訊發送器
只在啟動資訊頻道發送當前機器人的啟動訊息（不使用webhook）
"""

import discord
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

STARTUP_CHANNEL_ID = int(os.getenv("STARTUP_WEBHOOK_CHANNEL_ID", "0"))
BOT_NAME_MAP = {
    "bot": "🤖 Main Bot",
    "shopbot": "🛍️ Shop Bot", 
    "uibot": "🎨 UI Bot"
}

# 追蹤已發送的啟動訊息 ID（防止重複）
startup_messages = {
    "bot": None,
    "shopbot": None,
    "uibot": None
}


async def send_startup_info(bot_type: str, bot: discord.Client):
    """
    發送當前機器人的啟動資訊到指定頻道
    
    Args:
        bot_type: "bot", "shopbot", "uibot"
        bot: Discord bot instance
    """
    try:
        if not STARTUP_CHANNEL_ID or STARTUP_CHANNEL_ID == 0:
            print(f"⚠️ 未配置 STARTUP_WEBHOOK_CHANNEL_ID，跳過啟動日誌")
            return
        
        channel = bot.get_channel(STARTUP_CHANNEL_ID)
        if not channel:
            print(f"⚠️ 找不到啟動日誌頻道 {STARTUP_CHANNEL_ID}")
            return
        
        # 檢查是否已發送過啟動訊息
        if startup_messages.get(bot_type):
            # 已發送過，嘗試編輯而不是重新發送
            try:
                msg = await channel.fetch_message(startup_messages[bot_type])
                bot_name = BOT_NAME_MAP.get(bot_type, bot_type)
                embed = discord.Embed(
                    title=f"{bot_name} 已啟動 🔄",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="🟢 狀態", value="在線 Online", inline=True)
                embed.add_field(name="⏰ 時間", value=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), inline=True)
                embed.add_field(name="🔧 配置", value="已檢查完成 ✅", inline=True)
                embed.set_footer(text=f"機器人類型: {bot_type.upper()} | 版本: 1.0.0")
                await msg.edit(embed=embed)
                print(f"✅ 啟動資訊已更新: {bot_name}")
                return
            except:
                # 訊息已失效，發送新訊息
                startup_messages[bot_type] = None
        
        # 新發送啟動訊息
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
        
        embed.set_footer(text=f"機器人類型: {bot_type.upper()} | 版本: 1.0.0")
        
        # 直接發送到頻道
        msg = await channel.send(embed=embed)
        startup_messages[bot_type] = msg.id
        
        print(f"✅ 啟動資訊已發送: {bot_name}")
        
    except Exception as e:
        print(f"⚠️ 發送啟動資訊失敗: {e}")
