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
import traceback
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Optional, Dict
from dotenv import load_dotenv, set_key
from discord.ext import tasks
import pathlib

load_dotenv()

# 台灣時區（UTC+8）
TAIWAN_TZ = timezone(timedelta(hours=8))

# Systemd 日誌配置
# 每個服務預設抓取的 systemd 日誌行數，可調大以便觀察
SYSTEMD_LOG_CONFIG = {
    "bot": {"service": "bot.service", "lines": 20, "enabled": True},
    "shopbot": {"service": "shopbot.service", "lines": 20, "enabled": True},
    "uibot": {"service": "uibot.service", "lines": 20, "enabled": True}
}

def get_taiwan_time():
    """獲取台灣時間"""
    return datetime.now(TAIWAN_TZ)

def format_taiwan_time():
    """格式化台灣時間為 HH:MM"""
    return get_taiwan_time().strftime("%H:%M")

# 配置常數
MAX_STARTUP_WAIT_SECONDS = 60  # 最多等待機器人就緒的時間（秒）

async def check_database_connection():
    """檢查 user_data.db 資料庫連接（異步版本）"""
    try:
        # 使用 asyncio.to_thread 將同步操作移到線程池，避免阻塞事件循環
        result = await asyncio.to_thread(_sync_check_database)
        return result
    except Exception as e:
        print(f"[DB CHECK] 資料庫連接檢查失敗: {e}")
        return False

def _sync_check_database():
    """同步的資料庫檢查函數"""
    conn = sqlite3.connect('user_data.db')
    conn.execute('SELECT 1')  # 簡單的測試查詢
    conn.close()
    return True

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

async def get_systemd_logs(bot_type: str) -> str:
    """從 systemd journal 獲取指定機器人的日誌"""
    config = SYSTEMD_LOG_CONFIG.get(bot_type)
    if not config or not config["enabled"]:
        return f"Systemd 日誌已停用 ({bot_type})"

    try:
        service_name = config["service"]
        lines = config["lines"]

        print(f"[SYSTEMD LOGS] {bot_type} 正在獲取 {service_name} 的日誌...")

        # 構建 journalctl 命令（使用完整路徑）
        cmd = [
            "/usr/bin/journalctl", "-u", service_name,
            "-n", str(lines), "--no-pager", "-o", "short-iso",
            "--since", "2 hours ago"  # 限制時間範圍避免過多數據
        ]

        # 異步執行命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logs = stdout.decode('utf-8', errors='ignore').strip()
            if logs:
                # 格式化日誌
                formatted_logs = []
                seen_messages = set()  # 用於記錄已處理的訊息
                for line in logs.split('\n'):
                    if line.strip():
                        parts = line.split(' ', 2)
                        if len(parts) >= 2:
                            timestamp = get_taiwan_time().strftime("%H:%M")
                            message = parts[2] if len(parts) > 2 else parts[1]
                            # 過濾非必要的訊息
                            if any(keyword in message for keyword in ["成功獲取消息", "日誌已成功更新", "更新完成"]):
                                continue
                            if message.startswith("UPDATE TASK"):
                                message = message.replace("UPDATE TASK ", "")
                            seen_messages.add(message)
                            formatted_logs.append(f"[{timestamp}] {message}")
                return '\n'.join(formatted_logs)
            else:
                print(f"[SYSTEMD LOGS] {bot_type} 沒有找到 {service_name} 的日誌")
                return f"無 {service_name} 日誌"
        else:
            error = stderr.decode('utf-8', errors='ignore').strip()
            print(f"[SYSTEMD LOGS ERROR] {bot_type} 獲取 {service_name} 日誌失敗: {error}")
            return f"journalctl 錯誤: {error[:50]}..."

    except FileNotFoundError:
        print(f"[SYSTEMD LOGS ERROR] {bot_type} /usr/bin/journalctl 命令不存在")
        return "/usr/bin/journalctl 命令不存在，請檢查系統安裝"
    except Exception as e:
        print(f"[SYSTEMD LOGS ERROR] {bot_type} 獲取日誌失敗: {e}")
        return f"獲取日誌失敗: {str(e)[:50]}"

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
        traceback.print_exc()

