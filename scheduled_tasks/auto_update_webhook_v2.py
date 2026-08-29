#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 改進版自動更新 GitHub Webhook 隧道 URL
使用 requests 庫替代 curl，加入重試邏輯、詳細日誌和 Discord 告警

使用方式：
  python3 auto_update_webhook_v2.py

  crontab: */5 * * * * cd /home/e193752468/kkgroup && python3 scheduled_tasks/auto_update_webhook_v2.py >> /var/log/webhook_auto_update_v2.log 2>&1
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 嘗試導入 requests，如果失敗則使用 urllib
try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from dotenv import load_dotenv

# 載入 .env 以取得 GITHUB_* 等變數
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# 配置
CONFIG_FILE = Path(__file__).parent.parent / "config" / "config.json"
WEBHOOK_CONFIG_FILE = Path(__file__).parent.parent / "config" / "webhook_config.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "321qwe321")
REPO_OWNER = "chenkankan1103"
REPO_NAME = "kkgroup"
WEBHOOK_ENDPOINT = "/webhook/github"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def log(msg, is_error=False):
    """記錄日誌並立即刷新"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "❌" if is_error else "✅"
    print(f"[{timestamp}] {prefix} {msg}")
    sys.stdout.flush()


def log_discord(message, is_error=False):
    """發送訊息到 Discord（可選）"""
    if not DISCORD_WEBHOOK:
        return

    try:
        color = 0xFF6B6B if is_error else 0x4ECDC4
        payload = {
            "embeds": [
                {
                    "title": "🤖 隧道 Webhook 更新",
                    "description": message,
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ]
        }

        if HAS_REQUESTS:
            requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
        else:
            import urllib.request

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                DISCORD_WEBHOOK, data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Debug: Discord 通知失敗（非致命）: {e}")


def _get_url_from_cloudflared_config():
    """備用方案：從 cloudflared JSON 設定檔提取 URL"""
    try:
        result = subprocess.run(
            "cat /root/.cloudflared/*.json 2>/dev/null || cat ~/.cloudflared/*.json 2>/dev/null || echo ''",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout:
            match = re.search(
                r'"url":"(https://[a-z0-9\-]+\.trycloudflare\.com)"', result.stdout
            )
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def get_current_tunnel_url():
    """從 cloudflared 日誌提取當前隧道 URL - 改進版本（含備用方案）"""
    print("🔍 提取隧道 URL...")

    try:
        # L118: 使用 subprocess + grep（最穩定）
        result = subprocess.run(
            ["grep", "-oP", r"https://[a-zA-Z0-9_-]+\.trycloudflare\.com"],
            input=subprocess.run(
                [
                    "sudo",
                    "journalctl",
                    "-u",
                    "cloudflared.service",
                    "-n",
                    "100",
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout,
            capture_output=True,
            text=True,
            timeout=5,
        )

        urls = [url.strip() for url in result.stdout.strip().split("\n") if url.strip()]
        if urls:
            current_url = urls[-1]  # 取最後一個（最新的）
            print(f"✅ 提取到隧道 URL (journalctl): {current_url}")
            return current_url

        # 備用方案：從 cloudflared JSON 設定檔提取
        print("⚠️ journalctl 中未找到 URL，嘗試從設定檔提取...")
        fallback_url = _get_url_from_cloudflared_config()
        if fallback_url:
            print(f"✅ 從設定檔提取到 URL: {fallback_url}")
            return fallback_url

        print("⚠️ 所有方法都無法提取 Tunnel URL")
        return None

    except Exception as e:
        print(f"❌ journalctl 提取失敗: {e}，嘗試設定檔備用方案...")
        try:
            fallback_url = _get_url_from_cloudflared_config()
            if fallback_url:
                print(f"✅ 從設定檔提取到 URL: {fallback_url}")
                return fallback_url
        except Exception:
            pass
        return None


def load_webhook_config():
    """加載上次保存的 webhook 配置"""
    if WEBHOOK_CONFIG_FILE.exists():
        try:
            with open(WEBHOOK_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                print(f"✅ 加載 webhook 配置: {config}")
                return config
        except Exception as e:
            print(f"⚠️ 加載配置失敗: {e}")

    return {"tunnel_url": None, "webhook_id": None}


def save_webhook_config(tunnel_url, webhook_id):
    """保存 webhook 配置"""
    try:
        config = {
            "tunnel_url": tunnel_url,
            "webhook_id": webhook_id,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }
        WEBHOOK_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(WEBHOOK_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        print("✅ 保存 webhook 配置")
    except Exception as e:
        print(f"❌ 保存配置失敗: {e}")


def update_config_json(tunnel_url):
    """更新 config.json"""
    try:
        config = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

        config["url"] = tunnel_url
        config["API_BASE"] = tunnel_url
        config["lastUpdated"] = datetime.utcnow().isoformat() + "Z"
        # 保留原有 imageURL（若有）
        # Note: imageURL 處理在原腳本中保留

        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        print(f"✅ config.json 已更新: {tunnel_url}")
        return True
    except Exception as e:
        print(f"❌ 更新 config.json 失敗: {e}")
        return False


def update_github_webhook(tunnel_url, retry_count=0):
    """使用 GitHub API 更新 webhook（帶重試邏輯）"""

    if not GITHUB_TOKEN:
        print("⚠️ 未設置 GITHUB_TOKEN，跳過 GitHub webhook 更新")
        return False

    webhook_url = f"{tunnel_url}{WEBHOOK_ENDPOINT}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "kkgroup-webhook-updater",
    }

    try:
        print("🔍 查詢現有 webhook...")

        # 列出 webhooks
        if HAS_REQUESTS:
            response = requests.get(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks",
                headers=headers,
                timeout=10,
            )
            webhooks = response.json()
        else:
            import urllib.request

            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                webhooks = json.loads(resp.read().decode("utf-8"))

        if not isinstance(webhooks, list):
            print(f"❌ GitHub API 返回錯誤: {webhooks}")
            return False

        # 查找 webhook
        webhook_id = None
        for hook in webhooks:
            if WEBHOOK_ENDPOINT in hook.get("config", {}).get("url", ""):
                webhook_id = hook.get("id")
                old_url = hook.get("config", {}).get("url")
                print(f"✅ 找到 webhook ID: {webhook_id}")
                print(f"   舊 URL: {old_url}")
                print(f"   新 URL: {webhook_url}")
                break

        if not webhook_id:
            print("⚠️ 找不到現有 webhook")
            return False

        # 更新 webhook
        print("🔄 更新 webhook URL...")
        update_data = {
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": GITHUB_WEBHOOK_SECRET,
                "insecure_ssl": "0",
            },
            "events": ["push"],
            "active": True,
        }

        if HAS_REQUESTS:
            response = requests.patch(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}",
                headers=headers,
                json=update_data,
                timeout=10,
            )
            if response.status_code == 200:
                print("✅ Webhook 已更新成功")
                log_discord(f"✅ Webhook 已更新成功\n新 URL: {webhook_url}")
                return True
            else:
                print(
                    f"❌ Webhook 更新失敗 (HTTP {response.status_code}): {response.text}"
                )
                if retry_count < MAX_RETRIES:
                    print(
                        f"⏱️ 等待 {RETRY_DELAY} 秒後重試 ({retry_count + 1}/{MAX_RETRIES})..."
                    )
                    time.sleep(RETRY_DELAY)
                    return update_github_webhook(tunnel_url, retry_count + 1)
                return False
        else:
            import urllib.error
            import urllib.request

            data = json.dumps(update_data).encode("utf-8")
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks/{webhook_id}",
                data=data,
                headers={**headers, "Content-Type": "application/json"},
                method="PATCH",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        print("✅ Webhook 已更新成功")
                        log_discord(f"✅ Webhook 已更新成功\n新 URL: {webhook_url}")
                        return True
            except urllib.error.HTTPError as e:
                print(
                    f"❌ Webhook 更新失敗 (HTTP {e.code}): {e.read().decode('utf-8')}"
                )
                if retry_count < MAX_RETRIES:
                    print(
                        f"⏱️ 等待 {RETRY_DELAY} 秒後重試 ({retry_count + 1}/{MAX_RETRIES})..."
                    )
                    time.sleep(RETRY_DELAY)
                    return update_github_webhook(tunnel_url, retry_count + 1)
                return False
    except Exception as e:
        print(f"❌ 更新 webhook 失敗: {e}")
        if retry_count < MAX_RETRIES:
            print(
                f"⏱️ 等待 {RETRY_DELAY} 秒後重試 ({retry_count + 1}/{MAX_RETRIES})..."
            )
            time.sleep(RETRY_DELAY)
            return update_github_webhook(tunnel_url, retry_count + 1)

        log_discord(
            f"❌ Webhook 更新失敗（已重試 {MAX_RETRIES} 次）\n錯誤: {str(e)}",
            is_error=True,
        )
        return False


def git_commit_changes(tunnel_url):
    """git commit 和 push config.json"""
    try:
        repo_dir = Path(__file__).parent.parent

        print("📝 git add config.json...")
        subprocess.run(
            ["git", "add", "config/config.json"],
            cwd=repo_dir,
            capture_output=True,
            timeout=10,
            check=True,
        )

        print("📝 git commit...")
        result = subprocess.run(
            ["git", "commit", "-m", f"Auto-update: Tunnel URL changed to {tunnel_url}"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            print("✅ git commit 成功")

            print("📤 git push...")
            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if push_result.returncode == 0:
                print("✅ git push 成功")
                log_discord(f"✅ Git 提交成功\n隧道已更新: {tunnel_url}")
                return True
            else:
                print(f"⚠️ git push 失敗: {push_result.stderr}")
        else:
            # 無變更可提交
            print(f"ℹ️ 無變更需要提交: {result.stderr}")

        return True
    except Exception as e:
        print(f"❌ Git 操作失敗: {e}")
        log_discord(f"❌ Git 操作失敗: {str(e)}", is_error=True)
        return False


def main():
    """主函數"""
    print("=" * 60)
    print("🚀 開始隧道 URL 自動更新檢查")
    print("=" * 60)

    # 1. 提取當前隧道 URL
    current_url = get_current_tunnel_url()
    if not current_url:
        print("❌ 無法提取隧道 URL，本次更新失敗")
        log_discord("❌ 無法提取隧道 URL - 隧道可能未啟動", is_error=True)
        return False

    # 2. 加載上次保存的配置
    old_config = load_webhook_config()
    old_url = old_config.get("tunnel_url")

    # 3. 檢查是否需要更新
    if current_url == old_url:
        print("✅ 隧道 URL 無變化，無需更新")
        return True

    print("⚠️ 隧道 URL 已變更！")
    print(f"   舊 URL: {old_url}")
    print(f"   新 URL: {current_url}")
    log_discord(f"🚨 隧道 URL 已變更\n舊: {old_url}\n新: {current_url}")

    # 4. 更新 config.json
    if not update_config_json(current_url):
        print("❌ config.json 更新失敗")
        return False

    # 5. 更新 GitHub webhook
    if not update_github_webhook(current_url):
        print("❌ GitHub webhook 更新失敗")
        return False

    # 6. 保存配置
    save_webhook_config(current_url, old_config.get("webhook_id"))

    # 7. git commit
    if not git_commit_changes(current_url):
        print("⚠️ Git 提交失敗，但隧道 URL 已更新")

    print("=" * 60)
    print("✅ 隧道 URL 自動更新完成")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ 程式崩潰: {e}")
        log_discord(f"❌ webhook 更新程式崩潰\n錯誤: {str(e)}", is_error=True)
        sys.exit(1)
