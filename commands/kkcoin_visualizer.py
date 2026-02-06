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
from io import BytesIO

# 延迟导入 matplotlib（用于图表生成）
try:
    import matplotlib
    matplotlib.use('Agg')  # 设置非交互后端（必须在 pyplot 导入前）
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ [警告] matplotlib/numpy 未安装: {e}")
    print("   请运行: pip install matplotlib numpy")
    MATPLOTLIB_AVAILABLE = False
    plt = None
    np = None

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
    if not MATPLOTLIB_AVAILABLE:
        raise RuntimeError("matplotlib 未安裝，無法生成圖表。請執行: pip install matplotlib numpy")
    
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


async def create_weekly_stats_image(total_coins, this_week_total, last_week_total, member_count):
    """
    創建本週統計圖表
    
    Args:
        total_coins: 當前排行榜總KK幣
        this_week_total: 本週新增KK幣
        last_week_total: 上週新增KK幣
        member_count: 總成員數
    """
    if not MATPLOTLIB_AVAILABLE:
        raise RuntimeError("matplotlib 未安裝，無法生成圖表。請執行: pip install matplotlib numpy")
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10), facecolor='#f5f8fc')
    
    # 1. 本週vs上週對比
    weeks = ['上週', '本週']
    totals = [last_week_total, this_week_total]
    colors_comp = ['#FF6464', '#6496FF']
    bars = ax1.bar(weeks, totals, color=colors_comp, edgecolor='black', linewidth=2, width=0.6)
    
    for bar, total in zip(bars, totals):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(total):,}',
                ha='center', va='bottom', fontsize=14, fontweight='bold')
    
    # 增長率
    if last_week_total > 0:
        growth_rate = ((this_week_total - last_week_total) / last_week_total) * 100
        growth_text = f"增長 +{growth_rate:.1f}%" if growth_rate > 0 else f"下降 {growth_rate:.1f}%"
        growth_color = '#FF6464' if growth_rate < 0 else '#6BBF59'
    else:
        growth_text = "首次統計"
        growth_color = '#FFA500'
    
    ax1.text(0.5, max(totals) * 0.9, growth_text, 
            ha='center', fontsize=13, fontweight='bold', color=growth_color,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    ax1.set_ylabel('KK幣數量', fontsize=12, fontweight='bold')
    ax1.set_title('📊 本週 vs 上週', fontsize=14, fontweight='bold')
    ax1.set_ylim(0, max(totals) * 1.3)
    ax1.grid(axis='y', alpha=0.3)
    
    # 2. 園區總資產變化（圖表）
    wealth_data = [
        ('館長', 15000),
        ('夜店', 12000),
        ('競技場', 10000),
        ('其他', 8000)
    ]
    locations = [w[0] for w in wealth_data]
    coins_by_loc = [w[1] for w in wealth_data]
    colors_loc = ['#FFD700', '#FF6464', '#6496FF', '#FFA500']
    
    wedges, texts, autotexts = ax2.pie(
        coins_by_loc,
        labels=locations,
        autopct='%1.1f%%',
        colors=colors_loc,
        startangle=45,
        textprops={'fontsize': 10, 'fontweight': 'bold'}
    )
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    ax2.set_title('🏢 園區資產分布', fontsize=14, fontweight='bold')
    
    # 3. 關鍵指標卡片（1）
    ax3.axis('off')
    
    # 總KK幣
    ax3.text(0.5, 0.75, '金庫總額', fontsize=12, fontweight='bold',
            ha='center', transform=ax3.transAxes, color='#666')
    ax3.text(0.5, 0.55, f'{int(total_coins):,}', fontsize=28, fontweight='bold',
            ha='center', transform=ax3.transAxes, color='#FFD700')
    ax3.text(0.5, 0.35, 'KK幣', fontsize=11,
            ha='center', transform=ax3.transAxes, color='#888')
    
    # 背景色
    rect_main = plt.Rectangle((0.05, 0.05), 0.9, 0.9, 
                               transform=ax3.transAxes,
                               facecolor='#fff9e6', edgecolor='#FFD700', linewidth=2,
                               zorder=-1)
    ax3.add_patch(rect_main)
    
    # 4. 關鍵指標卡片（2）
    ax4.axis('off')
    
    # 參與成員
    ax4.text(0.5, 0.75, '參與成員', fontsize=12, fontweight='bold',
            ha='center', transform=ax4.transAxes, color='#666')
    ax4.text(0.5, 0.55, f'{member_count}', fontsize=28, fontweight='bold',
            ha='center', transform=ax4.transAxes, color='#6496FF')
    ax4.text(0.5, 0.35, '名', fontsize=11,
            ha='center', transform=ax4.transAxes, color='#888')
    
    # 背景色
    rect_member = plt.Rectangle((0.05, 0.05), 0.9, 0.9,
                                 transform=ax4.transAxes,
                                 facecolor='#e6f2ff', edgecolor='#6496FF', linewidth=2,
                                 zorder=-1)
    ax4.add_patch(rect_member)
    
    plt.suptitle('📈 KK幣本週統計', fontsize=18, fontweight='bold', y=0.98)
    
    # 更新時間戳
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.text(0.99, 0.01, f'更新時間：{time_str}', ha='right', fontsize=9, color='#999')
    
    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#f5f8fc')
    buf.seek(0)
    plt.close(fig)
    
    return Image.open(buf).convert("RGBA")


async def create_weekly_mvp_image(mvp_member, this_week_coins, rank_position, total_members):
    """
    創建本週績效王卡片
    
    Args:
        mvp_member: 本週MVP成員
        this_week_coins: 本週新增KK幣
        rank_position: 總排行中的位置
        total_members: 總成員數
    """
    WIDTH, HEIGHT = 1000, 600
    BG_COLOR = (30, 40, 80)  # 深藍背景
    
    try:
        FONT_TITLE = ImageFont.truetype(FONT_PATH, 48)
        FONT_NAME = ImageFont.truetype(FONT_PATH, 56)
        FONT_STATS = ImageFont.truetype(FONT_PATH, 32)
        FONT_LABEL = ImageFont.truetype(FONT_PATH, 24)
        FONT_DESC = ImageFont.truetype(FONT_PATH, 20)
    except:
        FONT_TITLE = ImageFont.load_default()
        FONT_NAME = ImageFont.load_default()
        FONT_STATS = ImageFont.load_default()
        FONT_LABEL = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
    
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 漸層背景效果（用矩形堆疊）
    for i in range(HEIGHT):
        alpha = int(255 * (1 - i / HEIGHT * 0.3))
        color = (30 + int(20 * (i / HEIGHT)), 40 + int(40 * (i / HEIGHT)), 120)
        draw.rectangle([(0, i), (WIDTH, i + 1)], fill=color)
    
    # 頂部金色裝飾
    draw.rectangle([(0, 0), (WIDTH, 8)], fill=(255, 215, 0))
    
    # 標題
    draw.text((50, 40), "🏆 本週績效王 🏆", fill=(255, 215, 0), font=FONT_TITLE)
    
    # 頭像區域
    avatar_x = 150
    avatar_y = 150
    avatar_size = 200
    
    try:
        avatar_url = None
        if hasattr(mvp_member, 'display_avatar'):
            avatar_url = str(mvp_member.display_avatar)
        elif hasattr(mvp_member, 'avatar') and mvp_member.avatar:
            avatar_url = mvp_member.avatar.url
        
        if avatar_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        avatar = Image.open(io.BytesIO(await resp.read())).convert("RGBA")
                        avatar = avatar.resize((avatar_size, avatar_size))
                        
                        # 圓形頭像（帶金色邊框）
                        circle_img = Image.new("RGBA", (avatar_size + 20, avatar_size + 20), (0, 0, 0, 0))
                        circle_draw = ImageDraw.Draw(circle_img)
                        circle_draw.ellipse([(0, 0), (avatar_size + 20, avatar_size + 20)], 
                                          outline=(255, 215, 0), width=4)
                        
                        # 貼上頭像
                        circle_img.paste(avatar, (10, 10), avatar)
                        img.paste(circle_img, (avatar_x - 10, avatar_y - 10), circle_img)
    except Exception as e:
        print(f"頭像加載失敗: {e}")
    
    # 玩家信息區域
    info_x = avatar_x + avatar_size + 80
    
    # 玩家名稱
    draw.text((info_x, avatar_y + 30), mvp_member.display_name[:20], 
             fill=(255, 255, 255), font=FONT_NAME)
    
    # 本週新增KK幣
    draw.text((info_x, avatar_y + 110), "本週新增", fill=(200, 200, 200), font=FONT_LABEL)
    draw.text((info_x, avatar_y + 145), f"{int(this_week_coins):,}", 
             fill=(100, 255, 150), font=FONT_STATS)
    draw.text((info_x + 350, avatar_y + 150), "KK幣", fill=(100, 255, 150), font=FONT_LABEL)
    
    # 排行位置
    draw.text((info_x, avatar_y + 220), f"總排行：第 {rank_position} 名（共 {total_members} 人）",
             fill=(150, 200, 255), font=FONT_DESC)
    
    # 底部勵志文案
    bottom_text = "🌟 妳是 KK garden 的榮耀 🌟"
    text_bbox = draw.textbbox((0, 0), bottom_text, font=FONT_LABEL)
    text_width = text_bbox[2] - text_bbox[0]
    draw.text(((WIDTH - text_width) / 2, HEIGHT - 80), bottom_text,
             fill=(255, 215, 0), font=FONT_LABEL)
    
    # 時間戳
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((50, HEIGHT - 40), f"更新時間：{time_str}", fill=(150, 150, 150), font=FONT_DESC)
    
    return img


async def setup(bot):
    """載入此模組"""
    print("✅ [KKCoin] 排行榜視覺化模組已載入")
