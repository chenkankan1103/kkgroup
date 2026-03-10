import discord
from discord import app_commands
from discord.ext import commands, tasks
import os, io, time, aiohttp
import asyncio
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from dotenv import load_dotenv, set_key
from io import BytesIO

# 匯入新的 DB 適配層
from db_adapter import get_user_field, add_user_field

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
UPDATE_INTERVAL = 10  # 更新間隔改為 10 秒

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
    """協程版本的圖片生成流程（在執行器中運行以避免阻塞）：
    1. 非同步地下載所有頭像（非密集型）
    2. 將所有 CPU 密集型的 PIL 繪製工作扔到 thread pool
    """
    # 先收集相關靜態資源，這部分屬於共享且不會每次都重新載入
    DESCRIPTION_HEIGHT = 80
    WIDTH, HEIGHT = 900, 75 + 60 * len(members_data) + DESCRIPTION_HEIGHT
    AVATAR_SIZE = 48
    MARGIN = 20
    BG_COLOR = (255,255,255)
    RANK_COLOR = (240,200,80)

    # fonts 和圖片都可以在同步函式中載入，因此在 thread 中進行
    # 先取得每個成員的頭像（或佔位）
    avatar_images = []
    placeholder = create_placeholder_avatar()
    async with aiohttp.ClientSession() as session:
        for member, _ in members_data:
            avatar = None
            try:
                url = None
                if hasattr(member, 'display_avatar') and member.display_avatar:
                    try:
                        url = member.display_avatar.url
                    except AttributeError:
                        pass
                if not url and hasattr(member, 'avatar') and member.avatar:
                    try:
                        url = member.avatar.url
                    except AttributeError:
                        pass
                if not url and hasattr(member, 'default_avatar') and member.default_avatar:
                    try:
                        url = member.default_avatar.url
                    except AttributeError:
                        pass
                if url:
                    avatar = await asyncio.wait_for(
                        fetch_avatar(session, url),
                        timeout=5.0  # 每個頭像 5 秒超時
                    )
                    if not avatar:
                        avatar = None  # 之後會替換成 placeholder
            except asyncio.TimeoutError:
                pass  # 頭像下載超時，使用 placeholder
            except Exception as e:
                print(f"❌ 頭像下載錯誤 ({member.display_name}): {e}")
            avatar_images.append(avatar or placeholder)

    # ✅ 在執行緒中完成剩下的繪製工作（避免阻塞事件迴圈）
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_build_leaderboard_image,
        members_data,
        avatar_images,
        WIDTH,
        HEIGHT,
        DESCRIPTION_HEIGHT,
        AVATAR_SIZE,
        MARGIN,
        BG_COLOR,
        RANK_COLOR,
    )


