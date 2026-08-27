import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import io
import time
import aiohttp
import re
import json
import datetime
import asyncio
from PIL import Image
from collections import defaultdict
from dotenv import load_dotenv, set_key
from io import BytesIO

# 匯入非同步 DB 適配層
from shared.db.async_adapter import (
    get_user_kkcoin,
    update_user_kkcoin,
    get_user_field,
    set_user_field,
    add_user_field,
    get_central_reserve,
    add_to_central_reserve,
    remove_from_central_reserve,
    set_central_reserve,
    get_reserve_pressure,
    get_dynamic_fee_rate,
    get_reserve_announcement,
)

# 匯入排行榜管理模組
from .leaderboard_manager import (
    make_leaderboard_image,
    get_current_leaderboard_data,
    has_data_changed,
)

# 載入 .env 檔案
load_dotenv()

# 配置常數
DB_FILE = "user_data.db"
FONT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "fonts", "NotoSansCJKtc-Regular.otf"
)
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
TROPHY_PATH = os.path.join(ASSETS_PATH, "trophy.png")
MEDAL_PATHS = [
    os.path.join(ASSETS_PATH, "1.png"),  # 金牌
    os.path.join(ASSETS_PATH, "2.png"),  # 銀牌
    os.path.join(ASSETS_PATH, "3.png"),  # 銅牌
]
USER_COOLDOWN_SECONDS = 30
UPDATE_INTERVAL = 300  # 更新間隔改為 5 分鐘 (300 秒)


# 資料庫操作方法 (非同步版本)
async def get_user_balance(user_id):
    """獲取玩家 KKCoin 餘額"""
    return await get_user_kkcoin(user_id)


async def update_user_balance(user_id, amount):  # 已修改
        """更新玩家 KKCoin 餘額"""
        return await update_user_kkcoin(user_id, amount)











# 環境變數操作
def get_from_env(variable_name, default=None):
    return os.getenv(variable_name, default)


def save_to_env(variable_name, value):
    """
    保存環境變數到 .env 檔案（不帶引號）
    確保 MESSAGE_ID 等數字值正確儲存（無引號）
    """
    value_str = str(value)
    # 移除任何已有的引號以防止雙重引號
    value_str = value_str.strip("'\"")
    set_key(".env", variable_name, value_str)


# 生成灰色占位頭像（當頭像加載失敗時使用）
def create_placeholder_avatar():
    """創建灰色占位圖像"""
    placeholder = Image.new("RGBA", (48, 48), (200, 200, 200, 255))
    return placeholder


# 取得 Discord 使用者頭像
async def fetch_avatar(session, url):
    """
    嘗試加載用戶頭像
    成功: 返回 Image 對象
    失敗: 返回 None（調用者應使用 placeholder）
    """
    if not url:
        return None

    try:
        # 增加超時時間，避免網路波動導致下載失敗
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            # 驗證 HTTP 狀態碼
            if resp.status != 200:
                print(f"⚠️ 頭像 URL 返回 {resp.status}: {url[:50]}...")
                return None

            # 讀取圖片數據
            data = await resp.read()
            if len(data) == 0:
                print(f"⚠️ 頭像數據為空: {url[:50]}...")
                return None

            # 嘗試加載圖片
            img = Image.open(io.BytesIO(data)).convert("RGBA")

            # 檢查圖片尺寸（避免 1x1 的空白圖）
            if img.size[0] < 16 or img.size[1] < 16:
                print(f"⚠️ 頭像尺寸過小: {img.size}")
                return None

            return img

    except asyncio.TimeoutError:
        print(f"⏱️ 頭像加載超時: {url[:50]}...")
        return None
    except Exception as e:
        print(f"❌ 頭像加載失敗 ({type(e).__name__}): {url[:50]}...")
        return None


async def make_leaderboard_image(members_data):
    """已移至 leaderboard_manager.py

    此處保留為向後相容性考慮
    """
    from .leaderboard_manager import make_leaderboard_image as _make_leaderboard_image

    return await _make_leaderboard_image(members_data)