# 初始化時執行環境檢查
# 注意: 不在此處加載日誌，防止每次重啟時日誌累積
env_diagnostics = check_environment()

# Message ID 存儲（每個機器人獨立）
message_ids = {
    "bot": {"dashboard": None, "logs": None},
    "shopbot": {"dashboard": None, "logs": None},
    "uibot": {"dashboard": None, "logs": None}
}

# 機器人實例存儲（每個機器人獨立）
bot_instances = {}

BOT_CONFIG = {
    "bot": {"名稱": "🤖 Main Bot", "顏色": discord.Color.blue(), "emoji": "🤖"},
    "shopbot": {"名稱": "🛍️ Shop Bot", "顏色": discord.Color.purple(), "emoji": "🛍️"},
    "uibot": {"名稱": "🎨 UI Bot", "顏色": discord.Color.gold(), "emoji": "🎨"}
}

# 追蹤當前機器人類型（在初始化時設置）
current_bot_type = None

# 每個機器人的獨立更新任務存儲
update_tasks = {}

# list of bots for which we suppress the routine start/finish logs
QUIET_UPDATE_BOTS = {"shopbot"}

def create_update_task(bot_type: str):
    """為指定機器人創建獨立的更新任務"""
    print(f"[DEBUG] 建立更新任務物件 ({bot_type})")

    # helper that prints only when verbosity is enabled for this bot
    def task_log(message: str):
        if bot_type not in QUIET_UPDATE_BOTS:
            print(message)

    async def individual_update_task():
        """個別機器人的儀表板更新任務 - 只更新自己的面板和日誌"""
        try:
            task_log(f"[UPDATE TASK {bot_type}] ===== 開始更新 {bot_type} 的儀表板和日誌 =====")

            # 檢查機器人實例
            if bot_type not in bot_instances:
                print(f"[UPDATE TASK {bot_type}] 實例未找到 - 取消任務")
                return

            bot_instance = get_bot_instance(bot_type)
            if not bot_instance:
                print(f"[UPDATE TASK {bot_type}] 實例為空 - 取消任務")
                return

            # 添加系統狀態日誌
            current_time = get_taiwan_time().strftime("%H:%M:%S")
            # 移除洗版日誌: add_log(bot_type, f"🔄 系統狀態檢查 - {current_time}")

            # 更新自己的面板
            try:
                task_log(f"[UPDATE TASK {bot_type}] 開始更新面板")
                await update_dashboard(bot_instance, bot_type)
                task_log(f"[UPDATE TASK {bot_type}] 面板更新完成")
            except Exception as e:
                print(f"[UPDATE TASK {bot_type} ERROR] 面板更新失敗: {e}")
                # write full traceback to separate file for postmortem
                with open("update_task_errors.log", "a", encoding="utf-8") as ef:
                    ef.write(f"[{datetime.now(TAIWAN_TZ)}] 面板更新失敗: {e}\n")
                    traceback.print_exc(file=ef)
                traceback.print_exc()

            # 更新自己的日誌
            try:
                task_log(f"[UPDATE TASK {bot_type}] 開始更新日誌")
                await update_dashboard_logs(bot_instance, bot_type)
                task_log(f"[UPDATE TASK {bot_type}] 日誌更新完成")
            except Exception as e:
                print(f"[UPDATE TASK {bot_type} ERROR] 日誌更新失敗: {e}")
                with open("update_task_errors.log", "a", encoding="utf-8") as ef:
                    ef.write(f"[{datetime.now(TAIWAN_TZ)}] 日誌更新失敗: {e}\n")
                    traceback.print_exc(file=ef)
                traceback.print_exc()

            task_log(f"[UPDATE TASK {bot_type}] ===== {bot_type} 更新完成 =====")

        except Exception as e:
            # errors should always be visible even for quiet bots
            print(f"[UPDATE TASK {bot_type} ERROR] 任務執行失敗: {e}")
            with open("update_task_errors.log", "a", encoding="utf-8") as ef:
                ef.write(f"[{datetime.now(TAIWAN_TZ)}] 任務執行失敗: {e}\n")
                traceback.print_exc(file=ef)
            traceback.print_exc()

    # 創建任務對象
    task = tasks.loop(seconds=60)(individual_update_task)
    task.__name__ = f"update_task_{bot_type}"

    return task

