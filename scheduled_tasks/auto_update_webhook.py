#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 自動更新 GitHub Webhook 隧道 URL
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

# 配置
WEBHOOK_CONFIG_FILE = '/home/e193752468/kkgroup/config/webhook_config.json'
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_OWNER = 'chenkankan1103'
REPO_NAME = 'kkgroup'
WEBHOOK_ENDPOINT = '/webhook/github'


def get_current_tunnel_url():
    """從 cloudflared 日誌提取當前隧道 URL"""
    try:
        result = subprocess.run(
            "sudo journalctl -u cloudflared.service -n 50 --no-pager | grep -oP 'https://[a-z0-9\-]+\.trycloudflare\.com' | head -1",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        url = result.stdout.strip()
        if url:
            logger.info(f"✅ 當前隧道 URL: {url}")
            return url
        else:
            logger.warning("⚠️ 無法從日誌提取隧道 URL")
            return None
    except Exception as e:
        logger.error(f"❌ 提取隧道 URL 失敗: {e}")
        return None


def load_webhook_config():
    """加載上次保存的 webhook 配置"""
    if os.path.exists(WEBHOOK_CONFIG_FILE):
        try:
            with open(WEBHOOK_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info(f"✅ 加載 webhook 配置: {config.get('tunnel_url')}")
                return config
        except Exception as e:
            logger.error(f"❌ 加載配置失敗: {e}")
    return {'tunnel_url': None, 'webhook_id': None}


def save_webhook_config(tunnel_url, webhook_id):
    """保存 webhook 配置"""
    try:
        config = {
            'tunnel_url': tunnel_url,
            'webhook_id': webhook_id,
            'last_updated': datetime.now().isoformat()
        }
        os.makedirs(os.path.dirname(WEBHOOK_CONFIG_FILE), exist_ok=True)
        with open(WEBHOOK_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"✅ 保存 webhook 配置")
    except Exception as e:
        logger.error(f"❌ 保存配置失敗: {e}")


def update_github_webhook(tunnel_url):
    """
    使用 GitHub API 更新 webhook URL
    需要環境變量 GITHUB_TOKEN
    """
    if not GITHUB_TOKEN:
        logger.warning("⚠️ 未設置 GITHUB_TOKEN，跳過 GitHub webhook 更新")
        logger.info("💡 設置方法: export GITHUB_TOKEN='your_token'")
        return False
    
    webhook_url = f"{tunnel_url}{WEBHOOK_ENDPOINT}"
    
    try:
        # 1. 列出現有的 webhooks
        logger.info("🔍 查詢現有 webhook...")
        list_cmd = f"""
        curl -s -H "Authorization: token {GITHUB_TOKEN}" \
             -H "Accept: application/vnd.github.v3+json" \
             https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks
        """
        result = subprocess.run(list_cmd, shell=True, capture_output=True, text=True, timeout=10)
        webhooks = json.loads(result.stdout)
        
        if not isinstance(webhooks, list):
            logger.error(f"❌ GitHub API 返回錯誤: {webhooks}")
            return False
        
        # 2. 查找包含 webhook/github 的 webhook
        webhook_id = None
        for hook in webhooks:
            if WEBHOOK_ENDPOINT in hook.get('config', {}).get('url', ''):
                webhook_id = hook.get('id')
                old_url = hook.get('config', {}).get('url')
                logger.info(f"✅ 找到 webhook ID: {webhook_id}")
                logger.info(f"   舊 URL: {old_url}")
                break
        
        if not webhook_id:
            logger.warning(f"⚠️ 找不到現有的 webhook，將跳過更新")
            logger.info(f"💡 新 webhook URL 應該是: {webhook_url}")
            return False
        
        # 3. 更新 webhook URL
        logger.info(f"🔄 更新 webhook URL...")
        update_cmd = f"""
        curl -s -X PATCH \
             -H "Authorization: token {GITHUB_TOKEN}" \
             -H "Accept: application/vnd.github.v3+json" \
             -d '{{"config": {{"url": "{webhook_url}", "content_type": "json", "secret": ""}}}}' \
             https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}
        """
        result = subprocess.run(update_cmd, shell=True, capture_output=True, text=True, timeout=10)
        response = json.loads(result.stdout)
        
        if response.get('id'):
            logger.info(f"✅ webhook 已更新: {webhook_url}")
            return True
        else:
            logger.error(f"❌ webhook 更新失敗: {response}")
            return False
    
    except Exception as e:
        logger.error(f"❌ 更新 GitHub webhook 失敗: {e}")
        return False


def update_local_config(tunnel_url):
    """更新本地 config.json"""
    try:
        config_file = Path('/home/e193752468/kkgroup/config/config.json')
        
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        old_url = config.get('url')
        if old_url == tunnel_url:
            logger.info("✅ config.json URL 已是最新，無需更新")
            return True
        
        logger.info(f"🔄 更新 config.json...")
        logger.info(f"   舊: {old_url}")
        logger.info(f"   新: {tunnel_url}")
        
        config['url'] = tunnel_url
        config['API_BASE'] = tunnel_url
        config['lastUpdated'] = datetime.now().isoformat()
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"✅ config.json 已更新")
        return True
    
    except Exception as e:
        logger.error(f"❌ 更新 config.json 失敗: {e}")
        return False


def main():
    """主程序"""
    logger.info("=" * 60)
    logger.info("🔄 自動更新 GitHub Webhook")
    logger.info("=" * 60)
    
    # 1. 獲取當前隧道 URL
    current_tunnel_url = get_current_tunnel_url()
    if not current_tunnel_url:
        logger.error("❌ 無法獲取當前隧道 URL，退出")
        return False
    
    # 2. 加載上次保存的配置
    saved_config = load_webhook_config()
    saved_tunnel_url = saved_config.get('tunnel_url')
    
    # 3. 檢查是否有變化
    if current_tunnel_url == saved_tunnel_url:
        logger.info(f"✅ 隧道 URL 無變化，無需更新")
        return True
    
    logger.warning(f"⚠️ 隧道 URL 已變化！")
    logger.warning(f"   舊: {saved_tunnel_url}")
    logger.warning(f"   新: {current_tunnel_url}")
    
    # 4. 更新本地 config.json
    if not update_local_config(current_tunnel_url):
        logger.error("❌ 更新本地配置失敗")
        return False
    
    # 5. 更新 GitHub webhook（如果有 token）
    if GITHUB_TOKEN:
        if update_github_webhook(current_tunnel_url):
            logger.info("✅ GitHub webhook 已更新")
        else:
            logger.warning("⚠️ GitHub webhook 更新失敗，但本地配置已更新")
    
    # 6. 保存新配置
    save_webhook_config(current_tunnel_url, saved_config.get('webhook_id'))
    
    logger.info("=" * 60)
    logger.info("✅ 自動更新完成")
    logger.info("=" * 60)
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
