#!/usr/bin/env python3
"""
🔄 隧道 URL 自動監控、config.json 自動更新 + GitHub Webhook 自動更新
功能:
1. 監控隧道 URL 變更
2. 自動更新 config.json
3. 自動更新 GitHub webhook 配置
4. 自動 git commit 和 push
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


def log(msg):
    """帶時間戳的日誌"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")
    sys.stdout.flush()


def get_latest_tunnel_url():
    """從 cloudflared journal 或日誌提取最新隧道 URL"""
    # 優先從 journalctl 取得
    try:
        result = subprocess.run(
            [
                "sudo",
                "journalctl",
                "-u",
                "cloudflared.service",
                "--no-pager",
                "--since",
                "24 hours ago",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # cloudflared 在 stdout 輸出 URL: https://xxxx.trycloudflare.com
        matches = re.findall(
            r"https://[a-zA-Z0-9_-]+\.trycloudflare\.com", result.stdout
        )
        if matches:
            return matches[-1]  # 最後一個 URL（最新的）
    except Exception as e:
        log(f"⚠️ journalctl 提取失敗: {e}")

    # Fallback: 從日誌檔案
    try:
        result = subprocess.run(
            [
                "grep",
                "-oP",
                "https://[a-zA-Z0-9_-]+\\.trycloudflare\\.com",
                "/tmp/cloudflared.log",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        urls = result.stdout.strip().split("\n")
        if urls and urls[-1]:
            return urls[-1]
    except Exception as e:
        log(f"⚠️ 日誌提取失敗: {e}")
    return None


def update_config_json(new_url):
    """更新 config/config.json 和 web/portal/config.json"""
    ROOT = Path(__file__).parent.parent  # kkgroup 根目錄

    # === 1. 更新 config/config.json（主配置，完整內容） ===
    config_path = ROOT / "config" / "config.json"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except:
        config = {}

    # 保留原有 imageURL（不要被覆寫）
    original_image = config.get("imageURL", "")

    config["url"] = new_url
    config["API_BASE"] = new_url
    config["lastUpdated"] = datetime.utcnow().isoformat()

    # 保留原有的 imageURL（由 monitor_leaderboard_url.py 管理）
    if original_image:
        config["imageURL"] = original_image

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    log(f"✅ config/config.json 已更新: {new_url}")

    # === 2. 同步更新 web/portal/config.json（入口網站用） ===
    portal_config_dir = ROOT / "web" / "portal"
    portal_config_dir.mkdir(parents=True, exist_ok=True)
    portal_config_path = portal_config_dir / "config.json"

    portal_config = {"url": new_url, "API_BASE": new_url}

    with open(portal_config_path, "w", encoding="utf-8") as f:
        json.dump(portal_config, f, ensure_ascii=False, indent=2)

    log(f"✅ web/portal/config.json 已同步: {new_url}")
    return True


def git_commit_changes(new_url):
    """提交 Git 變更"""
    ROOT = Path(__file__).parent.parent
    try:
        subprocess.run(
            ["git", "add", "config/config.json", "web/portal/config.json"],
            cwd=ROOT,
            timeout=5,
        )
        result = subprocess.run(
            ["git", "commit", "-m", "fix: 更新 config.json tunnel URL 為當前有效位址"],
            cwd=ROOT,
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            log("✅ Git 已提交變更")
            subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, timeout=10)
        else:
            log("ℹ️ 無新變更需要提交（或 URL 未變更）")
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
            "Accept": "application/vnd.github.v3+json",
        }

        # 更新 webhook 的 payload URL
        payload = {
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": os.getenv("GITHUB_WEBHOOK_SECRET", ""),
            },
            "active": True,
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
