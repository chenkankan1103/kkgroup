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
from db_adapter import (
    get_user_field, add_user_field,
    get_central_reserve, add_to_central_reserve, remove_from_central_reserve, set_central_reserve,
    get_reserve_pressure, get_dynamic_fee_rate, get_reserve_announcement
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
    """協程版本的圖片生成流程：
    1. 非同步地下載所有頭像（非密集型）
    2. 將所有 CPU 密集型的 PIL 繪製工作扔到 thread pool
    """
    RESERVE_SECTION_HEIGHT = 120  # 儲備池區域高度（置頂）
    DESCRIPTION_HEIGHT = 90
    WIDTH, HEIGHT = 1000, RESERVE_SECTION_HEIGHT + 75 + 60 * len(members_data) + DESCRIPTION_HEIGHT
    AVATAR_SIZE = 48
    MARGIN = 20
    BG_COLOR = (255,255,255)
    RANK_COLOR = (240,200,80)

    # 先取得每個成員的頭像（或佔位）
    avatar_images = []
    placeholder = create_placeholder_avatar()
    async with aiohttp.ClientSession() as session:
        for i, member_data in enumerate(members_data):
            # 相容新舊格式（三元組或二元組）
            if len(member_data) == 3:
                member, _, _ = member_data
            else:
                member = member_data[0]
            
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
                print(f"❌ 頭像下載錯誤: {e}")
            avatar_images.append(avatar or placeholder)

    # 獲取金庫信息
    reserve = get_central_reserve()
    reserve_pressure = get_reserve_pressure()
    reserve_announcement = get_reserve_announcement()
    
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
        RESERVE_SECTION_HEIGHT,
        AVATAR_SIZE,
        MARGIN,
        BG_COLOR,
        RANK_COLOR,
        reserve,
        reserve_pressure,
        reserve_announcement,
    )


