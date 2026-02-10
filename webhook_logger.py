"""
統一的啟動資訊發送器 - 使用 Webhook
機器人秘書頻道：1 個訊息 + 4 個 embeds
- 1 個總覽 embed（所有 bot 狀態）
- 3 個詳情 embed（bot、shopbot、uibot 各自的指令和擴展）
編輯原有訊息，無則新增

使用 Discord Webhook API，不依賴機器人客戶端直接發送
"""

import discord
import os
import aiohttp
from datetime import datetime
from dotenv import load_dotenv, set_key

load_dotenv()

# Webhook 配置
WEBHOOK_URL = os.getenv("STARTUP_WEBHOOK_URL", "")
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


async def create_overview_embed() -> dict:
    """創建狀態總覽 embed（字典格式用於 Webhook）"""
    status_text = ""
    for bot_name in ["bot", "shopbot", "uibot"]:
        info = bots_info[bot_name]
        emoji = "🟢" if info["狀態"] == "🟢 在線" else "🔴"
        time_text = info["啟動時間"] if info["啟動時間"] else "未啟動"
        status_text += f"{emoji} **{bot_name.upper()}** - {time_text}\n"
    
    return {
        "title": "🤖 所有機器人狀態",
        "description": status_text,
        "color": 3447003,  # blurple
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "機器人監控系統"}
    }


async def create_bot_detail_embed(bot_type: str) -> dict:
    """創建單個 bot 詳情 embed（字典格式用於 Webhook）"""
    bot_name_map = {
        "bot": "🤖 Main Bot",
        "shopbot": "🛍️ Shop Bot",
        "uibot": "🎨 UI Bot"
    }
    
    color_map = {
        "bot": 3447003,      # blue
        "shopbot": 9442302,  # purple
        "uibot": 16776960    # gold
    }
    
    info = bots_info[bot_type]
    
    fields = []
    
    # 擴展信息
    if info["擴展"]:
        ext_text = " | ".join(info["擴展"][:8])
        if len(info["擴展"]) > 8:
            ext_text += f"\n*...還有 {len(info['擴展']) - 8} 個*"
        fields.append({
            "name": f"📦 擴展 ({len(info['擴展'])})",
            "value": ext_text or "無",
            "inline": False
        })
    
    # 指令信息
    if info["指令"]:
        cmd_text = " | ".join(info["指令"][:10])
        if len(info["指令"]) > 10:
            cmd_text += f"\n*...還有 {len(info['指令']) - 10} 個*"
        fields.append({
            "name": f"⚡ Slash 指令 ({len(info['指令'])})",
            "value": cmd_text or "無",
            "inline": False
        })
    
    return {
        "title": f"{bot_name_map[bot_type]} 詳情",
        "color": color_map[bot_type],
        "fields": fields,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": f"狀態: {info['狀態']}"}
    }


async def send_or_update_startup_info():
    """
    使用 Webhook 發送或編輯啟動資訊訊息
    1 個訊息 + 4 個 embeds（概覽 + bot + shopbot + uibot）
    """
    global webhook_message_id
    
    if not WEBHOOK_URL:
        print(f"⚠️ 未配置 STARTUP_WEBHOOK_URL，跳過啟動日誌")
        return
    
    try:
        # 準備 4 個 embeds
        embeds = [
            await create_overview_embed(),
            await create_bot_detail_embed("bot"),
            await create_bot_detail_embed("shopbot"),
            await create_bot_detail_embed("uibot")
        ]
        
        payload = {"embeds": embeds}
        
        # 嘗試編輯已存在的訊息
        if webhook_message_id:
            # 嘗試編輯現有訊息
            url = f"{WEBHOOK_URL}/messages/{webhook_message_id}"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.patch(url, json=payload) as resp:
                        if resp.status == 200:
                            print(f"✅ 啟動資訊已更新 (訊息 ID: {webhook_message_id})")
                            return
                        else:
                            print(f"⚠️ 編輯訊息失敗 (狀態碼: {resp.status})，發送新訊息")
                            webhook_message_id = None
            except Exception as e:
                print(f"⚠️ 編輯訊息失敗: {e}，發送新訊息")
                webhook_message_id = None
        
        # 發送新訊息
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(WEBHOOK_URL, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        webhook_message_id = data.get("id")
                        
                        # 存儲到環境變數
                        set_key(".env", "WEBHOOK_MESSAGE_ID", str(webhook_message_id))
                        
                        print(f"✅ 啟動資訊已發送 (訊息 ID: {webhook_message_id})")
                    else:
                        print(f"⚠️ 發送訊息失敗 (狀態碼: {resp.status})")
                        error_text = await resp.text()
                        print(f"錯誤詳情: {error_text}")
        except Exception as e:
            print(f"⚠️ 發送啟動資訊失敗: {e}")


# 初始化時加載已存儲的 message_id
_stored_msg_id = os.getenv("WEBHOOK_MESSAGE_ID")
if _stored_msg_id:
    try:
        webhook_message_id = int(_stored_msg_id)
    except:
        pass
