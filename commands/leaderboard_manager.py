"""
=== 排行榜管理模組 ===

負責所有排行榜相關功能：
1. 圖片生成 (KK幣排行榜, 數位美金排行榜)
2. 數據提取和處理
3. 自動更新任務
4. Discord 訊息管理

這個模組從 kcoin.py 中獨立出來，以提升代碼可讀性和維護性。
"""

import discord
from discord.ext import commands, tasks
import os
import io
import time
import aiohttp
import re
import asyncio
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv, set_key

# pilmoji 用於正確處理 Emoji 渲染
try:
    from pilmoji import Pilmoji
    PILMOJI_AVAILABLE = True
except ImportError:
    PILMOJI_AVAILABLE = False
    print("⚠️ pilmoji 未安裝，Emoji 渲染可能不完美。執行: pip install pilmoji")

# 匯入資料庫相關
from db_adapter import (
    get_central_reserve, 
    get_reserve_pressure, 
    get_reserve_announcement,
    get_all_users
)

# 載入 .env 檔案
load_dotenv()

# 配置常數
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")
TROPHY_PATH = os.path.join(ASSETS_PATH, "trophy.png")
MEDAL_PATHS = [
    os.path.join(ASSETS_PATH, "1.png"),  # 金牌
    os.path.join(ASSETS_PATH, "2.png"),  # 銀牌
    os.path.join(ASSETS_PATH, "3.png"),  # 銅牌
]
UPDATE_INTERVAL = 300  # 更新間隔改為 5 分鐘 (300 秒)


# ======================================================================
# 輔助函數
# ======================================================================

def create_placeholder_avatar():
    """創建灰色占位圖像"""
    placeholder = Image.new('RGBA', (48, 48), (200, 200, 200, 255))
    return placeholder


async def fetch_avatar(session, url):
    """
    嘗試加載用戶頭像
    成功: 返回 Image 對象
    失敗: 返回 None（調用者應使用 placeholder）
    """
    if not url:
        return None
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                print(f"⚠️ 頭像 URL 返回 {resp.status}: {url[:50]}...")
                return None
            
            data = await resp.read()
            if len(data) == 0:
                print(f"⚠️ 頭像數據為空: {url[:50]}...")
                return None
            
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            
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


def get_from_env(variable_name, default=None):
    """從環境變數讀取值"""
    return os.getenv(variable_name, default)


def save_to_env(variable_name, value):
    """保存值到環境變數"""
    set_key(".env", variable_name, str(value))


# ======================================================================
# 圖像生成函數 - KK幣排行榜
# ======================================================================

