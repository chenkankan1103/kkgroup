"""
初版 KKCoin 排行榜代碼 - 用於 AI 畫圖參考
提供給其他 AI 幫忙優化視覺設計

核心特性:
- 900x(75+60*人數+80)px 尺寸
- 白色背景
- 頭像圓形顯示 (48×48)
- 金銀銅牌 (前3名)
- Trophy 圖標
- 藍色 KKCoin 數字

顏色方案:
- 背景: RGB(255,255,255) - 白色
- 排名號碼: RGB(240,200,80) - 金色
- 標題文字: RGB(60,60,60) - 深灰
- 名字: RGB(30,30,30) - 黑色
- KKCoin 數字: RGB(50,110,210) - 藍色
- 描述文字: RGB(100,100,100) - 灰色

字體大小:
- FONT_BIG: 28pt (標題)
- FONT_SMALL: 22pt (排名、名字)
- FONT_KKCOIN: 24pt (KKCoin 數字)
- FONT_DESC: 16pt (描述)

資源:
- fonts/NotoSansCJKtc-Regular.otf - 中文字體
- assets/trophy.png - Trophy 圖標 (44×44)
- assets/1.png - 金牌 (36×36)
- assets/2.png - 銀牌 (36×36)
- assets/3.png - 銅牌 (36×36)
"""

import discord
import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import os
from io import BytesIO

# ============================================================
# 配置常數
# ============================================================

FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")

TROPHY_PATH = os.path.join(ASSETS_PATH, "trophy.png")
MEDAL_PATHS = [
    os.path.join(ASSETS_PATH, "1.png"),  # 金牌
    os.path.join(ASSETS_PATH, "2.png"),  # 銀牌
    os.path.join(ASSETS_PATH, "3.png"),  # 銅牌
]

# 顏色方案 (RGB 元組)
COLOR_BG_MAIN = (255, 255, 255)           # 主背景：白色
COLOR_RANK_GOLD = (240, 200, 80)          # 排名號碼：金色
COLOR_TEXT_TITLE = (60, 60, 60)           # 標題：深灰
COLOR_TEXT_NAME = (30, 30, 30)            # 名字：黑
COLOR_TEXT_KKCOIN = (50, 110, 210)        # KKCoin 數字：藍
COLOR_TEXT_DESC = (100, 100, 100)         # 描述：灰

# 字體大小
FONT_SIZE_BIG = 28      # 標題 "KK幣排行榜（前20名）"
FONT_SIZE_SMALL = 22    # 排名、名字
FONT_SIZE_KKCOIN = 24   # KKCoin 數字
FONT_SIZE_DESC = 16     # 描述文字

# 尺寸
WIDTH = 900
AVATAR_SIZE = 48
MEDAL_SIZE = 36
TROPHY_SIZE = 44
MARGIN = 20
ROW_HEIGHT = 60
HEADER_HEIGHT = 75
DESCRIPTION_HEIGHT = 80

# ============================================================
# 輔助函數
# ============================================================

def create_placeholder_avatar():
    """創建灰色占位圖像 (當頭像加載失敗時使用)"""
    placeholder = Image.new('RGBA', (48, 48), (200, 200, 200, 255))
    return placeholder

async def fetch_avatar(session, url):
    """
    嘗試加載用戶頭像
    成功: 返回 Image 對象
    失敗: 返回 None
    """
    if not url:
        return None
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                print(f"⚠️ 頭像 URL 返回 {resp.status}")
                return None
            
            data = await resp.read()
            if len(data) == 0:
                print(f"⚠️ 頭像數據為空")
                return None
            
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            
            if img.size[0] < 16 or img.size[1] < 16:
                print(f"⚠️ 頭像尺寸過小: {img.size}")
                return None
            
            return img
    
    except Exception as e:
        print(f"❌ 頭像加載失敗: {type(e).__name__}")
        return None


# ============================================================
# 核心排行榜生成函數
# ============================================================

