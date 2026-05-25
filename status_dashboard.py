"""
統一監控儀表板管理系統
優先將三個 bot 的即時日誌發到論壇頻道 thread；若未配置論壇，再回退到一般文字頻道。
存儲 message_id / thread_id 到 .env 文件。

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
from types import SimpleNamespace
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
# 40 行日誌約 4400 字符（含標題/頁腳），接近 Discord embed 4000 字符限制
# 每 10 分鐘更新一次，平衡信息密度與 API 調用成本
SYSTEMD_LOG_CONFIG = {
    "bot": {"service": "bot.service", "lines": 40, "enabled": True},
    "shopbot": {"service": "shopbot.service", "lines": 40, "enabled": True},
    "uibot": {"service": "uibot.service", "lines": 40, "enabled": True}
}

# 控制 journalctl 查詢超時時間（秒）
# 現在已移除超時機制，因此該變數僅做為歷史備註，未被使用。
SYSTEMD_FETCH_TIMEOUT = 10.0  # unused

def get_taiwan_time():
    """獲取台灣時間"""
    return datetime.now(TAIWAN_TZ)

def format_taiwan_time():
    """格式化台灣時間為 MM-DD HH:MM (含日期)"""
    return get_taiwan_time().strftime("%m-%d %H:%M")


def clamp_embed_description(text: str, limit: int = 4096) -> str:
    """將 embed description 安全限制在 Discord 上限內。"""
    value = str(text or "")
    if len(value) <= limit:
        return value

    suffix = "\n```\n...[logs truncated]"
    head_limit = max(0, limit - len(suffix))
    truncated = value[:head_limit].rstrip()

    if truncated.endswith("```"):
        truncated = truncated[:-3].rstrip()

    return f"{truncated}{suffix}"

# 配置常數
MAX_STARTUP_WAIT_SECONDS = 60  # 最多等待機器人就緒的時間（秒）

# 不再使用舊訊息 ID 作為硬編碼回退。
HARDCODED_MESSAGE_IDS = {}

DEFAULT_FORUM_CHANNEL_ID = "1504438347974705152"
DASHBOARD_FORUM_CHANNEL_ID = int(
    os.getenv("DASHBOARD_FORUM_CHANNEL_ID")
    or os.getenv("LOG_FORUM_CHANNEL_ID")
    or DEFAULT_FORUM_CHANNEL_ID
)
LEGACY_DASHBOARD_CHANNEL_ID = int(
    "0"
)
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

        # 構建 journalctl 命令 - 直接獲取最後 N 行（不使用 --since 篩選）
        # 這樣可以保證總是獲取最新的日誌，不會因為時間戳問題而返回空結果
        cmd = [
            "/usr/bin/journalctl", "-u", service_name,
            "-n", str(lines), "--no-pager", "-o", "short-iso"
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
                            # 移除重複的服務名稱前綴（bot:, shopbot:, uibot:）以節省字數
                            message = re.sub(r"^(bot|shopbot|uibot):\s+", "", message)
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

# Message ID 存儲（每個機器人獨立，只保留日誌）
message_ids = {
    "bot": {"logs": None},
    "shopbot": {"logs": None},
    "uibot": {"logs": None}
}

thread_ids = {
    "bot": None,
    "shopbot": None,
    "uibot": None,
}

# 機器人實例存儲（每個機器人獨立）
bot_instances = {}

BOT_CONFIG = {
    "bot": {"名稱": "🤖 Main Bot", "顏色": discord.Color.blue(), "emoji": "🤖"},
    "shopbot": {"名稱": "🛍️ Shop Bot", "顏色": discord.Color.purple(), "emoji": "🛍️"},
    "uibot": {"名稱": "🎨 UI Bot", "顏色": discord.Color.gold(), "emoji": "🎨"}
}

THREAD_ENV_KEYS = {
    "bot": "DASHBOARD_BOT_THREAD_ID",
    "shopbot": "DASHBOARD_SHOPBOT_THREAD_ID",
    "uibot": "DASHBOARD_UIBOT_THREAD_ID",
}

THREAD_NAMES = {
    "bot": "🤖 Main Bot 即時日誌",
    "shopbot": "🛍️ Shop Bot 即時日誌",
    "uibot": "🎨 UI Bot 即時日誌",
}

# 追蹤當前機器人類型（在初始化時設置）
current_bot_type = None

# 每個機器人的獨立更新任務存儲
update_tasks = {}

# lock to prevent concurrent chart generation (serialize requests)
chart_generation_lock = asyncio.Lock()

# list of bots for which we suppress the routine start/finish logs
# now quiet all of them to eliminate per-minute console noise
# 恢復正常運行 - 只在非迴圈機器人時打印調試訊息
QUIET_UPDATE_BOTS = {"bot", "shopbot", "uibot"}

def create_update_task(bot_type: str):
    """為指定機器人創建獨立的更新任務"""

    # helper that prints only when verbosity is enabled for this bot
    def task_log(message: str):
        if bot_type not in QUIET_UPDATE_BOTS:
            print(message)

    async def individual_update_task():
        """Individual bot log update task - updates only own logs"""
        # First startup with random delay (0~60s) to avoid concurrent edits causing 429
        if not hasattr(individual_update_task, "_task_jittered"):
            individual_update_task._task_jittered = True
            # Delay import won't affect global random
            jitter = random.uniform(0, 60)
            task_log(f"[UPDATE TASK {bot_type}] First update delay {jitter:.1f}s")
            await asyncio.sleep(jitter)
        try:
            task_log(f"[UPDATE TASK {bot_type}] ===== Starting update for {bot_type} logs =====")
            # print(f"[UPDATE TASK {bot_type}] Starting loop execution", flush=True)  # Disabled to reduce log spam

            # Check bot instance
            if bot_type not in bot_instances:
                # print(f"[UPDATE TASK {bot_type}] Instance not found - cancelling task", flush=True)  # Disabled
                return

            bot_instance = get_bot_instance(bot_type)
            if not bot_instance:
                # print(f"[UPDATE TASK {bot_type}] Instance is null - cancelling task", flush=True)  # Disabled
                return

            # System status logging removed (prevent spam)

            # Only update logs (dashboard removed)
            try:
                task_log(f"[UPDATE TASK {bot_type}] Starting log update")
                # print(f"[UPDATE TASK {bot_type}] Calling update_dashboard_logs...", flush=True)  # Disabled
                await update_dashboard_logs(bot_instance, bot_type)
                task_log(f"[UPDATE TASK {bot_type}] Log update completed")
                # print(f"[UPDATE TASK {bot_type}] update_dashboard_logs completed", flush=True)  # Disabled
            except Exception as e:
                # print(f"[UPDATE TASK {bot_type} ERROR] Log update failed: {e}", flush=True)  # Keep ERROR disabled
                with open("update_task_errors.log", "a", encoding="utf-8") as ef:
                    ef.write(f"[{datetime.now(TAIWAN_TZ)}] Log update failed: {e}\n")
                    traceback.print_exc(file=ef)
                traceback.print_exc()

            task_log(f"[UPDATE TASK {bot_type}] ===== {bot_type} update completed =====")
            # print(f"[UPDATE TASK {bot_type}] Loop execution completed", flush=True)  # Disabled

        except Exception as e:
            # errors should always be visible even for quiet bots
            # print(f"[UPDATE TASK {bot_type} ERROR] Task execution failed: {e}", flush=True)  # Disabled
            task_log(f"[UPDATE TASK {bot_type} ERROR] Task execution failed: {e}")
            with open("update_task_errors.log", "a", encoding="utf-8") as ef:
                ef.write(f"[{datetime.now(TAIWAN_TZ)}] Task execution failed: {e}\n")
                traceback.print_exc(file=ef)
            traceback.print_exc()

    # 創建任務對象 - 每 10 分鐘檢查一次日誌
    # 如果內容相同會跳過 Discord 編輯，減少不必要的 API 調用
    # 
    # 流量估算：
    # - 每 600 秒（10 分鐘）× 3 機器人 = 最多 3 次 API edits（如果日誌改變）
    # - 每天 = 3 × 144 次 = ~432 次 API 調用
    # - 智能緩存會跳過內容未改變的編輯，實際調用數更少
    # - 主要網路開銷是本地 systemd journalctl 查詢（無外部流量）
    task = tasks.loop(minutes=10)(individual_update_task)
    task.__name__ = f"update_task_{bot_type}"

    return task

def register_bot_instance(bot_type: str, bot_instance):
    """Register bot instance and ensure update task starts"""
    bot_instances[bot_type] = bot_instance
    print(f"[REGISTER] {bot_type} instance recorded, starting update task", flush=True)

    # Ensure corresponding update task exists and starts (prevent initialize_dashboard failure)
    if bot_type not in update_tasks:
        try:
            print(f"[REGISTER] Creating new update task for {bot_type}...", flush=True)
            update_task = create_update_task(bot_type)
            print(f"[REGISTER] {bot_type} update task created, preparing to start", flush=True)
            update_tasks[bot_type] = update_task
            print(f"[REGISTER] Preparing to call .start()...", flush=True)
            update_task.start()
            print(f"[REGISTER] ✅ {bot_type} update task started successfully", flush=True)
        except Exception as e:
            print(f"[REGISTER ERROR] Failed to start {bot_type} update task: {e}", flush=True)
            import traceback
            traceback.print_exc()
    else:
        print(f"[REGISTER] {bot_type} update task already exists, skipping creation", flush=True)

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


def get_thread_id(bot_type: str) -> Optional[int]:
    return thread_ids.get(bot_type)


def save_thread_id(bot_type: str, thread_id: int):
    thread_ids[bot_type] = int(thread_id)
    save_message_ids(bot_type)


async def resolve_dashboard_target(bot, bot_type: str, create_if_missing: bool = False):
    forum_channel = bot.get_channel(DASHBOARD_FORUM_CHANNEL_ID) if DASHBOARD_FORUM_CHANNEL_ID else None
    if forum_channel is None and DASHBOARD_FORUM_CHANNEL_ID:
        try:
            forum_channel = await bot.fetch_channel(DASHBOARD_FORUM_CHANNEL_ID)
        except Exception:
            forum_channel = None
    if isinstance(forum_channel, discord.ForumChannel):
        saved_thread_id = get_thread_id(bot_type)
        thread = None
        if saved_thread_id:
            thread = bot.get_channel(saved_thread_id)
            if thread is None:
                for guild in bot.guilds:
                    thread = guild.get_thread(saved_thread_id)
                    if thread:
                        break
            if thread is None:
                try:
                    thread = await bot.fetch_channel(saved_thread_id)
                except Exception:
                    thread = None
        if thread is None and create_if_missing:
            created = await forum_channel.create_thread(
                name=THREAD_NAMES[bot_type],
                content=f"{BOT_CONFIG[bot_type]['名稱']} 日誌 thread（由 status_dashboard 自動維護）",
            )
            thread = created.thread
            save_thread_id(bot_type, thread.id)
        if thread:
            return SimpleNamespace(channel=thread, container=forum_channel, is_forum=True)

    legacy_channel = bot.get_channel(LEGACY_DASHBOARD_CHANNEL_ID) if LEGACY_DASHBOARD_CHANNEL_ID else None
    if legacy_channel:
        return SimpleNamespace(channel=legacy_channel, container=legacy_channel, is_forum=False)
    return None

# keep last rendered logs to prevent duplicate edits
last_logs_text: Dict[str, str] = {}

async def update_dashboard_logs(bot, bot_type: str):
    """Update logs for specified bot"""
    try:
        if bot_type not in QUIET_UPDATE_BOTS:
            print(f"[UPDATE LOGS] Starting log update for {bot_type}")

        # Check bot instance
        if not bot:
            print(f"[UPDATE LOGS ERROR] {bot_type} bot instance is null")
            return

        # Fetch only systemd logs
        systemd_logs = await get_systemd_logs(bot_type)
        combined_logs = ""
        if systemd_logs and systemd_logs not in ["No systemd logs", "Systemd logs disabled"]:
            combined_logs = f"📊 **Systemd Logs**\n```\n{systemd_logs}\n```"

        # If combined result is empty, both sides have no data; skip update to preserve old content
        if not combined_logs:
            if bot_type not in QUIET_UPDATE_BOTS:
                print(f"[UPDATE LOGS] {bot_type} no new logs, preserving existing content")
            return
        logs_text = combined_logs

        # Check if content is same as last time; if so, skip edit to reduce 429
        if last_logs_text.get(bot_type) == logs_text:
            if bot_type not in QUIET_UPDATE_BOTS:
                print(f"[UPDATE LOGS] {bot_type} log content unchanged, skipping edit")
            return
        last_logs_text[bot_type] = logs_text

        logs_text = clamp_embed_description(logs_text)


        # Create logs embed
        config = BOT_CONFIG.get(bot_type, {})
        embed = discord.Embed(
            title=f"{config['名稱']} 即時日誌",
            description=logs_text,
            color=config["顏色"]
            # Don't set timestamp so time doesn't appear at top of embed
        )

        embed.set_footer(text=f"有新日誌時即時更新 | 台灣時間 {format_taiwan_time()}")

        # Update message
        message_id = get_message_id(bot_type, "logs")
        
        target = await resolve_dashboard_target(bot, bot_type, create_if_missing=True)
        if not target or not target.channel:
            print(f"[UPDATE LOGS ERROR] {bot_type} unable to find dashboard target")
            return
        channel = target.channel
            
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(embed=embed)
            except asyncio.CancelledError:
                # network or task cancelled; just log and return so periodic task can retry
                if bot_type not in QUIET_UPDATE_BOTS:
                    print(f"[UPDATE LOGS] {bot_type} fetch_message was cancelled, skipping this cycle")
                return
            except discord.NotFound:
                if bot_type not in QUIET_UPDATE_BOTS:
                    print(f"[UPDATE LOGS] {bot_type} log message does not exist, recreating")
                try:
                    message = await channel.send(embed=embed, silent=True)
                    save_message_id(bot_type, "logs", str(message.id))
                    if bot_type not in QUIET_UPDATE_BOTS:
                        print(f"[UPDATE LOGS] {bot_type} log message recreated: {message.id}")
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"[UPDATE LOGS ERROR] {bot_type} failed to create new message: {e}")
            except discord.Forbidden:
                print(f"[UPDATE LOGS ERROR] {bot_type} no permission to edit message")
            except Exception as e:
                # catch-all for other errors; print traceback
                print(f"[UPDATE LOGS ERROR] {bot_type} log update error: {e}")
                traceback.print_exc()
        else:
            # Message ID doesn't exist, create new logs embed
            try:
                # Check if existing logs embed exists before creating
                existing_logs = []
                async for msg in channel.history(limit=20):
                    if msg.author.id == bot.user.id and msg.embeds:
                        for embed in msg.embeds:
                            if "即時日誌" in embed.title and BOT_CONFIG[bot_type]["名稱"] in embed.title:
                                existing_logs.append(msg)

                # If existing embed exists, update latest and delete others
                if existing_logs:
                    # Keep latest embed, delete others
                    existing_logs.sort(key=lambda m: m.created_at, reverse=True)
                    latest_msg = existing_logs[0]

                    # Delete duplicate embeds
                    for msg in existing_logs[1:]:
                        try:
                            await msg.delete()
                            print(f"[CLEANUP] Deleted duplicate log embed: {msg.id}")
                        except (discord.Forbidden, discord.HTTPException) as e:
                            print(f"[CLEANUP ERROR] Failed to delete duplicate embed {msg.id}: {e}")

                    # Update preserved embed
                    await latest_msg.edit(embed=embed)
                    message_ids[bot_type]["logs"] = latest_msg.id
                    save_message_ids(bot_type)
                    if bot_type not in QUIET_UPDATE_BOTS:
                        print(f"[UPDATE LOGS] {bot_type} updated existing logs embed: {latest_msg.id}")
                else:
                    # No embed found, create new one
                    message = await channel.send(embed=embed, silent=True)
                    message_ids[bot_type]["logs"] = message.id
                    save_message_ids(bot_type)
                    if bot_type not in QUIET_UPDATE_BOTS:
                        print(f"[UPDATE LOGS] {bot_type} created new logs embed: {message.id}")

            except Exception as create_error:
                print(f"[UPDATE LOGS ERROR] {bot_type} failed to create/update logs embed: {create_error}")

    except Exception as e:
        print(f"[UPDATE LOGS ERROR] {bot_type} unexpected error updating logs: {e}")
        traceback.print_exc()

# ========== 日誌管理系統 ==========

async def create_logs_embed(bot_type: str) -> discord.Embed:
    """Create logs Embed"""
    config = BOT_CONFIG.get(bot_type, {})
    embed = discord.Embed(
        title=f"{config['名稱']} 即時日誌",
        color=config['顏色']
    )
    
    # Log functionality removed, display placeholder text
    embed.description = "`日誌記錄中`"
    
    embed.set_footer(text="每 10 分鐘更新最多 4000 字")
    return embed

async def initialize_dashboard(bot_instance: discord.Client, bot_type_str: str):
    """
    初始化儀表板 - 簡化版本，只初始化日誌
    
    Args:
        bot_instance: Discord bot instance
        bot_type_str: "bot", "shopbot", "uibot"
    """
    print(f"[INIT] initialize_dashboard started bot_type={bot_type_str}", flush=True)
    
    # Add delay to avoid simultaneous initialization
    delay_map = {"bot": 0, "shopbot": 5, "uibot": 10}
    delay = delay_map.get(bot_type_str, 0)
    if delay > 0:
        print(f"[INIT] {bot_type_str} waiting {delay}s before initialization...", flush=True)
        await asyncio.sleep(delay)
    
    # current_bot_type tracking completed in function signature
    
    # Load message IDs (including hardcoded fallback values)
    print(f"[INIT] Loading message IDs for {bot_type_str}...", flush=True)
    load_message_ids(bot_type_str)
    
    try:
        print(f"[INIT] Resolving dashboard target for {bot_type_str}...", flush=True)
        with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] Resolving dashboard target for {bot_type_str}\n")
            f.flush()

        target = await resolve_dashboard_target(bot_instance, bot_type_str, create_if_missing=True)
        channel = target.channel if target else None
        if not channel:
            with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] ERROR: Dashboard target not found for {bot_type_str}\n")
                f.flush()
            print(f"X [INIT] Cannot find dashboard target for {bot_type_str}", flush=True)
            return False

        with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] OK: Found dashboard target {getattr(channel, 'id', 'unknown')}\n")
            f.flush()
        print(f"[INIT] OK Found dashboard target {getattr(channel, 'id', 'unknown')}", flush=True)
        
        # Clean up old log embeds and initialize new ones
        found_logs = None
        logs_count = 0
        old_logs = []
        
        # Find existing log messages (only from current bot)
        async for msg in channel.history(limit=100):
            if msg.author.id != bot_instance.user.id:
                continue  # Skip messages from other bots
            
            if msg.embeds:
                for embed in msg.embeds:
                    bot_name = BOT_CONFIG[bot_type_str]["名稱"]
                    if "即時日誌" in embed.title and bot_name in embed.title:
                        logs_count += 1
                        if logs_count <= 1:
                            found_logs = msg
                        else:
                            old_logs.append(msg)
        
        print(f"[INIT] Found {logs_count} existing log embeds", flush=True)
        
        # Clean up old log embeds
        for msg in old_logs:
            try:
                await msg.delete()
                print(f"OK [INIT] Cleaned up old {bot_type_str} logs", flush=True)
            except Exception as e:
                print(f"WARN [INIT] Failed to clean up old logs {msg.id}: {e}", flush=True)
        
        # Create or update logs embed
        if not found_logs:
            # No existing found, create new one
            try:
                with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] Creating new logs embed for {bot_type_str}...\n")
                    f.flush()
                print(f"[INIT] Creating new logs embed for {bot_type_str}...", flush=True)
                logs_embed = await create_logs_embed(bot_type_str)
                with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] Sending new logs embed to channel...\n")
                    f.flush()
                print(f"[INIT] Sending new logs embed to channel...", flush=True)
                # First send without flags, then edit with flags if needed
                logs_msg = await channel.send(embed=logs_embed)
                # Try to edit with suppress_notifications flag
                try:
                    await logs_msg.edit(suppress=True)
                except:
                    pass  # Flag setting is optional, don't fail if not supported
                message_ids[bot_type_str]["logs"] = logs_msg.id
                save_message_id(bot_type_str, "logs", str(logs_msg.id))
                with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] OK: Created {bot_type_str} logs: {logs_msg.id}\n")
                    f.flush()
                print(f"OK [INIT] Created {bot_type_str} logs: {logs_msg.id}", flush=True)
                add_log(bot_type_str, "OK Log system initialized")
            except Exception as e:
                with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] ERROR creating logs: {e}\n")
                    import traceback
                    traceback.print_exc(file=f)
                    f.flush()
                print(f"WARN [INIT] Failed to create logs: {e}", flush=True)
                import traceback
                traceback.print_exc()
                return False
        else:
            # Has existing, save ID for future updates
            message_ids[bot_type_str]["logs"] = found_logs.id
            save_message_ids(bot_type_str)
            print(f"OK [INIT] Using existing {bot_type_str} logs: {found_logs.id}", flush=True)
            add_log(bot_type_str, "OK Log system ready")
        
        # Clear initial logs, prevent duplicate accumulation
        # logs_storage may not contain key yet, use setdefault to ensure exists
        logs_storage.setdefault(bot_type_str, []).clear()
        save_logs()
        
        # Metrics initialization removed
        
        # Register bot instance and start independent update task
        try:
            with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] About to register {bot_type_str} bot instance...\n")
                f.flush()
            print(f"[INIT] About to register {bot_type_str} bot instance...", flush=True)
            register_bot_instance(bot_type_str, bot_instance)
            with open("/tmp/dashboard_init.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] OK {bot_type_str} instance registered successfully\n")
                f.flush()
            print(f"[INIT] OK {bot_type_str} instance registered successfully", flush=True)

            # Create and start independent update task for current bot
            print(f"[INIT] Checking {bot_type_str} update task status...", flush=True)
            if bot_type_str not in update_tasks:
                print(f"[INIT] Task does not exist, creating new one...", flush=True)
                update_task = create_update_task(bot_type_str)
                update_tasks[bot_type_str] = update_task
                print(f"[INIT] Starting {bot_type_str} update task...", flush=True)
                update_task.start()
                print(f"[INIT] OK {bot_type_str} independent update task started", flush=True)
            else:
                # If task exists but unexpectedly stopped, restart
                existing = update_tasks[bot_type_str]
                if not existing.is_running():
                    print(f"[INIT] {bot_type_str} task stopped, restarting...", flush=True)
                    try:
                        existing.start()
                    except Exception as restart_error:
                        print(f"[INIT ERROR] Failed to restart {bot_type_str} task: {restart_error}", flush=True)
                else:
                    print(f"[INIT] OK {bot_type_str} update task already running", flush=True)
            
            # Metrics initialization removed
            print(f"[INIT] OK {bot_type_str} initialization completed", flush=True)
                    
        except Exception as e:
            print(f"[INIT ERROR] {bot_type_str} task startup failed: {e}", flush=True)
            traceback.print_exc()
        
        return True
                
    except Exception as e:
        print(f"X [INIT] Initialization failed: {e}", flush=True)
        traceback.print_exc()
        return False

# Watchdog daemon for update tasks, periodically detects and restarts stopped update tasks
@tasks.loop(minutes=5)
async def update_task_watchdog():
    # If no tasks in dict, try to create for all registered bots
    if not update_tasks:
        print("[WATCHDOG] No update tasks exist yet, attempting to create for registered bots")
        for bot_type in bot_instances.keys():
            if bot_type not in update_tasks:
                try:
                    t = create_update_task(bot_type)
                    update_tasks[bot_type] = t
                    t.start()
                    print(f"[WATCHDOG] Created and started update task for {bot_type}")
                except Exception as e:
                    print(f"[WATCHDOG ERROR] Failed to create task for {bot_type}: {e}")

    for bot_type, task in list(update_tasks.items()):
        if not task.is_running():
            print(f"[WATCHDOG] {bot_type} update task stopped, attempting restart")
            try:
                task.start()
            except Exception as e:
                print(f"[WATCHDOG ERROR] Failed to restart {bot_type} task: {e}")

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
        # Check if update_task_watchdog is already running
        if not update_task_watchdog.is_running():
            update_task_watchdog.start()
            print("[WATCHDOG] Update task watchdog started")
        else:
            print("[WATCHDOG] Update task watchdog already running")
        
        # PAUSE GCP Metrics chart generation to isolate connection stability issues
        # Metrics chart generation (matplotlib) may cause event loop blocking and heartbeat timeouts
        # Will re-enable after full debugging
        print("[METRICS TASK] PAUSE GCP Metrics chart generation DISABLED (debugging) - waiting for connection stability verification")
    except Exception as e:
        # swallow startup errors; they will be retried in bot init
        print(f"[WATCHDOG ERROR] Failed to start watchdog: {e}")
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
        # 只保存日誌 ID
        logs_id = message_ids[bot_type].get("logs")
        if logs_id:
            env_key = f"DASHBOARD_{bot_type.upper()}_LOGS"
            set_key(env_path, env_key, str(logs_id))

        thread_id = thread_ids.get(bot_type)
        if thread_id:
            set_key(env_path, THREAD_ENV_KEYS[bot_type], str(thread_id))
    except Exception as e:
        # 不讓任何寫入失敗中斷初始化流程
        print(f"[ENV WRITE ERROR] 無法保存 {bot_type} 訊息 ID 到 .env: {e}")

def load_message_ids(bot_type: str):
    """從 .env 加載訊息與 thread ID（簡化版本，只加載日誌）"""
    
    # 只加載日誌 ID
    logs_id = os.getenv(f"DASHBOARD_{bot_type.upper()}_LOGS")

    if logs_id:
        message_ids[bot_type]["logs"] = int(logs_id)
        print(f"[LOAD IDS] {bot_type} 日誌 ID: {logs_id}")
    else:
        message_ids[bot_type]["logs"] = None
        print(f"[LOAD IDS] {bot_type} 日誌 ID 未設置")

    thread_id = os.getenv(THREAD_ENV_KEYS[bot_type])
    thread_ids[bot_type] = int(thread_id) if thread_id else None

# REMOVED: update_dashboard 已被移除 - 日誌更新由 update_dashboard_logs 處理