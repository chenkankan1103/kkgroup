# -*- coding: utf-8 -*-
"""
🪝 GitHub Webhook 接收器
當代碼 push 到 GitHub 時自動拉取更新並重啟 bot 服務

功能:
1. 接收 GitHub webhook 推送事件
2. 驗證 webhook 簽名（安全）
3. 執行 git pull + systemctl restart
4. 發送結果回報到 Discord
"""

import os
import sys
import hmac
import hashlib
import subprocess
import asyncio
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

# 加載環境變數
load_dotenv()

# 建立 Blueprint
webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')

# 常數配置
PROJECT_DIR = Path("/home/e193752468/kkgroup")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_SYS_CHANNEL_ID = os.getenv("DISCORD_SYS_CHANNEL_ID", "")
SYSTEMD_SERVICES = ["bot.service", "shopbot.service", "uibot.service"]

# ============================================================
# Webhook 簽名驗證
# ============================================================

def verify_github_signature(payload_body, signature_header):
    """
    驗證 GitHub webhook 簽名
    
    Args:
        payload_body (bytes): webhook 的原始 body
        signature_header (str): GitHub 發送的簽名 header (X-Hub-Signature-256)
    
    Returns:
        bool: 簽名是否有效
    """
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("⚠️ 未設置 GITHUB_WEBHOOK_SECRET，跳過簽名驗證")
        return True
    
    # GitHub 使用 SHA-256，格式為 "sha256=xxxxx"
    signature = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    expected = f"sha256={signature}"
    
    # 常時間比較（防止時序攻擊）
    return hmac.compare_digest(expected, signature_header)


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
            timeout=60
        )
        
        if result.returncode != 0:
            logger.error(f"❌ git fetch 失敗: {result.stderr}")
            return False, f"git fetch 失敗: {result.stderr}"
        
        # 強制重置到最新
        result = subprocess.run(
            ["git", "reset", "--hard", "origin/restructure-project-20260414"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=60
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
            timeout=30
        )
        
        success_count = 0
        failed_services = []
        
        for service in SYSTEMD_SERVICES:
            try:
                result = subprocess.run(
                    ["sudo", "systemctl", "restart", service],
                    capture_output=True,
                    text=True,
                    timeout=30
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

async def send_discord_notification(title, description, color, details=None):
    """
    發送 Discord 通知
    """
    if not DISCORD_BOT_TOKEN or not DISCORD_SYS_CHANNEL_ID:
        logger.warning("⚠️ 缺少 Discord 配置，跳過通知")
        return
    
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
                timestamp=datetime.now()
            )
            
            if details:
                for name, value in details.items():
                    embed.add_field(
                        name=name,
                        value=f"```\n{value}\n```" if len(value) > 50 else value,
                        inline=False
                    )
            
            embed.set_footer(text="🪝 GitHub Webhook 自動部署")
            await channel.send(embed=embed)
            logger.info("📢 Discord 通知已發送")
            
        except Exception as e:
            logger.error(f"❌ Discord 通知失敗: {e}")
        finally:
            await bot.close()
    
    try:
        await asyncio.wait_for(bot.start(DISCORD_BOT_TOKEN), timeout=15)
    except asyncio.TimeoutError:
        logger.warning("⏱️ Discord 通知超時")
    except Exception as e:
        logger.error(f"❌ Discord 通知異常: {e}")


# ============================================================
# Webhook 路由
# ============================================================

@webhook_bp.route('/github', methods=['POST'])
def github_webhook():
    """
    接收 GitHub webhook 推送事件
    
    GitHub 配置:
    1. 進入倉庫設置 → Webhooks
    2. Payload URL: https://your-vm-ip:your-port/webhook/github
    3. Content type: application/json
    4. Secret: 設置一個強密碼，存入 .env 的 GITHUB_WEBHOOK_SECRET
    5. 選擇事件: Push events
    6. Active: 打勾
    """
    
    # 驗證簽名
    signature_header = request.headers.get('X-Hub-Signature-256', '')
    payload_body = request.get_data()
    
    if not verify_github_signature(payload_body, signature_header):
        logger.warning("❌ Webhook 簽名驗證失敗")
        return jsonify({"status": "error", "message": "簽名驗證失敗"}), 401
    
    try:
        payload = request.get_json()
    except Exception as e:
        logger.error(f"❌ JSON 解析失敗: {e}")
        return jsonify({"status": "error", "message": "JSON 解析失敗"}), 400
    
    # 檢查推送事件
    if payload.get('action') == 'opened' or 'push' in request.headers.get('X-GitHub-Event', ''):
        logger.info("🔔 收到 GitHub push 事件")
        
        # 獲取提交信息
        ref = payload.get('ref', '')
        branch_name = ref.replace('refs/heads/', '')
        commits = payload.get('commits', [])
        
        logger.info(f"📌 分支: {branch_name}")
        logger.info(f"📝 提交數: {len(commits)}")
        
        # 只處理 restructure-project-20260414 分支
        if branch_name != 'restructure-project-20260414':
            logger.info(f"⏭️ 忽略分支 {branch_name}，仅監控 restructure-project-20260414")
            return jsonify({"status": "ok", "message": "已忽略該分支"}), 200
        
        # 執行更新和重啟
        logger.info("🚀 開始執行自動部署流程...")
        
        pull_success, pull_msg = execute_git_pull()
        
        if not pull_success:
            logger.error(f"❌ 部署失敗: {pull_msg}")
            # 發送失敗通知
            asyncio.run(send_discord_notification(
                "❌ GitHub Webhook 部署失敗",
                f"Git pull 失敗: {pull_msg}",
                0xFF0000,
                {"錯誤": pull_msg}
            ))
            return jsonify({
                "status": "error",
                "message": "Git pull 失敗",
                "details": pull_msg
            }), 500
        
        # Git pull 成功，重啟服務
        restart_success, restart_msg = restart_services()
        
        if restart_success:
            logger.info("✅ 部署成功！所有服務已重啟")
            
            # 構建通知內容
            commit_msgs = [c.get('message', '').split('\n')[0] for c in commits[:5]]
            details = {
                "分支": branch_name,
                "提交數": str(len(commits)),
                "最新提交": "\n".join(commit_msgs) if commit_msgs else "無",
                "服務狀態": "✅ 所有服務已重啟"
            }
            
            asyncio.run(send_discord_notification(
                "✅ GitHub Webhook 自動部署成功",
                f"已成功拉取 {len(commits)} 個提交並重啟所有服務",
                0x00FF00,
                details
            ))
            
            return jsonify({
                "status": "success",
                "message": "自動部署完成",
                "details": {
                    "git_pull": pull_msg,
                    "restart": restart_msg
                }
            }), 200
        else:
            logger.error(f"❌ 部分服務重啟失敗: {restart_msg}")
            
            asyncio.run(send_discord_notification(
                "⚠️ GitHub Webhook 部分部署失敗",
                f"Git pull 成功，但某些服務重啟失敗: {restart_msg}",
                0xFFFF00,
                {"錯誤": restart_msg}
            ))
            
            return jsonify({
                "status": "partial",
                "message": "部分部署失敗",
                "details": {
                    "git_pull": pull_msg,
                    "restart": restart_msg
                }
            }), 206
    
    except Exception as e:
        logger.error(f"❌ Webhook 處理異常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return jsonify({
            "status": "error",
            "message": "伺服器內部錯誤",
            "error": str(e)
        }), 500


@webhook_bp.route('/health', methods=['GET'])
def webhook_health():
    """
    Webhook 健康檢查
    """
    return jsonify({
        "status": "ok",
        "service": "GitHub Webhook Receiver",
        "configured": bool(GITHUB_WEBHOOK_SECRET),
        "discord_enabled": bool(DISCORD_BOT_TOKEN and DISCORD_SYS_CHANNEL_ID)
    }), 200
