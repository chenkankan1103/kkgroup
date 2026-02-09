"""
專業深色主題 KKCoin 排行榜 - Pro 版本
特點：圓形頭像、動態長條圖、發光效果、前3名高亮
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

WIDTH = 900
COLOR_BG = (18, 18, 22)         # 主背景（深灰）
COLOR_CARD = (30, 31, 36)       # 一般行背景
COLOR_HIGHLIGHT = (40, 42, 50)  # 前三名高亮背景
COLOR_KK_BLUE = (0, 210, 255)   # KKCoin 發光藍
COLOR_BAR_BG = (45, 46, 52)     # 長條圖底軌
COLOR_TEXT_PRIMARY = (240, 240, 240)    # 主文字色
COLOR_TEXT_SECONDARY = (150, 150, 160)  # 次要文字色

FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")

# 尺寸
ROW_HEIGHT = 80
HEADER_HEIGHT = 120
FOOTER_HEIGHT = 80
AVATAR_SIZE = 50
AVATAR_X = 135
MARGIN = 30

# ============================================================
# 輔助函數
# ============================================================

def mask_circle(img, size):
    """
    將圖片裁切為圓形
    - 使用 LANCZOS 高質量縮放
    - 添加抗鋸齒遮罩
    """
    img = img.resize((size, size), Image.LANCZOS)
    
    # 創建圓形遮罩
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    
    # 應用遮罩
    output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0))
    output.putalpha(mask)
    
    return output

async def fetch_avatar_image(session, url):
    """從 Discord 加載用戶頭像"""
    if not url:
        return None
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            
            data = await resp.read()
            if len(data) == 0:
                return None
            
            img = Image.open(BytesIO(data)).convert("RGBA")
            return img
    
    except Exception as e:
        print(f"❌ 頭像加載失敗: {e}")
        return None

def create_placeholder_avatar(size=50):
    """創建漸層灰色占位頭像"""
    img = Image.new('RGBA', (size, size), (60, 60, 70, 255))
    return img

def draw_rounded_rectangle(draw, xy, radius=15, **kwargs):
    """
    繪製圓角矩形
    xy: (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = xy
    
    # 四個角
    draw.ellipse((x1, y1, x1 + radius * 2, y1 + radius * 2), **kwargs)
    draw.ellipse((x2 - radius * 2, y1, x2, y1 + radius * 2), **kwargs)
    draw.ellipse((x1, y2 - radius * 2, x1 + radius * 2, y2), **kwargs)
    draw.ellipse((x2 - radius * 2, y2 - radius * 2, x2, y2), **kwargs)
    
    # 四條邊
    draw.rectangle((x1 + radius, y1, x2 - radius, y2), **kwargs)
    draw.rectangle((x1, y1 + radius, x2, y2 - radius), **kwargs)

# ============================================================
# 核心排行榜生成函數
# ============================================================

async def make_pro_leaderboard(members_data):
    """
    生成專業深色主題排行榜
    
    輸入:
    - members_data: [(member_obj, kkcoin_amount), ...]
    
    輸出:
    - PIL Image 對象
    
    特點:
    - 深灰色背景 (RGB 18, 18, 22)
    - 圓形頭像
    - 動態長條圖
    - 發光藍色 KKCoin 數字
    - 前3名高亮背景
    """
    
    count = len(members_data)
    HEIGHT = HEADER_HEIGHT + (count * ROW_HEIGHT) + FOOTER_HEIGHT
    
    # 創建圖像
    img = Image.new("RGBA", (WIDTH, HEIGHT), COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    # 加載字體
    try:
        font_title = ImageFont.truetype(FONT_PATH, 36)
        font_name = ImageFont.truetype(FONT_PATH, 26)
        font_coin = ImageFont.truetype(FONT_PATH, 24)
        font_footer = ImageFont.truetype(FONT_PATH, 18)
        font_rank = ImageFont.truetype(FONT_PATH, 28)
    except Exception as e:
        print(f"❌ 字體加載失敗: {e}")
        font_title = font_name = font_coin = font_footer = font_rank = ImageFont.load_default()
    
    # ========== 繪製標題 ==========
    draw.text((MARGIN, 40), "📊 KK 園區資產排行榜", fill=COLOR_TEXT_PRIMARY, font=font_title)
    
    # 計算最大值用於長條圖比例
    max_amount = max([amount for _, amount in members_data]) if members_data else 1
    if max_amount == 0:
        max_amount = 1
    
    # ========== 繪製排行榜行 ==========
    async with aiohttp.ClientSession() as session:
        for i, (member, amount) in enumerate(members_data):
            y = HEADER_HEIGHT + (i * ROW_HEIGHT)
            
            # --- 背景卡片 (圓角矩形) ---
            bg_color = COLOR_HIGHLIGHT if i < 3 else COLOR_CARD
            
            # 使用簡單矩形（PIL 的 rounded_rectangle 在某些版本不可用）
            draw.rectangle(
                [MARGIN, y, WIDTH - MARGIN, y + 70],
                fill=bg_color
            )
            
            # --- 排名與獎盃 ---
            rank_x = MARGIN + 20
            rank_y = y + 15
            
            if i == 0:
                # 第1名：金牌符號
                draw.text((rank_x, rank_y), "🥇", font=font_rank)
            elif i == 1:
                # 第2名：銀牌符號
                draw.text((rank_x, rank_y), "🥈", font=font_rank)
            elif i == 2:
                # 第3名：銅牌符號
                draw.text((rank_x, rank_y), "🥉", font=font_rank)
            else:
                # 其他排名：號碼
                rank_color = (255, 215, 0) if i < 10 else COLOR_TEXT_SECONDARY
                draw.text((rank_x + 5, rank_y), f"#{i+1:02d}", fill=rank_color, font=font_name)
            
            # --- 圓形頭像 ---
            avatar_img = None
            try:
                # 優先使用 display_avatar
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
                
                # 加載圖片
                if avatar_url:
                    avatar_img = await fetch_avatar_image(session, avatar_url)
            
            except Exception as e:
                print(f"❌ 頭像加載異常 ({member.display_name}): {e}")
            
            # 使用真實頭像或占位圖
            if avatar_img:
                circle_avatar = mask_circle(avatar_img, AVATAR_SIZE)
            else:
                circle_avatar = mask_circle(create_placeholder_avatar(AVATAR_SIZE), AVATAR_SIZE)
            
            img.paste(circle_avatar, (AVATAR_X, y + 10), circle_avatar)
            
            # --- 玩家名稱 ---
            name_x = AVATAR_X + AVATAR_SIZE + 20
            name_y = y + 18
            
            # 限制名字長度
            display_name = member.display_name[:15]
            draw.text((name_x, name_y), display_name, fill=COLOR_TEXT_PRIMARY, font=font_name)
            
            # --- 動態長條圖 ---
            bar_x_start = 380
            bar_x_max = 280
            bar_y = y + 45
            bar_height = 8
            bar_radius = 4
            
            # 背景軌道
            draw.rectangle(
                [bar_x_start, bar_y, bar_x_start + bar_x_max, bar_y + bar_height],
                fill=COLOR_BAR_BG
            )
            
            # 填充長條
            current_bar_w = int((amount / max_amount) * bar_x_max)
            if current_bar_w > 5:
                draw.rectangle(
                    [bar_x_start, bar_y, bar_x_start + current_bar_w, bar_y + bar_height],
                    fill=COLOR_KK_BLUE
                )
            
            # --- KKCoin 與金額 ---
            coin_x = WIDTH - 240
            coin_y = y + 18
            
            # KK幣圖示 (簡單用 emoji)
            draw.text((coin_x, coin_y), "💰", font=font_name)
            
            # 金額數字（發光藍色）
            amount_str = f"{amount:,}"
            draw.text((coin_x + 40, coin_y), amount_str, fill=COLOR_KK_BLUE, font=font_coin)
            
            # KK 單位
            draw.text((WIDTH - 70, coin_y + 2), "KK", fill=COLOR_TEXT_SECONDARY, font=font_footer)
    
    # ========== 底部資訊區 ==========
    footer_y = HEADER_HEIGHT + (count * ROW_HEIGHT) + 15
    
    # 分隔線
    draw.line(
        [(MARGIN, footer_y), (WIDTH - MARGIN, footer_y)],
        fill=(60, 60, 65),
        width=2
    )
    
    # 資訊文字
    info_text = "⚠️ 園區警告：資產低於平均值者請注意安全。數據每 10 分鐘清算。"
    draw.text((MARGIN, footer_y + 20), info_text, fill=COLOR_TEXT_SECONDARY, font=font_footer)
    
    return img


# ============================================================
# 使用範例
# ============================================================

"""
使用方式:

from commands.kkcoin_pro import make_pro_leaderboard

# 在 Discord 命令中使用
@app_commands.command(name="kkcoin_pro", description="顯示專業深色主題排行榜")
async def kkcoin_pro(self, interaction: discord.Interaction):
    await interaction.response.defer()
    
    members_data = self.get_current_leaderboard_data()
    
    if not members_data:
        await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
        return
    
    try:
        image = await make_pro_leaderboard(members_data)
        with io.BytesIO() as img_bytes:
            image.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            file = discord.File(img_bytes, filename="kkcoin_pro.png")
            await interaction.followup.send(file=file)
    except Exception as e:
        print(f"❌ 生成排行榜失敗: {e}")
        await interaction.followup.send(f"❌ 生成排行榜失敗：{str(e)[:100]}", ephemeral=True)
"""