def register_bot_instance(bot_type: str, bot_instance):
    """註冊機器人實例並確保更新任務啟動"""
    bot_instances[bot_type] = bot_instance
    print(f"[DEBUG] {bot_type} 機器人實例已註冊")

    # 確保對應的更新任務存在並啟動（防止 initialize_dashboard 失敗）
    if bot_type not in update_tasks:
        print(f"[DEBUG] {bot_type} 更新任務不存在，register_bot_instance 將建立")
        try:
            update_task = create_update_task(bot_type)
            update_tasks[bot_type] = update_task
            update_task.start()
            print(f"[DEBUG] {bot_type} 更新任務已由 register_bot_instance 啟動")
        except Exception as e:
            print(f"[ERROR] 無法啟動 {bot_type} 更新任務: {e}")

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
    """更新指定機器人的日誌"""
    try:
        print(f"[UPDATE LOGS] 開始更新 {bot_type} 日誌")

        # 檢查機器人實例
        if not bot:
            print(f"[UPDATE LOGS ERROR] {bot_type} 機器人實例為空")
            return

        # 獲取應用程序內部日誌
        internal_logs = get_logs_text(bot_type)

        # 獲取 systemd 日誌
        systemd_logs = await get_systemd_logs(bot_type)

        # 合併日誌顯示 - 改進格式化
        if systemd_logs and systemd_logs not in ["無 systemd 日誌", "Systemd 日誌已停用"]:
            combined_logs = f"📊 **Systemd 日誌**\n```\n{systemd_logs}\n```\n\n📝 **應用日誌**\n```\n{internal_logs}\n```"
        else:
            combined_logs = f"📝 **應用日誌**\n```\n{internal_logs}\n```"

        logs_text = combined_logs

        # 確保總長度不超過 Discord embed 限制 (4000 字符)
        if len(logs_text) > 4000:
            logs_text = logs_text[:3997] + "..."

        print(f"[UPDATE LOGS] {bot_type} 日誌內容長度: {len(logs_text)} 字符")
        print(f"[UPDATE LOGS] {bot_type} 日誌內容預覽: {logs_text[:100] if logs_text else '空'}")

        # 創建日誌 embed
        config = BOT_CONFIG.get(bot_type, {})
        embed = discord.Embed(
            title=f"{config['名稱']} 實時日誌",
            description=logs_text,
            color=config["顏色"],
            timestamp=get_taiwan_time()  # 使用台灣時間
        )

        embed.set_footer(text=f"每 60 秒自動更新 | 台灣時間•今天 下午 {format_taiwan_time()}")

        # 更新訊息
        message_id = get_message_id(bot_type, "logs")
        print(f"[UPDATE LOGS] {bot_type} 嘗試更新消息ID: {message_id}")
        
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"[UPDATE LOGS ERROR] {bot_type} 找不到頻道 {DASHBOARD_CHANNEL_ID}")
            return
            
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                print(f"[UPDATE LOGS] {bot_type} 成功獲取消息，當前embed數量: {len(message.embeds) if message.embeds else 0}")
                await message.edit(embed=embed)
                print(f"[UPDATE LOGS] {bot_type} 日誌已成功更新")
            except discord.NotFound:
                print(f"[UPDATE LOGS] {bot_type} 日誌訊息不存在，重新創建")
                try:
                    message = await channel.send(embed=embed)
                    save_message_id(bot_type, "logs", str(message.id))
                    print(f"[UPDATE LOGS] {bot_type} 日誌訊息已重新創建: {message.id}")
                except Exception as create_error:
                    print(f"[UPDATE LOGS ERROR] {bot_type} 創建新訊息失敗: {create_error}")
            except discord.Forbidden:
                print(f"[UPDATE LOGS ERROR] {bot_type} 沒有權限編輯訊息")
            except Exception as e:
                print(f"[UPDATE LOGS ERROR] {bot_type} 日誌更新錯誤: {e}")
                traceback.print_exc()
        else:
            # 訊息ID不存在，創建新的日誌embed
            print(f"[UPDATE LOGS] {bot_type} 日誌訊息ID不存在，創建新的embed")
            try:
                # 在創建前檢查是否已經有現有的日誌embed
                existing_logs = []
                async for msg in channel.history(limit=20):
                    if msg.author.id == bot.user.id and msg.embeds:
                        for embed in msg.embeds:
                            if "實時日誌" in embed.title and BOT_CONFIG[bot_type]["名稱"] in embed.title:
                                existing_logs.append(msg)

                # 如果有現有的embed，更新最新的，刪除其他的
                if existing_logs:
                    # 保留最新的embed，刪除其他的
                    existing_logs.sort(key=lambda m: m.created_at, reverse=True)
                    latest_msg = existing_logs[0]

                    # 刪除重複的embed
                    for msg in existing_logs[1:]:
                        try:
                            await msg.delete()
                            print(f"[CLEANUP] 刪除重複日誌embed: {msg.id}")
                        except Exception as delete_error:
                            print(f"[CLEANUP ERROR] 刪除重複embed失敗 {msg.id}: {delete_error}")

                    # 更新保留的embed
                    await latest_msg.edit(embed=embed)
                    message_ids[bot_type]["logs"] = latest_msg.id
                    save_message_ids(bot_type)
                    print(f"[UPDATE LOGS] {bot_type} 更新現有日誌embed: {latest_msg.id}")
                else:
                    # 真的沒有embed，才創建新的
                    message = await channel.send(embed=embed)
                    message_ids[bot_type]["logs"] = message.id
                    save_message_ids(bot_type)
                    print(f"[UPDATE LOGS] {bot_type} 創建新日誌embed: {message.id}")

            except Exception as create_error:
                print(f"[UPDATE LOGS ERROR] {bot_type} 創建/更新日誌embed失敗: {create_error}")

    except Exception as e:
        print(f"[UPDATE LOGS ERROR] {bot_type} 更新日誌時發生未預期錯誤: {e}")
        traceback.print_exc()

