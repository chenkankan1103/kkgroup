#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 GitHub Webhook 快速修復 - 直接版本
無需 SSH，直接讀取 config.json 並更新 GitHub webhook

使用：
  python webhook_quick_fix.py
"""

import os
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import logging

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """快速修復 GitHub webhook"""
    
    # 配置
    PROJECT_DIR = Path(__file__).parent
    CONFIG_FILE = PROJECT_DIR / 'config' / 'config.json'
    WEBHOOK_CONFIG_FILE = PROJECT_DIR / 'config' / 'webhook_config.json'
    
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    REPO_OWNER = 'chenkankan1103'
    REPO_NAME = 'kkgroup'
    WEBHOOK_ENDPOINT = '/webhook/github'
    
    # ===== 步驟 1：讀取當前隧道 URL =====
    logger.info("📋 步驟 1: 讀取隧道 URL...")
    
    if not CONFIG_FILE.exists():
        logger.error(f"❌ 找不到 {CONFIG_FILE}")
        sys.exit(1)
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        tunnel_url = config.get('url')
        
        if not tunnel_url:
            logger.error("❌ config.json 中沒有 'url' 字段")
            sys.exit(1)
            
        logger.info(f"✅ 當前隧道 URL: {tunnel_url}")
    except Exception as e:
        logger.error(f"❌ 讀取 config.json 失敗: {e}")
        sys.exit(1)
    
    # ===== 步驟 2：驗證隧道可訪問 =====
    logger.info("🔍 步驟 2: 驗證隧道可訪問...")
    
    webhook_url = f"{tunnel_url}{WEBHOOK_ENDPOINT}"
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', webhook_url],
            capture_output=True,
            text=True,
            timeout=10
        )
        status = result.stdout.strip()
        
        if status in ['405', '400']:
            logger.info(f"✅ 隧道可訪問 (狀態碼: {status})")
        elif status == '404':
            logger.warning(f"⚠️ webhook 端點返回 404，可能路由配置有誤")
            logger.info(f"   檢查: unified_api.py 是否掛載 webhook_bp")
        else:
            logger.warning(f"⚠️ 隧道返回狀態碼: {status}")
            
    except Exception as e:
        logger.warning(f"⚠️ 驗證隧道失敗 (可能網絡問題): {e}")
    
    # ===== 步驟 3：檢查 GitHub Token =====
    logger.info("🔑 步驟 3: 檢查 GitHub Token...")
    
    if not GITHUB_TOKEN:
        logger.error("❌ 未設置 GITHUB_TOKEN 環境變量")
        logger.info("   提示: export GITHUB_TOKEN='your_token'")
        sys.exit(1)
    
    logger.info(f"✅ GitHub Token 已設置 (前 20 字符: {GITHUB_TOKEN[:20]}...)")
    
    # ===== 步驟 4：查詢現有 webhook =====
    logger.info("🔍 步驟 4: 查詢現有 webhook...")
    
    try:
        list_cmd = f"""
        curl -s -H "Authorization: token {GITHUB_TOKEN}" \
             -H "Accept: application/vnd.github.v3+json" \
             https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks
        """
        result = subprocess.run(list_cmd, shell=True, capture_output=True, text=True, timeout=10)
        webhooks = json.loads(result.stdout)
        
        if not isinstance(webhooks, list):
            logger.error(f"❌ GitHub API 返回錯誤: {webhooks}")
            logger.info(f"   可能原因: Token 無效或已過期")
            sys.exit(1)
        
        logger.info(f"✅ 找到 {len(webhooks)} 個 webhook")
        
        # 查找 /webhook/github
        webhook_id = None
        old_url = None
        for i, hook in enumerate(webhooks):
            hook_url = hook.get('config', {}).get('url', '')
            if WEBHOOK_ENDPOINT in hook_url:
                webhook_id = hook.get('id')
                old_url = hook_url
                logger.info(f"✅ 找到目標 webhook: ID={webhook_id}")
                logger.info(f"   舊 URL: {old_url}")
                break
        
        if not webhook_id:
            logger.error(f"❌ 找不到包含 '{WEBHOOK_ENDPOINT}' 的 webhook")
            logger.info("   可能需要在 GitHub 上手動創建 webhook")
            logger.info(f"   期望的 URL: {webhook_url}")
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON 解析失敗: {e}")
        logger.info("   可能原因: API 返回非 JSON 響應或 Token 無效")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 查詢 webhook 失敗: {e}")
        sys.exit(1)
    
    # ===== 步驟 5：更新 webhook URL =====
    logger.info("🔄 步驟 5: 更新 webhook URL...")
    
    try:
        update_cmd = f"""
        curl -s -X PATCH \
             -H "Authorization: token {GITHUB_TOKEN}" \
             -H "Accept: application/vnd.github.v3+json" \
             -d '{{"config": {{"url": "{webhook_url}", "content_type": "json", "secret": ""}}}}' \
             https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}
        """
        result = subprocess.run(update_cmd, shell=True, capture_output=True, text=True, timeout=10)
        response = json.loads(result.stdout)
        
        if response.get('id') == webhook_id:
            new_url = response.get('config', {}).get('url', '')
            logger.info(f"✅ 成功更新 webhook!")
            logger.info(f"   新 URL: {new_url}")
        else:
            logger.error(f"❌ 更新失敗: {response.get('message', 'Unknown error')}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ 更新 webhook 失敗: {e}")
        sys.exit(1)
    
    # ===== 步驟 6：保存配置 =====
    logger.info("💾 步驟 6: 保存 webhook 配置...")
    
    try:
        webhook_config = {
            'tunnel_url': tunnel_url,
            'webhook_id': webhook_id,
            'webhook_url': webhook_url,
            'last_updated': datetime.now().isoformat(),
            'status': 'updated'
        }
        
        os.makedirs(WEBHOOK_CONFIG_FILE.parent, exist_ok=True)
        with open(WEBHOOK_CONFIG_FILE, 'w') as f:
            json.dump(webhook_config, f, indent=2)
        
        logger.info(f"✅ 保存到 {WEBHOOK_CONFIG_FILE}")
        
    except Exception as e:
        logger.error(f"❌ 保存配置失敗: {e}")
        sys.exit(1)
    
    # ===== 完成 =====
    logger.info("\n" + "="*60)
    logger.info("✅ 修復完成！")
    logger.info("="*60)
    logger.info(f"隧道 URL:      {tunnel_url}")
    logger.info(f"Webhook URL:   {webhook_url}")
    logger.info(f"Webhook ID:    {webhook_id}")
    logger.info("\n下一步:")
    logger.info("1. 推送代碼到 GitHub 測試")
    logger.info("2. 查看 bot 服務是否自動更新")
    logger.info("3. 檢查隧道日誌確認連接")
    logger.info("\n提示: 定期運行此腳本以應對隧道 URL 變更")

if __name__ == '__main__':
    main()
