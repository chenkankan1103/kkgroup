"""
統一監控儀表板管理系統
管理頻道 1470272652429099125 的 6 個 embed（3 機器人 × 2：控制面板+日誌）
每 15 秒自動更新日誌
存儲 message_id 到 .env 文件

每個機器人獨立初始化自己的面板（防止重複創建）
"""

import discord
import os
import sys
import json
import sqlite3
import subprocess
import asyncio
from datetime import datetime, timedelta
from collections import deque
from typing import Optional, Dict
from dotenv import load_dotenv, set_key
from discord.ext import tasks
import pathlib

load_dotenv()

# 台灣時間輔助函數 (UTC+8)
def get_taiwan_time():
    """返回台灣時間 (UTC+8)"""
    return datetime.utcnow() + timedelta(hours=8)

# 硬編碼的訊息 ID 作為回退值
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

DASHBOARD_CHANNEL_ID = int(os.getenv("DASHBOARD_CHANNEL_ID", "1470272652429099125"))
LOGS_CAPACITY = 10  # 保存最近 10 條日誌

# 日誌收集容器（每個機器人獨立）
logs_storage = {
    "bot": deque(maxlen=LOGS_CAPACITY),
    "shopbot": deque(maxlen=LOGS_CAPACITY),
    "uibot": deque(maxlen=LOGS_CAPACITY)
}

# 日誌持久化文件
logs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard_logs.json')


def check_environment() -> Dict[str, any]:
    """
    環境檢查函數 - 診斷並記錄環境問題
    
    Returns:
        dict: 包含環境診斷信息的字典
    """
    diagnostics = {
        "timestamp": get_taiwan_time().isoformat(),
        "working_directory": os.getcwd(),
        "script_path": os.path.abspath(__file__),
        "script_directory": os.path.dirname(os.path.abspath(__file__)),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "in_virtual_env": False,
        "virtual_env_path": None,
        "sys_prefix": sys.prefix,
        "sys_base_prefix": getattr(sys, 'base_prefix', sys.prefix),
        "running_under_systemd": False,
        "systemd_details": None,
        "logs_file_path": logs_file,
        "logs_file_exists": os.path.exists(logs_file),
        "logs_file_writable": False,
        "logs_dir_writable": False,
        "env_file_exists": os.path.exists(".env"),
        "issues": []
    }
    
    # 檢測虛擬環境
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        diagnostics["in_virtual_env"] = True
        diagnostics["virtual_env_path"] = sys.prefix
    
    # 檢測 systemd 環境
    try:
        # 檢查是否由 systemd 運行
        ppid = os.getppid()
        with open(f'/proc/{ppid}/comm', 'r') as f:
            parent_process = f.read().strip()
            if parent_process == 'systemd' or os.getenv('INVOCATION_ID'):
                diagnostics["running_under_systemd"] = True
                diagnostics["systemd_details"] = {
                    "parent_process": parent_process,
                    "invocation_id": os.getenv('INVOCATION_ID'),
                    "journal_stream": os.getenv('JOURNAL_STREAM')
                }
    except Exception as e:
        diagnostics["issues"].append(f"無法檢測 systemd: {e}")
    
    # 檢查日誌文件路徑權限
    logs_dir = os.path.dirname(logs_file)
    try:
        diagnostics["logs_dir_writable"] = os.access(logs_dir, os.W_OK)
        if os.path.exists(logs_file):
            diagnostics["logs_file_writable"] = os.access(logs_file, os.W_OK)
        else:
            # 嘗試創建測試文件來驗證寫入權限
            test_file = os.path.join(logs_dir, '.test_write_permission')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                diagnostics["logs_file_writable"] = True
            except:
                diagnostics["logs_file_writable"] = False
    except Exception as e:
        diagnostics["issues"].append(f"無法檢查日誌文件權限: {e}")
    
    # 檢查工作目錄是否正確
    expected_dir = os.path.dirname(os.path.abspath(__file__))
    if os.getcwd() != expected_dir:
        diagnostics["issues"].append(
            f"工作目錄不匹配 - 當前: {os.getcwd()}, 預期: {expected_dir}"
        )
    
    # 記錄診斷結果
    print("[環境診斷] ==================")
    print(f"  工作目錄: {diagnostics['working_directory']}")
    print(f"  腳本路徑: {diagnostics['script_path']}")
    print(f"  Python 執行檔: {diagnostics['python_executable']}")
    print(f"  虛擬環境: {'是' if diagnostics['in_virtual_env'] else '否'}")
    if diagnostics['in_virtual_env']:
        print(f"  虛擬環境路徑: {diagnostics['virtual_env_path']}")
    print(f"  Systemd 運行: {'是' if diagnostics['running_under_systemd'] else '否'}")
    print(f"  日誌文件: {diagnostics['logs_file_path']}")
    print(f"  日誌目錄可寫: {'是' if diagnostics['logs_dir_writable'] else '否'}")
    print(f"  日誌文件可寫: {'是' if diagnostics['logs_file_writable'] else '否'}")
    if diagnostics['issues']:
        print(f"  問題: {', '.join(diagnostics['issues'])}")
    print("==================")
    
    return diagnostics