class DashboardButtons(discord.ui.View):
    """控制面板按鈕"""
    
    def __init__(self, bot_type: str, bot: discord.Client):
        super().__init__(timeout=None)  # 持久化按鈕
        self.bot_type = bot_type
        self.bot = bot
        
        # 為按鈕設置唯一的 custom_id
        # 通過按鈕的標籤來識別按鈕類型
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.label == "重啟":
                    item.custom_id = f"restart_{bot_type}"
                elif item.label == "狀態":
                    item.custom_id = f"status_{bot_type}"
                elif item.label == "啟動LOG":
                    item.custom_id = f"start_log_{bot_type}"
    
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
時間: <t:{int(datetime.now(timezone.utc).timestamp())}:R>
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
    
    @discord.ui.button(label="啟動LOG", emoji="📝", style=discord.ButtonStyle.primary)
    async def start_log_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """啟動日誌系統"""
        await interaction.response.defer(thinking=True)

        try:
            # 檢查日誌任務是否已經運行
            if self.bot_type in update_tasks and update_tasks[self.bot_type] and not update_tasks[self.bot_type].is_running():
                # 重新啟動任務
                update_tasks[self.bot_type].start()
                await interaction.followup.send(
                    f"✅ {BOT_CONFIG[self.bot_type]['名稱']} 日誌系統已啟動\n將每60秒自動更新日誌",
                    ephemeral=True
                )
                add_log(self.bot_type, f"📝 日誌系統已手動啟動")
            elif self.bot_type in update_tasks and update_tasks[self.bot_type] and update_tasks[self.bot_type].is_running():
                await interaction.followup.send(
                    f"ℹ️ {BOT_CONFIG[self.bot_type]['名稱']} 日誌系統已在運行中",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {BOT_CONFIG[self.bot_type]['名稱']} 日誌系統初始化失敗",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.followup.send(f"❌ 啟動日誌失敗: {e}", ephemeral=True)

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
        print(f"[LOG-{bot_type}] {message}")  # 確保打印
        save_logs()
        print(f"[DEBUG] 日誌已保存，當前{len(logs_storage[bot_type])}條")  # 添加調試
    else:
        print(f"[ERROR] bot_type '{bot_type}' 不存在於logs_storage")

def get_logs_text(bot_type: str) -> str:
    """獲取格式化的日誌文本"""
    if bot_type not in logs_storage:
        return "無日誌"
    
    logs = list(logs_storage[bot_type])
    if not logs:
        return "無日誌"
    
    return "\n".join(logs[::-1])  # 倒序顯示（最新在最上面）

# 調試助手：顯示儀表板 embed 的現有狀態
async def inspect_dashboard(bot: discord.Client, bot_type: str = "bot") -> None:
    """直接從 Discord 拉取儀表板和日誌訊息並打印資訊"""
    channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
    if not channel:
        print("[INSPECT] 無法找到儀表板頻道")
        return
    ids = message_ids.get(bot_type, {})
    print(f"[INSPECT] {bot_type} message_ids: {ids}")
    for typ in ("dashboard", "logs"):
        msg_id = ids.get(typ)
        if not msg_id:
            print(f"[INSPECT] {bot_type} {typ} ID 不存在")
            continue
        try:
            msg = await channel.fetch_message(int(msg_id))
            print(f"[INSPECT] {bot_type} {typ} embed: {msg.embeds[0] if msg.embeds else '無'}")
        except Exception as e:
            print(f"[INSPECT] 無法抓取 {typ} 訊息 {msg_id}: {e}")

async def create_dashboard_embed(bot_type: str) -> discord.Embed:
    """創建控制面板 Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 控制面板",
        color=config['顏色'],
        timestamp=datetime.now(timezone.utc)  # 使用 UTC 時間，讓 Discord 正確處理時區
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
    
    # 移除 footer 的時間，只保留空 footer
    embed.set_footer(text="")
    return embed

async def create_logs_embed(bot_type: str) -> discord.Embed:
    """創建日誌 Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 實時日誌",
        color=config['顏色'],
        timestamp=datetime.now(timezone.utc)  # 使用 UTC 時間，讓 Discord 正確處理時區
    )
    
    logs_text = get_logs_text(bot_type)
    embed.description = f"```\n{logs_text}\n```"
    
    embed.set_footer(text="更新頻率: 60秒")
    return embed