async def make_leaderboard_image(members_data):
    """
    生成排行榜圖像
    
    輸入:
    - members_data: [(member_object, kkcoin_amount), ...]
    
    輸出:
    - PIL Image 對象
    
    布局說明:
    1. 標題區域 (75px 高)
       - Trophy 圖標 (44×44) + "KK幣排行榜（前20名）"
    
    2. 排行榜行 (每行 60px)
       - [獎牌/排名] [頭像] [名字] [KKCoin數字]
       - 前3名顯示 1.png / 2.png / 3.png
       - 其他行顯示排名號碼 (金色)
    
    3. 描述區域 (80px 高)
       - KKCoin 獲得方法說明
    """
    
    # 計算圖像高度
    HEIGHT = HEADER_HEIGHT + len(members_data) * ROW_HEIGHT + DESCRIPTION_HEIGHT
    
    # 嘗試加載字體
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, FONT_SIZE_BIG)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, FONT_SIZE_KKCOIN)
        FONT_DESC = ImageFont.truetype(FONT_PATH, FONT_SIZE_DESC)
    except Exception as e:
        print(f"❌ 載入字體失敗: {e}")
        # 備選方案：使用默認字體
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
    
    # 加載資源圖片
    trophy_img = None
    try:
        trophy_img = Image.open(TROPHY_PATH).convert("RGBA")
    except Exception as e:
        print(f"❌ 載入 trophy.png 失敗: {e}")
    
    medal_imgs = []
    for idx, path in enumerate(MEDAL_PATHS):
        try:
            medal_imgs.append(Image.open(path).convert("RGBA"))
        except Exception as e:
            print(f"❌ 載入 medal {idx+1} 失敗: {e}")
            medal_imgs.append(None)
    
    # 創建新圖像 (白色背景)
    img = Image.new("RGBA", (WIDTH, HEIGHT), COLOR_BG_MAIN)
    draw = ImageDraw.Draw(img)
    
    # ========== 繪製標題 ==========
    title_x = MARGIN
    if trophy_img:
        # 粘貼 Trophy 圖標
        trophy_resized = trophy_img.resize((TROPHY_SIZE, TROPHY_SIZE))
        img.paste(trophy_resized, (MARGIN, 12), trophy_resized)
        title_x = MARGIN + TROPHY_SIZE + 10
    
    # 繪製標題文字
    draw.text(
        (title_x, 18),
        "KK幣排行榜（前20名）",
        fill=COLOR_TEXT_TITLE,
        font=FONT_BIG
    )
    
    # ========== 創建占位頭像 ==========
    placeholder_avatar = create_placeholder_avatar()
    
    # ========== 繪製排行榜行 ==========
    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            y = HEADER_HEIGHT + i * ROW_HEIGHT
            rank_x = MARGIN
            
            # 前 3 名: 顯示獎牌圖片
            if i < 3 and medal_imgs[i]:
                medal_resized = medal_imgs[i].resize((MEDAL_SIZE, MEDAL_SIZE))
                img.paste(medal_resized, (MARGIN, y + 6), medal_resized)
                rank_x = MARGIN + MEDAL_SIZE + 8
            else:
                # 其他名次: 顯示排名號碼 (金色)
                draw.text(
                    (rank_x, y),
                    f"{i+1:2d}",
                    fill=COLOR_RANK_GOLD,
                    font=FONT_SMALL
                )
            
            # ========== 加載並顯示頭像 ==========
            avatar = None
            try:
                # 優先順序: display_avatar → avatar → default_avatar
                avatar_url = None
                
                if hasattr(member, 'display_avatar') and member.display_avatar:
                    try:
                        avatar_url = member.display_avatar.url
                    except:
                        pass
                
                if not avatar_url and hasattr(member, 'avatar') and member.avatar:
                    try:
                        avatar_url = member.avatar.url
                    except:
                        pass
                
                if not avatar_url and hasattr(member, 'default_avatar'):
                    try:
                        avatar_url = member.default_avatar.url
                    except:
                        pass
                
                # 嘗試加載圖片
                if avatar_url:
                    avatar = await fetch_avatar(session, avatar_url)
            
            except Exception as e:
                print(f"❌ 頭像加載異常 ({member.display_name}): {e}")
            
            # 使用實際頭像或灰色占位圖
            display_avatar = avatar if avatar else placeholder_avatar
            display_avatar = display_avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
            img.paste(display_avatar, (rank_x + 40, y), display_avatar)
            
            # ========== 繪製玩家資訊 ==========
            name_x = rank_x + 100
            name_y = y + 8
            
            # 玩家名字 (黑色)
            draw.text(
                (name_x, name_y),
                member.display_name,
                fill=COLOR_TEXT_NAME,
                font=FONT_SMALL
            )
            
            # KKCoin 數字 (藍色) - 靠右對齐
            draw.text(
                (WIDTH - 180, y + 8),
                f"{kkcoin} KK幣",
                fill=COLOR_TEXT_KKCOIN,
                font=FONT_KKCOIN
            )
    
    # ========== 繪製描述區域 ==========
    desc_y = HEADER_HEIGHT + len(members_data) * ROW_HEIGHT + 15
    
    # 分隔線
    draw.line(
        [(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)],
        fill=(200, 200, 200),
        width=1
    )
    
    # 描述標題
    draw.text(
        (MARGIN, desc_y),
        " KKcoin獲得方法：",
        fill=(80, 80, 80),
        font=FONT_SMALL
    )
    
    # 描述內容
    descriptions = [
        " 發送訊息獲得KK幣：10字+1幣 | 25字+2幣 | 50字+3幣 （冷卻30秒）",
        " 限制：重複訊息、純表情不給幣 |  語音掛機可獲得額外獎勵"
    ]
    
    for idx, desc in enumerate(descriptions):
        desc_text_y = desc_y + 25 + idx * 22
        draw.text(
            (MARGIN + 10, desc_text_y),
            desc,
            fill=COLOR_TEXT_DESC,
            font=FONT_DESC
        )
    
    return img


# ============================================================
# 使用範例
# ============================================================

"""
使用方式:

from commands.kcoin_original import make_leaderboard_image

# 準備數據 (member 需要有 display_name 屬性)
members_data = [
    (member_object_1, 1000),
    (member_object_2, 950),
    (member_object_3, 890),
    ...
]

# 生成圖像
image = await make_leaderboard_image(members_data)

# 保存或發送
with io.BytesIO() as img_bytes:
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    file = discord.File(img_bytes, filename="kkcoin_rank.png")
    await interaction.followup.send(file=file)
"""