async def make_leaderboard_image(members_data):
    """協程版本的圖片生成流程：
    1. 非同步地下載所有頭像（非密集型）
    2. 將所有 CPU 密集型的 PIL 繪製工作扔到 thread pool
    """
    RESERVE_SECTION_HEIGHT = 120
    DESCRIPTION_HEIGHT = 90
    WIDTH, HEIGHT = 1000, RESERVE_SECTION_HEIGHT + 75 + 70 * len(members_data) + DESCRIPTION_HEIGHT
    AVATAR_SIZE = 48
    MARGIN = 20
    BG_COLOR = (54, 57, 63)
    RANK_COLOR = (240, 200, 80)

    # 先取得每個成員的頭像（或佔位）、計算最大資產值用於進度條
    avatar_images = []
    member_totals = []
    max_assets = 0
    
    for member_data in members_data:
        if len(member_data) == 3:
            _, kkcoin, digital_usd = member_data
        else:
            _, kkcoin = member_data
            digital_usd = 0
        total_assets = float(kkcoin or 0) + float(digital_usd or 0) / 35
        member_totals.append(total_assets)
        if total_assets > max_assets:
            max_assets = total_assets
    
    placeholder = create_placeholder_avatar()
    async with aiohttp.ClientSession() as session:
        for i, member_data in enumerate(members_data):
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
                        timeout=5.0
                    )
                    if not avatar:
                        avatar = None
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"❌ 頭像下載錯誤: {e}")
            avatar_images.append(avatar or placeholder)

    reserve = get_central_reserve()
    reserve_pressure = get_reserve_pressure()
    reserve_announcement = get_reserve_announcement()
    
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
        member_totals,
        max_assets,
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
    member_totals,
    max_assets,
):
    """純同步版，執行在工作執行緒中，不會阻塞事件循環"""
    
    def draw_bank_icon(draw, x, y, size=12, color=(150, 180, 255)):
        """繪製銀行/金庫圖標"""
        draw.rectangle([(x, y), (x+size, y+size)], outline=color, width=2)
        draw.line([(x+size//2, y), (x+size//2, y+size)], fill=color, width=1)
    
    def draw_warning_icon(draw, x, y, size=12, color=(255, 193, 7)):
        """繪製警告圖標"""
        points = [(x+size//2, y), (x+size, y+size), (x, y+size)]
        draw.polygon(points, outline=color, width=2)
        draw.ellipse([(x+size//2-2, y+size-6), (x+size//2+2, y+size-2)], fill=color)
    
    def draw_info_icon(draw, x, y, size=12, color=(150, 160, 200)):
        """繪製說明圖標"""
        draw.rectangle([(x, y), (x+size-2, y+size//2)], outline=color, width=1)
        draw.rectangle([(x+2, y+size//2), (x+size, y+size)], outline=color, width=1)
    
    def draw_bubble_icon(draw, x, y, size=10, color=(180, 180, 200)):
        """繪製氣泡圖標"""
        draw.ellipse([(x, y), (x+size, y+size)], outline=color, width=1)
        draw.polygon([(x+size-2, y+size-2), (x+size+4, y+size-2), (x+size+2, y+size+4)], fill=color)
    
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, 28)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, 22)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 20)
        FONT_DESC = ImageFont.truetype(FONT_PATH, 16)
        FONT_RANK = ImageFont.truetype(FONT_PATH, 30)
        fonts_loaded = True
    except Exception as e:
        print(f"⚠️ 載入自定義字體失敗: {e}，使用預設字體")
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
        FONT_RANK = ImageFont.load_default()
        fonts_loaded = False
    
    trophy_img = None
    try:
        if os.path.exists(TROPHY_PATH):
            trophy_img = Image.open(TROPHY_PATH).convert("RGBA")
    except Exception as e:
        print(f"⚠️ 載入獎杯圖片失敗: {e}")
    
    medal_imgs = []
    for idx, path in enumerate(MEDAL_PATHS):
        try:
            if os.path.exists(path):
                medal_imgs.append(Image.open(path).convert("RGBA"))
            else:
                medal_imgs.append(None)
        except Exception as e:
            print(f"⚠️ 載入獎牌 {idx+1} 失敗: {e}")
            medal_imgs.append(None)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 如果 pilmoji 可用，則初始化 Pilmoji Drawer（即使自定義字體載入失敗，也能渲染 Emoji）
    drawer = None
    if PILMOJI_AVAILABLE:
        try:
            drawer = Pilmoji(img)
        except Exception as e:
            print(f"⚠️ pilmoji 初始化失敗: {e}，使用標準 draw")
            drawer = None
    
    # 統一的文字繪製函數，支持 emoji 和對齐
    def draw_text(pos, text, font=FONT_DESC, fill=(255, 255, 255), shadow=False, shadow_color=(0, 0, 0), shadow_offset=(1, 1)):
        """繪製文字，自動處理 emoji 對齐

        - 優先使用 pilmoji Drawer（支持 emoji）
        - 可選擇加一點陰影，使數字更立體（不超過1px偏移）
        - 降級使用標準 draw（當 pilmoji 不可用）
        """
        x, y = pos
        if shadow:
            sx, sy = shadow_offset
            # 先繪製陰影
            try:
                if drawer is not None and PILMOJI_AVAILABLE:
                    drawer.text((x + sx, y + sy), text, font=font, fill=shadow_color)
                else:
                    draw.text((x + sx, y + sy), text, font=font, fill=shadow_color)
            except Exception:
                pass
        try:
            if drawer is not None and PILMOJI_AVAILABLE:
                # 使用 pilmoji 的 text 方法，自動處理 emoji 對齐
                drawer.text((x, y), text, font=font, fill=fill)
            else:
                # 降級方案：使用標準 ImageDraw
                draw.text((x, y), text, font=font, fill=fill)
        except Exception as e:
            print(f"⚠️ 文字繪製失敗 ({text[:20]}...): {e}")
            # 最後的降級方案
            try:
                draw.text((x, y), text, font=font, fill=fill)
            except Exception as e2:
                print(f"❌ 文字繪製徹底失敗: {e2}")
    
    # 第一部分：置頂的儲備池區塊
    reserve_bg_y_start = MARGIN
    reserve_bg_y_end = MARGIN + RESERVE_SECTION_HEIGHT - 5
    draw.rectangle(
        [(MARGIN, reserve_bg_y_start), (WIDTH - MARGIN, reserve_bg_y_end)],
        fill=(68, 71, 90),
        outline=(100, 110, 150),
        width=2
    )
    
    draw_bank_icon(draw, MARGIN + 5, MARGIN + 12, size=14, color=(150, 180, 255))
    draw_text((MARGIN + 25, MARGIN + 8), "園區中央儲備池", font=FONT_BIG, fill=(150, 180, 255))
    
    reserve_formatted = f"{reserve:,.0f}" if reserve else "0"
    draw_text((MARGIN + 15, MARGIN + 45), f"[金庫] {reserve_formatted} KK", font=FONT_SMALL, fill=(100, 180, 220))
    
    # 壓力條
    bar_x = MARGIN + 280
    bar_y = MARGIN + 48
    bar_width = WIDTH - MARGIN - bar_x - 20
    bar_height = 18
    
    draw.rectangle(
        [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
        fill=(100, 110, 140),
        outline=(120, 130, 160)
    )
    
    if reserve_pressure < 33:
        pressure_color = (76, 175, 80)
    elif reserve_pressure < 66:
        pressure_color = (255, 193, 7)
    else:
        pressure_color = (244, 67, 54)
    
    filled_width = int(bar_width * reserve_pressure / 100)
    if filled_width > 0:
        draw.rectangle(
            [(bar_x, bar_y), (bar_x + filled_width, bar_y + bar_height)],
            fill=pressure_color
        )
    
    if reserve_announcement:
        draw_text((MARGIN + 15, MARGIN + 75), f"📢 {reserve_announcement}", font=FONT_DESC, fill=(180, 180, 200))
    else:
        draw_text((MARGIN + 15, MARGIN + 75), "💡 儲備池用於金流斷點手續費收取與獎勵發放", font=FONT_DESC, fill=(180, 180, 200))
    
    # 第二部分：排行榜標題和資料
    leaderboard_start_y = MARGIN + RESERVE_SECTION_HEIGHT + 10
    
    if trophy_img:
        try:
            img.paste(trophy_img.resize((44, 44)), (MARGIN, leaderboard_start_y + 5), trophy_img.resize((44, 44)))
            title_x = MARGIN + 54
        except Exception as e:
            print(f"⚠️ 貼上獎杯失敗: {e}")
            title_x = MARGIN
    else:
        title_x = MARGIN
    
    draw_text((title_x, leaderboard_start_y + 8), "💰 KK園區 - 總資產排行", font=FONT_BIG, fill=(200, 200, 220))

    # 顯示欄位標題：KK幣 / 數位美金
    header_y = leaderboard_start_y + 45
    kk_label = "KK幣"
    usd_label = "數位美金"
    kk_right = WIDTH - 140
    usd_right = WIDTH - 20

    kk_label_w = FONT_DESC.getbbox(kk_label)[2] - FONT_DESC.getbbox(kk_label)[0]
    usd_label_w = FONT_DESC.getbbox(usd_label)[2] - FONT_DESC.getbbox(usd_label)[0]
    draw_text((kk_right - kk_label_w, header_y), kk_label, font=FONT_DESC, fill=(160, 160, 180))
    draw_text((usd_right - usd_label_w, header_y), usd_label, font=FONT_DESC, fill=(160, 160, 180))

    # 畫各行
    for i, member_data in enumerate(zip(members_data, avatar_images)):
        if len(member_data[0]) == 3:
            member, kkcoin, digital_usd = member_data[0]
        else:
            member, kkcoin = member_data[0]
            digital_usd = 0
        
        avatar_img = member_data[1]
        
        y = leaderboard_start_y + 75 + i*70
        if i < 3 and medal_imgs[i]:
            try:
                img.paste(medal_imgs[i].resize((36, 36)), (MARGIN, y+6), medal_imgs[i].resize((36, 36)))
                rank_x = MARGIN + 44
            except Exception as e:
                print(f"⚠️ 貼上獎牌失敗: {e}")
                rank_x = MARGIN
        else:
            rank_x = MARGIN
        
        # 第4-9 名靠左一點，第10名起更靠左一些
        if i >= 3:
            offset = 10 if i < 9 else 5
            draw_text((rank_x + offset, y + 18), f"{i+1}", font=FONT_RANK, fill=(255, 20, 147))

        # 前三名的頭貼要更靠左且放大一些
        avatar_size = AVATAR_SIZE
        avatar_x = rank_x + 40
        if i < 3:
            avatar_size = AVATAR_SIZE + 12
            avatar_x = rank_x + 30

        display_avatar = None
        if avatar_img:
            try:
                display_avatar = avatar_img.resize((avatar_size, avatar_size))
                img.paste(display_avatar, (avatar_x, y), display_avatar)
            except Exception as e:
                print(f"⚠️ 貼上頭像失敗: {e}")
                display_avatar = create_placeholder_avatar()
                display_avatar = display_avatar.resize((avatar_size, avatar_size))
                img.paste(display_avatar, (avatar_x, y), display_avatar)
        else:
            display_avatar = create_placeholder_avatar()
            display_avatar = display_avatar.resize((avatar_size, avatar_size))
            img.paste(display_avatar, (avatar_x, y), display_avatar)
        
        name_x = rank_x + 100
        name_y = y+8
        draw_text((name_x, name_y), member.display_name, font=FONT_SMALL, fill=(200, 200, 220))
        
        kkcoin_text = f"{int(float(kkcoin or 0))} KK"
        usd_text = f"${float(digital_usd or 0):,.0f}"

        # 右對齊：KK幣在靠右位置，數位美金緊貼最右邊
        kkcoin_width = FONT_KKCOIN.getbbox(kkcoin_text)[2] - FONT_KKCOIN.getbbox(kkcoin_text)[0]
        usd_width = FONT_KKCOIN.getbbox(usd_text)[2] - FONT_KKCOIN.getbbox(usd_text)[0]
        kk_right = WIDTH - 140
        usd_right = WIDTH - 20
        kkcoin_x = kk_right - kkcoin_width
        usd_x = usd_right - usd_width

        draw_text((kkcoin_x, y+8), kkcoin_text, font=FONT_KKCOIN, fill=(100, 180, 220))
        draw_text((usd_x, y+8), usd_text, font=FONT_KKCOIN, fill=(100, 220, 150))
        
        # 進度條
        if max_assets > 0:
            current_assets = member_totals[i]
            percent = min(100, (current_assets / max_assets) * 100)
        else:
            percent = 0
        
        progress_bar_y = y + 35
        progress_bar_x = rank_x + 100
        progress_bar_width = WIDTH - rank_x - 120 - 300
        progress_bar_height = 16
        
        try:
            draw.rounded_rectangle(
                [(progress_bar_x, progress_bar_y), (progress_bar_x + progress_bar_width, progress_bar_y + progress_bar_height)],
                radius=8,
                fill=(80, 90, 120),
                outline=(120, 130, 160),
                width=1
            )
        except AttributeError:
            draw.rectangle(
                [(progress_bar_x, progress_bar_y), (progress_bar_x + progress_bar_width, progress_bar_y + progress_bar_height)],
                fill=(80, 90, 120),
                outline=(120, 130, 160),
                width=1
            )
        
        if percent > 0:
            filled_width = int(progress_bar_width * percent / 100)
            if percent >= 80:
                bar_color = (0, 255, 127)
            elif percent >= 60:
                bar_color = (57, 255, 20)
            elif percent >= 40:
                bar_color = (255, 240, 0)
            else:
                bar_color = (255, 16, 240)
            
            try:
                draw.rounded_rectangle(
                    [(progress_bar_x, progress_bar_y), (progress_bar_x + filled_width, progress_bar_y + progress_bar_height)],
                    radius=8,
                    fill=bar_color
                )
            except AttributeError:
                draw.rectangle(
                    [(progress_bar_x, progress_bar_y), (progress_bar_x + filled_width, progress_bar_y + progress_bar_height)],
                    fill=bar_color
                )
        
        percent_text = f"{percent:.0f}%"
        draw_text((progress_bar_x + progress_bar_width + 10, progress_bar_y), percent_text, font=FONT_DESC, fill=(255, 16, 240))

    # 第三部分：說明區塊
    desc_y = leaderboard_start_y + 75 + len(members_data) * 70 + 15
    draw.line([(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)], fill=(100, 110, 150), width=1)
    
    descriptions = [
        "KK幣是「未洗淨的髒錢」- 交易/賣出資產時給予",
        "可透過「金流斷點」轉換為 D-USD 數位美金",
        "排名計算：總資產 = KK幣 + (D-USD ÷ 35)"
    ]
    draw_info_icon(draw, MARGIN + 5, desc_y + 5, size=12, color=(150, 160, 200))
    draw_text((MARGIN + 20, desc_y), "金流說明：", font=FONT_SMALL, fill=(150, 160, 200))
    
    for i, desc in enumerate(descriptions):
        desc_text_y = desc_y + 25 + i * 22
        draw_bubble_icon(draw, MARGIN + 10, desc_text_y + 3, size=10, color=(180, 180, 200))
        draw_text((MARGIN + 25, desc_text_y), desc, font=FONT_DESC, fill=(180, 180, 200))

    return img


# ======================================================================
# 數據提取函數 - KK幣排行榜
# ======================================================================

def get_current_leaderboard_data(bot, rank_channel_id):
    """取得當前排行榜資料（包含 KK幣和數位美金，按總資產排序）"""
    if not rank_channel_id:
        return []
        
    channel = bot.get_channel(rank_channel_id)
    if not channel:
        return []
        
    guild = channel.guild
    
    members_data = []
    all_users = get_all_users()
    
    users = [u for u in all_users if (u.get('kkcoin') or 0) > 0 or (u.get('digital_usd') or 0) > 0]
    users.sort(
        key=lambda x: float(x.get('kkcoin') or 0) + float(x.get('digital_usd') or 0) / 35,
        reverse=True
    )
    users = users[:15]
    
    for user in users:
        user_id = int(user["user_id"])
        kkcoin = float(user.get('kkcoin') or 0)
        digital_usd = float(user.get('digital_usd') or 0)
        
        member = guild.get_member(user_id)
        
        if member:
            members_data.append((member, kkcoin, digital_usd))
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
            members_data.append((fallback, kkcoin, digital_usd))
    
    return members_data


def has_data_changed(new_data, last_data):
    """檢查資料是否有變化，返回 True 表示有變化"""
    if not last_data:
        print("🔍 沒有快取資料，需要更新")
        return True
        
    if len(new_data) != len(last_data):
        print(f"🔍 資料筆數變化：{len(last_data)} → {len(new_data)}")
        return True
    
    for i, (member, kkcoin, digital_usd) in enumerate(new_data):
        if i >= len(last_data):
            print(f"🔍 索引超出範圍：{i}")
            return True
            
        old_member, old_kkcoin, old_digital_usd = last_data[i]
        
        new_kk = float(kkcoin or 0)
        old_kk = float(old_kkcoin or 0)
        new_usd = float(digital_usd or 0)
        old_usd = float(old_digital_usd or 0)
        
        if member.id != old_member.id:
            print(f"🔍 排名變化：位置 {i+1} 從 {old_member.display_name} 變成 {member.display_name}")
            return True
            
        if new_kk != old_kk or new_usd != old_usd:
            print(f"🔍 資料變化：{member.display_name} ({old_kk} KK, ${old_usd} USD → {new_kk} KK, ${new_usd} USD)")
            return True
    
    print("🔍 資料沒有變化，跳過更新")
    return False


# ======================================================================
# 圖像生成函數 - 數位美金排行榜
# ======================================================================

async def make_digital_usd_leaderboard_image(bot, members_data):
    """生成數位美金排行榜圖片"""
    DESCRIPTION_HEIGHT = 80
    WIDTH, HEIGHT = 900, 75 + 60 * len(members_data) + DESCRIPTION_HEIGHT
    AVATAR_SIZE = 48
    MARGIN = 20
    BG_COLOR = (54, 57, 63)
    RANK_COLOR = (100, 220, 150)

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
        _sync_build_digital_usd_leaderboard_image,
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
        fonts_loaded = True
    except Exception as e:
        print(f"❌ 載入字體失敗: {e}")
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
        fonts_loaded = False

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Pilmoji 初始化
    drawer = None
    if PILMOJI_AVAILABLE and fonts_loaded:
        try:
            drawer = Pilmoji(img)
        except Exception as e:
            print(f"⚠️ Pilmoji 初始化失敗: {e}")
            drawer = None
    
    def draw_text(pos, text, font=FONT_DESC, fill=(255, 255, 255), shadow=False, shadow_color=(0, 0, 0), shadow_offset=(1, 1)):
        """繪製文字，自動處理 emoji 對齊

        支援選擇性陰影，使數字更立體。
        """
        x, y = pos
        if shadow:
            sx, sy = shadow_offset
            try:
                if drawer is not None and PILMOJI_AVAILABLE:
                    drawer.text((x + sx, y + sy), text, font=font, fill=shadow_color)
                else:
                    draw.text((x + sx, y + sy), text, font=font, fill=shadow_color)
            except Exception:
                pass
        if drawer is not None and PILMOJI_AVAILABLE:
            try:
                drawer.text((x, y), text, font=font, fill=fill)
            except Exception as e:
                print(f"⚠️ pilmoji 繪製失敗: {e}")
                draw.text((x, y), text, font=font, fill=fill)
        else:
            draw.text((x, y), text, font=font, fill=fill)
    
    draw_text((MARGIN, 18), "💵 KK園區 - 數位美金排行", font=FONT_BIG, fill=(50, 200, 50))

    # 欄位標題：數位美金
    header_y = 50
    usd_label = "數位美金"
    usd_label_w = FONT_DESC.getbbox(usd_label)[2] - FONT_DESC.getbbox(usd_label)[0]
    usd_right = WIDTH - 20
    draw_text((usd_right - usd_label_w, header_y), usd_label, font=FONT_DESC, fill=(160, 160, 180))

    for i, ((member, digital_usd), avatar_img) in enumerate(zip(members_data, avatar_images)):
        y = 75 + i*60
        rank_x = MARGIN
        draw_text((rank_x, y), f"{i+1:2d}", font=FONT_SMALL, fill=RANK_COLOR)

        display_avatar = avatar_img.resize((AVATAR_SIZE, AVATAR_SIZE))
        img.paste(display_avatar, (rank_x + 40, y), display_avatar)
        name_x = rank_x + 100
        name_y = y+8
        draw_text((name_x, name_y), member.display_name, font=FONT_SMALL, fill=(30, 30, 30))
        usd_text = f"${digital_usd:,.0f} D-USD"
        usd_width = FONT_KKCOIN.getbbox(usd_text)[2] - FONT_KKCOIN.getbbox(usd_text)[0]
        usd_right = WIDTH - 20
        usd_x = usd_right - usd_width
        draw_text((usd_x, y+8), usd_text, font=FONT_KKCOIN, fill=(50, 200, 50))

    desc_y = 75 + len(members_data) * 60 + 15
    draw.line([(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)], fill=(200, 200, 200), width=1)
    descriptions = [
        " 💵 數位美金 (D-USD) 是「洗淨的白錢」- 透過「金流斷點」轉換而來",
        " 🔄 轉換公式：KK幣 × 95% (扣5%損耗) ÷ 35 = D-USD"
    ]
    draw_text((MARGIN, desc_y), " 🏦 虛擬金融說明：", font=FONT_SMALL, fill=(50, 200, 50))
    for i, desc in enumerate(descriptions):
        desc_text_y = desc_y + 25 + i * 22
        draw_text((MARGIN + 10, desc_text_y), desc, font=FONT_DESC, fill=(100, 100, 100))

    return img


# ======================================================================
# 數據提取函數 - 數位美金排行榜
# ======================================================================

def get_digital_usd_leaderboard_data(bot, digital_usd_channel_id):
    """取得當前數位美金排行榜資料"""
    if not digital_usd_channel_id:
        return []
        
    channel = bot.get_channel(digital_usd_channel_id)
    if not channel:
        return []
        
    guild = channel.guild
    
    members_data = []
    all_users = get_all_users()
    
    users = [u for u in all_users if (u.get('digital_usd') or 0) > 0]
    users.sort(key=lambda x: (x.get('digital_usd') or 0), reverse=True)
    users = users[:15]
    
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


def has_digital_usd_data_changed(new_data, last_data):
    """檢查數位美金排行榜資料是否有變化"""
    if not last_data:
        return True
        
    if len(new_data) != len(last_data):
        return True
    
    for i, (member, digital_usd) in enumerate(new_data):
        if i >= len(last_data):
            return True
            
        old_member, old_digital_usd = last_data[i]
        
        new_usd = digital_usd or 0
        old_usd = old_digital_usd or 0
        
        if member.id != old_member.id or new_usd != old_usd:
            return True
    
    return False
