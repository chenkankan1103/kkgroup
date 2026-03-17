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

# 控制 journalctl 查詢超時時間（秒）
# 現在已移除超時機制，因此該變數僅做為歷史備註，未被使用。
SYSTEMD_FETCH_TIMEOUT = 10.0  # unused

def get_taiwan_time():
    """獲取台灣時間"""
    return datetime.now(TAIWAN_TZ)

def format_taiwan_time():
    """格式化台灣時間為 HH:MM"""
    return get_taiwan_time().strftime("%H:%M")

# 配置常數
MAX_STARTUP_WAIT_SECONDS = 60  # 最多等待機器人就緒的時間（秒）

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
LOGS_CAPACITY = 10  # 保存最近 10 條日誌（目前未使用）

# 應用日誌功能已移除，保留常數作為註解。
logs_storage = {}

# add_log used to record application-level logs. 這個功能已經移除，
# 但部分初始化路徑仍會呼叫它；為避免 NameError，我們保留一個
# 空實現作為兼容。
def add_log(_bot_type: str, _message: str):
    # no-op placeholder - 應用日誌功能已移除
    return

logs_file = None  # unused

# GCP Metrics 追蹤上次的 embed 內容（避免重複更新）
last_metrics_text = ""

# keep track of last fetch time for each bot to avoid re-reading the same log
_last_log_fetch: Dict[str, datetime] = {}

async def get_systemd_logs(bot_type: str) -> Optional[str]:
    """從 systemd journal 獲取指定機器人的日誌

    為了降低磁碟 I/O，僅抓取自上次查詢以來的新條目。
    初次呼叫會使用 "10 minutes ago" 作為保底，之後視為迭代式。
    查詢包含兩個 await，執行時間不再受限（不使用超時保護），
    這意味著 journalctl 的 I/O 開銷如果很大，任務會等到完成再回應。

    呼叫方仍然會在日誌文本超長時截斷，以避免 Discord embed
    超過 4000 字符的限制。
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

        # 異步執行命令；移除超時保護，使 journalctl 執行時間不限
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

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
        print("[LOGS ERROR] 嘗試使用不同的編碼讀取文件")
    except Exception as e:
        print(f"[LOGS ERROR] 未預期的錯誤加載日誌: {e}")
        traceback.print_exc()

def save_logs():
    """保存日誌到文件 - 改進的錯誤處理

    如果 logs_file 尚未設置（None），直接返回，不執行任何操作。
    """
    if not logs_file:
        # 日誌功能已移除，無需保存
        return
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
        print("[LOGS ERROR] 編碼錯誤 - 日誌數據包含無法編碼的字符")
        print(f"  詳情: {e}")
    except Exception as e:
        print(f"[LOGS ERROR] 未預期的錯誤保存日誌: {e}")
        traceback.print_exc()

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

# lock to prevent concurrent chart generation (serialize requests)
chart_generation_lock = asyncio.Lock()

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
        if not hasattr(individual_update_task, "_task_jittered"):
            individual_update_task._task_jittered = True
            # 延遲導入不會影響全域 random
            jitter = random.uniform(0, 60)
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

            # 系統狀態日誌已移除（防止洗版）

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

        # 僅獲取 systemd 日誌
        systemd_logs = await get_systemd_logs(bot_type)
        combined_logs = ""
        if systemd_logs and systemd_logs not in ["無 systemd 日誌", "Systemd 日誌已停用"]:
            combined_logs = f"📊 **Systemd 日誌**\n```\n{systemd_logs}\n```"

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

        # 先前為防止超過 Discord embed 限制而截斷，
        # 現在 embed 允許達到完整 4000 字符，故不再主動截取。
        # Discord 在輸入超過限制時會拒絕，因此保留此註解以備未來調整。


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
                    print(f"[UPDATE LOGS] {bot_type} fetch_message 被中止，跳過此循環")
                return
            except discord.NotFound:
                if bot_type not in QUIET_UPDATE_BOTS:
                    print(f"[UPDATE LOGS] {bot_type} 日誌訊息不存在，重新創建")
                try:
                    message = await channel.send(embed=embed)
                    save_message_id(bot_type, "logs", str(message.id))
                    if bot_type not in QUIET_UPDATE_BOTS:
                        print(f"[UPDATE LOGS] {bot_type} 日誌訊息已重新創建: {message.id}")
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"[UPDATE LOGS ERROR] {bot_type} 創建新訊息失敗: {e}")
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
                        except (discord.Forbidden, discord.HTTPException) as e:
                            print(f"[CLEANUP ERROR] 刪除重複embed失敗 {msg.id}: {e}")

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

# ========== GCP Metrics 管理系統 ==========

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

# Metrics 函數已移除 - 不再監測出站流量和計費

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
    
    # 日誌功能已移除，顯示占位文字
    embed.description = "`日誌功能已停用`"
    
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
    
    # 添加延遲以避免同時初始化
    delay_map = {"bot": 0, "shopbot": 5, "uibot": 10}
    delay = delay_map.get(bot_type_str, 0)
    if delay > 0:
        print(f"[DASHBOARD] {bot_type_str} 等待 {delay} 秒後初始化...")
        await asyncio.sleep(delay)
    
    # current_bot_type 追蹤已在函式簽名中完成
    
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
                add_log(bot_type_str, "✅ 日誌系統已初始化")
            except Exception as e:
                print(f"⚠️ 初始化時創建日誌失敗: {e}")
                return False
        else:
            # 有現有的，保存ID供後續更新
            message_ids[bot_type_str]["logs"] = found_logs.id
            save_message_ids(bot_type_str)
            print(f"✅ 使用現有 {bot_type_str} 日誌: {found_logs.id}")
            add_log(bot_type_str, "✅ 日誌系統已就緒")
        
        # 清空初始日誌，防止重複累積
        # logs_storage 可能尚未包含鍵，因此使用 setdefault 保證存在
        logs_storage.setdefault(bot_type_str, []).clear()
        save_logs()
        
        # Metrics 初始化已移除
        
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
            
            # Metrics 初始化已移除
                    
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