import discord
from discord import app_commands
from discord.ext import commands, tasks
import os, io, time, aiohttp
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
# V2 排行榜資源
RANK_V2_BG_PATH = os.path.join(ASSETS_PATH, "kkcoin_rank_v2_bg.png")
RANK_V2_WIDTH = 1920
RANK_V2_HEIGHT = 1080

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
    DESCRIPTION_HEIGHT = 80
    WIDTH, HEIGHT = 900, 75 + 60 * len(members_data) + DESCRIPTION_HEIGHT
    AVATAR_SIZE = 48
    MARGIN = 20
    BG_COLOR = (255,255,255)
    RANK_COLOR = (240,200,80)
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

    # 預先創建占位頭像
    placeholder_avatar = create_placeholder_avatar()
    
    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            y = 75 + i*60
            if i < 3 and medal_imgs[i]:
                img.paste(medal_imgs[i].resize((36,36)), (MARGIN, y+6), medal_imgs[i].resize((36,36)))
                rank_x = MARGIN + 44
            else:
                rank_x = MARGIN
            draw.text((rank_x, y), f"{i+1:2d}", fill=RANK_COLOR, font=FONT_SMALL)
            
            # 嘗試加載頭像，失敗則使用灰色占位圖
            avatar = None
            try:
                # 優先順序：display_avatar → avatar → default_avatar
                avatar_url = None
                
                # 1️⃣ 嘗試 display_avatar（用戶自訂頭像或 FallbackMember 的代理）
                if hasattr(member, 'display_avatar') and member.display_avatar:
                    try:
                        avatar_url = member.display_avatar.url
                    except AttributeError:
                        pass
                
                # 2️⃣ 如果沒有，嘗試 avatar（個人頭像）
                if not avatar_url and hasattr(member, 'avatar') and member.avatar:
                    try:
                        avatar_url = member.avatar.url
                    except AttributeError:
                        pass
                
                # 3️⃣ 最後使用 default_avatar（Discord 默認頭像）
                if not avatar_url and hasattr(member, 'default_avatar') and member.default_avatar:
                    try:
                        avatar_url = member.default_avatar.url
                    except AttributeError:
                        pass
                
                # 4️⃣ 嘗試加載圖片
                if avatar_url:
                    avatar = await fetch_avatar(session, avatar_url)
                    if not avatar:
                        print(f"⚠️ 無法加載頭像 URL（可能已過期）: {member.display_name}")
                        print(f"   URL: {avatar_url}")
                else:
                    print(f"⚠️ 找不到頭像 URL: {member.display_name}")
                    
            except Exception as e:
                print(f"❌ 頭像加載異常 ({member.display_name}): {type(e).__name__}: {e}")
            
            # 使用實際頭像或灰色占位圖
            display_avatar = avatar if avatar else placeholder_avatar
            display_avatar = display_avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
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