async def initialize_dashboard(bot_instance: discord.Client, bot_type_str: str):
    """
    初始化儀表板 - 每個機器人只初始化自己的面板
    
    Args:
        bot_instance: Discord bot instance
        bot_type_str: "bot", "shopbot", "uibot"
    """
    print(f"[INIT] initialize_dashboard called for {bot_type_str}")
    global current_bot_type
    
    # 添加延遲以避免同時初始化
    delay_map = {"bot": 0, "shopbot": 5, "uibot": 10}
    delay = delay_map.get(bot_type_str, 0)
    if delay > 0:
        print(f"[DASHBOARD] {bot_type_str} 等待 {delay} 秒後初始化...")
        await asyncio.sleep(delay)
    
    current_bot_type = bot_type_str
    
    # 加載訊息 ID（包括硬編碼的回退值）
    load_message_ids(bot_type_str)
    
    try:
        channel = bot_instance.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"❌ 找不到儀表板頻道: {DASHBOARD_CHANNEL_ID}")
            return False
        
        # 只初始化該機器人自己的訊息
        found_dashboard = None
        dashboard_count = 0
        old_dashboards = []
        
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
        
        # 清理舊的控制面板 embed
        for msg in old_dashboards:
            try:
                await msg.delete()
                print(f"✓ 已清理舊的 {bot_type_str} 控制面板")
            except:
                pass
        
        # 創建或註冊控制面板
        if not found_dashboard:
            embed = await create_dashboard_embed(bot_type_str, bot_instance)
            view = DashboardButtons(bot_type_str, bot_instance)
            msg = await channel.send(embed=embed, view=view)
            message_ids[bot_type_str]["dashboard"] = msg.id
            save_message_id(bot_type_str, "dashboard", str(msg.id))  # 立即保存到 .env
            print(f"✅ 創建 {bot_type_str} 控制面板: {msg.id}")
        else:
            message_ids[bot_type_str]["dashboard"] = found_dashboard.id
            # 編輯舊訊息以更新embed和按鈕視圖
            try:
                embed = await create_dashboard_embed(bot_type_str, bot_instance)
                view = DashboardButtons(bot_type_str, bot_instance)
                await found_dashboard.edit(embed=embed, view=view)
                # 成功編輯後保存到 .env（確保 .env 有正確的 ID）
                save_message_ids(bot_type_str)
            except:
                pass
            print(f"✅ 編輯 {bot_type_str} 控制面板: {found_dashboard.id}")
        
        # 保存到 .env
        save_message_ids(bot_type_str)
        
        # 創建或確保日誌embed存在（初始化時創建，之後由全域任務更新）
        # 類似控制面板邏輯，先檢查現有embed，清理重複的
        found_logs = None
        logs_count = 0
        old_logs = []
        
        # 查找現有日誌訊息（只查找由當前 bot 發送的）
        async for msg in channel.history(limit=50):
            if msg.author.id != bot_instance.user.id:
                continue  # 跳過其他 bot 的訊息
            
            if msg.embeds:
                for embed in msg.embeds:
                    bot_name = BOT_CONFIG[bot_type_str]["名稱"]
                    if "實時日誌" in embed.title and bot_name in embed.title:
                        logs_count += 1
                        if logs_count <= 1:
                            found_logs = msg
                        else:
                            old_logs.append(msg)
        
        # 清理舊的日誌 embed
        for msg in old_logs:
            try:
                await msg.delete()
                print(f"✓ 已清理舊的 {bot_type_str} 日誌embed")
            except Exception as e:
                print(f"⚠️ 清理舊日誌embed失敗 {msg.id}: {e}")
        
        # 創建或更新日誌embed
        if not found_logs:
            # 沒有找到現有的，創建新的
            try:
                logs_embed = await create_logs_embed(bot_type_str)
                logs_msg = await channel.send(embed=logs_embed)
                message_ids[bot_type_str]["logs"] = logs_msg.id
                save_message_id(bot_type_str, "logs", str(logs_msg.id))
                print(f"✅ 初始化時創建 {bot_type_str} 日誌embed: {logs_msg.id}")
                add_log(bot_type_str, f"✅ 日誌系統已初始化")
            except Exception as e:
                print(f"⚠️ 初始化時創建 {bot_type_str} 日誌embed失敗: {e}")
        else:
            # 有現有的，更新它並保存ID
            message_ids[bot_type_str]["logs"] = found_logs.id
            try:
                logs_embed = await create_logs_embed(bot_type_str)
                await found_logs.edit(embed=logs_embed)
                save_message_ids(bot_type_str)
                print(f"✅ 更新現有 {bot_type_str} 日誌embed: {found_logs.id}")
                add_log(bot_type_str, f"✅ 日誌系統已就緒")
            except Exception as e:
                print(f"⚠️ 更新現有日誌embed失敗 {found_logs.id}: {e}")
                add_log(bot_type_str, f"✅ 日誌系統已就緒")
        
        # 🔧 初始化時清空日誌，防止重複累積
        # 尤其是在重新啟動時，舊日誌應該被新的一次啟動替換
        logs_storage[bot_type_str].clear()
        
        # 記錄環境信息到日誌
        if env_diagnostics:
            env_summary = f"環境: {'虛擬環境' if env_diagnostics['in_virtual_env'] else '系統環境'}"
            if env_diagnostics['running_under_systemd']:
                env_summary += " | systemd"
            add_log(bot_type_str, f"✅ {env_summary}")
        
        # 註冊機器人實例並啟動獨立更新任務
        try:
            register_bot_instance(bot_type_str, bot_instance)
            print(f"[DASHBOARD] {bot_type_str} 實例已註冊")

            # 為當前機器人創建並啟動獨立的更新任務
            print(f"[DASHBOARD] 正在為 {bot_type_str} 創建更新任務...")
            if bot_type_str not in update_tasks:
                update_task = create_update_task(bot_type_str)
                update_tasks[bot_type_str] = update_task
                print(f"[DASHBOARD] 正在啟動 {bot_type_str} 更新任務...")
                update_task.start()
                print(f"[DASHBOARD] {bot_type_str} 獨立更新任務已啟動")
            else:
                # 如果任務存在但意外停止，重新啟動
                existing = update_tasks[bot_type_str]
                if not existing.is_running():
                    print(f"[DASHBOARD] {bot_type_str} 更新任務存在但已停止，重新啟動")
                    try:
                        existing.start()
                    except Exception as restart_error:
                        print(f"[DASHBOARD ERROR] 重啟 {bot_type_str} 任務失敗: {restart_error}")
                else:
                    print(f"[DASHBOARD] {bot_type_str} 更新任務已在運行")
        except Exception as e:
            print(f"[DASHBOARD ERROR] {bot_type_str} 任務啟動失敗: {e}")
            import traceback
            traceback.print_exc()
    except Exception as e:
        print(f"❌ 初始化儀表板失敗: {e}")
        traceback.print_exc()
        return False

