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
import re
import random
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Optional, Dict
from dotenv import load_dotenv, set_key
from discord.ext import tasks
import pathlib

# ⏸️ METRICS 管理 - 優化版本
# 注意：Metrics 更新必須由 "bot" 單獨負責（不是 shopbot/uibot）
# 原因：避免並發競爭、重複 API 調用導致 CPU 飙高
# 特性：

#   - 20 分鐘更新一次（降低 API 呼叫頻率）
#   - 非同步操作 + 10s 超時保護
#   - 線程池執行 matplotlib 圖表生成
#   - 數據緩存避免重複計算
GCP_METRICS_ENABLED = True  # 是否啓用 Metrics 更新
GCP_METRICS_ONLY_BOT_RESPONSIBLE = "bot"  # 只有這個 bot 負責更新 metrics
GCP_METRICS_UPDATE_INTERVAL_MINUTES = 5  # 更新間隔（分鐘）
print("[DASHBOARD INIT] 📊 GCP Metrics Manager initialized - only 'bot' will update")

load_dotenv()

# 台灣時區（UTC+8）
TAIWAN_TZ = timezone(timedelta(hours=8))

# Systemd 日誌配置
# 只抓8行最新日誌以減少磁盤I/O，每行都很重要（最後一行為最新錯誤/狀態）
SYSTEMD_LOG_CONFIG = {
    "bot": {"service": "bot.service", "lines": 8, "enabled": True},
    "shopbot": {"service": "shopbot.service", "lines": 8, "enabled": True},
    "uibot": {"service": "uibot.service", "lines": 8, "enabled": True}
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

# 硬編碼的訊息 ID 作為回退值（只保留日誌，控制面板已移除）
HARDCODED_MESSAGE_IDS = {
    "bot": {
        "logs": 1470781481868591187
    },
    "shopbot": {
        "logs": 1470782650716389648
    },
    "uibot": {
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

# GCP Metrics 追蹤上次的 embed 內容（避免重複更新）
last_metrics_text = ""

# keep track of last fetch time for each bot to avoid re-reading the same log
_last_log_fetch: Dict[str, datetime] = {}

async def get_systemd_logs(bot_type: str) -> str:
    """從 systemd journal 獲取指定機器人的日誌

    為了降低磁碟 I/O，僅抓取自上次查詢以來的新條目。
    初次呼叫會使用 "2 hours ago" 作為保底，之後視為迭代式。
    每次查詢有 3s 超時，以避免事件征環被凍結。
    """
    config = SYSTEMD_LOG_CONFIG.get(bot_type)
    if not config or not config["enabled"]:
        return f"Systemd 日誌已停用 ({bot_type})"

    try:
        service_name = config["service"]
        lines = config["lines"]

        # 只有在非靜默機器人時才打印進度
        if bot_type not in QUIET_UPDATE_BOTS:
            print(f"[SYSTEMD LOGS] {bot_type} 正在獲取 {service_name} 的日誌...")

        # 使用上次查詢時間構造 --since 參數
        since_time = _last_log_fetch.get(bot_type)
        if since_time is None:
            # 第一次查詢：從最近 10 分鐘開始
            since_arg = "10 minutes ago"
        else:
            # journalctl 不喜歡帶時區或微秒的 ISO 字串，會報 "Failed to parse timestamp"
            # 使用最簡單的年月日時分秒格式即可
            # since_time 存的是本地台灣時區時間
            since_arg = since_time.strftime("%Y-%m-%d %H:%M:%S")

        # 構建 journalctl 命令（使用完整路徑）
        cmd = [
            "/usr/bin/journalctl", "-u", service_name,
            "-n", str(lines), "--no-pager", "-o", "short-iso",
            "--since", since_arg
        ]

        # 異步執行命令，帶 3s 超時
        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                ),
                timeout=3.0
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=3.0
            )
        except asyncio.TimeoutError:
            if bot_type not in QUIET_UPDATE_BOTS:
                print(f"[SYSTEMD LOGS] {bot_type} journalctl 查詢超時")
            return f"journalctl 查詢超時 (3s)"

        if process.returncode == 0:
            # 使用 errors='replace' 而非 'ignore'，以便看到編碼問題（用替代符號表示）
            # 這樣日誌中會出現 U+FFFD '？' 而不是無聲丟棄無效字符
            logs = stdout.decode('utf-8', errors='replace').strip()
            # 更新 fetch 時間，無論是否有新內容
            _last_log_fetch[bot_type] = datetime.now(TAIWAN_TZ)

            if logs:
                # 格式化日誌
                formatted_logs = []
                seen_messages = set()  # 用於記錄已處理的訊息
                for line in logs.split('\n'):
                    if line.strip():
                        parts = line.split(' ', 2)
                        if len(parts) >= 2:
                            # 直接使用 journalctl 原始時間，不要再插入新的時間
                            message = parts[2] if len(parts) > 2 else parts[1]
                            # 刪除 PID（例如 service[1234]）以縮短行長
                            message = re.sub(r"\[\d+\]", "", message)
                            # 過濾非必要的訊息
                            if any(keyword in message for keyword in ["成功獲取消息", "日誌已成功更新", "更新完成"]):
                                continue
                            # 排除 systemd 本身的「entries --」或空標頭
                            if message.strip().lower().startswith("entries --") or message.strip() == "-- reboot --":
                                continue
                            if message.startswith("UPDATE TASK"):
                                message = message.replace("UPDATE TASK ", "")
                            seen_messages.add(message)
                            formatted_logs.append(message)
                return '\n'.join(formatted_logs)


        # 異步執行命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            # 使用 errors='replace' 而非 'ignore'，讓編碼錯誤以替代符號顯示
            logs = stdout.decode('utf-8', errors='replace').strip()
            # 更新 fetch 時間，無論是否有新內容
            _last_log_fetch[bot_type] = datetime.now(TAIWAN_TZ)

            if logs:
                # 格式化日誌
                formatted_logs = []
                seen_messages = set()  # 用於記錄已處理的訊息
                for line in logs.split('\n'):
                    if line.strip():
                        parts = line.split(' ', 2)
                        if len(parts) >= 2:
                            # 直接使用 journalctl 原始時間，不要再插入新的時間
                            message = parts[2] if len(parts) > 2 else parts[1]
                            # 刪除 PID（例如 service[1234]）以縮短行長
                            message = re.sub(r"\[\d+\]", "", message)
                            # 過濾非必要的訊息
                            if any(keyword in message for keyword in ["成功獲取消息", "日誌已成功更新", "更新完成"]):
                                continue
                            # 排除 systemd 本身的「entries --」或空標頭
                            if message.strip().lower().startswith("entries --") or message.strip() == "-- reboot --":
                                continue
                            if message.startswith("UPDATE TASK"):
                                message = message.replace("UPDATE TASK ", "")
                            seen_messages.add(message)
                            formatted_logs.append(message)
                return '\n'.join(formatted_logs)
            else:
                if bot_type not in QUIET_UPDATE_BOTS:
                    print(f"[SYSTEMD LOGS] {bot_type} 沒有找到 {service_name} 的日誌")
                return f"無 {service_name} 日誌"
        else:
            # 使用 errors='replace' 讓錯誤訊息中的編碼問題可見
            error = stderr.decode('utf-8', errors='replace').strip()
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
        # track whether we can write to .env, since many components rely on it
        "env_file_writable": False,
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

    # 檢查 .env 文件可寫
    try:
        diagnostics["env_file_writable"] = os.access(".env", os.W_OK)
        if not diagnostics["env_file_writable"] and diagnostics["env_file_exists"]:
            diagnostics["issues"].append(".env 文件存在但不可寫，可能導致保存 ID 失敗")
    except Exception as e:
        diagnostics["issues"].append(f"無法檢查 .env 權限: {e}")
    
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
    "bot": {"logs": None},
    "shopbot": {"logs": None},
    "uibot": {"logs": None},
    "metrics": {"message": None}  # GCP Metrics 使用全域 message ID（已禁用）
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

# 每個機器人的 GCP Metrics 更新任務存儲
metrics_tasks = {}

# list of bots for which we suppress the routine start/finish logs
# now quiet all of them to eliminate per-minute console noise
QUIET_UPDATE_BOTS = {"bot", "shopbot", "uibot"}

def create_update_task(bot_type: str):
    """為指定機器人創建獨立的更新任務"""

    # helper that prints only when verbosity is enabled for this bot
    def task_log(message: str):
        if bot_type not in QUIET_UPDATE_BOTS:
            print(message)

    async def individual_update_task():
        """個別機器人的儀表板更新任務 - 只更新自己的面板和日誌"""
        # 首次啟動時隨機延遲 (0~60s)，避免多個 bot 同刻編輯造成 429
        if not hasattr(individual_update_task, "_jittered"):
            individual_update_task._jittered = True
            # import locally in case the global namespace somehow loses `random`
            import random as _rand
            jitter = _rand.uniform(0, 60)
            task_log(f"[UPDATE TASK {bot_type}] 首次更新延遲 {jitter:.1f}s")
            await asyncio.sleep(jitter)
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

            # 只更新日誌（控制面板已移除）
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

    # 創建任務對象 - 優化：每 120 秒更新一次（從 60 秒改為減少 I/O）
    task = tasks.loop(seconds=120)(individual_update_task)
    task.__name__ = f"update_task_{bot_type}"

    return task

def register_bot_instance(bot_type: str, bot_instance):
    """註冊機器人實例並確保更新任務啟動"""
    bot_instances[bot_type] = bot_instance

    # 確保對應的更新任務存在並啟動（防止 initialize_dashboard 失敗）
    if bot_type not in update_tasks:
        try:
            update_task = create_update_task(bot_type)
            update_tasks[bot_type] = update_task
            update_task.start()
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

# keep last rendered logs to prevent duplicate edits
last_logs_text: Dict[str, str] = {}

async def update_dashboard_logs(bot, bot_type: str):
    """更新指定機器人的日誌"""
    try:
        if bot_type not in QUIET_UPDATE_BOTS:
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
            combined_logs = f"📊 **Systemd 日誌**\n```\n{systemd_logs}\n```"
            # 只有應用日誌不為空才加入
            if internal_logs and internal_logs != "無日誌":
                combined_logs += f"\n\n📝 **應用日誌**\n```\n{internal_logs}\n```"
        else:
            if internal_logs and internal_logs != "無日誌":
                combined_logs = f"📝 **應用日誌**\n```\n{internal_logs}\n```"
            else:
                combined_logs = ""

        # 若合併結果為空，說明兩邊都沒有資料；跳過更新以保留舊內容
        if not combined_logs:
            if bot_type not in QUIET_UPDATE_BOTS:
                print(f"[UPDATE LOGS] {bot_type} 無新日誌，保留現有內容")
            return
        logs_text = combined_logs

        # 檢查是否與上次內容相同；若相同則跳過編輯，減少 429
        if last_logs_text.get(bot_type) == logs_text:
            if bot_type not in QUIET_UPDATE_BOTS:
                print(f"[UPDATE LOGS] {bot_type} 日誌內容未變，跳過編輯")
            return
        last_logs_text[bot_type] = logs_text

        # 確保總長度不超過 Discord embed 限制 (4000 字符)
        if len(logs_text) > 4000:
            logs_text = logs_text[:3997] + "..."


        # 創建日誌 embed
        config = BOT_CONFIG.get(bot_type, {})
        embed = discord.Embed(
            title=f"{config['名稱']} 實時日誌",
            description=logs_text,
            color=config["顏色"]
            # 不設定 timestamp 讓時間不出現在 embed 頂部
        )

        embed.set_footer(text=f"每 120 秒自動更新 | 台灣時間•{format_taiwan_time()}")

        # 更新訊息
        message_id = get_message_id(bot_type, "logs")
        
        channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
        if not channel:
            print(f"[UPDATE LOGS ERROR] {bot_type} 找不到頻道 {DASHBOARD_CHANNEL_ID}")
            return
            
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(embed=embed)
            except asyncio.CancelledError:
                # network or task cancelled; just log and return so periodic task can retry
                if bot_type not in QUIET_UPDATE_BOTS:
                    print(f"[UPDATE LOGS] {bot_type} fetch_message cancelled, skipping this cycle")
                return
            except discord.NotFound:
                if bot_type not in QUIET_UPDATE_BOTS:
                    print(f"[UPDATE LOGS] {bot_type} 日誌訊息不存在，重新創建")
                try:
                    message = await channel.send(embed=embed)
                    save_message_id(bot_type, "logs", str(message.id))
                    if bot_type not in QUIET_UPDATE_BOTS:
                        print(f"[UPDATE LOGS] {bot_type} 日誌訊息已重新創建: {message.id}")
                except Exception as create_error:
                    print(f"[UPDATE LOGS ERROR] {bot_type} 創建新訊息失敗: {create_error}")
            except discord.Forbidden:
                print(f"[UPDATE LOGS ERROR] {bot_type} 沒有權限編輯訊息")
            except Exception as e:
                # catch-all for other errors; print traceback
                print(f"[UPDATE LOGS ERROR] {bot_type} 日誌更新錯誤: {e}")
                traceback.print_exc()
        else:
            # 訊息ID不存在，創建新的日誌embed
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
                    if bot_type not in QUIET_UPDATE_BOTS:
                        print(f"[UPDATE LOGS] {bot_type} 更新現有日誌embed: {latest_msg.id}")
                else:
                    # 真的沒有embed，才創建新的
                    message = await channel.send(embed=embed)
                    message_ids[bot_type]["logs"] = message.id
                    save_message_ids(bot_type)
                    if bot_type not in QUIET_UPDATE_BOTS:
                        print(f"[UPDATE LOGS] {bot_type} 創建新日誌embed: {message.id}")

            except Exception as create_error:
                print(f"[UPDATE LOGS ERROR] {bot_type} 創建/更新日誌embed失敗: {create_error}")

    except Exception as e:
        print(f"[UPDATE LOGS ERROR] {bot_type} 更新日誌時發生未預期錯誤: {e}")
        traceback.print_exc()

async def update_dashboard_metrics(bot):
    """
    ⏸️ 舊版本已完全禁用
    新的 metrics 更新邏輯在 create_metrics_update_task() 中實現
    """
    return

# ========== 優化的 GCP Metrics 管理系統 ==========

# 快取管理 - 避免頻繁 API 調用
class MetricsCache:
    """Simple metrics data cache to prevent redundant API calls"""
    def __init__(self):
        self.data = None
        self.timestamp = None
        self.ttl_seconds = 600  # 10 分鐘緩存
    
    def is_stale(self):
        """Check if cache data is stale"""
        if not self.timestamp:
            return True
        elapsed = (datetime.now(TAIWAN_TZ) - self.timestamp).total_seconds()
        return elapsed > self.ttl_seconds
    
    def set(self, data):
        """Store metrics data"""
        self.data = data
        self.timestamp = datetime.now(TAIWAN_TZ)
    
    def get(self):
        """Retrieve metrics data if not stale"""
        if self.is_stale():
            return None
        return self.data

metrics_cache = MetricsCache()

async def create_metrics_update_task(bot_type_str: str):
    """
    為指定機器人創建 metrics 更新任務
    注意：只有 bot 類型會實際執行更新；其他類型是 NO-OP
    """
    
    if bot_type_str != GCP_METRICS_ONLY_BOT_RESPONSIBLE:
        # 非 bot 類型不執行任何操作
        async def noop_task():
            return
        task = tasks.loop(minutes=GCP_METRICS_UPDATE_INTERVAL_MINUTES)(noop_task)
        task.__name__ = f"metrics_task_{bot_type_str}_noop"
        return task
    
    if not GCP_METRICS_ENABLED:
        # Metrics 被禁用
        async def disabled_task():
            if False:  # 永不執行
                pass
        task = tasks.loop(minutes=GCP_METRICS_UPDATE_INTERVAL_MINUTES)(disabled_task)
        task.__name__ = f"metrics_task_{bot_type_str}_disabled"
        return task
    
    # 從環境變數加載初始的 metrics message ID
    if "metrics" not in message_ids:
        message_ids["metrics"] = {"message": None}
    
    if not message_ids["metrics"].get("message"):
        env_metrics_id = os.getenv("DASHBOARD_METRICS_MESSAGE")
        if env_metrics_id:
            message_ids["metrics"]["message"] = env_metrics_id
            print(f"[METRICS INIT] 從環境變數加載 metrics message ID: {env_metrics_id}")
    
    # 實際的 metrics 更新任務
    async def actual_metrics_task():
        """每 {GCP_METRICS_UPDATE_INTERVAL_MINUTES} 分鐘更新一次 GCP Metrics embed"""
        try:
            print(f"[METRICS TASK] 開始更新 GCP Metrics（{bot_type_str}）")
            
            channel = bot_instances[bot_type_str].get_channel(DASHBOARD_CHANNEL_ID)
            if not channel:
                print("[METRICS TASK ERROR] 找不到儀表板頻道")
                return
            
            # 嘗試導入 metrics monitor（延遲導入以避免啟動延遲）
            try:
                from gcp_metrics_monitor import GCPMetricsMonitor
                monitor = GCPMetricsMonitor(project_id="kkgroup")
                if not monitor.available:
                    print("[METRICS TASK] GCP Monitor 不可用，跳過更新")
                    return
            except ImportError:
                print("[METRICS TASK] 無法導入 GCP Metrics Monitor")
                return
            
            # 檢查快取 - 如果有有效的快取數據，跳過 API 調用
            cached = metrics_cache.get()
            if cached:
                print("[METRICS TASK] 使用快取數據，避免 API 調用")
                data_points, billing_info, monthly_gb = cached
            else:
                # 從 API 獲取新數據（帶超時保護）
                try:
                    data_points = await asyncio.wait_for(
                        monitor.get_network_egress_data(hours=6),
                        timeout=10.0
                    )
                    billing_info = await asyncio.wait_for(
                        monitor.get_billing_data(),
                        timeout=10.0
                    )
                    monthly_gb = await asyncio.wait_for(
                        monitor.get_monthly_egress_data(days=30),
                        timeout=15.0
                    )
                    
                    # 存儲到快取
                    metrics_cache.set((data_points, billing_info, monthly_gb))
                    print(f"[METRICS TASK] 成功獲取 metrics 數據（{len(data_points)} 數據點)")
                    
                except asyncio.TimeoutError:
                    print("[METRICS TASK] ⏱️ Metrics API 調用超時")
                    return
                except Exception as e:
                    print(f"[METRICS TASK ERROR] 獲取 metrics 數據失敗: {e}")
                    return
            
            # 收集系統信息（不使用快取，每次都更新以保持最新）
            try:
                sys_stats = await asyncio.wait_for(
                    monitor.get_system_stats(),
                    timeout=10.0
                )
                print(f"[METRICS TASK] 系統信息已收集: {sys_stats}")
            except asyncio.TimeoutError:
                print("[METRICS TASK] ⏱️ 系統信息獲取超時")
                sys_stats = {'cpu': None, 'mem': None, 'disk': None}
            except Exception as e:
                print(f"[METRICS TASK] 系統信息收集失敗: {e}")
                sys_stats = {'cpu': None, 'mem': None, 'disk': None}
            
            # 創建 embed（包含系統信息）
            embed = monitor.create_metrics_embed(
                data_points=data_points,
                billing_info=billing_info,
                monthly_gb=monthly_gb,
                sys_stats=sys_stats
            )
            embed.set_footer(text=f"每 {GCP_METRICS_UPDATE_INTERVAL_MINUTES} 分鐘自動更新 | 台灣時間 • {get_taiwan_time().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 生成圖表（非同步 + 線程執行器避免阻塞）
            chart_file = await monitor.generate_metrics_chart_async(
                data_points=data_points,
                monthly_cost=float(billing_info.get('total_cost', 0)) if billing_info.get('total_cost') else None
            )
            
            # 查找或創建 metrics message
            message_id = message_ids["metrics"]["message"]
            if message_id:
                try:
                    msg = await channel.fetch_message(int(message_id))
                    # 編輯現有訊息（同時更新 embed 和附件）
                    if chart_file:
                        await msg.edit(embed=embed, attachments=[chart_file])
                    else:
                        await msg.edit(embed=embed)
                    print(f"[METRICS TASK] metrics embed 已更新")
                except discord.NotFound:
                    print("[METRICS TASK] metrics 訊息不存在，重新發送")
                    msg = await channel.send(embed=embed, file=chart_file)
                    message_ids["metrics"]["message"] = msg.id
                    save_message_ids("metrics")
            else:
                # 創建新訊息
                msg = await channel.send(embed=embed, file=chart_file)
                message_ids["metrics"]["message"] = msg.id
                save_message_ids("metrics")
                print(f"[METRICS TASK] metrics embed 已創建: {msg.id}")
            
        except Exception as e:
            print(f"[METRICS TASK ERROR] 執行失敗: {e}")
            traceback.print_exc()
    
    task = tasks.loop(minutes=GCP_METRICS_UPDATE_INTERVAL_MINUTES)(actual_metrics_task)
    task.__name__ = f"metrics_task_{bot_type_str}"
    return task

def add_log(bot_type: str, message: str):
    """添加日誌條目。

    以前會在訊息前加上時間戳記，現在改為只儲存純文字，
    以避免 embed 內出現重複時間標籤。
    """
    if bot_type in logs_storage:
        log_entry = message  # 直接保存文字，不附加時間
        logs_storage[bot_type].append(log_entry)
        print(f"[LOG-{bot_type}] {message}")  # 確保打印
        save_logs()
    else:
        print(f"[ERROR] bot_type '{bot_type}' 不存在於logs_storage")

def get_logs_text(bot_type: str) -> str:
    """獲取格式化的日誌文本

    舊日誌可能含有時間前綴（例如 "[12:00:00] ..."），
    顯示時會自動移除以保持整潔。
    """
    if bot_type not in logs_storage:
        return "無日誌"
    
    logs = list(logs_storage[bot_type])
    if not logs:
        return "無日誌"
    
    # 移除可能存在的時間戳記前綴和控制字符
    cleaned = []
    for entry in logs[::-1]:  # 最新在最上面
        # 匹配開頭 [hh:mm:ss] 或 [hh:mm]
        text = re.sub(r"^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*", "", entry)
        # 移除控制字符（不可打印字符），保留中文和常见符号
        text = ''.join(c for c in text if ord(c) >= 32 or c in '\t\n')
        if text.strip():  # 只添加非空行
            cleaned.append(text)
    return "\n".join(cleaned)


def clear_logs(bot_type: str) -> None:
    """清空指定機器人的應用日誌並立即儲存。

    用於初始化或手動重置，避免舊日誌在儀表板中殘留。
    """
    if bot_type in logs_storage:
        logs_storage[bot_type].clear()
        save_logs()
        print(f"[LOG] {bot_type} 日誌已清空")
    else:
        print(f"[LOG WARN] 未找到 {bot_type} 的日誌儲存區")

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
    初始化儀表板 - 簡化版本，只初始化日誌
    
    Args:
        bot_instance: Discord bot instance
        bot_type_str: "bot", "shopbot", "uibot"
    """
    print(f"[INIT] initialize_dashboard called for {bot_type_str}")
    print(f"[DEBUG] GCP_METRICS_ENABLED={GCP_METRICS_ENABLED}, GCP_METRICS_ONLY_BOT_RESPONSIBLE={GCP_METRICS_ONLY_BOT_RESPONSIBLE}")
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
        
        # 清理舊日誌 embed 並初始化新的
        found_logs = None
        logs_count = 0
        old_logs = []
        
        # 查找現有日誌訊息（只查找由當前 bot 發送的）
        async for msg in channel.history(limit=100):
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
                print(f"✓ 已清理舊的 {bot_type_str} 日誌")
            except Exception as e:
                print(f"⚠️ 清理舊日誌失敗 {msg.id}: {e}")
        
        # 創建或更新日誌embed
        if not found_logs:
            # 沒有找到現有的，創建新的
            try:
                logs_embed = await create_logs_embed(bot_type_str)
                logs_msg = await channel.send(embed=logs_embed)
                message_ids[bot_type_str]["logs"] = logs_msg.id
                save_message_id(bot_type_str, "logs", str(logs_msg.id))
                print(f"✅ 初始化時創建 {bot_type_str} 日誌: {logs_msg.id}")
                add_log(bot_type_str, f"✅ 日誌系統已初始化")
            except Exception as e:
                print(f"⚠️ 初始化時創建日誌失敗: {e}")
                return False
        else:
            # 有現有的，保存ID供後續更新
            message_ids[bot_type_str]["logs"] = found_logs.id
            save_message_ids(bot_type_str)
            print(f"✅ 使用現有 {bot_type_str} 日誌: {found_logs.id}")
            add_log(bot_type_str, f"✅ 日誌系統已就緒")
        
        # 清空初始日誌，防止重複累積
        logs_storage[bot_type_str].clear()
        save_logs()
        
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
            
            # ===== METRICS 初始化 =====
            if bot_type_str == GCP_METRICS_ONLY_BOT_RESPONSIBLE and GCP_METRICS_ENABLED:
                print(f"[METRICS INIT] 為 {bot_type_str} 初始化 metrics")
                try:
                    # 直接發送一個初始的 metrics embed  
                    from gcp_metrics_monitor import GCPMetricsMonitor
                    monitor = GCPMetricsMonitor(project_id="kkgroup")
                    if monitor.available:
                        print(f"[METRICS INIT] 嘗試獲取初始 metrics 數據...")
                        try:
                            data_points = await asyncio.wait_for(
                                monitor.get_network_egress_data(hours=6),
                                timeout=10.0
                            )
                            billing_info = await asyncio.wait_for(
                                monitor.get_billing_data(),
                                timeout=10.0
                            )
                            monthly_gb = await asyncio.wait_for(
                                monitor.get_monthly_egress_data(days=30),
                                timeout=15.0
                            )
                            
                            # 收集系統信息
                            sys_stats = await asyncio.wait_for(
                                monitor.get_system_stats(),
                                timeout=10.0
                            )
                            print(f"[METRICS INIT] 系統信息已收集: {sys_stats}")
                            
                            embed = monitor.create_metrics_embed(
                                data_points=data_points,
                                billing_info=billing_info,
                                monthly_gb=monthly_gb,
                                sys_stats=sys_stats
                            )
                            embed.set_footer(text=f"初始化時生成 | 台灣時間 • {get_taiwan_time().strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            chart_file = await monitor.generate_metrics_chart_async(
                                data_points=data_points,
                                monthly_cost=float(billing_info.get('total_cost', 0)) if billing_info.get('total_cost') else None
                            )
                            
                            # 發送或更新 metrics embed
                            metrics_msg_id = os.getenv("DASHBOARD_METRICS_MESSAGE")
                            if metrics_msg_id:
                                try:
                                    msg = await channel.fetch_message(int(metrics_msg_id))
                                    if chart_file:
                                        await msg.edit(embed=embed, attachments=[chart_file])
                                    else:
                                        await msg.edit(embed=embed)
                                    print(f"[METRICS INIT] ✅ Metrics embed 已更新: {metrics_msg_id}")
                                except discord.NotFound:
                                    print(f"[METRICS INIT] 舊消息不存在，創建新的")
                                    msg = await channel.send(embed=embed, file=chart_file)
                                    set_key(".env", "DASHBOARD_METRICS_MESSAGE", str(msg.id))
                                    print(f"[METRICS INIT] ✅ Metrics embed 已創建: {msg.id}")
                            else:
                                # 創建新消息
                                msg = await channel.send(embed=embed, file=chart_file)
                                set_key(".env", "DASHBOARD_METRICS_MESSAGE", str(msg.id))
                                print(f"[METRICS INIT] ✅ Metrics embed 已創建: {msg.id}")
                            
                            # 現在啟動定時任務
                            print(f"[METRICS INIT] 啟動定時 metrics 更新任務...")
                            metrics_task = await create_metrics_update_task(bot_type_str)
                            metrics_tasks[bot_type_str] = metrics_task
                            metrics_task.start()
                            print(f"[METRICS INIT] ✅ Metrics 任務已啟動")
                            
                        except asyncio.TimeoutError:
                            print(f"[METRICS INIT] ⏱️ 初始 metrics 獲取超時")
                        except Exception as e:
                            print(f"[METRICS INIT ERROR] 初始 metrics 生成失敗: {e}")
                    else:
                        print(f"[METRICS INIT] Monitor 不可用")
                except ImportError:
                    print(f"[METRICS INIT] 無法導入 GCPMetricsMonitor")
                except Exception as e:
                    print(f"[METRICS INIT ERROR] {e}")
            else:
                if bot_type_str != GCP_METRICS_ONLY_BOT_RESPONSIBLE:
                    print(f"[METRICS INIT] ⏸️ {bot_type_str} 不負責 metrics（只有 {GCP_METRICS_ONLY_BOT_RESPONSIBLE} 負責）")
                    
        except Exception as e:
            print(f"[DASHBOARD ERROR] {bot_type_str} 任務啟動失敗: {e}")
            traceback.print_exc()
        
        return True
                
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

# ===== METRICS 更新任務 (動態創建) =====
# 注意：具體的任務在 initialize_dashboard 中為每個 bot 類型動態創建
# 只有 bot 類型會實際執行更新；其他類型是 NO-OP
# 如需手動啟用/禁用，修改 GCP_METRICS_ENABLED 標誌


# Starting a tasks.loop before the event loop is running can trigger
# a "coroutine 'Loop._loop' was never awaited" warning.  Instead we
# schedule the start so that it executes on the first iteration of the
# asyncio loop.  If the loop is already running we start immediately.

def _start_watchdog():
    try:
        # 檢查 update_task_watchdog 是否已在運行
        if not update_task_watchdog.is_running():
            update_task_watchdog.start()
            print("[WATCHDOG] 更新任務守護程序已啟動")
        else:
            print("[WATCHDOG] 更新任務守護程序已在運行中")
        
        # ⏸️ 暫停 GCP Metrics 圖表生成以隔離連線穩定性問題
        # Metrics 圖表生成（matplotlib）可能導致事件循環阻塞和心跳超時
        # 待完全 debug 後重新啟用
        print("[METRICS TASK] ⏸️ GCP Metrics 圖表生成 DISABLED（debug 中）- 等待連線穩定度驗證")
    except Exception as e:
        # swallow startup errors; they will be retried in bot init
        print(f"[WATCHDOG ERROR] 無法啟動守護程序: {e}")
        traceback.print_exc()

# If there is a running loop, start right away; otherwise queue the
# helper to run when the loop starts.
try:
    _loop = asyncio.get_running_loop()
except RuntimeError:
    _loop = None

if _loop and _loop.is_running():
    _start_watchdog()
else:
    # schedule for when the event loop begins
    try:
        asyncio.get_event_loop().call_soon(_start_watchdog)
    except Exception:
        # the very first import may not have a loop yet; ignore silently
        pass

def save_message_ids(bot_type: str):
    """將訊息 ID 保存到 .env（簡化版本，只保留日誌）

    為了避免 .env 權限錯誤導致整個腳本崩潰，
    任何 write 操作都在 try/except 塊中捕獲異常並記錄。
    """
    env_path = ".env"

    try:
        if bot_type == "metrics":
            # 特殊處理 metrics message ID（已禁用）
            metrics_id = message_ids["metrics"].get("message")
            if metrics_id:
                set_key(env_path, "DASHBOARD_METRICS_MESSAGE", str(metrics_id))
        else:
            # 只保存日誌 ID
            logs_id = message_ids[bot_type].get("logs")
            if logs_id:
                env_key = f"DASHBOARD_{bot_type.upper()}_LOGS"
                set_key(env_path, env_key, str(logs_id))
    except Exception as e:
        # 不讓任何寫入失敗中斷初始化流程
        print(f"[ENV WRITE ERROR] 無法保存 {bot_type} 訊息 ID 到 .env: {e}")

def load_message_ids(bot_type: str):
    """從 .env 加載訊息 ID，如果沒有則使用硬編碼的回退值（簡化版本，只加載日誌）"""
    
    if bot_type == "metrics":
        # 特殊處理 metrics message ID（已禁用）
        metrics_id = os.getenv("DASHBOARD_METRICS_MESSAGE")
        if metrics_id:
            message_ids["metrics"]["message"] = int(metrics_id)
            print(f"[LOAD IDS] Metrics 訊息 ID: {metrics_id}")
        else:
            message_ids["metrics"]["message"] = None
    else:
        # 只加載日誌 ID
        logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")

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

# REMOVED: update_dashboard 已被移除 - 日誌更新由 update_dashboard_logs 處理