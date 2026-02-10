"""
統一的啟動資訊發送器
機器人秘書頻道：1 個訊息 + 4 個 embeds
- 1 個總覽 embed（所有 bot 狀態）
- 3 個詳情 embed（bot、shopbot、uibot 各自的指令和擴展）
編輯原有訊息，無則新增
"""

import discord
import os
from datetime import datetime
from dotenv import load_dotenv, set_key

load_dotenv()

STARTUP_CHANNEL_ID = int(os.getenv("STARTUP_WEBHOOK_CHANNEL_ID", "0"))
BOT_LOGS_CHANNEL = int(os.getenv("DISCORD_SYS_CHANNEL_ID", "0"))  # 機器人秘書

# 存儲每個 bot 的資訊
bots_info = {
    "bot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []},
    "shopbot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []},
    "uibot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []}
}

# 存儲 webhook 訊息 ID
webhook_message_id = None


async def update_bot_info(bot_type: str, startup_time: str, commands: list, extensions: list):
    """更新機器人資訊"""
    if bot_type in bots_info:
        bots_info[bot_type]["啟動時間"] = startup_time
        bots_info[bot_type]["狀態"] = "🟢 在線"
        bots_info[bot_type]["指令"] = commands
        bots_info[bot_type]["擴展"] = extensions


async def create_overview_embed() -> discord.Embed:
    """創建狀態總覽 embed"""
    embed = discord.Embed(
        title="🤖 所有機器人狀態",
        color=discord.Color.blurple(),
        timestamp=datetime.utcnow()
    )
    
    status_text = ""
    for bot_name in ["bot", "shopbot", "uibot"]:
        info = bots_info[bot_name]
        emoji = "🟢" if info["狀態"] == "🟢 在線" else "🔴"
        time_text = info["啟動時間"] if info["啟動時間"] else "未啟動"
        status_text += f"{emoji} **{bot_name.upper()}** - {time_text}\n"
    
    embed.description = status_text
    embed.set_footer(text="機器人監控系統")
    return embed


async def create_bot_detail_embed(bot_type: str) -> discord.Embed:
    """創建單個 bot 詳情 embed"""
    bot_name_map = {
        "bot": "🤖 Main Bot",
        "shopbot": "🛍️ Shop Bot",
        "uibot": "🎨 UI Bot"
    }
    
    color_map = {
        "bot": discord.Color.blue(),
        "shopbot": discord.Color.purple(),
        "uibot": discord.Color.gold()
    }
    
    info = bots_info[bot_type]
    
    embed = discord.Embed(
        title=f"{bot_name_map[bot_type]} 詳情",
        color=color_map[bot_type],
        timestamp=datetime.utcnow()
    )
    
    # 擴展信息
    if info["擴展"]:
        ext_text = " | ".join(info["擴展"][:8])
        if len(info["擴展"]) > 8:
            ext_text += f"\n*...還有 {len(info['擴展']) - 8} 個*"
        embed.add_field(
            name=f"📦 擴展 ({len(info['擴展'])})",
            value=ext_text or "無",
            inline=False
        )
    
    # 指令信息
    if info["指令"]:
        cmd_text = " | ".join(info["指令"][:10])
        if len(info["指令"]) > 10:
            cmd_text += f"\n*...還有 {len(info['指令']) - 10} 個*"
        embed.add_field(
            name=f"⚡ Slash 指令 ({len(info['指令'])})",
            value=cmd_text or "無",
            inline=False
        )
    
    embed.set_footer(text=f"狀態: {info['狀態']}")
    return embed


async def send_or_update_startup_info(bot: discord.Client):
    """
    發送或編輯啟動資訊訊息
    1 個訊息 + 4 個 embeds（概覽 + bot + shopbot + uibot）
    """
    global webhook_message_id
    
    try:
        if not BOT_LOGS_CHANNEL or BOT_LOGS_CHANNEL == 0:
            print(f"⚠️ 未配置 DISCORD_SYS_CHANNEL_ID (機器人秘書)，跳過啟動日誌")
            return
        
        channel = bot.get_channel(BOT_LOGS_CHANNEL)
        if not channel:
            print(f"⚠️ 找不到機器人秘書頻道 {BOT_LOGS_CHANNEL}")
            return
        
        # 準備 4 個 embeds
        embeds = [
            await create_overview_embed(),
            await create_bot_detail_embed("bot"),
            await create_bot_detail_embed("shopbot"),
            await create_bot_detail_embed("uibot")
        ]
        
        # 嘗試編輯已存在的訊息
        if webhook_message_id:
            try:
                msg = await channel.fetch_message(webhook_message_id)
                await msg.edit(embeds=embeds)
                print(f"✅ 啟動資訊已更新 (訊息 ID: {webhook_message_id})")
                return
            except discord.NotFound:
                webhook_message_id = None
                print("⚠️ 原訊息已刪除，發送新訊息")
        
        # 發送新訊息
        msg = await channel.send(embeds=embeds)
        webhook_message_id = msg.id
        
        # 存儲到環境變數
        set_key(".env", "WEBHOOK_MESSAGE_ID", str(webhook_message_id))
        
        print(f"✅ 啟動資訊已發送 (訊息 ID: {webhook_message_id})")
        
    except Exception as e:
        print(f"⚠️ 發送啟動資訊失敗: {e}")


# 初始化時加載已存儲的 message_id
_stored_msg_id = os.getenv("WEBHOOK_MESSAGE_ID")
if _stored_msg_id:
    try:
        webhook_message_id = int(_stored_msg_id)
    except:
        pass