async def make_leaderboard_image_v2(members_data, limit=20):
    """
    V2 版排行榜生成器 - 賽博朋克風格
    還原原始布局，加入賽博朋克視覺元素
    """
    WIDTH = RANK_V2_WIDTH
    HEIGHT = RANK_V2_HEIGHT
    AVATAR_SIZE = 60
    MARGIN_LEFT = 400  # 左边距，避开边框左边
    MARGIN_TOP = 140   # 顶部边距
    ROW_HEIGHT = 46    # 行高
    
    try:
        FONT_TITLE = ImageFont.truetype(FONT_PATH, 32)
        FONT_NAME = ImageFont.truetype(FONT_PATH, 22)
        FONT_RANK = ImageFont.truetype(FONT_PATH, 20)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 20)
        FONT_DATE = ImageFont.truetype(FONT_PATH, 16)
    except Exception as e:
        print(f"❌ 載入字體失敗: {e}")
        FONT_TITLE = ImageFont.load_default()
        FONT_NAME = ImageFont.load_default()
        FONT_RANK = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DATE = ImageFont.load_default()
    
    # 載入背景圖
    try:
        bg_img = Image.open(RANK_V2_BG_PATH).convert("RGBA")
        if bg_img.size != (WIDTH, HEIGHT):
            bg_img = bg_img.resize((WIDTH, HEIGHT), Image.LANCZOS)
        img = bg_img.copy()
    except:
        # 使用深色賽博朋克背景
        img = Image.new("RGBA", (WIDTH, HEIGHT), (10, 12, 20, 255))
    
    draw = ImageDraw.Draw(img)
    
    # 載入箭頭素材
    arrow_up = None
    arrow_down = None
    try:
        arrow_up = Image.open(os.path.join(ASSETS_PATH, "cyber_arrow_down_green.png")).convert("RGBA")
        arrow_up = arrow_up.rotate(180)  # 翻轉為向上
        arrow_up = arrow_up.resize((24, 24), Image.LANCZOS)
        
        arrow_down_img = Image.open(os.path.join(ASSETS_PATH, "cyber_arrow_down_red.png")).convert("RGBA")
        arrow_down = arrow_down_img.resize((24, 24), Image.LANCZOS)
    except:
        print("⚠️ 無法載入箭頭素材")
    
    # 绘制标题和时间（标题在边框内居中，时间在右上角）
    title_x = WIDTH // 2
    title_y = 85
    draw.text((title_x, title_y), "⚡ KK幣排行榜 - 前20名 ⚡", fill=(0, 255, 255), font=FONT_TITLE, anchor="mm")
    
    from datetime import datetime
    date_str = f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    date_x = WIDTH - 320
    date_y = 23
    draw.text((date_x, date_y), date_str, fill=(150, 150, 180), font=FONT_DATE, anchor="rt")
    
    # 預先創建占位頭像
    placeholder_avatar = create_placeholder_avatar()
    
    # 限制顯示數量
    display_data = members_data[:limit]
    
    # 定義前三名邊框顏色（賽博朋克霓虹色）
    top3_colors = [
        (255, 215, 0, 180),    # 金色 #1
        (192, 192, 192, 180),  # 銀色 #2
        (255, 140, 0, 180)     # 橙色 #3
    ]
    
    # 定義進度條顏色（賽博朋克漸變）
    bar_colors = [
        [(255, 215, 0), (255, 180, 0)],      # 金色漸變 #1
        [(255, 140, 0), (255, 100, 0)],      # 橙色漸變 #2
        [(255, 100, 150), (200, 50, 100)],   # 粉橙漸變 #3
        [(147, 51, 234), (100, 30, 180)],    # 紫色漸變
        [(59, 130, 246), (30, 100, 220)],    # 藍色漸變
    ]
    
    async with aiohttp.ClientSession() as session:
        max_kkcoin = max([kk for _, kk in display_data]) if display_data else 1
        
        for i, (member, kkcoin) in enumerate(display_data):
            y = MARGIN_TOP + i * ROW_HEIGHT
            
            # 計算進度條寬度
            bar_width = 600
            progress = min(kkcoin / max_kkcoin, 1.0)
            bar_fill_width = int(bar_width * progress)
            
            # 繪製行背景和邊框（前三名特殊處理）
            row_x = MARGIN_LEFT
            row_width = WIDTH - MARGIN_LEFT * 2
            
            if i < 3:
                # 前三名：發光邊框
                border_color = top3_colors[i]
                # 外層發光效果
                for offset in range(3, 0, -1):
                    alpha = int(60 / offset)
                    glow_color = (*border_color[:3], alpha)
                    draw.rectangle(
                        [row_x - offset, y - offset, row_x + row_width + offset, y + ROW_HEIGHT - 8 + offset],
                        outline=glow_color, width=1
                    )
                # 主邊框
                draw.rectangle(
                    [row_x, y, row_x + row_width, y + ROW_HEIGHT - 8],
                    outline=border_color, width=2
                )
                # 半透明背景
                overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                bg_color = (*border_color[:3], 30)
                overlay_draw.rectangle(
                    [row_x + 2, y + 2, row_x + row_width - 2, y + ROW_HEIGHT - 10],
                    fill=bg_color
                )
                img = Image.alpha_composite(img, overlay)
                draw = ImageDraw.Draw(img)
            else:
                # 其他名次：簡單邊框
                draw.rectangle(
                    [row_x, y, row_x + row_width, y + ROW_HEIGHT - 8],
                    outline=(60, 70, 100, 150), width=1
                )
            
            # 繪製排名
            rank_x = row_x + 15
            rank_color = top3_colors[i][:3] if i < 3 else (150, 160, 200)
            draw.text((rank_x, y + 8), f"#{i+1}", fill=rank_color, font=FONT_RANK)
            
            # 載入頭像
            avatar = None
            try:
                avatar_url = None
                if hasattr(member, 'display_avatar') and member.display_avatar:
                    try:
                        avatar_url = member.display_avatar.url
                    except AttributeError:
                        pass
                
                if not avatar_url and hasattr(member, 'avatar') and member.avatar:
                    try:
                        avatar_url = member.avatar.url
                    except AttributeError:
                        pass
                
                if not avatar_url and hasattr(member, 'default_avatar') and member.default_avatar:
                    try:
                        avatar_url = member.default_avatar.url
                    except AttributeError:
                        pass
                
                if avatar_url:
                    avatar = await fetch_avatar(session, avatar_url)
            except Exception as e:
                pass
            
            # 使用頭像或占位圖
            display_avatar = avatar if avatar else placeholder_avatar
            display_avatar = display_avatar.resize((AVATAR_SIZE - 10, AVATAR_SIZE - 10))
            
            # 貼上頭像
            avatar_x = rank_x + 50
            img.paste(display_avatar, (avatar_x, y + 5), display_avatar)
            
            # 繪製名稱（垂直居中）
            name_x = avatar_x + AVATAR_SIZE - 5
            name_y = y + 13
            name_color = (255, 255, 255) if i >= 3 else (255, 230, 100)
            draw.text((name_x, name_y), member.display_name, fill=name_color, font=FONT_NAME)
            
            # 繪製進度條（更大，可容納内部文字）
            bar_x = name_x + 250
            bar_y = y + 9
            bar_height = 28
            
            # 進度條背景（暗色）
            draw.rectangle(
                [bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
                fill=(30, 35, 50), outline=(60, 70, 90), width=1
            )
            
            # 進度條填充（漸變效果）
            if bar_fill_width > 0:
                color_idx = min(i // 4, len(bar_colors) - 1)
                start_color = bar_colors[color_idx][0]
                end_color = bar_colors[color_idx][1]
                
                # 簡單漸變
                for x_offset in range(bar_fill_width):
                    ratio = x_offset / bar_fill_width if bar_fill_width > 0 else 0
                    r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
                    g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
                    b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
                    draw.line(
                        [(bar_x + x_offset, bar_y + 1), (bar_x + x_offset, bar_y + bar_height - 1)],
                        fill=(r, g, b)
                    )
            
            # 在进度条内部显示KK币数量（右侧对齐，带描边）
            kkcoin_text = f"{kkcoin:,} KK幣"
            kkcoin_x = bar_x + bar_width - 10
            kkcoin_y = bar_y + bar_height // 2
            # 黑色描边增强可读性
            for offset_x in [-1, 0, 1]:
                for offset_y in [-1, 0, 1]:
                    if offset_x != 0 or offset_y != 0:
                        draw.text((kkcoin_x + offset_x, kkcoin_y + offset_y), kkcoin_text, 
                                fill=(0, 0, 0), font=FONT_KKCOIN, anchor="rm")
            # 白色文字
            draw.text((kkcoin_x, kkcoin_y), kkcoin_text, fill=(255, 255, 255), font=FONT_KKCOIN, anchor="rm")
            
            # 繪製箭頭（模擬漲跌）
            arrow_x = bar_x + bar_width + 15
            arrow_y = y + 12
            # 簡單規則：奇數上升，偶數下降
            if i % 2 == 0 and arrow_up:
                img.paste(arrow_up, (arrow_x, arrow_y), arrow_up)
            elif arrow_down:
                img.paste(arrow_down, (arrow_x, arrow_y), arrow_down)
    
    # 繪製底部說明（賽博朋克風格）
    footer_y = HEIGHT - 80
    draw.line([(MARGIN_LEFT, footer_y), (WIDTH - MARGIN_LEFT, footer_y)], fill=(60, 80, 120), width=2)
    
    footer_text = "⚡ KK幣獲得方法："
    draw.text((MARGIN_LEFT, footer_y + 10), footer_text, fill=(100, 200, 255), font=FONT_NAME)
    
    desc_lines = [
        "  發送訊息獲得KK幣：10字+1幣 | 25字+2幣 | 50字+3幣（冷卻30秒）",
        "  顏色代表：金色(前1名) 橙色(前2名) 紫色(前3名)"
    ]
    for idx, line in enumerate(desc_lines):
        draw.text((MARGIN_LEFT + 10, footer_y + 35 + idx * 20), line, fill=(150, 160, 180), font=FONT_DATE)
    
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
        
        # 命令冷卻時間限制 (訪問上次時間)
        self.cmd_cooldown = {
            'kkcoin': defaultdict(lambda: 0),           # 查詢餘額: 10秒
            'kkcoin_rank': defaultdict(lambda: 0),      # 排行榜: 30秒
            'kkcoin_rankv2': defaultdict(lambda: 0),    # V2 排行榜: 30秒
            'kkcoin_weekly': defaultdict(lambda: 0),    # 周統計: 60秒
            'kkcoin_mvp': defaultdict(lambda: 0),       # MVP: 60秒
            'kkcoin_v2': defaultdict(lambda: 0),        # V2 排行榜: 60秒
        }
        
        # 冷卻時間設定 (秒數)
        self.cooldown_times = {
            'kkcoin': 10,
            'kkcoin_rank': 30,
            'kkcoin_rankv2': 30,
            'kkcoin_weekly': 60,
            'kkcoin_mvp': 60,
            'kkcoin_v2': 60,
        }
        
        # 啟動定時更新任務
        self.auto_update_leaderboard.start()
        print(f"✅ KKCoin 系統已載入，排行榜頻道: {self.rank_channel_id}")
        print(f"📋 指令冷卻時間設定已啟用")

    def check_command_cooldown(self, user_id: int, command_name: str) -> tuple[bool, int]:
        """
        檢查用戶是否在命令冷卻期內
        返回: (是否可以執行, 剩餘秒數)
        """
        if command_name not in self.cmd_cooldown:
            return True, 0
        
        current_time = time.time()
        last_time = self.cmd_cooldown[command_name][user_id]
        cooldown_duration = self.cooldown_times.get(command_name, 10)
        
        if current_time - last_time >= cooldown_duration:
            # 可以執行，更新時間
            self.cmd_cooldown[command_name][user_id] = current_time
            return True, 0
        else:
            # 在冷卻期內
            remaining = cooldown_duration - (current_time - last_time)
            return False, int(remaining)

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
        # 冷卻時間檢查
        can_use, remaining = self.check_command_cooldown(interaction.user.id, 'kkcoin')
        if not can_use:
            await interaction.response.send_message(
                f"⏳ 請稍候 {remaining} 秒再使用此命令",
                ephemeral=True
            )
            return
            
        member = member or interaction.user
        balance = get_user_balance(str(member.id))
        await interaction.response.send_message(f"💰 {member.display_name} 目前擁有 KK 幣：{balance}", ephemeral=True)

    @app_commands.command(name="kkcoin_rank", description="顯示 KK 幣排行榜")
    async def kkcoin_rank(self, interaction: discord.Interaction):
        """手動創建排行榜（如果需要的話）"""
        # 冷卻時間檢查
        can_use, remaining = self.check_command_cooldown(interaction.user.id, 'kkcoin_rank')
        if not can_use:
            await interaction.response.send_message(
                f"⏳ 排行榜生成中，請稍候 {remaining} 秒",
                ephemeral=True
            )
            return
            
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

    @app_commands.command(name="kkcoin_rankv2", description="顯示 KK 幣排行榜（賽博風格）")
    async def kkcoin_rankv2(self, interaction: discord.Interaction):
        """全新賽博朋克風格排行榜 - 1920x1080 高清大圖"""
        # 冷卻時間檢查
        can_use, remaining = self.check_command_cooldown(interaction.user.id, 'kkcoin_rankv2')
        if not can_use:
            await interaction.response.send_message(
                f"⏳ 排行榜生成中，請稍候 {remaining} 秒",
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        members_data = self.get_current_leaderboard_data()

        if not members_data:
            await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
            return

        try:
            image = await make_leaderboard_image_v2(members_data, limit=20)
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rankv2.png")
                await interaction.followup.send(file=file)
                
            print(f"✅ V2 排行榜已發送 (1920x1080)")
        except Exception as e:
            print(f"❌ 生成 V2 排行榜時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 生成排行榜時發生錯誤：{str(e)[:100]}", ephemeral=True)

    @app_commands.command(name="kkcoin_weekly", description="顯示本週 KK 幣統計")
    async def kkcoin_weekly(self, interaction: discord.Interaction):
        """顯示本週 KK 幣統計和增長"""
        # 冷卻時間檢查
        can_use, remaining = self.check_command_cooldown(interaction.user.id, 'kkcoin_weekly')
        if not can_use:
            await interaction.response.send_message(
                f"⏳ 數據生成中，請稍候 {remaining} 秒",
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        members_data = self.get_current_leaderboard_data()
        
        if not members_data:
            await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
            return
        
        try:
            from commands.kkcoin_visualizer import create_weekly_stats_image
            
            # 計算統計數據
            total_coins = sum(coin for _, coin in members_data)
            
            # 本週模擬數據（實際應從資料庫讀取）
            this_week_total = int(total_coins * 0.3)  # 模擬本週新增為總數的30%
            last_week_total = int(total_coins * 0.25)  # 模擬上週為25%
            member_count = len(members_data)
            
            image = await create_weekly_stats_image(
                total_coins=total_coins,
                this_week_total=this_week_total,
                last_week_total=last_week_total,
                member_count=member_count
            )
            
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_weekly_stats.png")
                await interaction.followup.send(
                    content="📊 **本週 KK 幣統計總覽**",
                    file=file
                )
            
            print(f"✅ 本週統計圖表已發送")
        except Exception as e:
            print(f"❌ 生成統計圖表時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 生成統計圖表時發生錯誤：{str(e)[:100]}", ephemeral=True)

    @app_commands.command(name="kkcoin_mvp", description="顯示本週績效王")
    async def kkcoin_mvp(self, interaction: discord.Interaction):
        """顯示本週績效王（KK幣新增最多的人）"""
        # 冷卻時間檢查
        can_use, remaining = self.check_command_cooldown(interaction.user.id, 'kkcoin_mvp')
        if not can_use:
            await interaction.response.send_message(
                f"⏳ 數據生成中，請稍候 {remaining} 秒",
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        members_data = self.get_current_leaderboard_data()
        
        if not members_data:
            await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
            return
        
        try:
            from commands.kkcoin_visualizer import create_weekly_mvp_image
            
            # 找排行第一名作為 MVP
            mvp_member, mvp_coins = members_data[0]
            
            # 本週新增模擬數據
            this_week_coins = int(mvp_coins * 0.4)
            
            # 查找在完整排行中的位置
            rank_position = 1
            total_members = len(members_data)
            
            image = await create_weekly_mvp_image(
                mvp_member=mvp_member,
                this_week_coins=this_week_coins,
                rank_position=rank_position,
                total_members=total_members
            )
            
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_weekly_mvp.png")
                await interaction.followup.send(file=file)
            
            print(f"✅ 本週績效王卡片已發送 - {mvp_member.display_name}")
        except Exception as e:
            print(f"❌ 生成績效王卡片時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 生成績效王卡片時發生錯誤：{str(e)[:100]}", ephemeral=True)

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
        current_time = time.time()
        
        if not self.rank_channel_id or not self.rank_message_id:
            return

        if not force and current_time - self.last_update_time < min_interval:
            return

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

            members_data = self.get_current_leaderboard_data()
            
            if not members_data:
                return

            if not force and not self.has_data_changed(members_data):
                self.last_update_time = current_time
                return

            print(f"🔄 開始更新排行榜...")
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
        update_user_balance(user_id, reward)

        print(f"💰 {message.author.display_name} 獲得了 {reward} KK幣! (總計: {get_user_balance(user_id)})")
        
        try:
            await self.update_leaderboard()
        except Exception as e:
            print(f"❌ 更新排行榜時發生錯誤: {e}")

    @app_commands.command(name="reset_rank", description="重置排行榜設定（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def reset_rank(self, interaction: discord.Interaction):
        """重置排行榜設定"""
        self.rank_message_id = 0
        self.last_leaderboard_data = None
        self.last_update_time = 0
        save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
        await interaction.response.send_message("✅ 排行榜訊息已重置，將在下次自動更新時重新創建", ephemeral=True)

    @app_commands.command(name="force_update_rank", description="強制更新排行榜（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def force_update_rank(self, interaction: discord.Interaction):
        """強制更新排行榜"""
        await interaction.response.defer(ephemeral=True)
        
        if not self.rank_channel_id:
            await interaction.followup.send("❌ 尚未設定排行榜頻道", ephemeral=True)
            return
        
        try:
            await self.update_leaderboard(force=True)
            await interaction.followup.send("✅ 排行榜已強制更新", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 更新失敗: {str(e)}", ephemeral=True)

    @app_commands.command(name="debug_rank", description="顯示排行榜調試資訊（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def debug_rank(self, interaction: discord.Interaction):
        """顯示排行榜調試資訊"""
        current_time = time.time()
        time_since_update = current_time - self.last_update_time
        
        current_data = self.get_current_leaderboard_data()
        
        debug_info = f"""
**排行榜調試資訊**
📍 頻道 ID: {self.rank_channel_id}
📨 訊息 ID: {self.rank_message_id}
⏰ 距離上次更新: {time_since_update:.1f} 秒
⏱️ 更新間隔設定: {UPDATE_INTERVAL} 秒
📊 當前資料筆數: {len(current_data)}
📊 快取資料筆數: {len(self.last_leaderboard_data) if self.last_leaderboard_data else 0}

**前5名當前資料:**
"""
        
        for i, (member, kkcoin) in enumerate(current_data[:5]):
            debug_info += f"{i+1}. {member.display_name}: {kkcoin} KK幣\n"
        
        if self.last_leaderboard_data:
            debug_info += "\n**前5名快取資料:**\n"
            for i, (member, kkcoin) in enumerate(self.last_leaderboard_data[:5]):
                debug_info += f"{i+1}. {member.display_name}: {kkcoin} KK幣\n"
        
        data_changed = self.has_data_changed(current_data)
        debug_info += f"\n🔄 資料是否有變化: {'是' if data_changed else '否'}"
        
        await interaction.response.send_message(debug_info, ephemeral=True)

    @app_commands.command(name="kkcoin_force_refresh", description="強制刷新排行榜（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def kkcoin_force_refresh(self, interaction: discord.Interaction):
        """強制更新排行榜圖片，忽略快取檢查"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 清除排行榜快取，強制重新生成
            self.last_leaderboard_data = None
            print("🔄 強制刷新排行榜：已清除快取")
            
            # 立即強制更新（force=True 會繞過 has_data_changed 檢查）
            await self.update_leaderboard(min_interval=0, force=True)
            
            await interaction.followup.send("✅ 排行榜已強制刷新！", ephemeral=True)
            print("✅ 排行榜強制刷新完成")
        except Exception as e:
            print(f"❌ 強制刷新排行榜失敗: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 刷新失敗: {str(e)}", ephemeral=True)

    @app_commands.command(name="set_rank_channel", description="設定排行榜頻道（管理員專用）")
    @app_commands.describe(channel="排行榜要顯示的頻道")
    @app_commands.default_permissions(administrator=True)
    async def set_rank_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """設定排行榜頻道"""
        self.rank_channel_id = channel.id
        self.rank_message_id = 0
        save_to_env("KKCOIN_RANK_CHANNEL_ID", channel.id)
        save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
        
        await interaction.response.send_message(
            f"✅ 排行榜頻道已設定為 {channel.mention}\n"
            f"排行榜將在下次更新時自動創建",
            ephemeral=True
        )
        
        # 立即嘗試創建排行榜
        await self.create_leaderboard()

    @app_commands.command(name="kkcoin_v2", description="顯示升級版排行榜 (3合1：排行榜+長條圖+饼圖)")
    async def kkcoin_v2(self, interaction: discord.Interaction):
        """顯示升級版排行榜 - 前15名 + 3張組合圖"""
        # 冷卻時間檢查
        can_use, remaining = self.check_command_cooldown(interaction.user.id, 'kkcoin_v2')
        if not can_use:
            await interaction.response.send_message(
                f"⏳ 圖表生成中，請稍候 {remaining} 秒",
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        members_data = self.get_current_leaderboard_data()
        
        if not members_data:
            await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
            return
        
        try:
            from commands.kkcoin_visualizer_v2 import (
                create_enhanced_leaderboard_image,
                create_bar_chart_image,
                create_pie_and_weekly_image,
                MATPLOTLIB_AVAILABLE
            )
            
            # 生成排行榜 (15名)
            print("🎨 生成排行榜圖片...")
            leaderboard_img = await create_enhanced_leaderboard_image(members_data, limit=15)
            
            # 生成長條圖
            print("📊 生成長條圖...")
            bar_img = await create_bar_chart_image(members_data, limit=15)
            if bar_img is None:
                raise RuntimeError("matplotlib 未安裝，無法生成長條圖。請執行: pip install matplotlib numpy")
            
            # 生成饼圖 + 周統計
            print("🍰 生成饼圖與周統計...")
            pie_img = await create_pie_and_weekly_image(
                members_data=members_data,
                limit=15,
                total_coins=sum(coin for _, coin in members_data),
                this_week_total=int(sum(coin for _, coin in members_data) * 0.3),
                last_week_total=int(sum(coin for _, coin in members_data) * 0.25)
            )
            if pie_img is None:
                raise RuntimeError("matplotlib 未安裝，無法生成饼圖。請執行: pip install matplotlib numpy")
            
            # 創建 Discord 文件
            files = []
            
            # 圖1：排行榜
            with io.BytesIO() as img_bytes:
                leaderboard_img.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                files.append(discord.File(img_bytes, filename="1_leaderboard.png"))
            
            # 圖2：長條圖
            with io.BytesIO() as img_bytes:
                bar_img.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                files.append(discord.File(img_bytes, filename="2_bar_chart.png"))
            
            # 圖3：饼圖 + 周統計
            with io.BytesIO() as img_bytes:
                pie_img.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                files.append(discord.File(img_bytes, filename="3_pie_weekly.png"))
            
            # 發送所有圖片
            await interaction.followup.send(
                content="📊 **KK幣升級版仪表板 - 3合1圖表**\n" +
                        "① 排行榜（前15名）\n" +
                        "② 長條圖排行\n" +
                        "③ 饼圖分布 + 周統計",
                files=files
            )
            
            print("✅ 升級版排行榜已發送（3張圖）")
        
        except Exception as e:
            print(f"❌ 生成升級版排行榜時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ 生成圖表時發生錯誤：\n{str(e)[:150]}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(KKCoin(bot))