def _sync_build_leaderboard_image(
    members_data,
    avatar_images,
    WIDTH,
    HEIGHT,
    DESCRIPTION_HEIGHT,
    AVATAR_SIZE,
    MARGIN,
    BG_COLOR,
    RANK_COLOR,
):
    """純同步版，執行在工作執行緒中，不會阻塞事件循環"""
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, 28)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, 22)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 24)
        FONT_DESC = ImageFont.truetype(FONT_PATH, 16)
    except Exception as e:
        print(f"❌ 載入字體失敗: {e}")
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
    try:
        trophy_img = Image.open(TROPHY_PATH).convert("RGBA")
    except Exception as e:
        print(f"❌ 載入 trophy.png 失敗: {e}")
        trophy_img = None
    medal_imgs = []
    for idx, path in enumerate(MEDAL_PATHS):
        try:
            medal_imgs.append(Image.open(path).convert("RGBA"))
        except Exception as e:
            print(f"❌ 載入 medal {idx+1} 失敗: {e}")
            medal_imgs.append(None)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    if trophy_img:
        img.paste(trophy_img.resize((44,44)), (MARGIN, 12), trophy_img.resize((44,44)))
        title_x = MARGIN + 54
    else:
        title_x = MARGIN
    draw.text((title_x, 18), "KK幣排行榜（前20名）", fill=(60,60,60), font=FONT_BIG)

    # 畫各行
    for i, ((member, kkcoin), avatar_img) in enumerate(zip(members_data, avatar_images)):
        y = 75 + i*60
        if i < 3 and medal_imgs[i]:
            img.paste(medal_imgs[i].resize((36,36)), (MARGIN, y+6), medal_imgs[i].resize((36,36)))
            rank_x = MARGIN + 44
        else:
            rank_x = MARGIN
        draw.text((rank_x, y), f"{i+1:2d}", fill=RANK_COLOR, font=FONT_SMALL)

        display_avatar = avatar_img.resize((AVATAR_SIZE, AVATAR_SIZE))
        img.paste(display_avatar, (rank_x + 40, y), display_avatar)
        name_x = rank_x + 100
        name_y = y+8
        draw.text((name_x, name_y), member.display_name, fill=(30,30,30), font=FONT_SMALL)
        draw.text((WIDTH-180, y+8), f"{kkcoin} KK幣", fill=(50,110,210), font=FONT_KKCOIN)

    desc_y = 75 + len(members_data) * 60 + 15
    draw.line([(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)], fill=(200,200,200), width=1)
    descriptions = [
        " 發送訊息獲得KK幣：10字+1幣 | 25字+2幣 | 50字+3幣 （冷卻30秒）",
        " 限制：重複訊息、純表情不給幣 |  語音掛機可獲得額外獎勵"
    ]
    draw.text((MARGIN, desc_y), " KKcoin獲得方法：", fill=(80,80,80), font=FONT_SMALL)
    for i, desc in enumerate(descriptions):
        desc_text_y = desc_y + 25 + i * 22
        draw.text((MARGIN + 10, desc_text_y), desc, fill=(100,100,100), font=FONT_DESC)

    return img

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
        
        self.last_kkcoin_time = defaultdict(lambda: 0)
        self.last_message_cache = defaultdict(str)
        self.last_update_time = 0
        self.last_leaderboard_data = None
        
        # 啟動定時更新任務
        self.auto_update_leaderboard.start()
        print(f"✅ KKCoin 系統已載入，排行榜頻道: {self.rank_channel_id}")

    def cog_unload(self):
        """當 Cog 卸載時停止定時任務"""
        self.auto_update_leaderboard.cancel()

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
                    return
                except discord.NotFound:
                    print(f"⚠️ 訊息 {self.rank_message_id} 不存在，嘗試重新查找...")
                    self.rank_message_id = 0
                    save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
            
            # 在頻道中查找所有訊息，尋找舊的排行榜訊息
            print("🔍 在頻道中查找舊排行榜訊息...")
            async for msg in channel.history(limit=100):
                if msg.author.id == self.bot.user.id and msg.attachments:
                    for attachment in msg.attachments:
                        if "kkcoin_rank" in attachment.filename:
                            print(f"✅ 找到舊排行榜訊息 ID: {msg.id}，將重用此訊息")
                            self.rank_message_id = msg.id
                            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
                            return
            
            # 如果沒有找到舊訊息，等待第一次循環自動創建
            print("📝 未找到舊訊息，將在第一次循環時創建...")
        
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
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rank.png")
                msg = await channel.send(file=file)
            
            # 立即儲存訊息 ID（防止重複創建）
            self.rank_message_id = msg.id
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
            
            # 快取資料
            self.last_leaderboard_data = members_data.copy()
            self.last_update_time = time.time()
            
            print(f"✅ 排行榜已創建 - 頻道: {channel.name}, 訊息 ID: {msg.id}")
            
        except Exception as e:
            print(f"❌ 創建排行榜失敗: {e}")
            import traceback
            traceback.print_exc()

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
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rank.png")
                msg = await interaction.followup.send(file=file)

            # 更新設定
            save_to_env("KKCOIN_RANK_CHANNEL_ID", interaction.channel.id)
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
            self.rank_channel_id = interaction.channel.id
            self.rank_message_id = msg.id
            
            self.last_leaderboard_data = members_data.copy()
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
        """取得當前排行榜資料"""
        if not self.rank_channel_id:
            return []
            
        channel = self.bot.get_channel(self.rank_channel_id)
        if not channel:
            return []
            
        guild = channel.guild
        
        from db_adapter import get_all_users
        
        members_data = []
        all_users = get_all_users()
        
        # 篩選 kkcoin > 0，排序，取前 20
        # 修正：處理 kkcoin 為 None 的情況
        users = [u for u in all_users if (u.get('kkcoin') or 0) > 0]
        users.sort(key=lambda x: (x.get('kkcoin') or 0), reverse=True)
        users = users[:20]
        
        # 嘗試獲取 Discord member，若失敗則使用 DB 數據
        for user in users:
            user_id = int(user["user_id"])
            member = guild.get_member(user_id)
            
            if member:
                # ✅ 成功找到 Discord member
                members_data.append((member, user["kkcoin"]))
            else:
                # ⚠️ Guild 中沒有該成員，使用備用方案
                # 創建一個簡單的對象來存儲用戶信息，包括 Discord 默認頭像
                class FallbackMember:
                    """當玩家不在 Guild 中時使用的備用成員對象"""
                    def __init__(self, user_id, nickname):
                        self.id = user_id
                        self.display_name = nickname or f"未知玩家 ({user_id})"
                        
                        # 為 FallbackMember 構造一個虛擬的 display_avatar 對象
                        # Discord 默認頭像 URL: https://cdn.discordapp.com/embed/avatars/{color}.png
                        # color 是 0-5 之間的顏色索引（根據用戶 ID 計算）
                        avatar_color = user_id % 6  # 0-5 之間
                        default_avatar_url = f"https://cdn.discordapp.com/embed/avatars/{avatar_color}.png"
                        
                        # 構造一個類似 display_avatar 的對象
                        class AvatarProxy:
                            def __init__(self, url):
                                self.url = url
                        
                        self.display_avatar = AvatarProxy(default_avatar_url)
                
                fallback = FallbackMember(
                    user_id,
                    user.get('nickname', user.get('user_name', f'User {user_id}'))
                )
                members_data.append((fallback, user["kkcoin"]))
        
        return members_data

    def has_data_changed(self, new_data):
        """檢查資料是否有變化，返回 True 表示有變化"""
        if not self.last_leaderboard_data:
            print("🔍 沒有快取資料，需要更新")
            return True
            
        if len(new_data) != len(self.last_leaderboard_data):
            print(f"🔍 資料筆數變化：{len(self.last_leaderboard_data)} → {len(new_data)}")
            return True
        
        for i, (member, kkcoin) in enumerate(new_data):
            if i >= len(self.last_leaderboard_data):
                print(f"🔍 索引超出範圍：{i}")
                return True
                
            old_member, old_kkcoin = self.last_leaderboard_data[i]
            
            # 安全比較 KK幣 (處理 None 值)
            new_kk = kkcoin or 0
            old_kk = old_kkcoin or 0
            
            if member.id != old_member.id:
                print(f"🔍 排名變化：位置 {i+1} 從 {old_member.display_name} 變成 {member.display_name}")
                return True
                
            if new_kk != old_kk:
                print(f"🔍 KK幣變化：{member.display_name} 從 {old_kk} 變成 {new_kk}")
                return True
        
        print("🔍 資料沒有變化，跳過更新")
        return False

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
                    self.last_update_time = current_time
                    return

                print(f"🔄 開始更新排行榜...")
                # 生成圖片 (內部會在需要時移至執行緒)
                image = await make_leaderboard_image(members_data)

                with io.BytesIO() as img_bytes:
                    image.save(img_bytes, format="PNG")
                    img_bytes.seek(0)
                    file = discord.File(img_bytes, filename="kkcoin_rank.png")
                    await msg.edit(attachments=[file])

                self.last_leaderboard_data = members_data.copy()
                self.last_update_time = current_time
                print(f"✅ 排行榜更新成功 ({len(members_data)} 名使用者)")

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
            len(content) < 10 or
            now - self.last_kkcoin_time[user_id] < USER_COOLDOWN_SECONDS or
            content == self.last_message_cache[user_id]
        ):
            return

        reward = 3 if len(content) >= 50 else 2 if len(content) >= 25 else 1

        self.last_kkcoin_time[user_id] = now
        self.last_message_cache[user_id] = content
        # 同步操作寫入資料庫可能較快，但若擔心可改為 to_thread
        update_user_balance(user_id, reward)
        print(f"💰 {message.author.display_name} 獲得了 {reward} KK幣! (總計: {get_user_balance(user_id)})")

        # 排行榜更新不等待，透過 create_task 並靠內部節流控制頻率
        asyncio.create_task(self.update_leaderboard())













async def setup(bot):
    await bot.add_cog(KKCoin(bot))
