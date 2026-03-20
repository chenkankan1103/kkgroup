import discord
from discord import app_commands
from discord.ext import commands, tasks
import os, io, time, aiohttp, re, subprocess, json, datetime
import asyncio
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from dotenv import load_dotenv, set_key
from io import BytesIO

# 匯入新的 DB 適配層
from db_adapter import (
    get_user_field, add_user_field,
    get_central_reserve, add_to_central_reserve, remove_from_central_reserve, set_central_reserve,
    get_reserve_pressure, get_dynamic_fee_rate, get_reserve_announcement
)

# 匯入排行榜管理模組
from .leaderboard_manager import (
    make_leaderboard_image,
    get_current_leaderboard_data,
    has_data_changed,
    get_digital_usd_leaderboard_data,
    has_digital_usd_data_changed,
    make_digital_usd_leaderboard_image,
)

# 載入 .env 檔案
load_dotenv()

# 配置常數
DB_FILE = "user_data.db"
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")
TROPHY_PATH = os.path.join(ASSETS_PATH, "trophy.png")
MEDAL_PATHS = [
    os.path.join(ASSETS_PATH, "1.png"),  # 金牌
    os.path.join(ASSETS_PATH, "2.png"),  # 銀牌
    os.path.join(ASSETS_PATH, "3.png"),  # 銅牌
]
USER_COOLDOWN_SECONDS = 30
UPDATE_INTERVAL = 300  # 更新間隔改為 5 分鐘 (300 秒)

# 資料庫初始化
def initialize_database():
    """初始化數據庫 (已遷移到 Sheet-Driven 系統)"""
    try:
        from db_adapter import get_db
        db = get_db()
        print(f"✅ KKCoin DB 就緒")
    except Exception as e:
        print(f"❌ KKCoin DB 初始化失敗: {e}")

# 資料庫操作方法
def get_user_balance(user_id):
    """獲取玩家 KKCoin 餘額"""
    return get_user_field(user_id, 'kkcoin', default=0)

def update_user_balance(user_id, amount):
    """更新玩家 KKCoin 餘額"""
    return add_user_field(user_id, 'kkcoin', amount)

def get_user_digital_usd(user_id):
    """獲取玩家數位美金（洗出的白錢）"""
    value = get_user_field(user_id, 'digital_usd', default=0)
    # 確保返回的是數字類型（處理字符串情況）
    if isinstance(value, str):
        # 處理空字符串
        if not value or value.strip() == '':
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    return float(value) if value else 0.0

def update_user_digital_usd(user_id, amount):
    """更新玩家數位美金"""
    return add_user_field(user_id, 'digital_usd', amount)

# 環境變數操作
def get_from_env(variable_name, default=None):
    return os.getenv(variable_name, default)

def save_to_env(variable_name, value):
    set_key(".env", variable_name, str(value))

# 生成灰色占位頭像（當頭像加載失敗時使用）
def create_placeholder_avatar():
    """創建灰色占位圖像"""
    placeholder = Image.new('RGBA', (48, 48), (200, 200, 200, 255))
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
    emoji_pattern = regex.compile(r'^\s*(?:\p{Emoji_Presentation}|\p{Emoji}\uFE0F|\p{Emoji_Modifier_Base}|\p{Emoji_Component})+\s*$')
    return bool(emoji_pattern.fullmatch(text))

class KKCoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        initialize_database()
        
        # 從 .env 讀取排行榜頻道 ID
        self.rank_channel_id = int(get_from_env("KKCOIN_RANK_CHANNEL_ID", 0))
        self.rank_message_id = int(get_from_env("KKCOIN_RANK_MESSAGE_ID", 0))
        
        # 數位美金排行榜
        self.digital_usd_channel_id = int(get_from_env("DIGITAL_USD_RANK_CHANNEL_ID", 0))
        self.digital_usd_message_id = int(get_from_env("DIGITAL_USD_RANK_MESSAGE_ID", 0))
        
        # 園區中央儲備金狀態
        self.reserve_channel_id = int(get_from_env("RESERVE_STATUS_CHANNEL_ID", 0))
        self.reserve_message_id = int(get_from_env("RESERVE_STATUS_MESSAGE_ID", 0))
        
        self.last_kkcoin_time = defaultdict(lambda: 0)
        self.last_message_cache = defaultdict(str)
        self.last_update_time = 0
        self.last_leaderboard_data = None
        self.last_digital_usd_data = None
        
        # Cloudflare Quick Tunnel 支援
        self.base_url = "https://kkgroup.com"  # 預設值，將在 on_ready 嘗試更新
        self.tunnel_url_lock = asyncio.Lock()
        self.last_synced_tunnel_url = None  # 追蹤上一次同步的 URL
        
        # 啟動定時更新任務
        self.auto_update_leaderboard.start()
        self.auto_update_digital_usd_leaderboard.start()
        self.auto_update_reserve_status.start()
        self.auto_check_tunnel_url.start()  # 🔄 啟動隧道 URL 自動檢查（每 10 分鐘）
        self.auto_push_leaderboard_to_github.start()  # 📤 啟動排行榜 GitHub 推送（每 5 分鐘）
        print(f"✅ KKCoin 系統已載入，排行榜頻道: {self.rank_channel_id}")
        print(f"✅ 數位美金排行榜頻道: {self.digital_usd_channel_id}")
        print(f"✅ 園區儲備狀態頻道: {self.reserve_channel_id}")
        print(f"🔄 隧道 URL 自動檢查已啟用（每 10 分鐘掃描一次）")
        print(f"📤 排行榜每 5 分鐘透過 GitHub API 覆蓋上傳（無歷史累積，CDN 自動分發，VM 無出站流量）")

    def cog_unload(self):
        """當 Cog 卸載時停止定時任務"""
        self.auto_update_leaderboard.cancel()
        self.auto_update_digital_usd_leaderboard.cancel()
        self.auto_update_reserve_status.cancel()
        self.auto_check_tunnel_url.cancel()  # 🔄 取消隧道檢查任務
        if self.auto_push_leaderboard_to_github.is_running():
            self.auto_push_leaderboard_to_github.cancel()  # 📤 取消 GitHub 推送任務
    
    async def sync_to_github(self, new_url, image_url="https://raw.githubusercontent.com/chenkankan1103/kkgroup/main/docs/assets/leaderboard.png"):
        """將新的隧道 URL 同步到 GitHub Pages 入口
        
        參數:
            new_url: 新的 Tunnel URL (e.g., https://xxx.trycloudflare.com)
        
        流程:
            1. 讀取/更新本地 docs/config.json （GitHub Pages 讀取點）
            2. Git add/commit/push 到遠端 GitHub
        """
        try:
            import subprocess
            import json
            from datetime import datetime
            
            # 使用 docs/config.json（GitHub Pages 正確位置）
            config_path = os.path.join(os.path.dirname(__file__), "..", "docs", "config.json")
            
            # 檢查 docs 目錄是否存在
            docs_dir = os.path.dirname(config_path)
            if not os.path.exists(docs_dir):
                print(f"❌ docs 目錄不存在: {docs_dir}")
                return False
            
            # 更新 config.json
            config_data = {
                "url": new_url,
                "API_BASE": new_url,
                "imageURL": image_url,  # 📤 使用 GitHub CDN，不流量隧道
                "DISCORD_URL": "https://discord.gg/5JtuJvhhHu",
                "lastUpdated": datetime.utcnow().isoformat() + "Z"
            }
            
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 已更新 docs/config.json: {new_url}")
            
            # Git 操作（在項目根目錄中執行）
            git_commands = [
                ["git", "add", "docs/config.json"],
                ["git", "commit", "-m", f"Auto-sync: Update tunnel URL to {new_url}"],
                ["git", "push", "origin", "main"]
            ]
            
            for cmd in git_commands:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, cwd=os.path.dirname(__file__) + "/../..")
                    if result.returncode == 0:
                        print(f"✅ Git 指令成功: {' '.join(cmd[1:])}")
                    else:
                        # 如果是 commit 時沒有變更，允許這個錯誤
                        if "nothing to commit" in result.stderr or "nothing added to commit" in result.stderr:
                            print(f"ℹ️  config.json 未有變更，跳過提交")
                        else:
                            print(f"⚠️  Git 指令警告: {result.stderr[:100]}")
                except subprocess.TimeoutExpired:
                    print(f"⏱️ 指令超時: {' '.join(cmd)}")
                    return False
                except Exception as e:
                    print(f"❌ Git 操作失敗: {e}")
                    return False
            
            print(f"🚀 GitHub Pages 已更新隧道 URL: https://chenkankan1103.github.io/kkgroup/")
            return True
        
        except Exception as e:
            print(f"❌ 同步到 GitHub 失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @tasks.loop(minutes=5)
    async def auto_push_leaderboard_to_github(self):
        """🔄 每 5 分鐘自動推送排行榜圖片到 GitHub API（覆蓋模式）
        
        功能:
            1. 生成最新排行榜圖片
            2. 儲存到本地 /var/www/html/assets/leaderboard.png
            3. 使用 GitHub API 直接覆蓋 docs/assets/leaderboard.png （無歷史累積）
            4. CDN 自動更新，減少 VM 出站流量
        """
        try:
            # 取得排行榜資料
            members_data = await asyncio.to_thread(self.get_current_leaderboard_data)
            if not members_data:
                print("⚠️ 無可用排行榜資料，跳過推送")
                return
            
            print("🎨 生成排行榜圖片...")
            image = await make_leaderboard_image(members_data)
            
            # 保存到本地 Nginx（隧道 URL 用）
            leaderboard_nginx_path = "/var/www/html/assets/leaderboard.png"
            try:
                image.save(
                    leaderboard_nginx_path,
                    format="PNG",
                    optimize=True,
                    compress_level=9
                )
                file_size_kb = os.path.getsize(leaderboard_nginx_path) / 1024
                print(f"✅ 排行榜已存到 Nginx: {file_size_kb:.1f}KB")
            except Exception as e:
                print(f"⚠️ Nginx 保存失敗（本地開發可忽略）: {e}")
            
            # 上傳到 GitHub API（覆蓋模式）
            await self._upload_leaderboard_via_api(image, len(members_data))
        
        except Exception as e:
            print(f"❌ 推送排行榜時發生錯誤: {e}")
            import traceback
            traceback.print_exc()

    async def _upload_leaderboard_via_api(self, image, user_count):
        """使用 GitHub API 上傳排行榜（每次直接覆蓋，無歷史累積）"""
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
            encoded_content = base64.b64encode(img_byte_arr.read()).decode('utf-8')
            
            # GitHub API
            owner = "chenkankan1103"
            repo = "kkgroup"
            file_path = "docs/assets/leaderboard.png"  # 存到 docs 目錄
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
            
            async with aiohttp.ClientSession() as session:
                # 先取得現有文件的 SHA（用於覆蓋）
                current_sha = None
                try:
                    async with session.get(
                        api_url,
                        headers={"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            current_sha = data.get('sha')
                        elif resp.status == 404:
                            print("ℹ️ 檔案不存在，將創建新檔案")
                except Exception as e:
                    print(f"⚠️ 獲取 SHA 失敗（首次上傳可忽略）: {e}")
                
                # 上傳數據
                upload_data = {
                    "message": f"Auto-update leaderboard: {user_count} users - {datetime.datetime.now().isoformat()}",
                    "content": encoded_content,
                    "branch": "main"
                }
                if current_sha:
                    upload_data["sha"] = current_sha
                
                # PUT 上傳
                async with session.put(
                    api_url,
                    json=upload_data,
                    headers={"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status in [200, 201]:
                        print(f"✅ GitHub API 上傳成功 ({user_count} 使用者)")
                        print(f"📍 CDN: https://raw.githubusercontent.com/chenkankan1103/kkgroup/main/docs/assets/leaderboard.png")
                    else:
                        error_text = await resp.text()
                        print(f"❌ GitHub API 上傳失敗 ({resp.status}): {error_text[:200]}")
        
        except Exception as e:
            print(f"❌ API 上傳錯誤: {e}")
            import traceback
            traceback.print_exc()

    @auto_push_leaderboard_to_github.before_loop
    async def before_auto_push_leaderboard(self):
        """等待 bot 準備完成後再啟動推送」"""
        await self.bot.wait_until_ready()
        print("✅ GitHub API 自動推送任務已啟動（每 5 分鐘該一次，直接覆蓋無歷史累積，CDN 自動分發）")
        # 延遲 60 秒後首次執行，讓 bot 充分初始化
        await asyncio.sleep(60)
    
    async def get_tunnel_url(self):
        """從 docs/config.json 或 /tmp/cloudflared.log 讀取 Cloudflare Quick Tunnel 網址
        
        優先順序:
        1. docs/config.json (GitHub同步，優先級最高 - 確保本機開發和GCP部署URL一致)
        2. /tmp/cloudflared.log (GCP VM本地cloudflared - 備用)
        
        成功: 更新 self.base_url 並返回該 URL
        失敗: 返回 None
        """
        async with self.tunnel_url_lock:
            try:
                import json
                
                # 1️⃣ 優先方式: 嘗試讀取 docs/config.json (GitHub同步，確保URL一致)
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                config_file = os.path.join(project_root, "docs", "config.json")
                
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            config_data = json.load(f)
                            tunnel_url = config_data.get("url")
                            
                            if tunnel_url and tunnel_url.startswith("https://"):
                                self.base_url = tunnel_url
                                print(f"✅ 已設定 Tunnel URL (from config.json): {tunnel_url}")
                                return tunnel_url
                    except Exception as config_err:
                        print(f"⚠️ 從 config.json 讀取失敗: {config_err}")
                
                # 2️⃣ 備用方式: 嘗試讀取 /tmp/cloudflared.log (本地cloudflared)
                log_file = "/tmp/cloudflared.log"
                if os.path.exists(log_file):
                    try:
                        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
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
                
                print(f"⚠️ 無法獲取隧道 URL (兩種方式均失敗)")
                return None
            
            except Exception as e:
                print(f"❌ 讀取隧道 URL 失敗: {e}")
                return None
    
    @commands.Cog.listener()
    async def on_ready(self):
        """機器人啟動時執行 - 嘗試獲取 Tunnel URL 並同步到 GitHub Pages"""
        print("🔍 正在嘗試獲取 Cloudflare Tunnel URL...")
        tunnel_url = await self.get_tunnel_url()
        
        if tunnel_url:
            # 檢查隧道 URL 是否與上一次不同
            stored_config_path = os.path.join(os.path.dirname(__file__), "..", "web_portal", "config.json")
            last_url = None
            
            try:
                import json
                if os.path.exists(stored_config_path):
                    with open(stored_config_path, "r", encoding="utf-8") as f:
                        stored_config = json.load(f)
                        last_url = stored_config.get("url")
            except Exception as e:
                print(f"⚠️  無法讀取上一次的隧道 URL: {e}")
            
            # 如果 URL 發生變更，同步到 GitHub
            if last_url != tunnel_url:
                print(f"📡 偵測到隧道 URL 變更！")
                print(f"   舊: {last_url}")
                print(f"   新: {tunnel_url}")
                sync_result = await self.sync_to_github(tunnel_url)
                if sync_result:
                    print(f"✅ 已同步到 GitHub Pages 入口")
            else:
                print(f"ℹ️  隧道 URL 未變更，跳過同步")
        else:
            print(
                "\n" + "="*70
                + "\n⚠️  【警告】無法獲取 Cloudflare Quick Tunnel 網址！\n"
                + "="*70
                + "\n\n📋 請在 GCP 終端機執行以下指令：\n\n"
                + "  cloudflared tunnel --url http://localhost:80 --logfile /tmp/cloudflared.log &\n\n"
                + "✅ 執行後，機器人會自動從 /tmp/cloudflared.log 讀取隧道 URL\n\n"
                + "="*70 + "\n"
            )
        
        # 🔥 執行 Nginx 健康檢查
        print("\n🔍 正在執行 Nginx 健康檢查...")
        await self.check_nginx_health()

    async def check_nginx_health(self):
        """✅ 檢查 Nginx 是否正確提供排行榜圖片
        
        功能:
            1. 測試本地 Nginx: http://127.0.0.1/assets/leaderboard.png
            2. 若返回 200 則成功，否則通知管理員
            3. 記錄檢查結果
        """
        admin_id = int(get_from_env("ADMIN_USER_ID", 0))
        if not admin_id:
            print("⚠️  未設定 ADMIN_USER_ID，無法發送健康檢查通知")
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                try:
                    # 測試本地 Nginx 連接
                    async with session.get(
                        "http://127.0.0.1/assets/leaderboard.png", 
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            print(f"✅ 【Nginx 健康檢查】排行榜圖片可正確提供 (HTTP {response.status})")
                            return True
                        else:
                            error_msg = f"❌ 【Nginx 健康檢查失敗】HTTP {response.status} (預期 200)"
                            print(error_msg)
                            
                            # 通知管理員
                            try:
                                admin = await self.bot.fetch_user(admin_id)
                                if admin:
                                    embed = discord.Embed(
                                        title="🚨 Nginx 健康檢查失敗",
                                        description=error_msg,
                                        color=discord.Color.red(),
                                        timestamp=discord.utils.utcnow()
                                    )
                                    embed.add_field(name="📍 檔案路徑", value="/var/www/html/assets/leaderboard.png", inline=False)
                                    embed.add_field(name="🔗 Tunnel URL", value=self.base_url, inline=False)
                                    await admin.send(embed=embed)
                                    print(f"📢 已發送 Discord 警報給管理員 {admin_id}")
                            except Exception as e:
                                print(f"⚠️  無法發送 Discord 通知: {e}")
                            
                            return False
                            
                except asyncio.TimeoutError:
                    error_msg = "❌ 【Nginx 健康檢查失敗】連接超時（可能 Nginx 未啟動）"
                    print(error_msg)
                    
                    # 通知管理員
                    try:
                        admin = await self.bot.fetch_user(admin_id)
                        if admin:
                            embed = discord.Embed(
                                title="🚨 Nginx 連接超時",
                                description=error_msg,
                                color=discord.Color.red(),
                                timestamp=discord.utils.utcnow()
                            )
                            embed.add_field(name="💡 可能原因", value="• Nginx 服務未啟動\n• 防火牆阻擋本地連接\n• 系統資源不足", inline=False)
                            await admin.send(embed=embed)
                    except Exception as e:
                        print(f"⚠️  無法發送 Discord 通知: {e}")
                    
                    return False
                    
        except Exception as e:
            print(f"❌ 【Nginx 健康檢查異常】{e}")
            return False

    @tasks.loop(minutes=10)
    async def auto_check_tunnel_url(self):
        """🔄 每 10 分鐘檢查一次隧道 URL 是否變更
        
        如果隧道 URL 發生變更：
        1. 更新 self.base_url
        2. 同步到 GitHub Pages 的 config.json  
        3. 發送 Discord 警報通知
        """
        try:
            # 獲取當前隧道 URL
            current_tunnel_url = await self.get_tunnel_url()
            
            if not current_tunnel_url:
                # 未找到隧道，使用預設域名
                return
            
            # 檢查 URL 是否與上次已同步的 URL 不同
            if current_tunnel_url != self.last_synced_tunnel_url:
                print(f"\n⚠️  【隧道 URL 變更偵測】")
                print(f"   舊 URL: {self.last_synced_tunnel_url}")
                print(f"   新 URL: {current_tunnel_url}\n")
                
                # 同步到 GitHub
                sync_success = await self.sync_to_github(current_tunnel_url)
                
                if sync_success:
                    self.last_synced_tunnel_url = current_tunnel_url
                    self.base_url = current_tunnel_url
                    
                    # 發送 Discord 通知（如果有指定通知頻道）
                    notify_channel_id = int(get_from_env("TUNNEL_NOTIFY_CHANNEL_ID", 0))
                    if notify_channel_id:
                        try:
                            channel = self.bot.get_channel(notify_channel_id)
                            if channel:
                                embed = discord.Embed(
                                    title="🚀 Cloudflare 隧道 URL 已更新",
                                    description=f"**新網址：** {current_tunnel_url}",
                                    color=discord.Color.green(),
                                    timestamp=discord.utils.utcnow()
                                )
                                embed.add_field(name="📡 狀態", value="✅ GitHub Pages 已同步", inline=False)
                                embed.add_field(name="🔗 入口網址", value="https://chenkankan1103.github.io/kkgroup/", inline=False)
                                await channel.send(embed=embed)
                                print(f"✅ Discord 通知已發送到頻道 {notify_channel_id}")
                        except Exception as e:
                            print(f"⚠️  無法發送 Discord 通知: {e}")
                else:
                    print(f"❌ 同步 GitHub 失敗，隧道 URL 未更新")
        
        except Exception as e:
            print(f"❌ 自動檢查隧道 URL 時發生錯誤: {e}")
            import traceback
            traceback.print_exc()

    @auto_check_tunnel_url.before_loop
    async def before_auto_check_tunnel(self):
        """等待 bot 準備完成後再啟動隧道檢查"""
        await self.bot.wait_until_ready()
        print("✅ 隧道 URL 自動檢查任務已啟動（每 10 分鐘檢查一次）")
        # 立即執行一次檢查
        await self.auto_check_tunnel_url()

    @tasks.loop(minutes=5)
    async def auto_update_leaderboard(self):
        """每 5 分鐘自動更新排行榜"""
        if not self.rank_channel_id:
            return
            
        # 如果沒有訊息 ID，嘗試創建排行榜（只有在 before_loop 失敗時才會執行）
        if not self.rank_message_id:
            await self.create_leaderboard()
        else:
            # 否則更新現有排行榜
            await self.update_leaderboard(min_interval=0)

    @auto_update_leaderboard.before_loop
    async def before_auto_update(self):
        """等待 bot 準備完成，並在啟動時查找/創建排行榜"""
        await self.bot.wait_until_ready()
        print("✅ 排行榜自動更新任務已啟動，正在查找舊訊息...")
        
        # 在 bot 啟動時立即查找或創建排行榜
        if not self.rank_channel_id:
            print("❌ 未設定排行榜頻道 ID")
            return
        
        try:
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到頻道 {self.rank_channel_id}")
                return
            
            # 優先嘗試使用已保存的 rank_message_id
            if self.rank_message_id:
                try:
                    msg = await channel.fetch_message(self.rank_message_id)
                    print(f"✅ 找到並重用排行榜訊息 ID: {self.rank_message_id}")
                    # 立即強制更新一次
                    print("🔄 第一次啟動強制更新排行榜...")
                    await self.update_leaderboard(min_interval=0, force=True)
                    return
                except discord.NotFound:
                    print(f"⚠️ 訊息 {self.rank_message_id} 不存在，嘗試重新查找...")
                    self.rank_message_id = 0
                    save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
            
            # 在頻道中查找所有訊息，尋找舊的排行榜訊息（可能是 Embed 或附件格式）
            print("🔍 在頻道中查找舊排行榜訊息...")
            async for msg in channel.history(limit=100):
                if msg.author.id == self.bot.user.id:
                    # 檢查是否有：1. 經由我們發送的排行榜 Embed，或 2. 帶有排行榜附件的消息
                    is_embed_leaderboard = msg.embeds and any("KK" in embed.title or "排行榜" in embed.title for embed in msg.embeds)
                    is_attachment_leaderboard = msg.attachments and any("kkcoin_rank" in att.filename for att in msg.attachments)
                    
                    if is_embed_leaderboard or is_attachment_leaderboard:
                        print(f"✅ 找到舊排行榜訊息 ID: {msg.id}（格式: {'Embed' if is_embed_leaderboard else '附件'}），將重用此訊息")
                        self.rank_message_id = msg.id
                        save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
                        # 立即強制更新一次
                        print("🔄 第一次啟動強制更新排行榜...")
                        await self.update_leaderboard(min_interval=0, force=True)
                        return
            
            # 如果沒有找到舊訊息，立即創建新的
            print("📝 未找到舊訊息，立即創建新的...")
            await self.create_leaderboard()
        
        except Exception as e:
            print(f"❌ 初始化排行榜時發生錯誤: {e}")
            import traceback
            traceback.print_exc()

    async def create_leaderboard(self):
        """自動創建排行榜訊息（防止重複創建）"""
        if not self.rank_channel_id:
            print("❌ 未設定排行榜頻道 ID")
            return
        
        # 防止同時創建多個排行榜
        if self.rank_message_id:
            print(f"⚠️ 排行榜已存在 (訊息 ID: {self.rank_message_id})，跳過創建")
            return
            
        try:
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到頻道 {self.rank_channel_id}")
                return
            
            members_data = self.get_current_leaderboard_data()
            
            if not members_data:
                print("❌ 沒有使用者資料，無法創建排行榜")
                return
            
            # 創建圖片
            print("🎨 生成排行榜圖片...")
            image = await make_leaderboard_image(members_data)
            
            # 固定儲存路徑（用於 Cloudflare Quick Tunnel）
            leaderboard_path = "/var/www/html/assets/leaderboard.png"
            os.makedirs(os.path.dirname(leaderboard_path), exist_ok=True)
            
            # 儲存到固定路徑（覆蓋舊檔）並進行權限偵測
            try:
                # 優化 PNG：壓縮級別 9（最大），過濾優化
                image.save(
                    leaderboard_path,
                    format="PNG",
                    optimize=True,
                    compress_level=9
                )
                file_size_kb = os.path.getsize(leaderboard_path) / 1024
                print(f"✅ 排行榜已存到: {leaderboard_path} ({file_size_kb:.1f}KB)")
            except PermissionError:
                print(
                    f"❌ 無法寫入 {leaderboard_path}！\\n"
                    f"請在 GCP 中執行以下指令修正權限：\\n"
                    f"  sudo chown -R $USER:$USER /var/www/html"
                )
                return
            except Exception as e:
                print(f"❌ 保存圖片失敗: {e}")
                return
            
            # 使用 GitHub Raw 的排行榜圖片 URL（無隧道流量）
            image_url = "https://raw.githubusercontent.com/chenkankan1103/kkgroup/main/docs/assets/leaderboard.png?t=0"
            embed = discord.Embed(title="🏆 KK幣排行榜", color=discord.Color.gold())
            embed.set_image(url=image_url)
            msg = await channel.send(embed=embed)

            # 立即儲存訊息 ID（防止重複創建）
            self.rank_message_id = msg.id
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)

            # 快取資料
            self.last_leaderboard_data = [m[:3] if len(m) >= 3 else m for m in members_data]
            self.last_update_time = time.time()

            print(f"✅ 排行榜已創建 - 頻道: {channel.name}, 訊息 ID: {msg.id}")
            print(f"📍 圖片 URL: {image_url}")
            
        except Exception as e:
            print(f"❌ 創建排行榜失敗: {e}")
            import traceback
            traceback.print_exc()

    # ============================================================
    # 數位美金排行榜相關
    # ============================================================

    @tasks.loop(minutes=5)
    async def auto_update_digital_usd_leaderboard(self):
        """每 5 分鐘自動更新數位美金排行榜"""
        if not self.digital_usd_channel_id:
            return
            
        # 如果沒有訊息 ID，嘗試創建排行榜
        if not self.digital_usd_message_id:
            await self.create_digital_usd_leaderboard()
        else:
            # 否則更新現有排行榜
            await self.update_digital_usd_leaderboard(min_interval=0)

    @auto_update_digital_usd_leaderboard.before_loop
    async def before_auto_update_digital_usd(self):
        """等待 bot 準備完成，並在啟動時查找/創建數位美金排行榜"""
        await self.bot.wait_until_ready()
        print("✅ 數位美金排行榜自動更新任務已啟動，正在查找舊訊息...")
        
        if not self.digital_usd_channel_id:
            print("⚠️ 未設定數位美金排行榜頻道 ID")
            return
        
        try:
            channel = self.bot.get_channel(self.digital_usd_channel_id)
            if not channel:
                print(f"❌ 找不到數位美金排行榜頻道 {self.digital_usd_channel_id}")
                return
            
            if self.digital_usd_message_id:
                try:
                    msg = await channel.fetch_message(self.digital_usd_message_id)
                    print(f"✅ 找到並重用數位美金排行榜訊息 ID: {self.digital_usd_message_id}")
                    return
                except discord.NotFound:
                    print(f"⚠️ 訊息 {self.digital_usd_message_id} 不存在")
                    self.digital_usd_message_id = 0
                    save_to_env("DIGITAL_USD_RANK_MESSAGE_ID", 0)
        
        except Exception as e:
            print(f"❌ 初始化數位美金排行榜時發生錯誤: {e}")

    # ============================================================
    # 園區中央儲備金狀態相關
    # ============================================================

    @tasks.loop(minutes=2)
    async def auto_update_reserve_status(self):
        """每 2 分鐘自動更新園區儲備狀態"""
        if not self.reserve_channel_id:
            return
            
        # 如果沒有訊息 ID，嘗試創建
        if not self.reserve_message_id:
            await self.create_reserve_status()
        else:
            # 否則更新現有狀態
            await self.update_reserve_status(min_interval=0)

    @auto_update_reserve_status.before_loop
    async def before_auto_update_reserve(self):
        """等待 bot 準備完成"""
        await self.bot.wait_until_ready()
        print("✅ 園區儲備狀態自動更新任務已啟動...")

    async def create_reserve_status(self):
        """創建園區儲備狀態訊息"""
        if not self.reserve_channel_id:
            print("❌ 未設定園區儲備狀態頻道 ID")
            return
        
        if self.reserve_message_id:
            return  # 已存在
            
        try:
            channel = self.bot.get_channel(self.reserve_channel_id)
            if not channel:
                print(f"❌ 找不到儲備狀態頻道 {self.reserve_channel_id}")
                return
            
            embed = self.create_reserve_embed()
            msg = await channel.send(embed=embed)
            
            # 立即儲存訊息 ID
            self.reserve_message_id = msg.id
            save_to_env("RESERVE_STATUS_CHANNEL_ID", channel.id)
            save_to_env("RESERVE_STATUS_MESSAGE_ID", msg.id)
            
            print(f"✅ 園區儲備狀態已創建 - 訊息 ID: {msg.id}")
            
        except Exception as e:
            print(f"❌ 創建儲備狀態失敗: {e}")

    def create_reserve_embed(self) -> discord.Embed:
        """建立園區儲備狀態 Embed"""
        reserve = get_central_reserve()
        pressure = get_reserve_pressure()
        fee_rate = get_dynamic_fee_rate()
        announcement = get_reserve_announcement()
        
        # 繪製壓力條
        bar_length = 20
        filled = int(pressure / 100 * bar_length)
        empty = bar_length - filled
        pressure_bar = "█" * filled + "░" * empty
        
        # 根據壓力等級選擇顏色
        if pressure >= 80:
            color = 0x00ff00  # 綠色 - 充裕
            status = "✅ 充裕"
        elif pressure >= 50:
            color = 0xffff00  # 黃色 - 正常
            status = "🟡 正常"
        else:
            color = 0xff0000  # 紅色 - 風險
            status = "⚠️ 風險"
        
        embed = discord.Embed(
            title="🏦 園區中央儲備金 (The Reserve)",
            description=f"園區資金池管理與金流斷點動態費率系統",
            color=color
        )
        
        embed.add_field(
            name="💰 儲備餘額",
            value=f"**{reserve:,} KK幣**",
            inline=False
        )
        
        embed.add_field(
            name="🌡️ 洗錢壓力",
            value=f"{pressure_bar} {pressure:.1f}% ({status})",
            inline=False
        )
        
        embed.add_field(
            name="💸 動態手續費率",
            value=f"**{fee_rate*100:.1f}%**",
            inline=True
        )
        
        embed.add_field(
            name="📊 壓力影響",
            value="- ≥80% 壓力: 3% 費率 (優待)\n"
                  "- 50-80% 壓力: 5% 費率 (正常)\n"
                  "- <50% 壓力: 8% 費率 (高額)",
            inline=False
        )
        
        embed.add_field(
            name="📢 今日公告",
            value=announcement,
            inline=False
        )
        
        embed.add_field(
            name="💡 說明",
            value="**進帳來源:**\n"
                  "• 玩家股市操作虧損\n"
                  "• 購買道具扣款\n"
                  "• 金流斷點手續費\n\n"
                  "**支出用途:**\n"
                  "• 金流斷點獎勵發放\n"
                  "• 日常活動獎勵",
            inline=False
        )
        
        embed.set_footer(text="自動更新時間: 每 2 分鐘")
        
        return embed

    async def update_reserve_status(self, min_interval=60, force=False):
        """更新園區儲備狀態訊息"""
        if not self.reserve_channel_id or not self.reserve_message_id:
            return
        
        if not force and int(time.time()) % min_interval != 0:
            return  # 簡單節流

        try:
            channel = self.bot.get_channel(self.reserve_channel_id)
            if not channel:
                return

            try:
                msg = await channel.fetch_message(self.reserve_message_id)
            except discord.NotFound:
                print("❌ 儲備狀態訊息已被刪除，將重新創建")
                self.reserve_message_id = 0
                save_to_env("RESERVE_STATUS_MESSAGE_ID", 0)
                await self.create_reserve_status()
                return
            except Exception as e:
                print(f"❌ 取得訊息失敗: {e}")
                return

            embed = self.create_reserve_embed()
            await msg.edit(embed=embed)
            print(f"✅ 儲備狀態已更新")

        except Exception as e:
            print(f"❌ 更新儲備狀態時發生錯誤: {e}")

    async def create_digital_usd_leaderboard(self):
        """自動創建數位美金排行榜訊息"""
        if not self.digital_usd_channel_id:
            print("❌ 未設定數位美金排行榜頻道 ID")
            return
        
        if self.digital_usd_message_id:
            print(f"⚠️ 數位美金排行榜已存在 (訊息 ID: {self.digital_usd_message_id})，跳過創建")
            return
            
        try:
            channel = self.bot.get_channel(self.digital_usd_channel_id)
            if not channel:
                print(f"❌ 找不到頻道 {self.digital_usd_channel_id}")
                return
            
            members_data = self.get_digital_usd_leaderboard_data()
            
            if not members_data:
                print("❌ 沒有使用者資料，無法創建數位美金排行榜")
                return
            
            # 創建圖片
            print("🎨 生成數位美金排行榜圖片...")
            image = await self.make_digital_usd_leaderboard_image(members_data)
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="digital_usd_rank.png")
                msg = await channel.send(file=file)
            
            # 立即儲存訊息 ID
            self.digital_usd_message_id = msg.id
            save_to_env("DIGITAL_USD_RANK_MESSAGE_ID", msg.id)
            
            self.last_digital_usd_data = members_data.copy()
            
            print(f"✅ 數位美金排行榜已創建 - 頻道: {channel.name}, 訊息 ID: {msg.id}")
            
        except Exception as e:
            print(f"❌ 創建數位美金排行榜失敗: {e}")
            import traceback
            traceback.print_exc()

    def get_digital_usd_leaderboard_data(self):
        """取得當前數位美金排行榜資料（已移至 leaderboard_manager）"""
        return get_digital_usd_leaderboard_data(self.bot, self.digital_usd_channel_id)

    async def make_digital_usd_leaderboard_image(self, members_data):
        """生成數位美金排行榜圖片（已移至 leaderboard_manager）"""
        return await make_digital_usd_leaderboard_image(self.bot, members_data)

    async def update_digital_usd_leaderboard(self, min_interval=UPDATE_INTERVAL, force=False):
        """更新數位美金排行榜"""
        current_time = time.time()
        if not self.digital_usd_channel_id or not self.digital_usd_message_id:
            return
        if not force and current_time - self.last_update_time < min_interval:
            return

        if not hasattr(self, "_digital_usd_update_lock"):
            self._digital_usd_update_lock = asyncio.Lock()
        async with self._digital_usd_update_lock:
            try:
                channel = self.bot.get_channel(self.digital_usd_channel_id)
                if not channel:
                    return

                try:
                    msg = await channel.fetch_message(self.digital_usd_message_id)
                except discord.NotFound:
                    print("❌ 數位美金排行榜訊息已被刪除，將重新創建")
                    self.digital_usd_message_id = 0
                    save_to_env("DIGITAL_USD_RANK_MESSAGE_ID", 0)
                    await self.create_digital_usd_leaderboard()
                    return
                except Exception as e:
                    print(f"❌ 取得訊息失敗: {e}")
                    return

                members_data = await asyncio.to_thread(self.get_digital_usd_leaderboard_data)
                if not members_data:
                    return

                if not force and not self.has_digital_usd_data_changed(members_data):
                    return

                print(f"🔄 開始更新數位美金排行榜...")
                image = await self.make_digital_usd_leaderboard_image(members_data)

                with io.BytesIO() as img_bytes:
                    image.save(img_bytes, format="PNG")
                    img_bytes.seek(0)
                    file = discord.File(img_bytes, filename="digital_usd_rank.png")
                    await msg.edit(attachments=[file])

                self.last_digital_usd_data = members_data.copy()
                print(f"✅ 數位美金排行榜更新成功 ({len(members_data)} 名使用者)")

            except Exception as e:
                print(f"❌ 更新數位美金排行榜時發生錯誤: {e}")

    def has_digital_usd_data_changed(self, new_data):
        """檢查數位美金排行榜資料是否有變化（已移至 leaderboard_manager）"""
        return has_digital_usd_data_changed(new_data, self.last_digital_usd_data)

    @app_commands.command(name="kkcoin", description="查詢你的 KK 幣餘額")
    async def kkcoin(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        balance = get_user_balance(str(member.id))
        await interaction.response.send_message(f"💰 {member.display_name} 目前擁有 KK 幣：{balance}", ephemeral=True)

    @app_commands.command(name="kkcoin_rank", description="顯示 KK 幣排行榜")
    async def kkcoin_rank(self, interaction: discord.Interaction):
        """手動創建排行榜（如果需要的話）"""
        await interaction.response.defer()
        
        guild = interaction.guild
        members_data = self.get_current_leaderboard_data()

        if not members_data:
            await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
            return

        try:
            image = await make_leaderboard_image(members_data)
            # 使用 GitHub Raw 的排行榜圖片 URL
            image_url = f"https://raw.githubusercontent.com/chenkankan1103/kkgroup/main/docs/assets/leaderboard.png?t={int(time.time())}"
            embed = discord.Embed(title="🏆 KK幣排行榜", color=discord.Color.gold())
            embed.set_image(url=image_url)
            msg = await interaction.followup.send(embed=embed)

            # 更新設定
            save_to_env("KKCOIN_RANK_CHANNEL_ID", interaction.channel.id)
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
            self.rank_channel_id = interaction.channel.id
            self.rank_message_id = msg.id
            
            self.last_leaderboard_data = [m[:3] if len(m) >= 3 else m for m in members_data]
            self.last_update_time = time.time()

            print(f"✅ 排行榜已手動建立在頻道 {interaction.channel.id}，訊息 ID: {msg.id}")
        except Exception as e:
            print(f"❌ 建立排行榜時發生錯誤: {e}")
            await interaction.followup.send("❌ 建立排行榜時發生錯誤", ephemeral=True)







    @app_commands.command(name="kkcoin_admin", description="管理用戶的 KK 幣（管理員專用）")
    @app_commands.describe(
        member="要修改 KK 幣的用戶",
        action="操作類型",
        amount="數量"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="增加", value="add"),
        app_commands.Choice(name="減少", value="subtract"),
        app_commands.Choice(name="設定為", value="set")
    ])
    @app_commands.default_permissions(administrator=True)
    async def kkcoin_admin(self, interaction: discord.Interaction, member: discord.Member, action: str, amount: int):
        """管理用戶的 KK 幣"""
        if amount < 0:
            await interaction.response.send_message("❌ 數量不能為負數", ephemeral=True)
            return
            
        user_id = str(member.id)
        current_balance = get_user_balance(user_id)
        
        if action == "add":
            new_balance = current_balance + amount
            update_user_balance(user_id, amount)
            action_text = f"增加了 {amount}"
        elif action == "subtract":
            if current_balance < amount:
                await interaction.response.send_message(f"❌ {member.display_name} 目前只有 {current_balance} KK幣，不足扣除 {amount} KK幣", ephemeral=True)
                return
            new_balance = current_balance - amount
            update_user_balance(user_id, -amount)
            action_text = f"減少了 {amount}"
        else:  # set
            difference = amount - current_balance
            update_user_balance(user_id, difference)
            new_balance = amount
            action_text = f"設定為 {amount}"
        
        await interaction.response.send_message(
            f"✅ 已為 {member.display_name} {action_text} KK幣\n"
            f"💰 變更前：{current_balance} KK幣\n"
            f"💰 變更後：{new_balance} KK幣",
            ephemeral=True
        )
        
        print(f"🔧 管理員 {interaction.user.display_name} 為 {member.display_name} {action_text} KK幣 ({current_balance} → {new_balance})")
        
        # 異步更新排行榜
        try:
            await self.update_leaderboard(min_interval=0)
        except Exception as e:
            print(f"❌ 更新排行榜時發生錯誤: {e}")

    def get_current_leaderboard_data(self):
        """取得當前排行榜資料（已移至 leaderboard_manager）"""
        return get_current_leaderboard_data(self.bot, self.rank_channel_id)

    def has_data_changed(self, new_data):
        """檢查資料是否有變化（已移至 leaderboard_manager）"""
        return has_data_changed(new_data, self.last_leaderboard_data)

    async def update_leaderboard(self, min_interval=UPDATE_INTERVAL, force=False):
        """
        更新排行榜
        min_interval: 最小更新間隔（秒）
        force: 是否強制更新（忽略時間和資料變化檢查）
        """
        # 簡單節流：10 秒內只能跑一次
        current_time = time.time()
        if not self.rank_channel_id or not self.rank_message_id:
            return
        if not force and current_time - self.last_update_time < min_interval:
            return

        # 避免同時多次更新，保證只有一個協程在修改同一張圖片
        if not hasattr(self, "_leaderboard_update_lock"):
            self._leaderboard_update_lock = asyncio.Lock()
        async with self._leaderboard_update_lock:
            try:
                channel = self.bot.get_channel(self.rank_channel_id)
                if not channel:
                    print(f"❌ 找不到頻道 {self.rank_channel_id}")
                    return

                try:
                    msg = await channel.fetch_message(self.rank_message_id)
                except discord.NotFound:
                    print("❌ 排行榜訊息已被刪除，將重新創建")
                    self.rank_message_id = 0
                    save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
                    await self.create_leaderboard()
                    return
                except Exception as e:
                    print(f"❌ 取得訊息失敗: {e}")
                    return

                # 將資料擷取與計算移到執行緒，減少事件循環阻塞
                members_data = await asyncio.to_thread(self.get_current_leaderboard_data)
                if not members_data:
                    return

                if not force and not self.has_data_changed(members_data):
                    return

                print(f"🔄 開始更新排行榜...")
                # 生成圖片 (內部會在需要時移至執行緒)
                image = await make_leaderboard_image(members_data)

                # 固定儲存路徑（用於 Cloudflare Quick Tunnel）
                leaderboard_path = "/var/www/html/assets/leaderboard.png"
                os.makedirs(os.path.dirname(leaderboard_path), exist_ok=True)
                
                # 儲存到固定路徑（覆蓋舊檔）並進行權限偵測
                try:
                    # 優化 PNG：壓縮級別 9（最大），濾波優化
                    image.save(
                        leaderboard_path,
                        format="PNG",
                        optimize=True,
                        compress_level=9
                    )
                    # 計算檔案大小
                    file_size_kb = os.path.getsize(leaderboard_path) / 1024
                    print(f"✅ 排行榜已存到: {leaderboard_path} ({file_size_kb:.1f}KB)")
                except PermissionError:
                    print(
                        f"❌ 無法寫入 {leaderboard_path}！\n"
                        f"請在 GCP 中執行以下指令修正權限：\n"
                        f"  sudo chown -R $USER:$USER /var/www/html"
                    )
                    return
                except Exception as e:
                    print(f"❌ 保存圖片失敗: {e}")
                    return

                # 使用 GitHub Raw 的排行榜圖片 URL（無隧道流量）
                image_url = f"https://raw.githubusercontent.com/chenkankan1103/kkgroup/main/docs/assets/leaderboard.png?t={int(time.time())}"
                embed = discord.Embed(title="🏆 KK幣排行榜", color=discord.Color.gold())
                embed.set_image(url=image_url)
                await msg.edit(embed=embed, content=None, attachments=[])

                self.last_leaderboard_data = members_data.copy()
                self.last_update_time = current_time
                file_size_kb = os.path.getsize(leaderboard_path) / 1024
                print(f"✅ 排行榜更新成功 ({len(members_data)} 名使用者，{file_size_kb:.1f}KB) - URL: {image_url}")

            except discord.HTTPException as e:
                print(f"❌ Discord API 錯誤: {e}")
            except Exception as e:
                print(f"❌ 更新排行榜時發生錯誤: {e}")
                import traceback
                traceback.print_exc()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 這個 listener 只負責處理 KK 幣獲取，所有耗時工作都交給背景任務
        if message.author.bot:
            return

        content = message.content.strip()
        user_id = str(message.author.id)
        now = time.time()

        if (
            len(content) < 1 or
            content == self.last_message_cache[user_id]
        ):
            return

        # 字數 = KK幣，最多50幣，無冷卻時間
        reward = min(len(content), 50)

        self.last_message_cache[user_id] = content
        # 同步操作寫入資料庫可能較快，但若擔心可改為 to_thread
        update_user_balance(user_id, reward)
        print(f"💰 {message.author.display_name} 獲得了 {reward} KK幣! (總計: {get_user_balance(user_id)})")

        # 排行榜更新不等待，透過 create_task 並靠內部節流控制頻率
        asyncio.create_task(self.update_leaderboard())

    @app_commands.command(name="reserve_status", description="查詢園區中央儲備金狀態")
    async def reserve_status(self, interaction: discord.Interaction):
        """顯示園區中央儲備金的狀態"""
        await interaction.response.defer()
        
        embed = self.create_reserve_embed()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="reserve_admin", description="管理園區儲備金（管理員專用）")
    @app_commands.describe(
        action="操作類型",
        amount="金額"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="增加", value="add"),
        app_commands.Choice(name="減少", value="subtract"),
        app_commands.Choice(name="設定為", value="set")
    ])
    @app_commands.default_permissions(administrator=True)
    async def reserve_admin(self, interaction: discord.Interaction, action: str, amount: int):
        """管理園區儲備金（測試用）"""
        if amount < 0:
            await interaction.response.send_message("❌ 金額不能為負數", ephemeral=True)
            return
        
        from db_adapter import set_central_reserve, remove_from_central_reserve
        
        current = get_central_reserve()
        
        if action == "add":
            add_to_central_reserve(amount)
            action_text = f"增加了 {amount:,}"
            new_amount = current + amount
        elif action == "subtract":
            if current < amount:
                await interaction.response.send_message(f"❌ 儲備金不足！當前只有 {current:,}，要扣 {amount:,}", ephemeral=True)
                return
            remove_from_central_reserve(amount)
            action_text = f"減少了 {amount:,}"
            new_amount = current - amount
        else:  # set
            set_central_reserve(amount)
            action_text = f"設定為 {amount:,}"
            new_amount = amount
        
        await interaction.response.send_message(
            f"✅ 已為園區儲備金 {action_text}\n"
            f"💰 變更前：{current:,} KK幣\n"
            f"💰 變更後：{new_amount:,} KK幣",
            ephemeral=True
        )
        
        print(f"🔧 管理員 {interaction.user.display_name} {action_text} 園區儲備金 ({current:,} → {new_amount:,})")













async def setup(bot):
    await bot.add_cog(KKCoin(bot))
