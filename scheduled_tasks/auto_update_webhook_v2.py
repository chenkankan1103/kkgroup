#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 改進版自動更新 GitHub Webhook 隧道 URL
使用 requests 庫替代 curl，加入重試邏輯、詳細日誌和 Discord 告警

使用方式：
  python3 auto_update_webhook_v2.py
  
  crontab: */5 * * * * cd /home/e193752468/kkgroup && python3 scheduled_tasks/auto_update_webhook_v2.py >> /var/log/webhook_auto_update_v2.log 2>&1
"""

import os
import json
import sys
import re
import time
from pathlib import Path
from datetime import datetime
import logging
from dotenv import load_dotenv
import subprocess

# 嘗試導入 requests，如果失敗則使用 urllib
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

# 加載 .env 文件
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# 設置日誌
log_dir = Path('/var/log')
if not log_dir.exists():
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

log_file = log_dir / 'webhook_auto_update_v2.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置
CONFIG_FILE = Path(__file__).parent.parent / 'config' / 'config.json'
WEBHOOK_CONFIG_FILE = Path(__file__).parent.parent / 'config' / 'webhook_config.json'
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', '321qwe321')
REPO_OWNER = 'chenkankan1103'
REPO_NAME = 'kkgroup'
WEBHOOK_ENDPOINT = '/webhook/github'
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_URL')
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def log_discord(message, is_error=False):
    """發送消息到 Discord（可選）"""
    if not DISCORD_WEBHOOK:
        return
    
    try:
        color = 0xFF6B6B if is_error else 0x4ECDC4
        payload = {
            "embeds": [{
                "title": "🤖 隧道 Webhook 更新",
                "description": message,
                "color": color,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        
        if HAS_REQUESTS:
            requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
        else:
            import urllib.request
            urllib.request.urlopen(
                urllib.request.Request(
                    DISCORD_WEBHOOK,
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                ),
                timeout=5
            )
    except Exception as e:
        logger.debug(f"Discord 通知失敗（非致命）: {e}")


def get_current_tunnel_url():
    """從 cloudflared 日誌提取當前隧道 URL - 改進版本"""
    logger.info("🔍 提取隧道 URL...")
    
    try:
        # 方案 1: 使用 subprocess + grep（更穩定）
        result = subprocess.run(
            ["grep", "-oP", r"https://[a-zA-Z0-9_-]+\.trycloudflare\.com"],
            input=subprocess.run(
                ["sudo", "journalctl", "-u", "cloudflared.service", "-n", "100", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10
            ).stdout,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        urls = [url.strip() for url in result.stdout.strip().split('\n') if url.strip()]
        if urls:
            current_url = urls[-1]  # 取最後一個（最新的）
            logger.info(f"✅ 提取到隧道 URL: {current_url}")
            return current_url
        else:
            logger.warning("⚠️ journalctl 中未找到隧道 URL")
            return None
            
    except Exception as e:
        logger.error(f"❌ 提取隧道 URL 失敗: {e}")
        return None


def load_webhook_config():
    """加載上次保存的 webhook 配置"""
    if WEBHOOK_CONFIG_FILE.exists():
        try:
            with open(WEBHOOK_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"✅ 加載 webhook 配置: {config}")
                return config
        except Exception as e:
            logger.warning(f"⚠️ 加載配置失敗: {e}")
    
    return {'tunnel_url': None, 'webhook_id': None}


def save_webhook_config(tunnel_url, webhook_id):
    """保存 webhook 配置"""
    try:
        config = {
            'tunnel_url': tunnel_url,
            'webhook_id': webhook_id,
            'last_updated': datetime.utcnow().isoformat() + "Z"
        }
        WEBHOOK_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(WEBHOOK_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 保存 webhook 配置")
    except Exception as e:
        logger.error(f"❌ 保存配置失敗: {e}")


def update_config_json(tunnel_url):
    """更新 config.json"""
    try:
        config = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        
        config['url'] = tunnel_url
        config['API_BASE'] = tunnel_url
        config['lastUpdated'] = datetime.utcnow().isoformat() + "Z"
        config['status'] = "✅ 隧道已恢復"
        
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ config.json 已更新: {tunnel_url}")
        return True
    except Exception as e:
        logger.error(f"❌ 更新 config.json 失敗: {e}")
        return False


def update_github_webhook(tunnel_url, retry_count=0):
    """使用 GitHub API 更新 webhook（帶重試邏輯）"""
    
    if not GITHUB_TOKEN:
        logger.warning("⚠️ 未設置 GITHUB_TOKEN，跳過 GitHub webhook 更新")
        return False
    
    webhook_url = f"{tunnel_url}{WEBHOOK_ENDPOINT}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "kkgroup-webhook-updater"
    }
    
    try:
        logger.info("🔍 查詢現有 webhook...")
        
        # 列出 webhooks
        if HAS_REQUESTS:
            response = requests.get(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks",
                headers=headers,
                timeout=10
            )
            webhooks = response.json()
        else:
            import urllib.request
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks",
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                webhooks = json.loads(response.read().decode('utf-8'))
        
        if not isinstance(webhooks, list):
            logger.error(f"❌ GitHub API 返回錯誤: {webhooks}")
            return False
        
        # 查找 webhook
        webhook_id = None
        for hook in webhooks:
            if WEBHOOK_ENDPOINT in hook.get('config', {}).get('url', ''):
                webhook_id = hook.get('id')
                old_url = hook.get('config', {}).get('url')
                logger.info(f"✅ 找到 webhook ID: {webhook_id}")
                logger.info(f"   舊 URL: {old_url}")
                logger.info(f"   新 URL: {webhook_url}")
                break
        
        if not webhook_id:
            logger.warning("⚠️ 找不到現有 webhook")
            return False
        
        # 更新 webhook
        logger.info(f"🔄 更新 webhook URL...")
        update_data = {
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": GITHUB_WEBHOOK_SECRET,
                "insecure_ssl": "0"
            },
            "events": ["push"],
            "active": True
        }
        
        if HAS_REQUESTS:
            response = requests.patch(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}",
                headers=headers,
                json=update_data,
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"✅ Webhook 已更新成功")
                log_discord(f"✅ Webhook 已更新成功\n新 URL: {webhook_url}")
                return True
            else:
                logger.error(f"❌ Webhook 更新失敗 (HTTP {response.status_code}): {response.text}")
                if retry_count < MAX_RETRIES:
                    logger.info(f"⏱️ 等待 {RETRY_DELAY} 秒後重試 ({retry_count + 1}/{MAX_RETRIES})...")
                    time.sleep(RETRY_DELAY)
                    return update_github_webhook(tunnel_url, retry_count + 1)
                return False
        else:
            import urllib.request
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}",
                data=json.dumps(update_data).encode('utf-8'),
                headers={**headers, 'Content-Type': 'application/json'},
                method='PATCH'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info(f"✅ Webhook 已更新成功")
                    log_discord(f"✅ Webhook 已更新成功\n新 URL: {webhook_url}")
                    return True
        
    except Exception as e:
        logger.error(f"❌ 更新 webhook 失敗: {e}")
        if retry_count < MAX_RETRIES:
            logger.info(f"⏱️ 等待 {RETRY_DELAY} 秒後重試 ({retry_count + 1}/{MAX_RETRIES})...")
            time.sleep(RETRY_DELAY)
            return update_github_webhook(tunnel_url, retry_count + 1)
        
        log_discord(f"❌ Webhook 更新失敗（已重試 {MAX_RETRIES} 次）\n錯誤: {str(e)}", is_error=True)
        return False


def git_commit_changes(tunnel_url):
    """git commit 和 push config.json"""
    try:
        repo_dir = Path(__file__).parent.parent
        
        logger.info("📝 git add config.json...")
        subprocess.run(
            ["git", "add", "config/config.json"],
            cwd=repo_dir,
            capture_output=True,
            timeout=10,
            check=True
        )
        
        logger.info("📝 git commit...")
        result = subprocess.run(
            ["git", "commit", "-m", f"Auto-update: Tunnel URL changed to {tunnel_url}"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logger.info("✅ git commit 成功")
            
            logger.info("📤 git push...")
            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if push_result.returncode == 0:
                logger.info("✅ git push 成功")
                log_discord(f"✅ Git 提交成功\n隧道已更新: {tunnel_url}")
                return True
            else:
                logger.warning(f"⚠️ git push 失敗: {push_result.stderr}")
        else:
            # 無變更可提交
            logger.info("ℹ️ 無變更需要提交")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Git 操作失敗: {e}")
        log_discord(f"❌ Git 操作失敗: {str(e)}", is_error=True)
        return False


def main():
    """主函數"""
    logger.info("=" * 60)
    logger.info("🚀 開始隧道 URL 自動更新檢查")
    logger.info("=" * 60)
    
    # 1. 提取當前隧道 URL
    current_url = get_current_tunnel_url()
    if not current_url:
        logger.error("❌ 無法提取隧道 URL，本次更新失敗")
        log_discord("❌ 無法提取隧道 URL - 隧道可能未啟動", is_error=True)
        return False
    
    # 2. 加載上次保存的配置
    old_config = load_webhook_config()
    old_url = old_config.get('tunnel_url')
    
    # 3. 檢查是否需要更新
    if current_url == old_url:
        logger.info(f"✅ 隧道 URL 無變化，無需更新")
        return True
    
    logger.warning(f"⚠️ 隧道 URL 已變更！")
    logger.warning(f"   舊 URL: {old_url}")
    logger.warning(f"   新 URL: {current_url}")
    log_discord(f"🚨 隧道 URL 已變更\n舊: {old_url}\n新: {current_url}")
    
    # 4. 更新 config.json
    if not update_config_json(current_url):
        logger.error("❌ config.json 更新失敗")
        return False
    
    # 5. 更新 GitHub webhook
    if not update_github_webhook(current_url):
        logger.error("❌ GitHub webhook 更新失敗")
        return False
    
    # 6. 保存配置
    save_webhook_config(current_url, old_config.get('webhook_id'))
    
    # 7. git commit
    if not git_commit_changes(current_url):
        logger.warning("⚠️ Git 提交失敗，但隧道 URL 已更新")
    
    logger.info("=" * 60)
    logger.info("✅ 隧道 URL 自動更新完成")
    logger.info("=" * 60)
    return True


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.exception(f"❌ 程式崩潰: {e}")
        log_discord(f"❌ webhook 更新程式崩潰\n錯誤: {str(e)}", is_error=True)
        sys.exit(1)
