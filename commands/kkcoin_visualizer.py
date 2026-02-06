"""
KK幣排行榜視覺化增強模組
支援：多種模式、彩色排名、圖表展示
"""

import discord
from discord import app_commands
from discord.ext import commands
import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import numpy as np
from io import BytesIO

# 配置
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")

# 排名顏色方案
RANK_COLORS = {
    1: (255, 215, 0),      # 🥇 金色
    2: (192, 192, 192),    # 🥈 銀色
    3: (205, 127, 50),     # 🥉 銅色
    'top_5': (255, 100, 100),    # 紅色
    'top_10': (255, 165, 0),     # 橙色
    'top_20': (100, 150, 255),   # 藍色
}

# 獎牌 emoji
MEDAL_EMOJI = {
    1: "🥇",
    2: "🥈", 
    3: "🥉",
}

async def create_colorful_leaderboard_image(members_data, limit=20):
    """
    創建彩色排行榜圖像
    
    Args:
        members_data: [(member, kkcoin), ...]
        limit: 顯示的排名限制 (3, 5, 10, 20)
    """
    members_data = members_data[:limit]
    
    DESCRIPTION_HEIGHT = 80
    WIDTH, HEIGHT = 1000, 75 + 65 * len(members_data) + DESCRIPTION_HEIGHT
    AVATAR_SIZE = 52
    MARGIN = 20
    BG_COLOR = (245, 248, 252)  # 淡藍背景
    
    # 加載字體
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, 32)
        FONT_RANK = ImageFont.truetype(FONT_PATH, 26)
        FONT_NAME = ImageFont.truetype(FONT_PATH, 24)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 28)
        FONT_DESC = ImageFont.truetype(FONT_PATH, 16)
    except:
        FONT_BIG = ImageFont.load_default()
        FONT_RANK = ImageFont.load_default()
        FONT_NAME = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
    
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 標題
    title = f"KK幣排行榜 - 前{limit}名"
    draw.text((MARGIN, 20), title, fill=(30, 30, 30), font=FONT_BIG)
    
    # 時間戳
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((WIDTH - 220, 25), f"更新時間：{time_str}", fill=(120, 120, 120), font=FONT_DESC)
    
    # 繪製排名行
    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            rank = i + 1
            y = 80 + i * 65
            
            # 確定顏色
            if rank <= 3:
                color = RANK_COLORS[rank]
                bg_alpha = 30
            elif rank <= 5:
                color = RANK_COLORS['top_5']
                bg_alpha = 20
            elif rank <= 10:
                color = RANK_COLORS['top_10']
                bg_alpha = 15
            else:
                color = RANK_COLORS['top_20']
                bg_alpha = 10
            
            # 背景 bar
            bar_color = tuple(list(color) + [bg_alpha])
            draw.rectangle(
                [(MARGIN, y - 5), (WIDTH - MARGIN, y + 60)],
                fill=(color[0], color[1], color[2], int(255 * (bg_alpha / 100)))
            )
            
            # 排名號
            medal_text = MEDAL_EMOJI.get(rank, f"#{rank:2d}")
            draw.text((MARGIN + 8, y + 8), medal_text, fill=color, font=FONT_RANK)
            
            # 頭像位置
            avatar_x = MARGIN + 60
            try:
                avatar_url = None
                if hasattr(member, 'display_avatar'):
                    avatar_url = str(member.display_avatar)
                elif hasattr(member, 'avatar') and member.avatar:
                    avatar_url = member.avatar.url
                
                if avatar_url:
                    async with session.get(avatar_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            avatar = Image.open(io.BytesIO(await resp.read())).convert("RGBA")
                            avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
                            img.paste(avatar, (avatar_x, y + 4), avatar)
            except:
                pass
            
            # 玩家名稱
            name_x = avatar_x + AVATAR_SIZE + 15
            draw.text((name_x, y + 8), member.display_name[:20], fill=(30, 30, 30), font=FONT_NAME)
            
            # KK幣數量（右側）
            kkcoin_text = f"{kkcoin:,} KK幣"
            kkcoin_bbox = draw.textbbox((0, 0), kkcoin_text, font=FONT_KKCOIN)
            kkcoin_width = kkcoin_bbox[2] - kkcoin_bbox[0]
            draw.text((WIDTH - MARGIN - kkcoin_width - 10, y + 10), kkcoin_text, fill=color, font=FONT_KKCOIN)
    
    # 說明
    desc_y = 85 + len(members_data) * 65
    draw.line([(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)], fill=(180, 180, 180), width=2)
    draw.text((MARGIN, desc_y), "💡 KKcoin 獲得方法", fill=(80, 80, 80), font=FONT_RANK)
    descriptions = [
        "• 發送訊息：10字+1幣 | 25字+2幣 | 50字+3幣（冷卻30秒）",
        "• 限制：重複訊息、純表情不給幣 | 語音掛機可獲得額外獎勵"
    ]
    for i, desc in enumerate(descriptions):
        draw.text((MARGIN + 15, desc_y + 28 + i * 22), desc, fill=(100, 100, 100), font=FONT_DESC)
    
    return img


async def create_chart_image(members_data, chart_type='bar', limit=10):
    """
    創建圖表（長條圖或圓餅圖）
    
    Args:
        members_data: [(member, kkcoin), ...]
        chart_type: 'bar' or 'pie'
        limit: 顯示數量
    """
    members_data = members_data[:limit]
    names = [m[0].display_name[:15] for m in members_data]
    coins = [m[1] for m in members_data]
    
    fig, ax = plt.subplots(figsize=(14, 8), facecolor='white')
    
    if chart_type == 'bar':
        # 長條圖：按排名用不同顏色
        colors = []
        for i in range(len(coins)):
            if i < 3:
                colors.append(['#FFD700', '#C0C0C0', '#CD7F32'][i])  # 金銀銅
            elif i < 5:
                colors.append('#FF6464')  # 紅
            elif i < 10:
                colors.append('#FFA500')  # 橙
            else:
                colors.append('#6496FF')  # 藍
        
        bars = ax.bar(names, coins, color=colors, edgecolor='black', linewidth=1.5)
        
        # 在長條上方顯示數值
        for bar, coin in zip(bars, coins):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(coin):,}',
                   ha='center', va='bottom', fontsize=12, fontweight='bold')
        
        ax.set_ylabel('KK幣數量', fontsize=14, fontweight='bold')
        ax.set_title('KK幣排行 - 長條圖', fontsize=16, fontweight='bold', pad=20)
        ax.set_ylim(0, max(coins) * 1.15)
        
    else:  # pie
        # 圓餅圖
        colors = ['#FFD700', '#C0C0C0', '#CD7F32'] + ['#FF6464'] * 2 + ['#FFA500'] * 5 + ['#6496FF'] * (limit - 10)
        colors = colors[:limit]
        
        wedges, texts, autotexts = ax.pie(
            coins, 
            labels=names,
            autopct='%1.1f%%',
            colors=colors,
            startangle=90,
            textprops={'fontsize': 10}
        )
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        ax.set_title(f'KK幣分布 - 圓餅圖（前{limit}名）', fontsize=16, fontweight='bold', pad=20)
    
    plt.tight_layout()
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig)
    
    return Image.open(buf).convert("RGBA")


async def setup(bot):
    """載入此模組"""
    print("✅ [KKCoin] 排行榜視覺化模組已載入")