def is_only_emojis(text):
    import regex

    emoji_pattern = regex.compile(
        r"^\s*(?:\p{Emoji_Presentation}|\p{Emoji}\uFE0F|\p{Emoji_Modifier_Base}|\p{Emoji_Component})+\s*$"
    )
    return bool(emoji_pattern.fullmatch(text))


class KKCoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # initialize_database() - async adapter 自動初始化，無需手動呼叫

        # 從 .env 讀取排行榜頻道 ID
        self.rank_channel_id = int(get_from_env("KKCOIN_RANK_CHANNEL_ID", 0))
        self.rank_message_id = int(get_from_env("KKCOIN_RANK_MESSAGE_ID", 0))

        # 園區中央儲備金狀態
        self.reserve_channel_id = int(get_from_env("RESERVE_STATUS_CHANNEL_ID", 0))
        self.reserve_message_id = int(get_from_env("RESERVE_STATUS_MESSAGE_ID", 0))

        self.last_kkcoin_time = defaultdict(lambda: 0)
        self.last_message_cache = defaultdict(str)
        self.last_update_time = 0
        self.last_leaderboard_data = None
        self._config_missing_warned = False  # 追踪是否已警告过 config.json 不存在

        # 🎯 事件驅動排行榜生成（資料變化時延遲 5 分鐘後生成，避免頻繁更新）
        self._pending_leaderboard_generation = False  # 標記是否有待生成的任務
        self._generation_timer = None  # 5 分鐘延遲計時器
        self._generation_lock = asyncio.Lock()  # 防止同時多次觸發

        # Cloudflare Quick Tunnel 支援
        # 不使用 kkgroup.com（已被第三方公司註冊），改從 config.json 讀取
        self.base_url = self._load_base_url_from_config()
        self.tunnel_url_lock = asyncio.Lock()
        self.last_synced_tunnel_url = None  # 追蹤上一次同步的 URL

        # 🔧 [改為事件驅動] 只在資料庫資產有變化時觸發更新，不做定時輪詢
        # 啟動必要的背景任務
        # self.auto_update_reserve_status.start()  # ❌ 已禁用：儲備狀態現在隨排行榜更新而更新
        self.auto_check_tunnel_url.start()  # 🔄 啟動隧道 URL 自動檢查（每 10 分鐘）
        # self.auto_push_leaderboard_to_github.start()  # 📤 ⏸️ 暫停：網頁開發的部分先停用
        print(f"✅ KKCoin 系統已載入，排行榜頻道: {self.rank_channel_id}")
        print(f"✅ 園區儲備狀態頻道: {self.reserve_channel_id}")
        print("🔄 隧道 URL 自動檢查已啟用（每 10 分鐘掃描一次）")
        print(
            "📤 ✨ 排行榜已改用事件驅動模式：資料有變化時，等 5 分鐘後生成一次（避免頻繁更新，减少 VM 出站流量）"
        )

    def cog_unload(self):
        """當 Cog 卸載時停止定時任務"""
        # self.auto_update_reserve_status.cancel()  # ❌ 已禁用：儲備狀態現在隨排行榜更新而更新
        self.auto_check_tunnel_url.cancel()  # 🔄 取消隧道檢查任務
        if self.auto_push_leaderboard_to_github.is_running():
            self.auto_push_leaderboard_to_github.cancel()  # 📤 取消 GitHub 推送任務

    def _load_base_url_from_config(self) -> str:
        """啟動時同步讀取 config/config.json 取得 tunnel URL（避免使用 kkgroup.com 預設值）"""
        try:
            import json

            config_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "config", "config.json"
            )
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    url = data.get("url", "")
                    if url and url.startswith("https://"):
                        print(f"✅ 啟動時從 config.json 讀取 base_url: {url}")
                        return url
        except Exception as e:
            print(f"⚠️ 啟動時讀取 config.json 失敗: {e}")
        return ""  # 空字串，不指向任何第三方網域

    async def sync_to_github(self, new_url):
        """將新的隧道 URL 同步到 GitHub Pages 入口

        參數:
            new_url: 新的 Tunnel URL (e.g., https://xxx.trycloudflare.com)

        流程:
            1. 讀取現有 config/config.json，保留 imageURL（Discord CDN 由 Bot 自動維護）
            2. 只更新隧道 URL：url 和 API_BASE
            3. Git add/commit/push 到遠端 GitHub
        """
        try:
            import subprocess
            import json
            from datetime import datetime

            # 使用 config/config.json
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "config", "config.json"
            )

            # 檢查 config 目錄是否存在
            config_dir = os.path.dirname(config_path)
            if not os.path.exists(config_dir):
                print(f"❌ config 目錄不存在: {config_dir}")
                return False

            # 讀取現有配置（保留排行榜 CDN URL，由 Bot 自動維護）
            existing_image_url = "https://chenkankan1103.github.io/kkgroup/assets/leaderboard.png"  # 備用值
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        existing_config = json.load(f)
                        existing_image_url = existing_config.get(
                            "imageURL", existing_image_url
                        )
                except Exception as e:
                    print(f"⚠️  讀取現有 config.json 失敗，使用備用 URL: {e}")

            # 更新 config.json（只更新隧道 URL，保留 imageURL）
            config_data = {
                "url": new_url,
                "API_BASE": new_url,
                "imageURL": existing_image_url,  # 📤 保留現有的排行榜 CDN URL（由 Bot 自動維護）
                "DISCORD_URL": "https://discord.gg/5JtuJvhhHu",
                "lastUpdated": datetime.utcnow().isoformat() + "Z",
            }

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

            print(f"✅ 已更新 config.json: {new_url}")

            # Git 操作（在項目根目錄中執行）
            git_commands = [
                ["git", "add", "config/config.json"],
                ["git", "commit", "-m", f"Auto-sync: Update tunnel URL to {new_url}"],
                ["git", "push", "origin", "main"],
            ]

            for cmd in git_commands:
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=os.path.dirname(__file__) + "/../..",
                    )
                    if result.returncode == 0:
                        print(f"✅ Git 指令成功: {' '.join(cmd[1:])}")
                    else:
                        # 如果是 commit 時沒有變更，允許這個錯誤
                        if (
                            "nothing to commit" in result.stderr
                            or "nothing added to commit" in result.stderr
                        ):
                            print("ℹ️  config.json 未有變更，跳過提交")
                        else:
                            print(f"⚠️  Git 指令警告: {result.stderr[:100]}")
                except subprocess.TimeoutExpired:
                    print(f"⏱️ 指令超時: {' '.join(cmd)}")
                    return False
                except Exception as e:
                    print(f"❌ Git 操作失敗: {e}")
                    return False

            print(
                "🚀 GitHub Pages 已更新隧道 URL: https://chenkankan1103.github.io/kkgroup/"
            )
            return True

        except Exception as e:
            print(f"❌ 同步到 GitHub 失敗: {e}")
            import traceback

            traceback.print_exc()
            return False

    @tasks.loop(minutes=5)
    async def auto_push_leaderboard_to_github(self):
        """✅ [已停用] 原來的定時推送任務

        現在改用事件驅動模式：
        - 只在排行榜資料有變化時才生成圖片
        - 檢測到變化後延遲 5 分鐘再生成（避免頻繁更新）
        - 5 分鐘內多次變化只生成一次（減少出站流量）

        生成邏輯已移至 _trigger_leaderboard_generation()
        """
        # 此方法保留以維持向後兼容性，但不再執行任何操作
        pass

    async def _upload_leaderboard_to_discord(self, image, user_count):
        """上傳/編輯排行榜圖片到 Discord（只用 Discord CDN，無隧道流量）

        邏輯：
        1. 如果已有訊息，編輯其附件（覆蓋舊圖片）
        2. 如果沒有，新建訊息
        3. 從訊息附件取得 Discord CDN URL
        4. 存到 config.json 供網頁版讀取
        """
        try:
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到排行榜頻道 {self.rank_channel_id}")
                return

            # 把圖片存到 BytesIO
            buf = io.BytesIO()
            image.save(buf, format="PNG", optimize=True, compress_level=9)
            buf.seek(0)
            file = discord.File(buf, filename="leaderboard.png")

            # 更新或創建訊息
            if self.rank_message_id:
                try:
                    msg = await channel.fetch_message(self.rank_message_id)
                    # 編輯訊息的附件（覆蓋舊圖片）
                    await msg.edit(attachments=[file])
                    # 編輯後立即重新獲取訊息以確保附件 URL 已生成
                    await asyncio.sleep(0.5)  # 等待 Discord 處理
                    msg = await channel.fetch_message(self.rank_message_id)
                    print(f"✅ 排行榜圖片已更新（編輯附件）- {user_count} 人")
                except discord.NotFound:
                    print("⚠️ 舊訊息已刪除，創建新訊息")
                    self.rank_message_id = 0
                    msg = await channel.send(file=file)
                    self.rank_message_id = msg.id
                    save_to_env("KKCOIN_RANK_MESSAGE_ID", self.rank_message_id)
                    print("✅ 排行榜訊息已創建（新訊息）")
            else:
                # 首次上傳
                msg = await channel.send(file=file)
                self.rank_message_id = msg.id
                save_to_env("KKCOIN_RANK_MESSAGE_ID", self.rank_message_id)
                print("✅ 排行榜訊息已創建（首次）")

            # 從訊息附件取得 Discord CDN URL
            if msg.attachments and len(msg.attachments) > 0:
                leaderboard_url = msg.attachments[0].url
                print(f"📸 Discord CDN URL: {leaderboard_url}")

                # 💾 保存 URL 到 .env
                save_to_env("LEADERBOARD_URL", leaderboard_url)

                # 💾 更新 config.json 供網頁端讀取
                try:
                    config_path = os.path.join(
                        os.path.dirname(__file__), "..", "..", "config", "config.json"
                    )
                    if os.path.exists(config_path):
                        with open(config_path, "r", encoding="utf-8") as f:
                            config = json.load(f)
                        config["imageURL"] = leaderboard_url
                        config["lastUpdated"] = datetime.datetime.now().isoformat()
                        with open(config_path, "w", encoding="utf-8") as f:
                            json.dump(config, f, ensure_ascii=False, indent=2)
                        print(f"✅ 已更新 config.json: {leaderboard_url[:50]}...")
                    else:
                        # 只在首次警告
                        if not self._config_missing_warned:
                            print(f"⚠️ config.json 不存在: {config_path}")
                            self._config_missing_warned = True
                except Exception as e:
                    print(f"⚠️ 更新 config.json 失敗: {e}")
                    import traceback

                    traceback.print_exc()
            else:
                print(
                    f"❌ 訊息中沒有附件（attachments={msg.attachments if msg else 'N/A'}）"
                )

        except Exception as e:
            print(f"❌ 上傳排行榜到 Discord 失敗: {e}")
            import traceback

            traceback.print_exc()

    async def _upload_leaderboard_via_api(self, image, user_count):
        """[已停用] 使用 GitHub API 上傳排行榜 - 已改用 Discord CDN

        保留此方法以維持向後兼容性，但不再執行任何操作。
        排行榜現在直接上傳到 Discord CDN 進行存儲。
        """
        try:
            import base64

            github_token = get_from_env("GITHUB_TOKEN")
            if not github_token:
                print("⚠️ 未設定 GITHUB_TOKEN，跳過 API 上傳")
                return

            # 圖片轉 base64
            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format="PNG", optimize=True, compress_level=9)
            img_byte_arr.seek(0)
            encoded_content = base64.b64encode(img_byte_arr.read()).decode("utf-8")

            # GitHub API
            owner = "chenkankan1103"
            repo = "kkgroup"
            file_path = "docs/assets/leaderboard.png"  # 存到 docs 目錄
            api_url = (
                f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
            )

            async with aiohttp.ClientSession() as session:
                # 先取得現有文件的 SHA（用於覆蓋）
                current_sha = None
                try:
                    async with session.get(
                        api_url,
                        headers={
                            "Authorization": f"token {github_token}",
                            "Accept": "application/vnd.github.v3+json",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            current_sha = data.get("sha")
                        elif resp.status == 404:
                            print("ℹ️ 檔案不存在，將創建新檔案")
                except Exception as e:
                    print(f"⚠️ 獲取 SHA 失敗（首次上傳可忽略）: {e}")

                # 上傳數據
                upload_data = {
                    "message": f"Auto-update leaderboard: {user_count} users - {datetime.datetime.now().isoformat()}",
                    "content": encoded_content,
                    "branch": "main",
                }
                if current_sha:
                    upload_data["sha"] = current_sha

                # PUT 上傳
                async with session.put(
                    api_url,
                    json=upload_data,
                    headers={
                        "Authorization": f"token {github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in [200, 201]:
                        print(f"✅ GitHub API 上傳成功 ({user_count} 使用者)")
                        print(
                            "📍 CDN: https://raw.githubusercontent.com/chenkankan1103/kkgroup/main/docs/assets/leaderboard.png"
                        )
                    else:
                        error_text = await resp.text()
                        print(
                            f"❌ GitHub API 上傳失敗 ({resp.status}): {error_text[:200]}"
                        )

        except Exception as e:
            print(f"❌ API 上傳錯誤: {e}")
            import traceback

            traceback.print_exc()

    @auto_push_leaderboard_to_github.before_loop
    async def before_auto_push_leaderboard(self):
        """✅ [已停用] 原來用於初始化定時推送的方法

        現在改用事件驅動模式，此方法不再需要
        """
        # 原來的延遲邏輯已不需要，保持空實現以維持結構
        pass

    async def get_tunnel_url(self):
        """從 config/config.json 或 /tmp/cloudflared.log 讀取 Cloudflare Quick Tunnel 網址

        優先順序:
        1. config/config.json (GitHub同步，優先級最高 - 確保本機開發和GCP部署URL一致)
        2. /tmp/cloudflared.log (GCP VM本地cloudflared - 備用)

        成功: 更新 self.base_url 並返回該 URL
        失敗: 返回 None
        """
        async with self.tunnel_url_lock:
            try:
            import json

            # 1️⃣ 優先方式: 嘗試讀取 config/config.json (GitHub同步，確保URL一致)
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            config_file = os.path.join(project_root, "config", "config.json")

            if os.path.exists(config_file):
                try:
                    def _read_config():
                        with open(config_file, "r", encoding="utf-8") as f:
                            return json.load(f)
                    config_data = await asyncio.to_thread(_read_config)
                    tunnel_url = config_data.get("url")

                    if tunnel_url and tunnel_url.startswith("https://"):
                        self.base_url = tunnel_url
                        print(
                            f"✅ 已設定 Tunnel URL (from config.json): {tunnel_url}"
                        )
                        return tunnel_url
                except Exception as config_err:
                    print(f"⚠️ 從 config.json 讀取失敗: {config_err}")

            # 2️⃣ 備用方式: 嘗試讀取 /tmp/cloudflared.log (本地cloudflared)
            log_file = "/tmp/cloudflared.log"
            if os.path.exists(log_file):
                try:
                    def _read_log():
                        with open(
                            log_file, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            return f.read()
                    content = await asyncio.to_thread(_read_log)

                    # 使用 regex 抓取最新的 https://*.trycloudflare.com URL
                    pattern = r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com"
                    matches = re.findall(pattern, content)

                    if matches:
                        # 取最後一個（最新的）
                        tunnel_url = matches[-1]
                        self.base_url = tunnel_url
                        print(f"✅ 已設定 Tunnel URL (from log): {tunnel_url}")
                        return tunnel_url
                except Exception as log_err:
                    print(f"⚠️ 從 log 讀取失敗: {log_err}")

            print("⚠️ 無法獲取隧道 URL (兩種方式均失敗)")
            return None

        except Exception as e:
            print(f"❌ 讀取隧道 URL 失敗: {e}")
            return None

async def setup(bot):
    await bot.add_cog(KKCoin(bot))