def _sync_build_leaderboard_image(
    members_data,
    avatar_images,
    WIDTH,
    HEIGHT,
    DESCRIPTION_HEIGHT,
    RESERVE_SECTION_HEIGHT,
    AVATAR_SIZE,
    MARGIN,
    BG_COLOR,
    RANK_COLOR,
    reserve,
    reserve_pressure,
    reserve_announcement,
):
    """純同步版，執行在工作執行緒中，不會阻塞事件循環"""
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, 28)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, 22)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 20)
        FONT_DESC = ImageFont.truetype(FONT_PATH, 16)
    except Exception as e:
        print(f"❌ 載入字體失敗: {e}，使用預設字體")
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
    
    # 改進的圖片加載（有容錯機制）
    trophy_img = None
    try:
        if os.path.exists(TROPHY_PATH):
            trophy_img = Image.open(TROPHY_PATH).convert("RGBA")
        else:
            print(f"⚠️ 獎杯圖片不存在: {TROPHY_PATH}")
    except Exception as e:
        print(f"⚠️ 載入獎杯圖片失敗: {e}")
    
    medal_imgs = []
    for idx, path in enumerate(MEDAL_PATHS):
        try:
            if os.path.exists(path):
                medal_imgs.append(Image.open(path).convert("RGBA"))
            else:
                print(f"⚠️ 獎牌 {idx+1} 不存在: {path}")
                medal_imgs.append(None)
        except Exception as e:
            print(f"⚠️ 載入獎牌 {idx+1} 失敗: {e}")
            medal_imgs.append(None)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # ========== 第一部分：置頂的儲備池區塊 ==========
    # 背景色
    reserve_bg_y_start = MARGIN
    reserve_bg_y_end = MARGIN + RESERVE_SECTION_HEIGHT - 5
    draw.rectangle(
        [(MARGIN, reserve_bg_y_start), (WIDTH - MARGIN, reserve_bg_y_end)],
        fill=(245, 250, 255),  # 淺藍背景
        outline=(200, 220, 240),
        width=2
    )
    
    # 儲備池標題
    draw.text((MARGIN + 10, MARGIN + 8), "🏦 園區中央儲備池", fill=(0, 100, 200), font=FONT_BIG)
    
    # 餘額和壓力 (同一行)
    reserve_formatted = f"{reserve:,.0f}" if reserve else "0"
    draw.text((MARGIN + 15, MARGIN + 45), f"💰 {reserve_formatted} KK", fill=(50,110,210), font=FONT_SMALL)
    
    # 壓力條
    bar_x = MARGIN + 280
    bar_y = MARGIN + 48
    bar_width = WIDTH - MARGIN - bar_x - 20
    bar_height = 18
    
    # 背景條（灰色）
    draw.rectangle(
        [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
        fill=(220, 220, 220),
        outline=(180, 180, 180)
    )
    
    # 根據壓力等級選擇顏色
    if reserve_pressure < 33:
        pressure_color = (76, 175, 80)  # 綠色 - 低壓力
    elif reserve_pressure < 66:
        pressure_color = (255, 193, 7)  # 黃色 - 中等壓力
    else:
        pressure_color = (244, 67, 54)  # 紅色 - 高壓力
    
    # 填充條（根據壓力比例）
    filled_width = int(bar_width * reserve_pressure / 100)
    if filled_width > 0:
        draw.rectangle(
            [(bar_x, bar_y), (bar_x + filled_width, bar_y + bar_height)],
            fill=pressure_color
        )
    
    # 壓力比例文字
    pressure_text = f"{reserve_pressure:.0f}%"
    draw.text((bar_x + 8, bar_y + 2), pressure_text, fill=(50, 50, 50), font=FONT_DESC)
    
    # 簡介說明
    if reserve_announcement:
        draw.text((MARGIN + 15, MARGIN + 75), f"📢 {reserve_announcement}", fill=(100,100,100), font=FONT_DESC)
    else:
        draw.text((MARGIN + 15, MARGIN + 75), "💡 儲備池用於金流斷點手續費收取與獎勵發放", fill=(100,100,100), font=FONT_DESC)
    
    # ========== 第二部分：排行榜標題和資料 ==========
    leaderboard_start_y = MARGIN + RESERVE_SECTION_HEIGHT + 10
    
    if trophy_img:
        try:
            img.paste(trophy_img.resize((44,44)), (MARGIN, leaderboard_start_y + 5), trophy_img.resize((44,44)))
            title_x = MARGIN + 54
        except Exception as e:
            print(f"⚠️ 貼上獎杯失敗: {e}")
            title_x = MARGIN
    else:
        title_x = MARGIN
    
    draw.text((title_x, leaderboard_start_y + 8), "💰 金流斷點交易所 - 總資產排行", fill=(60,60,60), font=FONT_BIG)

    # ========== 畫各行 ==========
    for i, member_data in enumerate(zip(members_data, avatar_images)):
        # 相容新舊格式（三元組或二元組）
        if len(member_data[0]) == 3:
            member, kkcoin, digital_usd = member_data[0]
        else:
            member, kkcoin = member_data[0]
            digital_usd = 0
        
        avatar_img = member_data[1]
        
        y = leaderboard_start_y + 75 + i*60
        if i < 3 and medal_imgs[i]:
            try:
                img.paste(medal_imgs[i].resize((36,36)), (MARGIN, y+6), medal_imgs[i].resize((36,36)))
                rank_x = MARGIN + 44
            except Exception as e:
                print(f"⚠️ 貼上獎牌失敗: {e}")
                rank_x = MARGIN
        else:
            rank_x = MARGIN
        
        draw.text((rank_x, y), f"{i+1:2d}", fill=RANK_COLOR, font=FONT_SMALL)

        try:
            display_avatar = avatar_img.resize((AVATAR_SIZE, AVATAR_SIZE))
            img.paste(display_avatar, (rank_x + 40, y), display_avatar)
        except Exception as e:
            print(f"⚠️ 貼上頭像失敗: {e}")
        
        name_x = rank_x + 100
        name_y = y+8
        draw.text((name_x, name_y), member.display_name, fill=(30,30,30), font=FONT_SMALL)
        
        # 同時顯示 KK幣和數位美金
        kkcoin_text = f"{int(kkcoin)} KK"
        usd_text = f"${digital_usd:,.0f}"
        draw.text((WIDTH-280, y+8), kkcoin_text, fill=(50,110,210), font=FONT_KKCOIN)
        draw.text((WIDTH-120, y+8), usd_text, fill=(50,200,50), font=FONT_KKCOIN)

    # ========== 第三部分：說明區塊 ==========
    desc_y = leaderboard_start_y + 75 + len(members_data) * 60 + 15
    draw.line([(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)], fill=(200,200,200), width=1)
    
    descriptions = [
        " 💬 KK幣是「未洗淨的髒錢」- 交易/賣出資產時給予",
        " 🔄 可透過「金流斷點」轉換為 💵 數位美金（D-USD）",
        " 📊 排名計算：總資產 = KK幣 + (D-USD ÷ 35)"
    ]
    draw.text((MARGIN, desc_y), " 📚 金流說明：", fill=(80,80,80), font=FONT_SMALL)
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
        
        # 啟動定時更新任務
        self.auto_update_leaderboard.start()
        self.auto_update_digital_usd_leaderboard.start()
        self.auto_update_reserve_status.start()
        print(f"✅ KKCoin 系統已載入，排行榜頻道: {self.rank_channel_id}")
        print(f"✅ 數位美金排行榜頻道: {self.digital_usd_channel_id}")
        print(f"✅ 園區儲備狀態頻道: {self.reserve_channel_id}")

    def cog_unload(self):
        """當 Cog 卸載時停止定時任務"""
        self.auto_update_leaderboard.cancel()
        self.auto_update_digital_usd_leaderboard.cancel()
        self.auto_update_reserve_status.cancel()

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
            self.last_leaderboard_data = [m[:3] if len(m) >= 3 else m for m in members_data]
            self.last_update_time = time.time()
            
            print(f"✅ 排行榜已創建 - 頻道: {channel.name}, 訊息 ID: {msg.id}")
            
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
        """取得當前數位美金排行榜資料"""
        if not self.digital_usd_channel_id:
            return []
            
        channel = self.bot.get_channel(self.digital_usd_channel_id)
        if not channel:
            return []
            
        guild = channel.guild
        
        from db_adapter import get_all_users
        
        members_data = []
        all_users = get_all_users()
        
        # 篩選 digital_usd > 0，排序，取前 20
        users = [u for u in all_users if (u.get('digital_usd') or 0) > 0]
        users.sort(key=lambda x: (x.get('digital_usd') or 0), reverse=True)
        users = users[:20]
        
        for user in users:
            user_id = int(user["user_id"])
            member = guild.get_member(user_id)
            
            if member:
                members_data.append((member, user["digital_usd"]))
            else:
                class FallbackMember:
                    def __init__(self, user_id, nickname):
                        self.id = user_id
                        self.display_name = nickname or f"未知玩家 ({user_id})"
                        avatar_color = user_id % 6
                        default_avatar_url = f"https://cdn.discordapp.com/embed/avatars/{avatar_color}.png"
                        
                        class AvatarProxy:
                            def __init__(self, url):
                                self.url = url
                        
                        self.display_avatar = AvatarProxy(default_avatar_url)
                
                fallback = FallbackMember(
                    user_id,
                    user.get('nickname', user.get('user_name', f'User {user_id}'))
                )
                members_data.append((fallback, user["digital_usd"]))
        
        return members_data

    async def make_digital_usd_leaderboard_image(self, members_data):
        """生成數位美金排行榜圖片"""
        DESCRIPTION_HEIGHT = 80
        WIDTH, HEIGHT = 900, 75 + 60 * len(members_data) + DESCRIPTION_HEIGHT
        AVATAR_SIZE = 48
        MARGIN = 20
        BG_COLOR = (255,255,255)
        RANK_COLOR = (50,200,50)  # 綠色用於美金

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
                            timeout=5.0
                        )
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"❌ 頭像下載錯誤 ({member.display_name}): {e}")
                avatar_images.append(avatar or placeholder)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_build_digital_usd_leaderboard_image,
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

    def _sync_build_digital_usd_leaderboard_image(
        self,
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
        """純同步版數位美金排行榜圖片生成"""
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

        img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        draw.text((MARGIN, 18), "💵 虛擬金融市場 - 數位美金排行", fill=(50,200,50), font=FONT_BIG)

        # 畫各行
        for i, ((member, digital_usd), avatar_img) in enumerate(zip(members_data, avatar_images)):
            y = 75 + i*60
            rank_x = MARGIN
            draw.text((rank_x, y), f"{i+1:2d}", fill=RANK_COLOR, font=FONT_SMALL)

            display_avatar = avatar_img.resize((AVATAR_SIZE, AVATAR_SIZE))
            img.paste(display_avatar, (rank_x + 40, y), display_avatar)
            name_x = rank_x + 100
            name_y = y+8
            draw.text((name_x, name_y), member.display_name, fill=(30,30,30), font=FONT_SMALL)
            draw.text((WIDTH-220, y+8), f"${digital_usd:,.0f} D-USD", fill=(50,200,50), font=FONT_KKCOIN)

        desc_y = 75 + len(members_data) * 60 + 15
        draw.line([(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)], fill=(200,200,200), width=1)
        descriptions = [
            " 💵 數位美金 (D-USD) 是「洗淨的白錢」- 透過「金流斷點」轉換而來",
            " 🔄 轉換公式：KK幣 × 95% (扣5%損耗) ÷ 35 = D-USD"
        ]
        draw.text((MARGIN, desc_y), " 🏦 虛擬金融說明：", fill=(50,200,50), font=FONT_SMALL)
        for i, desc in enumerate(descriptions):
            desc_text_y = desc_y + 25 + i * 22
            draw.text((MARGIN + 10, desc_text_y), desc, fill=(100,100,100), font=FONT_DESC)

        return img

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
        """檢查數位美金排行榜資料是否有變化"""
        if not self.last_digital_usd_data:
            return True
            
        if len(new_data) != len(self.last_digital_usd_data):
            return True
        
        for i, (member, digital_usd) in enumerate(new_data):
            if i >= len(self.last_digital_usd_data):
                return True
                
            old_member, old_digital_usd = self.last_digital_usd_data[i]
            
            new_usd = digital_usd or 0
            old_usd = old_digital_usd or 0
            
            if member.id != old_member.id or new_usd != old_usd:
                return True
        
        return False

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
        """取得當前排行榜資料（包含 KK幣和數位美金，按總資產排序）"""
        if not self.rank_channel_id:
            return []
            
        channel = self.bot.get_channel(self.rank_channel_id)
        if not channel:
            return []
            
        guild = channel.guild
        
        from db_adapter import get_all_users
        
        members_data = []
        all_users = get_all_users()
        
        # 篩選有資產的使用者，按總資產排序 (KK幣 + 數位美金/35)
        users = [u for u in all_users if (u.get('kkcoin') or 0) > 0 or (u.get('digital_usd') or 0) > 0]
        users.sort(
            key=lambda x: (x.get('kkcoin') or 0) + (x.get('digital_usd') or 0) / 35,
            reverse=True
        )
        users = users[:20]
        
        # 嘗試獲取 Discord member，若失敗則使用 DB 數據
        for user in users:
            user_id = int(user["user_id"])
            kkcoin = user.get('kkcoin') or 0
            digital_usd = user.get('digital_usd') or 0
            
            member = guild.get_member(user_id)
            
            if member:
                # ✅ 成功找到 Discord member
                members_data.append((member, kkcoin, digital_usd))
            else:
                # ⚠️ Guild 中沒有該成員，使用備用方案
                class FallbackMember:
                    """當玩家不在 Guild 中時使用的備用成員對象"""
                    def __init__(self, user_id, nickname):
                        self.id = user_id
                        self.display_name = nickname or f"未知玩家 ({user_id})"
                        
                        avatar_color = user_id % 6
                        default_avatar_url = f"https://cdn.discordapp.com/embed/avatars/{avatar_color}.png"
                        
                        class AvatarProxy:
                            def __init__(self, url):
                                self.url = url
                        
                        self.display_avatar = AvatarProxy(default_avatar_url)
                
                fallback = FallbackMember(
                    user_id,
                    user.get('nickname', user.get('user_name', f'User {user_id}'))
                )
                members_data.append((fallback, kkcoin, digital_usd))
        
        return members_data

    def has_data_changed(self, new_data):
        """檢查資料是否有變化，返回 True 表示有變化"""
        if not self.last_leaderboard_data:
            print("🔍 沒有快取資料，需要更新")
            return True
            
        if len(new_data) != len(self.last_leaderboard_data):
            print(f"🔍 資料筆數變化：{len(self.last_leaderboard_data)} → {len(new_data)}")
            return True
        
        for i, (member, kkcoin, digital_usd) in enumerate(new_data):
            if i >= len(self.last_leaderboard_data):
                print(f"🔍 索引超出範圍：{i}")
                return True
                
            old_member, old_kkcoin, old_digital_usd = self.last_leaderboard_data[i]
            
            # 安全比較 KK幣和數位美金(處理 None 值)
            new_kk = kkcoin or 0
            old_kk = old_kkcoin or 0
            new_usd = digital_usd or 0
            old_usd = old_digital_usd or 0
            
            if member.id != old_member.id:
                print(f"🔍 排名變化：位置 {i+1} 從 {old_member.display_name} 變成 {member.display_name}")
                return True
                
            if new_kk != old_kk or new_usd != old_usd:
                print(f"🔍 資料變化：{member.display_name} ({old_kk} KK, ${old_usd} USD → {new_kk} KK, ${new_usd} USD)")
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
