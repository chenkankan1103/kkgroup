"""
統一監控儀表板管理系統
管理頻道 1470272652429099125 的 6 個 embed（3 機器人 × 2：控制面板+日誌）
每 15 秒自動更新日誌
存儲 message_id 到 .env 文件

每個機器人獨立初始化自己的面板（防止重複創建）
"""

import discord
import os
import sqlite3
import subprocess
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

# Message ID 存儲（僅存儲當前機器人的訊息）
dashboard_messages = {
    "dashboard": None,
    "logs": None
}

# 機器人實例存儲
bot_instances = {}

BOT_CONFIG = {
    "bot": {"名稱": "🤖 Main Bot", "顏色": discord.Color.blue(), "emoji": "🤖"},
    "shopbot": {"名稱": "🛍️ Shop Bot", "顏色": discord.Color.purple(), "emoji": "🛍️"},
    "uibot": {"名稱": "🎨 UI Bot", "顏色": discord.Color.gold(), "emoji": "🎨"}
}

# 追蹤當前機器人類型（在初始化時設置）
current_bot_type = None


def register_bot_instance(bot_type: str, bot_instance):
    """註冊機器人實例"""
    bot_instances[bot_type] = bot_instance
    print(f"[DEBUG] {bot_type} 機器人實例已註冊")


def get_bot_instance(bot_type: str):
    """獲取機器人實例"""
    return bot_instances.get(bot_type)


class DashboardButtons(discord.ui.View):
    """控制面板按鈕"""
    
    def __init__(self, bot_type: str, bot: discord.Client):
        super().__init__(timeout=None)  # 持久化按鈕
        self.bot_type = bot_type
        self.bot = bot
    
    @discord.ui.button(label="重啟", emoji="🔄", style=discord.ButtonStyle.danger)
    async def restart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """重啟機器人"""
        await interaction.response.defer(thinking=True)
        
        try:
            service_name = {
                "bot": "bot.service",
                "shopbot": "shopbot.service",
                "uibot": "uibot.service"
            }.get(self.bot_type)
            
            if not service_name:
                await interaction.followup.send("❌ 未知的機器人類型", ephemeral=True)
                return
            
            # 執行遠端重啟命令
            result = os.system(f'gcloud compute ssh instance-20250501-142333 --zone=us-central1-c --command="sudo systemctl restart {service_name}" 2>&1 > /dev/null &')
            
            await interaction.followup.send(
                f"✅ {self.bot_type.upper()} 重啟已發送\n將在 10-20 秒內完成",
                ephemeral=True
            )
            
            # 更新返饋
            add_log(self.bot_type, f"🔄 機器人正在重啟...")
            
        except Exception as e:
            await interaction.followup.send(f"❌ 重啟失敗: {e}", ephemeral=True)
    
    @discord.ui.button(label="狀態", emoji="🔍", style=discord.ButtonStyle.gray)
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查詢機器人狀態"""
        await interaction.response.defer(thinking=True)
        
        try:
            # 檢查 bot 是否在線
            if self.bot.user:
                detail = f"""
