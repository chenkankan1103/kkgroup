# -*- coding: utf-8 -*-
"""
🪝 GitHub Webhook 接收器
當代碼 push 到 GitHub 時自動拉取更新並重啟 bot 服務

功能:
1. 接收 GitHub webhook 推送事件
2. 驗證 webhook 簽名（安全）
3. 執行 git pull + systemctl restart
4. 發送結果回報到 Discord
5. 審計日誌 - 記錄所有 webhook 請求
6. 速率限制 - 防止暴力觸發
"""

import os
import hmac
import hashlib
import subprocess
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify
import logging
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 設置日誌
logger = logging.getLogger(__name__)

# 加載環境變數 - 明確指定 .env 路徑
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(env_path)
logger.info(f"📁 加載 .env 文件: {env_path} (存在: {os.path.exists(env_path)})")

# 建立 Blueprint
webhook_bp = Blueprint("webhook", __name__, url_prefix="/webhook")

# 常數配置
PROJECT_DIR = Path("/home/e193752468/kkgroup")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID", "")
SYSTEMD_SERVICES = [
    "bot.service",
    "shopbot.service",
    "uibot.service",
    "auto-self-heal.service",
]

# ============================================================
# 速率限制 & 審計
# ============================================================

# 速率限制：最多每 60 秒允許 1 次觸發
WEBHOOK_RATE_LIMIT = 60  # 秒
webhook_last_trigger = {}  # IP -> timestamp

# 審計日誌
audit_log_file = Path(__file__).parent.parent.parent / "logs" / "webhook_audit.log"
audit_log_file.parent.mkdir(parents=True, exist_ok=True)