# 監視任務的守護程序，定期檢測並重啟已停止的更新任務
@tasks.loop(minutes=5)
async def update_task_watchdog():
    # 如果字典中沒有任何任務，也試著為所有已註冊機器人建立
    if not update_tasks:
        print("[WATCHDOG] 尚無任何更新任務，嘗試為已註冊機器人建立")
        for bot_type in bot_instances.keys():
            if bot_type not in update_tasks:
                try:
                    t = create_update_task(bot_type)
                    update_tasks[bot_type] = t
                    t.start()
                    print(f"[WATCHDOG] 已為 {bot_type} 建立並啟動更新任務")
                except Exception as e:
                    print(f"[WATCHDOG ERROR] 建立 {bot_type} 任務失敗: {e}")

    for bot_type, task in list(update_tasks.items()):
        if not task.is_running():
            print(f"[WATCHDOG] {bot_type} 更新任務停止，嘗試重啟")
            try:
                task.start()
            except Exception as e:
                print(f"[WATCHDOG ERROR] 無法重啟 {bot_type} 任務: {e}")

# 在模組載入時啟動守護程序（不需要機器人實例）
try:
    update_task_watchdog.start()
    print("[WATCHDOG] 更新任務守護程序已啟動")
except Exception:
    # 如果在導入時機器人尚未啟動，等初始化時再啟動
    pass

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
    """從 .env 加載 message_id，如果沒有則使用硬編碼的回退值"""
    dashboard_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_DASHBOARD")
    logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")

    if dashboard_id:
        message_ids[bot_type]["dashboard"] = int(dashboard_id)
        print(f"[LOAD IDS] {bot_type} 控制面板 ID: {dashboard_id}")
    else:
        # 使用硬編碼的回退值
        fallback_id = HARDCODED_MESSAGE_IDS.get(bot_type, {}).get("dashboard")
        if fallback_id:
            message_ids[bot_type]["dashboard"] = fallback_id
            print(f"[LOAD IDS] {bot_type} 控制面板 ID 使用回退值: {fallback_id}")
        else:
            message_ids[bot_type]["dashboard"] = None
            print(f"[LOAD IDS] {bot_type} 控制面板 ID 未設置")

    if logs_id:
        message_ids[bot_type]["logs"] = int(logs_id)
        print(f"[LOAD IDS] {bot_type} 日誌 ID: {logs_id}")
    else:
        # 使用硬編碼的回退值
        fallback_id = HARDCODED_MESSAGE_IDS.get(bot_type, {}).get("logs")
        if fallback_id:
            message_ids[bot_type]["logs"] = fallback_id
            print(f"[LOAD IDS] {bot_type} 日誌 ID 使用回退值: {fallback_id}")
        else:
            message_ids[bot_type]["logs"] = None
            print(f"[LOAD IDS] {bot_type} 日誌 ID 未設置")