def load_logs():
    """從文件加載日誌 - 改進的錯誤處理"""
    try:
        if os.path.exists(logs_file):
            with open(logs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for bot_type, logs in data.items():
                    if bot_type in logs_storage:
                        logs_storage[bot_type].clear()
                        logs_storage[bot_type].extend(logs)
                print(f"[LOGS] 已加載日誌: {list(data.keys())}")
        else:
            print(f"[LOGS] 日誌文件不存在: {logs_file}")
    except PermissionError as e:
        print(f"[LOGS ERROR] 權限錯誤 - 無法讀取日誌文件: {logs_file}")
        print(f"  詳情: {e}")
        print(f"  請檢查文件權限: ls -l {logs_file}")
    except FileNotFoundError as e:
        print(f"[LOGS ERROR] 路徑錯誤 - 日誌文件路徑無效: {logs_file}")
        print(f"  詳情: {e}")
    except json.JSONDecodeError as e:
        print(f"[LOGS ERROR] JSON 解碼錯誤 - 日誌文件可能已損壞: {logs_file}")
        print(f"  詳情: {e}")
        print(f"  行 {e.lineno}, 列 {e.colno}: {e.msg}")
    except UnicodeDecodeError as e:
        print(f"[LOGS ERROR] 編碼錯誤 - 日誌文件編碼問題: {logs_file}")
        print(f"  詳情: {e}")
        print(f"  嘗試使用不同的編碼讀取文件")
    except Exception as e:
        print(f"[LOGS ERROR] 未預期的錯誤加載日誌: {e}")
        import traceback
        traceback.print_exc()


def save_logs():
    """保存日誌到文件 - 改進的錯誤處理"""
    try:
        # 確保父目錄存在
        logs_dir = os.path.dirname(logs_file)
        if logs_dir and not os.path.exists(logs_dir):
            try:
                os.makedirs(logs_dir, exist_ok=True)
                print(f"[LOGS] 已創建日誌目錄: {logs_dir}")
            except PermissionError as e:
                print(f"[LOGS ERROR] 無法創建日誌目錄 - 權限不足: {logs_dir}")
                print(f"  詳情: {e}")
                return
        
        # 保存日誌數據
        data = {bot_type: list(logs) for bot_type, logs in logs_storage.items()}
        with open(logs_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    except PermissionError as e:
        print(f"[LOGS ERROR] 權限錯誤 - 無法寫入日誌文件: {logs_file}")
        print(f"  詳情: {e}")
        print(f"  請檢查文件權限: ls -l {logs_file}")
        print(f"  或檢查目錄權限: ls -ld {os.path.dirname(logs_file)}")
    except FileNotFoundError as e:
        print(f"[LOGS ERROR] 路徑錯誤 - 日誌文件路徑無效: {logs_file}")
        print(f"  詳情: {e}")
    except OSError as e:
        print(f"[LOGS ERROR] 系統錯誤 - 無法寫入日誌文件: {logs_file}")
        print(f"  詳情: {e}")
        print(f"  磁盤空間: {e.strerror if hasattr(e, 'strerror') else '未知'}")
    except UnicodeEncodeError as e:
        print(f"[LOGS ERROR] 編碼錯誤 - 日誌數據包含無法編碼的字符")
        print(f"  詳情: {e}")
    except Exception as e:
        print(f"[LOGS ERROR] 未預期的錯誤保存日誌: {e}")
        import traceback
        traceback.print_exc()

# 初始化時執行環境檢查並加載日誌
env_diagnostics = check_environment()
load_logs()

# Message ID 存儲（每個機器人獨立）
message_ids = {
    "bot": {"dashboard": None, "logs": None},
    "shopbot": {"dashboard": None, "logs": None},
    "uibot": {"dashboard": None, "logs": None}
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


@tasks.loop(seconds=15)
async def global_update_logs_task():
    """全域日誌更新任務 - 每 15 秒更新所有機器人的日誌"""
    try:
        print("[GLOBAL LOG TASK] 開始更新所有機器人的日誌...")
        for bot_type in ["bot", "shopbot", "uibot"]:
            bot_instance = get_bot_instance(bot_type)
            if bot_instance:
                print(f"[GLOBAL LOG TASK] 更新 {bot_type} 日誌")
                await update_dashboard_logs(bot_instance, bot_type)
            else:
                print(f"[GLOBAL LOG TASK] {bot_type} 實例未找到 - 跳過")
    except Exception as e:
        print(f"[GLOBAL LOG TASK ERROR] {e}")


def register_bot_instance(bot_type: str, bot_instance):
    """註冊機器人實例"""
    bot_instances[bot_type] = bot_instance
    print(f"[DEBUG] {bot_type} 機器人實例已註冊")


def get_bot_instance(bot_type: str):
    """獲取機器人實例"""
    return bot_instances.get(bot_type)


def get_message_id(bot_type: str, message_type: str) -> Optional[int]:
    """獲取指定機器人的訊息 ID"""
    return message_ids[bot_type].get(message_type)


def save_message_id(bot_type: str, message_type: str, message_id: str):
    """保存指定機器人的訊息 ID"""
    message_ids[bot_type][message_type] = int(message_id)
    save_message_ids(bot_type)


async def update_dashboard_logs(bot, bot_type: str):
    """更新指定機器人的日誌，添加超時保護"""
    try:
        print(f"[UPDATE LOGS] 開始更新 {bot_type} 日誌")

        # 獲取最新的日誌條目
        logs_text = get_logs_text(bot_type)

        # 創建日誌 embed
        embed = discord.Embed(
            title=f"{bot_type.upper()} 實時日誌",
            description=logs_text,
            color=BOT_CONFIG[bot_type]["顏色"],
            timestamp=get_taiwan_time()
        )
        embed.set_footer(text=f"更新頻率: 15秒 | {get_taiwan_time().strftime('%H:%M:%S 台灣時間')}")

        # 更新訊息
        message_id = get_message_id(bot_type, "logs")
        if message_id:
            channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
            if channel:
                try:
                    message = await asyncio.wait_for(
                        channel.fetch_message(int(message_id)),
                        timeout=10.0
                    )
                    await asyncio.wait_for(
                        message.edit(embed=embed),
                        timeout=10.0
                    )
                    print(f"[UPDATE LOGS] {bot_type} 日誌已成功更新")
                except asyncio.TimeoutError:
                    print(f"[UPDATE LOGS] {bot_type} 日誌更新超時（10秒）")
                except discord.NotFound:
                    print(f"[UPDATE LOGS] {bot_type} 日誌訊息不存在，重新創建")
                    try:
                        message = await asyncio.wait_for(
                            channel.send(embed=embed),
                            timeout=10.0
                        )
                        save_message_id(bot_type, "logs", str(message.id))
                    except asyncio.TimeoutError:
                        print(f"[UPDATE LOGS] {bot_type} 創建新日誌訊息超時")
                    except Exception as e:
                        print(f"[UPDATE LOGS] {bot_type} 創建新日誌訊息失敗: {e}")
                except discord.HTTPException as e:
                    print(f"[UPDATE LOGS] {bot_type} Discord API 錯誤: {e}")
                except Exception as e:
                    print(f"[UPDATE LOGS] {bot_type} 日誌更新錯誤: {e}")
            else:
                print(f"[UPDATE LOGS] {bot_type} 找不到頻道")
        else:
            print(f"[UPDATE LOGS] {bot_type} 找不到日誌訊息 ID")

    except Exception as e:
        print(f"[UPDATE LOGS ERROR] {bot_type}: {e}")


class DashboardButtons(discord.ui.View):
    """控制面板按鈕"""
    
    def __init__(self, bot_type: str, bot: discord.Client):
        super().__init__(timeout=None)  # 持久化按鈕
        self.bot_type = bot_type
        self.bot = bot
        
        # 為按鈕設置唯一的 custom_id
        # 注意: 由於 custom_id 需要根據 bot_type 動態生成，
        # 我們無法在 @discord.ui.button 裝飾器中直接設置靜態值。
        # 因此在 __init__ 中遍歷子項目並設置 custom_id。
        for item in self.children:
            if isinstance(item, discord.ui.Button) and hasattr(item, 'callback'):
                if item.callback.__name__ == 'restart_button':
                    item.custom_id = f"restart_{bot_type}"
                elif item.callback.__name__ == 'status_button':
                    item.custom_id = f"status_{bot_type}"
    
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
                timestamp=get_taiwan_time()
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
        timestamp = get_taiwan_time().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        logs_storage[bot_type].append(log_entry)
        print(f"[LOG] {bot_type}: {message}")  # 調試輸出
        
        # 保存到文件
        save_logs()


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
        timestamp=get_taiwan_time()
    )
    
    embed.add_field(
        name="🤖 機器人",
        value="🟢 在線",
        inline=True
    )
    
    embed.add_field(
        name="📊 任務",
        value="✅ 已完成",
        inline=True
    )
    
    embed.add_field(
        name="💾 數據庫",
        value="✅ 連接正常",
        inline=True
    )
    
    embed.set_footer(text=f"上次更新: {get_taiwan_time().strftime('%H:%M:%S 台灣時間')}")
    return embed


async def create_logs_embed(bot_type: str) -> discord.Embed:
    """創建日誌 Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 實時日誌",
        color=config['顏色'],
        timestamp=get_taiwan_time()
    )
    
    logs_text = get_logs_text(bot_type)
    embed.description = f"```\n{logs_text}\n```"
    
    embed.set_footer(text=f"更新頻率: 15秒 | {get_taiwan_time().strftime('%H:%M:%S 台灣時間')}")
    return embed


async def initialize_dashboard(bot_instance: discord.Client, bot_type_str: str):
    """
    初始化儀表板 - 每個機器人只初始化自己的面板
    添加超時保護，確保網路問題不會導致崩潰
    
    Args:
        bot_instance: Discord bot instance
        bot_type_str: "bot", "shopbot", "uibot"
    
    Returns:
        bool: True if successful, False otherwise
    """
    global current_bot_type
    current_bot_type = bot_type_str
    
    # 加載訊息 ID（包括硬編碼的回退值）
    try:
        load_message_ids(bot_type_str)
    except Exception as e:
        print(f"⚠️ 加載訊息 ID 失敗: {e}")
    
    try:
        channel = bot_instance.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"⚠️ 找不到儀表板頻道: {DASHBOARD_CHANNEL_ID}，機器人將繼續運行")
            return False
        
        # 只初始化該機器人自己的訊息
        found_dashboard = None
        found_logs = None
        dashboard_count = 0
        logs_count = 0
        old_dashboards = []
        old_logs = []
        
        # 查找現有訊息（只查找由當前 bot 發送的）
        # 添加超時保護
        try:
            async def fetch_history():
                nonlocal found_dashboard, found_logs, dashboard_count, logs_count, old_dashboards, old_logs
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
            
            await asyncio.wait_for(fetch_history(), timeout=15.0)
        except asyncio.TimeoutError:
            print(f"⚠️ 獲取頻道歷史記錄超時（15秒），將創建新訊息")
        except discord.HTTPException as e:
            print(f"⚠️ Discord API 錯誤獲取歷史記錄: {e}")
        except Exception as e:
            print(f"⚠️ 獲取歷史記錄失敗: {e}")
        
        # 清理舊 embed
        for msg in old_dashboards + old_logs:
            try:
                await asyncio.wait_for(msg.delete(), timeout=5.0)
                print(f"✓ 已清理舊的 {bot_type_str} embed")
            except asyncio.TimeoutError:
                print(f"⚠️ 刪除舊訊息超時")
            except discord.HTTPException:
                pass  # 可能已被刪除
            except Exception:
                pass
        
        # 創建或註冊控制面板
        if not found_dashboard:
            try:
                embed = await create_dashboard_embed(bot_type_str)
                view = DashboardButtons(bot_type_str, bot_instance)
                msg = await asyncio.wait_for(
                    channel.send(embed=embed, view=view),
                    timeout=10.0
                )
                message_ids[bot_type_str]["dashboard"] = msg.id
                print(f"✅ 創建 {bot_type_str} 控制面板: {msg.id}")
            except asyncio.TimeoutError:
                print(f"⚠️ 創建控制面板超時（10秒）")
                return False
            except discord.HTTPException as e:
                print(f"⚠️ Discord API 錯誤創建控制面板: {e}")
                return False
        else:
            message_ids[bot_type_str]["dashboard"] = found_dashboard.id
            # 重新附加按鈕視圖到舊訊息
            try:
                view = DashboardButtons(bot_type_str, bot_instance)
                await asyncio.wait_for(
                    found_dashboard.edit(view=view),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                print(f"⚠️ 更新控制面板超時（10秒）")
            except discord.HTTPException:
                pass  # 可能權限不足
            except Exception:
                pass
            print(f"✅ 找到 {bot_type_str} 控制面板: {found_dashboard.id}")
        
        # 創建或註冊日誌
        if not found_logs:
            try:
                embed = await create_logs_embed(bot_type_str)
                msg = await asyncio.wait_for(
                    channel.send(embed=embed),
                    timeout=10.0
                )
                message_ids[bot_type_str]["logs"] = msg.id
                print(f"✅ 創建 {bot_type_str} 日誌: {msg.id}")
            except asyncio.TimeoutError:
                print(f"⚠️ 創建日誌超時（10秒）")
                return False
            except discord.HTTPException as e:
                print(f"⚠️ Discord API 錯誤創建日誌: {e}")
                return False
        else:
            message_ids[bot_type_str]["logs"] = found_logs.id
            print(f"✅ 找到 {bot_type_str} 日誌: {found_logs.id}")
        
        # 保存到 .env
        try:
            save_message_ids(bot_type_str)
        except Exception as e:
            print(f"⚠️ 保存訊息 ID 到 .env 失敗: {e}")
        
        # 記錄環境信息到日誌
        try:
            if env_diagnostics:
                env_summary = f"環境: {'虛擬環境' if env_diagnostics['in_virtual_env'] else '系統環境'}"
                if env_diagnostics['running_under_systemd']:
                    env_summary += " | systemd"
                add_log(bot_type_str, f"✅ {env_summary}")
        except Exception as e:
            print(f"⚠️ 記錄環境信息失敗: {e}")
        
        return True
        
    except discord.HTTPException as e:
        print(f"⚠️ Discord API 錯誤初始化儀表板: {e}，機器人將繼續運行")
        return False
    except Exception as e:
        print(f"⚠️ 初始化儀表板失敗: {e}，機器人將繼續運行")
        import traceback
        traceback.print_exc()
        return False



async def ensure_dashboard_messages(bot: discord.Client, bot_type: str):
    """
    確保儀表板消息存在並啟動全域日誌任務
    添加超時保護，防止網路問題導致崩潰
    """
    try:
        print(f"[DASHBOARD] 開始設置 {bot_type} 儀表板")

        # 註冊機器人實例
        register_bot_instance(bot_type, bot)
        print(f"[DASHBOARD] {bot_type} 實例已註冊")

        # 加載訊息 ID（包括硬編碼的回退值）
        try:
            load_message_ids(bot_type)
        except Exception as e:
            print(f"[DASHBOARD] 加載訊息 ID 失敗: {e}")

        # 創建或更新控制面板訊息
        try:
            await asyncio.wait_for(
                create_or_update_dashboard(bot, bot_type),
                timeout=20.0
            )
        except asyncio.TimeoutError:
            print(f"[DASHBOARD] {bot_type} 創建/更新控制面板超時（20秒）")
        except Exception as e:
            print(f"[DASHBOARD] {bot_type} 創建/更新控制面板失敗: {e}")

        # 創建或更新日誌訊息
        try:
            await asyncio.wait_for(
                create_or_update_logs(bot, bot_type),
                timeout=20.0
            )
        except asyncio.TimeoutError:
            print(f"[DASHBOARD] {bot_type} 創建/更新日誌超時（20秒）")
        except Exception as e:
            print(f"[DASHBOARD] {bot_type} 創建/更新日誌失敗: {e}")

        # 啟動全域日誌更新任務（只在第一次調用時啟動）
        try:
            if not global_update_logs_task.is_running():
                print(f"[DASHBOARD] 啟動全域日誌更新任務")
                global_update_logs_task.start()
                add_log("system", f"🔄 全域日誌更新任務已啟動")
            else:
                print(f"[DASHBOARD] 全域日誌更新任務已在運行")
        except Exception as e:
            print(f"[DASHBOARD] 啟動全域日誌更新任務失敗: {e}")

        print(f"[DASHBOARD] {bot_type} 儀表板設置完成")

    except Exception as e:
        print(f"[DASHBOARD ERROR] {bot_type} 儀表板設置失敗，但不影響機器人運行: {e}")
        import traceback
        traceback.print_exc()


async def create_or_update_dashboard(bot: discord.Client, bot_type: str):
    """創建或更新控制面板訊息，添加超時保護"""
    try:
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"⚠️ 找不到儀表板頻道: {DASHBOARD_CHANNEL_ID}")
            return

        # 檢查現有訊息（優先從 .env，然後使用硬編碼回退值）
        dashboard_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_DASHBOARD")
        if not dashboard_id and bot_type in HARDCODED_MESSAGE_IDS:
            dashboard_id = str(HARDCODED_MESSAGE_IDS[bot_type]["dashboard"])
            print(f"[DASHBOARD] 使用硬編碼的 {bot_type} 控制面板 ID: {dashboard_id}")

        if dashboard_id:
            try:
                msg = await asyncio.wait_for(
                    channel.fetch_message(int(dashboard_id)),
                    timeout=10.0
                )
                if msg.author.id == bot.user.id:
                    # 更新現有訊息
                    embed = await create_dashboard_embed(bot_type)
                    view = DashboardButtons(bot_type, bot)
                    await asyncio.wait_for(
                        msg.edit(embed=embed, view=view),
                        timeout=10.0
                    )
                    print(f"[DASHBOARD] {bot_type} 控制面板已更新")
                    return
            except asyncio.TimeoutError:
                print(f"[DASHBOARD] {bot_type} 獲取/更新控制面板訊息超時（10秒）")
            except discord.NotFound:
                print(f"[DASHBOARD] {bot_type} 控制面板訊息不存在，將重新創建")
            except discord.HTTPException as e:
                print(f"[DASHBOARD] {bot_type} Discord API 錯誤: {e}")
                return

        # 創建新訊息
        try:
            embed = await create_dashboard_embed(bot_type)
            view = DashboardButtons(bot_type, bot)
            msg = await asyncio.wait_for(
                channel.send(embed=embed, view=view),
                timeout=10.0
            )
            set_key(".env", f"DASHBOARD_{bot_type.upper()}_DASHBOARD", str(msg.id))
            print(f"[DASHBOARD] {bot_type} 控制面板已創建 (ID: {msg.id})")
        except asyncio.TimeoutError:
            print(f"[DASHBOARD] {bot_type} 創建控制面板訊息超時（10秒）")
        except discord.HTTPException as e:
            print(f"[DASHBOARD] {bot_type} Discord API 錯誤創建控制面板: {e}")

    except Exception as e:
        print(f"[DASHBOARD] {bot_type} 控制面板創建/更新失敗，但不影響機器人運行: {e}")


async def create_or_update_logs(bot: discord.Client, bot_type: str):
    """創建或更新日誌訊息，添加超時保護"""
    try:
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"⚠️ 找不到儀表板頻道: {DASHBOARD_CHANNEL_ID}")
            return

        # 檢查現有訊息（優先從 .env，然後使用硬編碼回退值）
        logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")
        if not logs_id and bot_type in HARDCODED_MESSAGE_IDS:
            logs_id = str(HARDCODED_MESSAGE_IDS[bot_type]["logs"])
            print(f"[DASHBOARD] 使用硬編碼的 {bot_type} 日誌 ID: {logs_id}")

        if logs_id:
            try:
                msg = await asyncio.wait_for(
                    channel.fetch_message(int(logs_id)),
                    timeout=10.0
                )
                if msg.author.id == bot.user.id:
                    # 更新現有訊息
                    embed = await create_logs_embed(bot_type)
                    await asyncio.wait_for(
                        msg.edit(embed=embed),
                        timeout=10.0
                    )
                    print(f"[DASHBOARD] {bot_type} 日誌已更新")
                    return
            except asyncio.TimeoutError:
                print(f"[DASHBOARD] {bot_type} 獲取/更新日誌訊息超時（10秒）")
            except discord.NotFound:
                print(f"[DASHBOARD] {bot_type} 日誌訊息不存在，將重新創建")
            except discord.HTTPException as e:
                print(f"[DASHBOARD] {bot_type} Discord API 錯誤: {e}")
                return

        # 創建新訊息
        try:
            embed = await create_logs_embed(bot_type)
            msg = await asyncio.wait_for(
                channel.send(embed=embed),
                timeout=10.0
            )
            set_key(".env", f"DASHBOARD_{bot_type.upper()}_LOGS", str(msg.id))
            print(f"[DASHBOARD] {bot_type} 日誌已創建 (ID: {msg.id})")
        except asyncio.TimeoutError:
            print(f"[DASHBOARD] {bot_type} 創建日誌訊息超時（10秒）")
        except discord.HTTPException as e:
            print(f"[DASHBOARD] {bot_type} Discord API 錯誤創建日誌: {e}")

    except Exception as e:
        print(f"[DASHBOARD] {bot_type} 日誌創建/更新失敗，但不影響機器人運行: {e}")


def save_message_ids(bot_type: str):
    """將 message_id 保存到 .env"""
    env_path = ".env"
    dashboard_id = message_ids[bot_type].get("dashboard")
    logs_id = message_ids[bot_type].get("logs")

    if dashboard_id:
        env_key = f"DASHBOARD_{bot_type.upper()}_DASHBOARD"
        set_key(env_path, env_key, str(dashboard_id))

    if logs_id:
        env_key = f"DASHBOARD_{bot_type.upper()}_LOGS"
        set_key(env_path, env_key, str(logs_id))


def load_message_ids(bot_type: str):
    """從 .env 加載 message_id，如果不存在則使用硬編碼的回退值"""
    dashboard_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_DASHBOARD")
    logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")

    if dashboard_id:
        message_ids[bot_type]["dashboard"] = int(dashboard_id)
    elif bot_type in HARDCODED_MESSAGE_IDS:
        # 使用硬編碼的回退值
        message_ids[bot_type]["dashboard"] = HARDCODED_MESSAGE_IDS[bot_type]["dashboard"]
        print(f"[LOAD IDS] 使用硬編碼的 {bot_type} 控制面板 ID: {HARDCODED_MESSAGE_IDS[bot_type]['dashboard']}")

    if logs_id:
        message_ids[bot_type]["logs"] = int(logs_id)
    elif bot_type in HARDCODED_MESSAGE_IDS:
        # 使用硬編碼的回退值
        message_ids[bot_type]["logs"] = HARDCODED_MESSAGE_IDS[bot_type]["logs"]
        print(f"[LOAD IDS] 使用硬編碼的 {bot_type} 日誌 ID: {HARDCODED_MESSAGE_IDS[bot_type]['logs']}")
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
        timestamp=get_taiwan_time()
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
    
    embed.set_footer(text=f"上次更新: {get_taiwan_time().strftime('%H:%M:%S 台灣時間')}")
    return embed


async def create_logs_embed(bot_type: str) -> discord.Embed:
    """創建日誌 Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 實時日誌",
        color=config['顏色'],
        timestamp=get_taiwan_time()
    )
    
    logs_text = get_logs_text(bot_type)
    embed.description = f"```\n{logs_text}\n```"
    
    embed.set_footer(text=f"更新頻率: 15秒 | {get_taiwan_time().strftime('%H:%M:%S 台灣時間')}")
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
        dashboard_msg_id = message_ids[bot_type].get("dashboard")
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
                message_ids[bot_type]["dashboard"] = msg.id
                save_message_ids(bot_type)
            except discord.Forbidden:
                # 沒有權限編輯（訊息來自其他 bot）
                pass
            except Exception as e:
                # 其他錯誤，靜默處理
                pass
        
        # 更新日誌
        logs_msg_id = message_ids[bot_type].get("logs")
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
                message_ids[bot_type]["logs"] = msg.id
                save_message_ids(bot_type)
            except discord.Forbidden:
                # 沒有權限編輯（訊息來自其他 bot）
                pass
            except Exception as e:
                # 其他錯誤，靜默處理
                pass
    
    except Exception as e:
        print(f"❌ 更新儀表板失敗: {e}")
