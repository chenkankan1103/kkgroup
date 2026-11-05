#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 改進版自動更新 GitHub Webhook 隧道 URL
使用 requests 庫替代 curl，加入重試邏輯、詳細日誌和 Discord 告警

使用方式（實際呼叫鏈，非 crontab）：
  cloudflared.service ExecStartPost
    → scripts/update_tunnel_url_event.sh（等 60 秒讓隧道註冊完成）
      → python3 scheduled_tasks/auto_update_webhook_v2.py >> /var/log/webhook_auto_update.log

行為設計（2026-11-06 修正）：
  1. 隧道 URL 只存在於 cloudflared 啟動日誌（quick tunnel 每次重啟隨機產生）
  2. URL 變更必然伴隨 cloudflared 重啟 → 重啟時日誌必新鮮，journalctl 一定撈得到
  3. 日誌輪轉後（未重啟）撈不到 URL → 視為無變更，安全 no-op（以 GitHub 現值佐證）
  4. 只更新 GitHub webhook；config.json 的 url/API_BASE 是 Discord OAuth 回呼基準，
     必須維持 duckdns 網域，絕不可改寫成隧道 URL
"""

import os
import json
import sys
import re
import time
from pathlib import Path
from datetime import datetime
import subprocess

# 嘗試導入 requests，如果失敗則使用 urllib
try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from dotenv import load_dotenv

# 載入 .env 以取得 GITHUB_* 等變數（本檔在 scheduled_tasks/ 下，專案根是 parents[1]）
dotenv_path = Path(__file__).resolve().parents[1] / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
else:
    # 保險：若相對路徑失效，退回 CWD 的 .env（ExecStartPost 會 cd 到專案根）
    load_dotenv(Path.cwd() / ".env")

# 配置
WEBHOOK_CONFIG_FILE = Path(__file__).parent.parent / "config" / "webhook_config.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "321qwe321")
REPO_OWNER = "chenkankan1103"
REPO_NAME = "kkgroup"
WEBHOOK_ENDPOINT = "/webhook/github"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def get_url_from_github():
    """第三層備援：從 GitHub API 讀取 webhook 目前指向的隧道 URL。

    cloudflared 日誌會輪轉（journald vacuum / 時間推移），註冊網址的那幾行
    可能消失；GitHub webhook 設定本身即是「現用網址」的真相來源。
    """
    if not GITHUB_TOKEN:
        return None
    try:
        import urllib.request

        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "kkgroup-webhook-updater",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            hooks = json.loads(resp.read().decode("utf-8"))
        for hook in hooks:
            url = hook.get("config", {}).get("url", "")
            if WEBHOOK_ENDPOINT in url:
                base = url.split(WEBHOOK_ENDPOINT)[0].rstrip("/")
                print(f"✅ 從 GitHub API 讀到現用隧道 URL: {base}")
                return base
    except Exception as e:
        print(f"⚠️ 讀取 GitHub webhook 現值失敗: {e}")
    return None


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
            import urllib.request
            import urllib.error

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
            print(f"⏱️ 等待 {RETRY_DELAY} 秒後重試 ({retry_count + 1}/{MAX_RETRIES})...")
            time.sleep(RETRY_DELAY)
            return update_github_webhook(tunnel_url, retry_count + 1)

        log_discord(
            f"❌ Webhook 更新失敗（已重試 {MAX_RETRIES} 次）\n錯誤: {str(e)}",
            is_error=True,
        )
        return False


def main():
    """主函數"""
    print("=" * 60)
    print("🚀 開始隧道 URL 自動更新檢查")
    print("=" * 60)

    # 1. 提取當前隧道 URL（journalctl → cloudflared 設定檔）
    current_url = get_current_tunnel_url()

    # 2. 加載上次保存的配置
    old_config = load_webhook_config()
    old_url = old_config.get("tunnel_url")

    # 3. 本機提取不到 URL（日誌已輪轉、隧道未重啟）→ 不可能發生「網址變更」
    #    （網址變更必然伴隨 cloudflared 重啟，重啟會寫入全新日誌）→ 安全 no-op
    if not current_url:
        github_current = get_url_from_github()
        print(f"ℹ️ 本機無法提取隧道 URL；GitHub webhook 現值: {github_current or '未知'}")
        print("ℹ️ 未偵測到可驗證的網址變更，本次不動任何設定（安全 no-op）")
        return True

    # 3.5 首次執行（無本地狀態檔）：以 GitHub 現值為基準，避免誤判「已變更」
    if old_url is None:
        github_current = get_url_from_github()
        if github_current == current_url:
            print("ℹ️ 無本地狀態檔，但 GitHub webhook 已指向相同 URL → 建立基準即可")
            save_webhook_config(current_url, None)
            return True
        if github_current:
            old_url = github_current
            print(f"ℹ️ 以 GitHub 現值為舊基準: {old_url}")

    # 4. 檢查是否需要更新
    if current_url == old_url:
        print("✅ 隧道 URL 無變化，無需更新")
        save_webhook_config(current_url, old_config.get("webhook_id"))
        return True

    print("⚠️ 隧道 URL 已變更！")
    print(f"   舊 URL: {old_url}")
    print(f"   新 URL: {current_url}")
    log_discord(f"🚨 隧道 URL 已變更\n舊: {old_url}\n新: {current_url}")

    # 5. 更新 GitHub webhook
    #    （config.json 的 url/API_BASE 現在是 Discord OAuth 回呼與紙娃娃 API 的
    #    基準網址，必須維持 duckdns 網域，不可改寫成隧道 URL——這是舊版行為的地雷）
    if not update_github_webhook(current_url):
        print("❌ GitHub webhook 更新失敗")
        return False

    # 6. 保存配置
    save_webhook_config(current_url, old_config.get("webhook_id"))

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