async def create_dashboard_embed(bot_type: str, bot: discord.Client = None) -> discord.Embed:
    """創建控制面板 Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 控制面板",
        color=config['顏色'],
        timestamp=get_taiwan_time()  # 使用台灣時間
    )

    # 檢查機器人狀態
    if bot and bot.user and bot.is_ready():
        bot_status = "🟢 **在線**"
        task_status = "✅ **正常**"
    else:
        bot_status = "🔴 **離線**"
        task_status = "❌ **異常**"

    # 實際檢查資料庫連接
    if await check_database_connection():
        db_status = "✅ **連接正常**"
    else:
        db_status = "❌ **連接失敗**"

    # 檢查日誌任務狀態
    if bot_type in update_tasks and update_tasks[bot_type] and update_tasks[bot_type].is_running():
        logs_status = "✅ **運行中**"
    else:
        logs_status = "❌ **已停止**"

    # 第一行：機器人狀態
    embed.add_field(
        name="🤖 機器人狀態",
        value=bot_status,
        inline=False
    )

    # 第二行：系統組件狀態
    embed.add_field(
        name="📊 任務狀態",
        value=task_status,
        inline=True
    )

    embed.add_field(
        name="💾 數據庫",
        value=db_status,
        inline=True
    )

    embed.add_field(
        name="📝 日誌系統",
        value=logs_status,
        inline=True
    )

    # 添加分隔線和最後更新時間
    current_time = get_taiwan_time().strftime("%H:%M:%S")
    embed.add_field(
        name="⏰ 最後更新",
        value=f"`{current_time}`",
        inline=False
    )

    embed.set_footer(text="每 60 秒自動更新 | 台灣時間")
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
                # 移除作者檢查 - 每個機器人負責更新自己類型的 embed
                embed = await create_dashboard_embed(bot_type, bot)
                view = DashboardButtons(bot_type, bot)
                await msg.edit(embed=embed, view=view)
            except discord.NotFound:
                print(f"⚠️ {bot_type} 控制面板訊息不存在，重新創建...")
                embed = await create_dashboard_embed(bot_type, bot)
                view = DashboardButtons(bot_type, bot)
                msg = await channel.send(embed=embed, view=view)
                message_ids[bot_type]["dashboard"] = msg.id
                save_message_ids(bot_type)
            except discord.Forbidden:
                # 沒有權限編輯（訊息來自其他 bot）
                print(f"⚠️ {bot_type} 沒有權限編輯控制面板訊息，嘗試重新創建...")
                try:
                    embed = await create_dashboard_embed(bot_type, bot)
                    view = DashboardButtons(bot_type, bot)
                    msg = await channel.send(embed=embed, view=view)
                    message_ids[bot_type]["dashboard"] = msg.id
                    save_message_ids(bot_type)
                    print(f"✅ {bot_type} 控制面板重新創建成功")
                except Exception as e2:
                    print(f"❌ {bot_type} 控制面板重新創建失敗: {e2}")
            except Exception as e:
                # 其他錯誤，靜默處理
                print(f"⚠️ {bot_type} 控制面板更新錯誤: {e}")
        
        # 日誌由 global_update_logs_task 的 update_dashboard_logs 處理
    
    except Exception as e:
        print(f"❌ 更新儀表板失敗: {e}")