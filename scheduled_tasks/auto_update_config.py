#!/usr/bin/env python3
"""
🔄 隧道 URL 自動監控、config.json 自動更新 + GitHub Webhook 自動更新
功能:
1. 監控隧道 URL 變更
2. 自動更新 config.json
3. 自動更新 GitHub webhook 配置
4. 自動 git commit 和 push
"""

import subprocess
import json
import re
import time
import sys
import os
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

def log(msg):
    """帶時間戳的日誌"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")
    sys.stdout.flush()

def get_latest_tunnel_url():
    """從 cloudflared 日誌提取最新隧道 URL"""
    try:
        result = subprocess.run(
            ["grep", "-oP", "https://[a-zA-Z0-9_-]+\\.trycloudflare\\.com", "/tmp/cloudflared.log"],
            capture_output=True,
            text=True,
            timeout=5
        )
        urls = result.stdout.strip().split('\n')
        if urls and urls[-1]:
            return urls[-1]
    except Exception as e:
        log(f"⚠️ 提取 URL 失敗: {e}")
    return None

def update_config_json(new_url):
    """更新 config.json"""
    config_path = Path(__file__).parent / "config" / "config.json"
    
    try:
        # 讀取現有配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except:
        config = {}
    
    # 更新 URL
    config['url'] = new_url
    config['imageURL'] = "https://chenkankan1103.github.io/kkgroup/assets/leaderboard.png"  # Use GitHub Pages
    config['lastUpdated'] = datetime.utcnow().isoformat() + "Z"
    config['status'] = "✅ 隧道已完全修復並正常運作"
    
    # 更新後端配置信息
    if 'backendConfig' not in config:
        config['backendConfig'] = {}
    
    config['backendConfig']['tunnelType'] = "Cloudflare 快速隧道（自動監控）"
    config['backendConfig']['lastAutoUpdate'] = datetime.utcnow().isoformat() + "Z"
    
    # 寫回文件
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    log(f"✅ config.json 已更新: {new_url}")
    return True

def git_commit_changes(new_url):
    """提交 Git 變更"""
    try:
        subprocess.run(["git", "add", "config/config.json"], cwd=Path(__file__).parent, timeout=5)
        result = subprocess.run(
            ["git", "commit", "-m", f"Auto-update: Tunnel URL changed to {new_url}"],
            cwd=Path(__file__).parent,
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            log("✅ Git 已提交變更")
            # 嘗試推送
            subprocess.run(["git", "push", "origin", "main"], cwd=Path(__file__).parent, timeout=10)
        else:
            log("ℹ️ 無新變更需要提交")
    except Exception as e:
        log(f"⚠️ Git 操作失敗: {e}")

def update_github_webhook(new_url):
    """自動更新 GitHub Webhook URL
    
    需要環境變數:
    - GITHUB_TOKEN: GitHub Personal Access Token（需要 repo/admin:repo_hook 權限）
    - GITHUB_REPO: 倉庫名（格式: owner/repo）
    - GITHUB_WEBHOOK_ID: Webhook ID（可從 repo 設定找到）
    """
    try:
        github_token = os.getenv("GITHUB_TOKEN")
        github_repo = os.getenv("GITHUB_REPO", "chenkankan1103/kkgroup")
        webhook_id = os.getenv("GITHUB_WEBHOOK_ID")
        
        if not github_token:
            log("⚠️ 未設置 GITHUB_TOKEN，跳過 webhook 更新")
            return False
        
        if not webhook_id:
            log("⚠️ 未設置 GITHUB_WEBHOOK_ID，跳過 webhook 更新")
            return False
        
        # 構建 webhook payload URL
        webhook_url = f"{new_url}/webhook/github"
        
        # GitHub API URL
        api_url = f"https://api.github.com/repos/{github_repo}/hooks/{webhook_id}"
        
        # 請求 header
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # 更新 webhook 的 payload URL
        payload = {
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": os.getenv("GITHUB_WEBHOOK_SECRET", "")
            },
            "active": True
        }
        
        response = requests.patch(api_url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            log(f"✅ GitHub Webhook 已更新: {webhook_url}")
            return True
        else:
            error_msg = response.text[:200]
            log(f"❌ GitHub Webhook 更新失敗 ({response.status_code}): {error_msg}")
            return False
            
    except Exception as e:
        log(f"⚠️ 更新 GitHub Webhook 異常: {e}")
        return False

def main():
    log("=" * 60)
    log("🚀 隧道 URL 自動監控服務已啟動")
    log("=" * 60)
    
    last_url = None
    wait_count = 0
    
    while True:
        try:
            current_url = get_latest_tunnel_url()
            
            if current_url:
                if current_url != last_url:
                    log("")
                    log("🚨 隧道 URL 變更偵測到！")
                    log(f"   舊: {last_url}")
                    log(f"   新: {current_url}")
                    log("")
                    
                    # 更新 config.json
                    if update_config_json(current_url):
                        # 提交 Git
                        git_commit_changes(current_url)
                        
                        # 更新 GitHub Webhook（如果配置了）
                        update_github_webhook(current_url)
                        
                        last_url = current_url
                        wait_count = 0
                        log("✅ 更新完成，現在持續監控...")
                else:
                    wait_count += 1
                    if wait_count % 12 == 0:  # 每 60 秒（12次 x 5秒）打印一次
                        log(f"✅ 監控中... (URL: {current_url[:40]}...)")
                    wait_count += 1
            else:
                log("⚠️ 無法從日誌提取隧道 URL")
            
            # 等待 5 秒後重新檢查
            time.sleep(5)
            
        except KeyboardInterrupt:
            log("")
            log("🛑 監控服務已停止")
            break
        except Exception as e:
            log(f"❌ 錯誤: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