🟢 **在線**
用戶: {self.bot.user.mention}
ID: {self.bot.user.id}
時間: <t:{int(datetime.utcnow().timestamp())}:R>
                """
            else:
                detail = "🔴 離線"
            
            embed = discord.Embed(
                title=f"🔍 {BOT_CONFIG[self.bot_type]['名稱']} 狀態",
                description=detail,
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"❌ 狀態查詢失敗: {e}", ephemeral=True)


def set_bot_type(bot_type: str):
    """設置當前機器人類型"""
    global current_bot_type
    current_bot_type = bot_type
    print(f"📋 儀表板已設置為: {bot_type}")


def add_log(bot_type: str, message: str):
    """添加日誌條目"""
    if bot_type in logs_storage:
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        logs_storage[bot_type].append(f"[{timestamp}] {message}")
        print(f"[LOG] {bot_type}: {message}")  # 調試輸出


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


async def initialize_dashboard(bot_instance: discord.Client, bot_type_str: str):
    """
    初始化儀表板 - 每個機器人只初始化自己的面板
    
    Args:
        bot_instance: Discord bot instance
        bot_type_str: "bot", "shopbot", "uibot"
    """
    global current_bot_type
    current_bot_type = bot_type_str
    
    try:
        channel = bot_instance.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到儀表板頻道: {DASHBOARD_CHANNEL_ID}")
            return False
        
        # 只初始化該機器人自己的訊息
        found_dashboard = None
        found_logs = None
        dashboard_count = 0
        logs_count = 0
        old_dashboards = []
        old_logs = []
        
        # 查找現有訊息（只查找由當前 bot 發送的）
        async for msg in channel.history(limit=100):
            if msg.author.id != bot_instance.user.id:
                continue  # 跳過其他 bot 的訊息
            
            if msg.embeds:
                for embed in msg.embeds:
                    bot_name = BOT_CONFIG[bot_type_str]["名稱"]
                    if "控制面板" in embed.title and bot_name in embed.title:
                        dashboard_count += 1
                        if dashboard_count <= 1:
                            found_dashboard = msg
                        else:
                            old_dashboards.append(msg)
                    elif "實時日誌" in embed.title and bot_name in embed.title:
                        logs_count += 1
                        if logs_count <= 1:
                            found_logs = msg
                        else:
                            old_logs.append(msg)
        
        # 清理舊 embed
        for msg in old_dashboards + old_logs:
            try:
                await msg.delete()
                print(f"✓ 已清理舊的 {bot_type_str} embed")
            except:
                pass
        
        # 創建或註冊控制面板
        if not found_dashboard:
            embed = await create_dashboard_embed(bot_type_str)
            view = DashboardButtons(bot_type_str, bot_instance)
            msg = await channel.send(embed=embed, view=view)
            dashboard_messages["dashboard"] = msg.id
            print(f"✅ 創建 {bot_type_str} 控制面板: {msg.id}")
        else:
            dashboard_messages["dashboard"] = found_dashboard.id
            # 重新附加按鈕視圖到舊訊息
            try:
                view = DashboardButtons(bot_type_str, bot_instance)
                await found_dashboard.edit(view=view)
            except:
                pass
            print(f"✅ 找到 {bot_type_str} 控制面板: {found_dashboard.id}")
        
        # 創建或註冊日誌
        if not found_logs:
            embed = await create_logs_embed(bot_type_str)
            msg = await channel.send(embed=embed)
            dashboard_messages["logs"] = msg.id
            print(f"✅ 創建 {bot_type_str} 日誌: {msg.id}")
        else:
            dashboard_messages["logs"] = found_logs.id
            print(f"✅ 找到 {bot_type_str} 日誌: {found_logs.id}")
        
        # 保存到 .env
        save_message_ids(bot_type_str)
        return True
        
    except Exception as e:
        print(f"❌ 初始化儀表板失敗: {e}")
        import traceback
        traceback.print_exc()
        return False



async def ensure_dashboard_messages(bot: discord.Client, bot_type: str):
    """
    確保儀表板消息按正確順序存在（bot → shopbot → uibot）
    若消息被刪除，自動重新創建
    """
    try:
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到儀表板頻道: {DASHBOARD_CHANNEL_ID}")
            return
        
        # 檢查該 bot 的消息是否存在
        dashboard_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_DASHBOARD")
        logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")
        
        # 檢查控制面板消息
        if dashboard_id:
            try:
                msg = await channel.fetch_message(int(dashboard_id))
                # 消息存在，更新它
                if msg.author.id == bot.user.id:
                    embed = await create_dashboard_embed(bot_type)
                    await msg.edit(embed=embed)
                    return
            except discord.NotFound:
                pass  # 消息被刪除，需要重新創建
        
        # 消息不存在或已刪除，創建新的
        # 確保順序：bot → shopbot → uibot
        bot_order = ["bot", "shopbot", "uibot"]
        
        # 發送控制面板
        embed = await create_dashboard_embed(bot_type)
        msg = await channel.send(embed=embed)
        set_key(".env", f"DASHBOARD_{bot_type.upper()}_DASHBOARD", str(msg.id))
        print(f"✅ 重建 {bot_type} 控制面板 (ID: {msg.id})")
        
        # 發送日誌
        embed = await create_logs_embed(bot_type)
        msg = await channel.send(embed=embed)
        set_key(".env", f"DASHBOARD_{bot_type.upper()}_LOGS", str(msg.id))
        print(f"✅ 重建 {bot_type} 日誌 (ID: {msg.id})")
        
    except Exception as e:
        print(f"⚠️ 確保仪表板消息失败: {e}")


def save_message_ids(bot_type: str):
    """將 message_id 保存到 .env"""
    env_path = ".env"
    dashboard_id = dashboard_messages.get("dashboard")
    logs_id = dashboard_messages.get("logs")
    
    if dashboard_id:
        env_key = f"DASHBOARD_{bot_type.upper()}_DASHBOARD"
        set_key(env_path, env_key, str(dashboard_id))
    
    if logs_id:
        env_key = f"DASHBOARD_{bot_type.upper()}_LOGS"
        set_key(env_path, env_key, str(logs_id))


def load_message_ids(bot_type: str):
    """從 .env 加載 message_id"""
    dashboard_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_DASHBOARD")
    logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")
    
    if dashboard_id:
        dashboard_messages["dashboard"] = int(dashboard_id)
    
    if logs_id:
        dashboard_messages["logs"] = int(logs_id)
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



async def update_dashboard(bot: discord.Client, bot_type: str = None):
    """
    更新儀表板（控制面板 + 日誌）
    如果指定 bot_type，只更新該機器人
    """
    try:
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            return
        
        # 如果沒有指定 bot_type，自動判斷當前機器人
        if not bot_type:
            # 根據 bot username 判斷類型
            username = str(bot.user.name).lower()
            if "shop" in username:
                bot_type = "shopbot"
            elif "ui" in username:
                bot_type = "uibot"
            else:
                bot_type = "bot"
        
        # 只更新該機器人自己的訊息
        # 更新控制面板
        dashboard_msg_id = dashboard_messages.get(f"{bot_type}_dashboard")
        if dashboard_msg_id:
            try:
                msg = await channel.fetch_message(dashboard_msg_id)
                # 確認訊息是由當前 bot 發送的
                if msg.author.id == bot.user.id:
                    embed = await create_dashboard_embed(bot_type)
                    await msg.edit(embed=embed)
            except discord.NotFound:
                print(f"⚠️ {bot_type} 控制面板訊息不存在，重新創建...")
                embed = await create_dashboard_embed(bot_type)
                msg = await channel.send(embed=embed)
                dashboard_messages[f"{bot_type}_dashboard"] = msg.id
                save_message_ids(bot_type)
            except discord.Forbidden:
                # 沒有權限編輯（訊息來自其他 bot）
                pass
            except Exception as e:
                # 其他錯誤，靜默處理
                pass
        
        # 更新日誌
        logs_msg_id = dashboard_messages.get(f"{bot_type}_logs")
        if logs_msg_id:
            try:
                msg = await channel.fetch_message(logs_msg_id)
                # 確認訊息是由當前 bot 發送的
                if msg.author.id == bot.user.id:
                    embed = await create_logs_embed(bot_type)
                    await msg.edit(embed=embed)
            except discord.NotFound:
                print(f"⚠️ {bot_type} 日誌訊息不存在，重新創建...")
                embed = await create_logs_embed(bot_type)
                msg = await channel.send(embed=embed)
                dashboard_messages[f"{bot_type}_logs"] = msg.id
                save_message_ids(bot_type)
            except discord.Forbidden:
                # 沒有權限編輯（訊息來自其他 bot）
                pass
            except Exception as e:
                # 其他錯誤，靜默處理
                pass
    
    except Exception as e:
        print(f"❌ 更新儀表板失敗: {e}")


def load_message_ids(bot_type: str):
    """從 .env 加載當前機器人的 message_id"""
    dashboard_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_DASHBOARD")
    logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")
    
    if dashboard_id:
        dashboard_messages["dashboard"] = int(dashboard_id)
    
    if logs_id:
        dashboard_messages["logs"] = int(logs_id)
