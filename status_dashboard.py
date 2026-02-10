"""
統一監控儀表板管理系統
管理頻道 1470272652429099125 的 6 個 embed（3 機器人 × 2：控制面板+日誌）
每 15 秒自動更新日誌
存儲 message_id 到 .env 文件
"""

import discord
import os
import sqlite3
from datetime import datetime
from collections import deque
from typing import Optional, Dict
from dotenv import load_dotenv, set_key

load_dotenv()

DASHBOARD_CHANNEL_ID = int(os.getenv("DASHBOARD_CHANNEL_ID", "1470272652429099125"))
LOGS_CAPACITY = 10  # 保存最近 10 條日誌

# 日誌收集容器（每個機器人獨立）
logs_storage = {
    "bot": deque(maxlen=LOGS_CAPACITY),
    "shopbot": deque(maxlen=LOGS_CAPACITY),
    "uibot": deque(maxlen=LOGS_CAPACITY)
}

# Message ID 存儲
dashboard_messages = {
    "bot_dashboard": None,
    "bot_logs": None,
    "shopbot_dashboard": None,
    "shopbot_logs": None,
    "uibot_dashboard": None,
    "uibot_logs": None
}

BOT_CONFIG = {
    "bot": {"名稱": "🤖 Main Bot", "顏色": discord.Color.blue(), "emoji": "🤖"},
    "shopbot": {"名稱": "🛍️ Shop Bot", "顏色": discord.Color.purple(), "emoji": "🛍️"},
    "uibot": {"名稱": "🎨 UI Bot", "顏色": discord.Color.gold(), "emoji": "🎨"}
}


def add_log(bot_type: str, message: str):
    """添加日誌條目"""
    if bot_type in logs_storage:
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        logs_storage[bot_type].append(f"[{timestamp}] {message}")


def get_logs_text(bot_type: str) -> str:
    """獲取格式化的日誌文本"""
    if bot_type not in logs_storage:
        return "無日誌"
    
    logs = list(logs_storage[bot_type])
    if not logs:
        return "無日誌"
    
    return "\n".join(logs[::-1])  # 倒序顯示（最新在最上面）


async def create_dashboard_embed(bot_type: str) -> discord.Embed:
    """創建控制面板 Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 控制面板",
        color=config['顏色'],
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="🔴 主進程",
        value="🟢 在線",
        inline=True
    )
    
    embed.add_field(
        name="📊 任務",
        value="✅ 2/2 運行中",
        inline=True
    )
    
    embed.add_field(
        name="💾 數據庫",
        value="✅ 連接正常",
        inline=True
    )
    
    embed.set_footer(text=f"上次更新: {datetime.utcnow().strftime('%H:%M:%S UTC')}")
    return embed


async def create_logs_embed(bot_type: str) -> discord.Embed:
    """創建日誌 Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 實時日誌",
        color=config['顏色'],
        timestamp=datetime.utcnow()
    )
    
    logs_text = get_logs_text(bot_type)
    embed.description = f"```\n{logs_text}\n```"
    
    embed.set_footer(text=f"更新頻率: 15秒 | {datetime.utcnow().strftime('%H:%M:%S UTC')}")
    return embed


async def initialize_dashboard(bot: discord.Client):
    """
    初始化儀表板
    查找或創建 6 個 embed 訊息
    """
    try:
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到儀表板頻道: {DASHBOARD_CHANNEL_ID}")
            return False
        
        # 查找或創建訊息
        for bot_type in ["bot", "shopbot", "uibot"]:
            # 查找現有訊息
            found_dashboard = None
            found_logs = None
            
            async for msg in channel.history(limit=100):
                if msg.embeds:
                    for embed in msg.embeds:
                        bot_name = BOT_CONFIG[bot_type]["名稱"]
                        if "控制面板" in embed.title and bot_name in embed.title:
                            found_dashboard = msg
                        elif "實時日誌" in embed.title and bot_name in embed.title:
                            found_logs = msg
            
            # 創建控制面板embed
            if not found_dashboard:
                embed = await create_dashboard_embed(bot_type)
                msg = await channel.send(embed=embed)
                dashboard_messages[f"{bot_type}_dashboard"] = msg.id
                print(f"✅ 創建 {bot_type} 控制面板: {msg.id}")
            else:
                dashboard_messages[f"{bot_type}_dashboard"] = found_dashboard.id
                print(f"✅ 找到 {bot_type} 控制面板: {found_dashboard.id}")
            
            # 創建日誌embed
            if not found_logs:
                embed = await create_logs_embed(bot_type)
                msg = await channel.send(embed=embed)
                dashboard_messages[f"{bot_type}_logs"] = msg.id
                print(f"✅ 創建 {bot_type} 日誌: {msg.id}")
            else:
                dashboard_messages[f"{bot_type}_logs"] = found_logs.id
                print(f"✅ 找到 {bot_type} 日誌: {found_logs.id}")
        
        # 保存到 .env
        save_message_ids()
        return True
        
    except Exception as e:
        print(f"❌ 初始化儀表板失敗: {e}")
        return False


async def update_dashboard(bot: discord.Client, bot_type: str = None):
    """
    更新儀表板（控制面板 + 日誌）
    如果指定 bot_type，只更新該機器人
    """
    try:
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            return
        
        # 確定要更新的機器人
        bot_types = [bot_type] if bot_type else ["bot", "shopbot", "uibot"]
        
        for btype in bot_types:
            # 更新控制面板
            dashboard_msg_id = dashboard_messages.get(f"{btype}_dashboard")
            if dashboard_msg_id:
                try:
                    msg = await channel.fetch_message(dashboard_msg_id)
                    embed = await create_dashboard_embed(btype)
                    await msg.edit(embed=embed)
                except discord.NotFound:
                    print(f"⚠️ {btype} 控制面板訊息不存在，重新創建...")
                    embed = await create_dashboard_embed(btype)
                    msg = await channel.send(embed=embed)
                    dashboard_messages[f"{btype}_dashboard"] = msg.id
                    save_message_ids()
            
            # 更新日誌
            logs_msg_id = dashboard_messages.get(f"{btype}_logs")
            if logs_msg_id:
                try:
                    msg = await channel.fetch_message(logs_msg_id)
                    embed = await create_logs_embed(btype)
                    await msg.edit(embed=embed)
                except discord.NotFound:
                    print(f"⚠️ {btype} 日誌訊息不存在，重新創建...")
                    embed = await create_logs_embed(btype)
                    msg = await channel.send(embed=embed)
                    dashboard_messages[f"{btype}_logs"] = msg.id
                    save_message_ids()
    
    except Exception as e:
        print(f"❌ 更新儀表板失敗: {e}")


def save_message_ids():
    """將 message_id 保存到 .env"""
    env_path = ".env"
    for key, msg_id in dashboard_messages.items():
        if msg_id:
            env_key = f"DASHBOARD_{key.upper()}"
            set_key(env_path, env_key, str(msg_id))
    print("✅ Message ID 已保存到 .env")


def load_message_ids():
    """從 .env 加載 message_id"""
    for key in dashboard_messages.keys():
        env_key = f"DASHBOARD_{key.upper()}"
        msg_id = os.getenv(env_key)
        if msg_id:
            dashboard_messages[key] = int(msg_id)
    print("✅ Message ID 已從 .env 加載")


# 初始化時加載
load_message_ids()
