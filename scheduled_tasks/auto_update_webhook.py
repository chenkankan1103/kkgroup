#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 自動更新 GitHub Webhook 隧道 URL (Python requests 版本)
監控隧道 URL 變化，自動更新 GitHub webhook 設定

使用方式：
  # 手動運行
  python3 auto_update_webhook.py
  
  # 或添加到 crontab（每 5 分鐘檢查一次）
  */5 * * * * cd /home/e193752468/kkgroup && python3 scheduled_tasks/auto_update_webhook.py
"""

import os
import json
import subprocess
import sys
import requests
from pathlib import Path
from datetime import datetime
import logging
from dotenv import load_dotenv

# 加載 .env 文件
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/var/log/webhook_auto_update.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置（使用絕對路徑）
PROJECT_DIR = Path('/home/e193752468/kkgroup')
WEBHOOK_CONFIG_FILE = PROJECT_DIR / 'config' / 'webhook_config.json'
CONFIG_FILE = PROJECT_DIR / 'config' / 'config.json'

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', '321qwe321')
REPO_OWNER = 'chenkankan1103'
REPO_NAME = 'kkgroup'
WEBHOOK_ENDPOINT = '/webhook/github'

# API 相關
GITHUB_API_BASE = 'https://api.github.com'
GITHUB_API_TIMEOUT = 10
RETRY_ATTEMPTS = 3
RETRY_DELAY = 1  # 秒


def get_current_tunnel_url():
    """從 cloudflared 日誌提取當前隧道 URL (改進版本)"""
    try:
        # 使用 shell 命令方式，提高兼容性
        cmd = 'sudo journalctl -u cloudflared.service -n 100 --no-pager | grep -o "https://[a-z0-9\\-]*\\.trycloudflare\\.com" | tail -1'
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
            check=False
        )
        
        url = result.stdout.strip() if result.stdout else None
        
        if url and 'trycloudflare.com' in url:
            logger.info(f"✅ 當前隧道 URL: {url}")
            return url
        
        # 備用方法：從 cloudflared 配置文件尋找 URL
        logger.warning("⚠️ 從日誌解析失敗，嘗試備用方法...")
        try:
            result2 = subprocess.run(
                'cat /root/.cloudflared/*.json 2>/dev/null || cat ~/.cloudflared/*.json 2>/dev/null || echo ""',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            
            if result2.stdout:
                import re
                match = re.search(r'"url":"(https://[a-z0-9\-]+\.trycloudflare\.com)"', result2.stdout)
                if match:
                    url = match.group(1)
                    logger.info(f"✅ 從配置文件獲取隧道 URL: {url}")
                    return url
        except:
            pass
        
        logger.error("❌ 無法獲取隧道 URL")
        return None
        
    except subprocess.TimeoutExpired:
        logger.error("❌ 命令執行超時（超過 15 秒）")
        return None
    except Exception as e:
        logger.error(f"❌ 提取隧道 URL 失敗: {e}")
        return None


def load_webhook_config():
    """加載上次保存的 webhook 配置"""
    try:
        if WEBHOOK_CONFIG_FILE.exists():
            with open(WEBHOOK_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info(f"✅ 加載 webhook 配置: tunnel_url={config.get('tunnel_url')}")
                return config
    except Exception as e:
        logger.error(f"⚠️ 加載配置失敗: {e}")
    
    return {'tunnel_url': None, 'webhook_id': None}


def save_webhook_config(tunnel_url, webhook_id):
    """保存 webhook 配置"""
    try:
        config = {
            'tunnel_url': tunnel_url,
            'webhook_id': webhook_id,
            'last_updated': datetime.now().isoformat()
        }
        WEBHOOK_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WEBHOOK_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"✅ 已保存 webhook 配置")
    except Exception as e:
        logger.error(f"❌ 保存配置失敗: {e}")


def get_github_webhooks():
    """使用 requests 獲取 GitHub webhook 列表"""
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN 未設置，無法獲取 webhook 列表")
        return None
    
    url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/hooks"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    for attempt in range(RETRY_ATTEMPTS):
        try:
            logger.info(f"🔍 查詢 GitHub webhook 列表 (嘗試 {attempt + 1}/{RETRY_ATTEMPTS})...")
            response = requests.get(url, headers=headers, timeout=GITHUB_API_TIMEOUT)
            
            logger.debug(f"HTTP 狀態碼: {response.status_code}")
            
            if response.status_code == 200:
                webhooks = response.json()
                logger.info(f"✅ 成功獲取 {len(webhooks)} 個 webhook")
                return webhooks
            
            elif response.status_code == 401:
                logger.error(f"❌ 認證失敗 (401): GitHub Token 無效或已過期")
                return None
            
            elif response.status_code == 403:
                logger.error(f"❌ 權限不足 (403): 檢查 GitHub Token 是否有 'repo_hook' 權限")
                return None
            
            else:
                logger.warning(f"⚠️ HTTP {response.status_code}: {response.text[:100]}")
                if attempt < RETRY_ATTEMPTS - 1:
                    logger.info(f"⏳ 稍後重試...")
                    import time
                    time.sleep(RETRY_DELAY)
                    continue
                return None
        
        except requests.exceptions.Timeout:
            logger.error(f"❌ 請求超時 (嘗試 {attempt + 1}/{RETRY_ATTEMPTS})")
            if attempt < RETRY_ATTEMPTS - 1:
                import time
                time.sleep(RETRY_DELAY)
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ 連接失敗 (嘗試 {attempt + 1}/{RETRY_ATTEMPTS}): {e}")
            if attempt < RETRY_ATTEMPTS - 1:
                import time
                time.sleep(RETRY_DELAY)
        
        except Exception as e:
            logger.error(f"❌ 未知錯誤 (嘗試 {attempt + 1}/{RETRY_ATTEMPTS}): {e}")
            return None
    
    return None


def find_webhook_id(webhooks):
    """在 webhook 列表中查找目標 webhook ID"""
    if not webhooks:
        return None
    
    for hook in webhooks:
        hook_url = hook.get('config', {}).get('url', '')
        if WEBHOOK_ENDPOINT in hook_url:
            webhook_id = hook.get('id')
            logger.info(f"✅ 找到目標 webhook ID: {webhook_id}")
            logger.debug(f"   現有 URL: {hook_url}")
            return webhook_id
    
    logger.warning(f"⚠️ 未找到包含 '{WEBHOOK_ENDPOINT}' 的 webhook")
    return None


def update_github_webhook_url(tunnel_url, webhook_id):
    """使用 requests 更新 GitHub webhook URL"""
    if not webhook_id:
        logger.warning("⚠️ webhook_id 為 None，跳過 GitHub webhook 更新")
        return False
    
    new_webhook_url = f"{tunnel_url}{WEBHOOK_ENDPOINT}"
    url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    payload = {
        "config": {
            "url": new_webhook_url,
            "content_type": "json",
            "secret": GITHUB_WEBHOOK_SECRET
        }
    }
    
    for attempt in range(RETRY_ATTEMPTS):
        try:
            logger.info(f"🔄 更新 GitHub webhook URL (嘗試 {attempt + 1}/{RETRY_ATTEMPTS})...")
            logger.info(f"   新 URL: {new_webhook_url}")
            
            response = requests.patch(url, json=payload, headers=headers, timeout=GITHUB_API_TIMEOUT)
            
            logger.debug(f"HTTP 狀態碼: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"✅ Webhook URL 已成功更新")
                return True
            
            elif response.status_code == 404:
                logger.error(f"❌ Webhook 未找到 (404): ID={webhook_id}")
                return False
            
            elif response.status_code == 422:
                logger.error(f"❌ 無效的 webhook 配置 (422): {response.json()}")
                return False
            
            else:
                logger.warning(f"⚠️ HTTP {response.status_code}: {response.text[:200]}")
                if attempt < RETRY_ATTEMPTS - 1:
                    logger.info(f"⏳ 稍後重試...")
                    import time
                    time.sleep(RETRY_DELAY)
                    continue
                return False
        
        except requests.exceptions.Timeout:
            logger.error(f"❌ 請求超時 (嘗試 {attempt + 1}/{RETRY_ATTEMPTS})")
            if attempt < RETRY_ATTEMPTS - 1:
                import time
                time.sleep(RETRY_DELAY)
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ 連接失敗 (嘗試 {attempt + 1}/{RETRY_ATTEMPTS}): {e}")
            if attempt < RETRY_ATTEMPTS - 1:
                import time
                time.sleep(RETRY_DELAY)
        
        except Exception as e:
            logger.error(f"❌ 未知錯誤 (嘗試 {attempt + 1}/{RETRY_ATTEMPTS}): {e}")
            return False
    
    return False


def update_local_config(tunnel_url):
    """更新本地 config.json"""
    try:
        if not CONFIG_FILE.exists():
            logger.error(f"❌ config.json 不存在: {CONFIG_FILE}")
            return False
        
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        old_url = config.get('url')
        if old_url == tunnel_url:
            logger.info("✅ config.json URL 已是最新，無需更新")
            return True
        
        logger.info(f"🔄 更新 config.json...")
        logger.info(f"   舊 URL: {old_url}")
        logger.info(f"   新 URL: {tunnel_url}")
        
        config['url'] = tunnel_url
        config['API_BASE'] = tunnel_url
        config['lastUpdated'] = datetime.now().isoformat()
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"✅ config.json 已更新")
        return True
    
    except Exception as e:
        logger.error(f"❌ 更新 config.json 失敗: {e}")
        return False


def main():
    """主程序"""
    logger.info("=" * 70)
    logger.info("🔄 GitHub Webhook 自動更新 (Python requests 版本)")
    logger.info("=" * 70)
    
    # 1. 獲取當前隧道 URL
    current_tunnel_url = get_current_tunnel_url()
    if not current_tunnel_url:
        logger.error("❌ 無法獲取當前隧道 URL，退出")
        logger.info("💡 請檢查 cloudflared 服務狀態")
        return False
    
    # 2. 加載上次保存的配置
    saved_config = load_webhook_config()
    saved_tunnel_url = saved_config.get('tunnel_url')
    saved_webhook_id = saved_config.get('webhook_id')
    
    # 3. 檢查是否有變化
    if current_tunnel_url == saved_tunnel_url:
        logger.info(f"✅ 隧道 URL 無變化，流程完成")
        return True
    
    logger.warning(f"⚠️ 隧道 URL 已變化！")
    logger.warning(f"   舊: {saved_tunnel_url}")
    logger.warning(f"   新: {current_tunnel_url}")
    
    # 4. 更新本地 config.json
    if not update_local_config(current_tunnel_url):
        logger.error("❌ 更新本地配置失敗")
        return False
    
    # 5. 更新 GitHub webhook
    if GITHUB_TOKEN:
        webhooks = get_github_webhooks()
        if webhooks:
            webhook_id = find_webhook_id(webhooks) or saved_webhook_id
            
            if update_github_webhook_url(current_tunnel_url, webhook_id):
                logger.info("✅ GitHub webhook 已成功更新")
                save_webhook_config(current_tunnel_url, webhook_id)
            else:
                logger.warning("⚠️ GitHub webhook 更新失敗，但本地配置已更新")
        else:
            logger.warning("⚠️ 無法獲取 GitHub webhook 列表，但本地配置已更新")
    else:
        logger.warning("⚠️ GITHUB_TOKEN 未設置，跳過 GitHub webhook 更新")
    
    logger.info("=" * 70)
    logger.info("✅ 自動更新流程完成")
    logger.info("=" * 70)
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
