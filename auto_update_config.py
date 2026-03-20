#!/usr/bin/env python3
"""
🔄 隧道 URL 自動監控與 config.json 自動更新
只有一個工作：不斷監控隧道 URL 變更 → 自動更新 config.json
"""

import subprocess
import json
import re
import time
import sys
from datetime import datetime
from pathlib import Path

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
    config_path = Path(__file__).parent / "docs" / "config.json"
    
    try:
        # 讀取現有配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except:
        config = {}
    
    # 更新 URL
    config['url'] = new_url
    config['imageURL'] = "https://cdn.jsdelivr.net/gh/chenkankan1103/kkgroup/docs/assets/leaderboard.png"  # 📤 使用 GitHub CDN，不流量隧道
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
        subprocess.run(["git", "add", "docs/config.json"], cwd=Path(__file__).parent, timeout=5)
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