def log_audit(ip, status, message, payload_info=""):
    """
    記錄 webhook 審計日誌

    Args:
        ip: 請求來源 IP
        status: 'ALLOWED', 'REJECTED', 'RATE_LIMITED', 'INVALID_SIGNATURE'
        message: 詳細信息
        payload_info: 載荷信息（commit 數、分支等）
    """
    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        log_entry = {
            "timestamp": timestamp,
            "ip": ip,
            "status": status,
            "message": message,
            "payload": payload_info,
        }

        with open(audit_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        logger.info(f"📋 [AUDIT] {status} | IP: {ip} | {message}")
    except Exception as e:
        logger.error(f"❌ 審計日誌記錄失敗: {e}")


def check_rate_limit(ip):
    """
    檢查速率限制

    Returns:
        (is_allowed, time_remaining)
    """
    now = datetime.utcnow().timestamp()
    last_time = webhook_last_trigger.get(ip, 0)
    time_diff = now - last_time

    if time_diff < WEBHOOK_RATE_LIMIT:
        return False, WEBHOOK_RATE_LIMIT - time_diff

    webhook_last_trigger[ip] = now
    return True, 0


# ============================================================
# Webhook 簽名驗證
# ============================================================


def verify_github_signature(payload_body, signature_header):
    """
    驗證 GitHub webhook 簽名 (強制檢查版本)

    Args:
        payload_body (bytes): webhook 的原始 body
        signature_header (str): GitHub 發送的簽名 header (X-Hub-Signature-256)

    Returns:
        bool: 簽名是否有效

    安全考量:
    - 如果未設置 SECRET，則拒絕所有 webhook（不是跳過驗證）
    - 使用常時間比較防止時序攻擊
    - 記錄所有簽名驗證失敗
    """
    # 🔴 強制檢查：未設置 SECRET 時拒絕 webhook
    if not GITHUB_WEBHOOK_SECRET:
        logger.error("🚨 CRITICAL: GITHUB_WEBHOOK_SECRET 未設置！無法驗證 webhook 簽名")
        logger.error("🚨 為了安全起見，已拒絕此 webhook 請求")
        logger.error("🚨 請在 .env 文件中設置 GITHUB_WEBHOOK_SECRET")
        return False

    if not signature_header:
        logger.warning("⚠️ 缺少 X-Hub-Signature-256 header")
        return False

    # GitHub 使用 SHA-256，格式為 "sha256=xxxxx"
    try:
        signature = hmac.new(
            GITHUB_WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
        ).hexdigest()

        expected = f"sha256={signature}"

        # 常時間比較（防止時序攻擊）
        is_valid = hmac.compare_digest(expected, signature_header)

        if not is_valid:
            logger.warning("⚠️ Webhook 簽名不匹配")
            logger.debug(f"   期望: {expected[:20]}...")
            logger.debug(f"   收到: {signature_header[:20]}...")

        return is_valid

    except Exception as e:
        logger.error(f"❌ 簽名驗證異常: {e}")
        return False


# ============================================================
# Git 操作
# ============================================================


def execute_git_pull():
    """
    執行 git pull 並更新代碼
    """
    try:
        logger.info("📥 開始執行 git pull...")

        # 移除鎖檔（如果存在）
        lockfile = PROJECT_DIR / ".git/index.lock"
        if lockfile.exists():
            try:
                lockfile.unlink()
                logger.info("移除遺留的 .git/index.lock")
            except Exception as e:
                logger.warning(f"無法刪除鎖檔: {e}")

        # 執行 git fetch + reset
        result = subprocess.run(
            ["git", "fetch"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logger.error(f"❌ git fetch 失敗: {result.stderr}")
            return False, f"git fetch 失敗: {result.stderr}"

        # 強制重置到最新
        result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logger.error(f"❌ git reset 失敗: {result.stderr}")
            return False, f"git reset 失敗: {result.stderr}"

        logger.info("✅ Git pull 成功")
        return True, "Git pull 成功"

    except subprocess.TimeoutExpired:
        logger.error("⏱️ git 操作超時")
        return False, "Git 操作超時"
    except Exception as e:
        logger.error(f"❌ Git 操作失敗: {e}")
        return False, str(e)


def restart_services():
    """
    重啟所有 systemd 服務
    """
    try:
        logger.info("🔄 開始重啟服務...")

        # 重新加載 systemd 配置
        subprocess.run(
            ["sudo", "systemctl", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        success_count = 0
        failed_services = []

        for service in SYSTEMD_SERVICES:
            try:
                result = subprocess.run(
                    ["sudo", "systemctl", "restart", service],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    logger.info(f"✅ {service} 重啟成功")
                    success_count += 1
                else:
                    logger.error(f"❌ {service} 重啟失敗: {result.stderr}")
                    failed_services.append(service)

            except Exception as e:
                logger.error(f"❌ 重啟 {service} 異常: {e}")
                failed_services.append(service)

        if failed_services:
            return False, f"部分服務重啟失敗: {', '.join(failed_services)}"

        logger.info("✅ 所有服務重啟成功")
        return True, "所有服務重啟成功"

    except Exception as e:
        logger.error(f"❌ 服務重啟失敗: {e}")
        return False, str(e)


# ============================================================
# Discord 通知
# ============================================================


def send_discord_notification_thread(title, description, color, details=None):
    """
    在後臺線程中發送 Discord 通知（避免 Flask 異步問題）
    """
    if not DISCORD_BOT_TOKEN or not DISCORD_SYS_CHANNEL_ID:
        logger.warning("⚠️ 缺少 Discord 配置，跳過通知")
        return

    try:
        # 在新的事件循環中運行異步代碼
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_send_discord_embed(title, description, color, details))
        loop.close()
    except Exception as e:
        logger.error(f"❌ Discord 線程異常: {e}")


async def _send_discord_embed(title, description, color, details=None):
    """
    異步發送 Discord embed
    """
    try:
        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!", intents=intents)

        @bot.event
        async def on_ready():
            try:
                channel_id = int(DISCORD_SYS_CHANNEL_ID)
                channel = bot.get_channel(channel_id)

                if not channel:
                    channel = await bot.fetch_channel(channel_id)

                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=color,
                    timestamp=datetime.now(),
                )

                if details:
                    for name, value in details.items():
                        embed.add_field(
                            name=name,
                            value=f"```\n{value}\n```" if len(value) > 50 else value,
                            inline=False,
                        )

                embed.set_footer(text="🪝 GitHub Webhook 自動部署")
                await channel.send(embed=embed)
                logger.info("✅ Discord 通知已發送")

            except Exception as e:
                logger.error(f"❌ Discord 通知失敗: {e}")
            finally:
                await bot.close()

        # 用超時保護防止掛起
        await asyncio.wait_for(bot.start(DISCORD_BOT_TOKEN), timeout=15)

    except asyncio.TimeoutError:
        logger.warning("⏱️ Discord 通知超時")
    except Exception as e:
        logger.error(f"❌ Discord 通知異常: {e}")


def notify_discord(title, description, color, details=None):
    """
    在後臺線程中異步發送 Discord 通知
    """
    thread = threading.Thread(
        target=send_discord_notification_thread,
        args=(title, description, color, details),
        daemon=True,
    )
    thread.start()
    # 不等待線程完成，立即返回


# ============================================================
# Webhook 路由
# ============================================================


@webhook_bp.route("/github", methods=["HEAD", "OPTIONS"])
def github_webhook_head():
    """
    允許 HEAD 和 OPTIONS 請求用於 webhook 連線測試和 CORS 預檢
    """
    return "", 200


@webhook_bp.route("/github", methods=["POST"])
def github_webhook():
    """
    接收 GitHub webhook 推送事件 (帶審計和速率限制)

    GitHub 配置:
    1. 進入倉庫設置 → Webhooks
    2. Payload URL: https://your-vm-ip:your-port/webhook/github
    3. Content type: application/json
    4. Secret: 設置一個強密碼，存入 .env 的 GITHUB_WEBHOOK_SECRET
    5. 選擇事件: Push events
    6. Active: 打勾
    """

    # 獲取客戶端 IP（考慮代理）
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    logger.info(f"📥 收到 webhook 請求 | IP: {client_ip}")

    # ============================================================
    # 第 1 層：速率限制檢查
    # ============================================================
    is_allowed, time_remaining = check_rate_limit(client_ip)
    if not is_allowed:
        logger.warning(
            f"🚫 速率限制 | IP: {client_ip} | 剩餘等待時間: {time_remaining:.1f}s"
        )
        log_audit(client_ip, "RATE_LIMITED", f"須等待 {time_remaining:.1f}s", "")
        return jsonify(
            {
                "status": "rate_limited",
                "message": f"請求過於頻繁，請在 {time_remaining:.1f} 秒後再試",
                "retry_after": int(time_remaining) + 1,
            }
        ), 429

    # ============================================================
    # 第 2 層：簽名驗證
    # ============================================================
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    payload_body = request.get_data()

    if not verify_github_signature(payload_body, signature_header):
        logger.warning(f"🔐 簽名驗證失敗 | IP: {client_ip}")
        log_audit(client_ip, "INVALID_SIGNATURE", "Webhook 簽名驗證失敗", "")
        return jsonify({"status": "error", "message": "簽名驗證失敗"}), 401

    logger.info(f"✅ 簽名驗證成功 | IP: {client_ip}")

    # ============================================================
    # 第 3 層：JSON 解析
    # ============================================================
    try:
        payload = request.get_json()
    except Exception as e:
        logger.error(f"❌ JSON 解析失敗: {e}")
        log_audit(client_ip, "REJECTED", f"JSON 解析失敗: {str(e)}", "")
        return jsonify({"status": "error", "message": "JSON 解析失敗"}), 400

    try:
        # ============================================================
        # 第 4 層：事件類型和分支檢查
        # ============================================================
        event_type = request.headers.get("X-GitHub-Event", "")

        if event_type != "push":
            logger.info(f"⏭️ 忽略非 push 事件 (類型: {event_type})")
            log_audit(
                client_ip,
                "ALLOWED",
                f"已忽略 {event_type} 事件",
                f"event_type={event_type}",
            )
            return jsonify(
                {"status": "ok", "message": f"已忽略 {event_type} 事件"}
            ), 200

        logger.info("🔔 收到 GitHub push 事件")

        # 獲取提交信息
        ref = payload.get("ref", "")
        branch_name = ref.replace("refs/heads/", "")
        commits = payload.get("commits", [])
        commit_messages = [c.get("message", "").split("\n")[0] for c in commits[:3]]

        logger.info(f"📌 分支: {branch_name}")
        logger.info(f"📝 提交數: {len(commits)}")
        if commit_messages:
            logger.info(f"📋 最近提交: {commit_messages[0][:50]}...")

        payload_info = f"branch={branch_name}, commits={len(commits)}"

        # 只處理 main 分支
        if branch_name != "main":
            logger.info(f"⏭️ 忽略分支 {branch_name}，僅監控 main")
            log_audit(client_ip, "ALLOWED", f"已忽略分支 {branch_name}", payload_info)
            return jsonify({"status": "ok", "message": "已忽略該分支"}), 200

        logger.info("🚀 開始執行自動部署流程...")
        log_audit(client_ip, "ALLOWED", f"開始部署 {branch_name}", payload_info)

        # 執行更新和重啟
        pull_success, pull_msg = execute_git_pull()

        if not pull_success:
            logger.error(f"❌ 部署失敗: {pull_msg}")
            log_audit(client_ip, "REJECTED", f"Git pull 失敗: {pull_msg}", payload_info)
            # 發送失敗通知（在後臺線程中）
            notify_discord(
                "❌ GitHub Webhook 部署失敗",
                f"Git pull 失敗: {pull_msg}",
                0xFF0000,
                {"錯誤": pull_msg},
            )
            return jsonify(
                {"status": "error", "message": "Git pull 失敗", "details": pull_msg}
            ), 500

        # Git pull 成功，重啟服務
        restart_success, restart_msg = restart_services()

        if restart_success:
            logger.info("✅ 部署成功！所有服務已重啟")
            log_audit(client_ip, "ALLOWED", f"部署成功 | {restart_msg}", payload_info)

            # 構建通知內容
            commit_msgs = [c.get("message", "").split("\n")[0] for c in commits[:5]]
            details = {
                "分支": branch_name,
                "提交數": str(len(commits)),
                "最新提交": "\n".join(commit_msgs) if commit_msgs else "無",
                "服務狀態": "✅ 所有服務已重啟",
            }

            notify_discord(
                "✅ GitHub Webhook 自動部署成功",
                f"已成功拉取 {len(commits)} 個提交並重啟所有服務",
                0x00FF00,
                details,
            )

            return jsonify(
                {
                    "status": "success",
                    "message": "自動部署完成",
                    "details": {"git_pull": pull_msg, "restart": restart_msg},
                }
            ), 200
        else:
            logger.error(f"❌ 部分服務重啟失敗: {restart_msg}")
            log_audit(
                client_ip, "ALLOWED", f"部分部署失敗 | {restart_msg}", payload_info
            )

            notify_discord(
                "⚠️ GitHub Webhook 部分部署失敗",
                f"Git pull 成功，但某些服務重啟失敗: {restart_msg}",
                0xFFFF00,
                {"錯誤": restart_msg},
            )

            return jsonify(
                {
                    "status": "partial",
                    "message": "部分部署失敗",
                    "details": {"git_pull": pull_msg, "restart": restart_msg},
                }
            ), 206

    except Exception as e:
        logger.error(f"❌ Webhook 處理異常: {e}")
        import traceback

        logger.error(traceback.format_exc())

        return jsonify(
            {"status": "error", "message": "伺服器內部錯誤", "error": str(e)}
        ), 500


@webhook_bp.route("/health", methods=["GET"])
def webhook_health():
    """
    Webhook 健康檢查
    """
    return jsonify(
        {
            "status": "ok",
            "service": "GitHub Webhook Receiver",
            "configured": bool(GITHUB_WEBHOOK_SECRET),
            "discord_enabled": bool(DISCORD_BOT_TOKEN and DISCORD_SYS_CHANNEL_ID),
        }
    ), 200
