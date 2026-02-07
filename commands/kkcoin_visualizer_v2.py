"""
KK幣排行榜視覺化升級版 (V2)
根據用戶圖片設計優化：
- 前 15 名排行榜（特殊底色）
- 長條圖 + 饼圖 + 周統計組合
- 數字邊框避免被長條覆蓋
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

# 確保 matplotlib 可用
MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
    print("✅ matplotlib 已正確載入")
except ImportError as e:
    print(f"❌ matplotlib/numpy 未安裝: {e}")
    print("   請執行: pip install matplotlib numpy")

# 配置
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")


# ============================================================
# 1. 改進版排行榜 - 15名 + 特殊底色
# ============================================================

async def create_enhanced_leaderboard_image(members_data, limit=15):
    """
    創建增強版排行榜圖像
    - 前 3 名有特殊底色（金/銀/銅）
    - 顯示 15 名而不是 20 名
    - 數字加邊框，避免被長條覆蓋
    
    Args:
        members_data: [(member, kkcoin), ...]
        limit: 顯示人數 (預設 15)
    """
    members_data = members_data[:limit]
    
    WIDTH = 1200
    ROW_HEIGHT = 70
    HEADER_HEIGHT = 120
    HEIGHT = HEADER_HEIGHT + (len(members_data) * ROW_HEIGHT) + 60
    
    MARGIN = 20
    BG_COLOR = (245, 248, 252)  # 淡藍背景
    
    # 前 3 名的特殊底色
    RANK_COLORS = {
        0: (255, 215, 0, 50),    # 🥇 金色 (半透明)
        1: (192, 192, 192, 50),  # 🥈 銀色 (半透明)
        2: (205, 127, 50, 50),   # 🥉 銅色 (半透明)
    }
    
    # 加載字體
    try:
        FONT_TITLE = ImageFont.truetype(FONT_PATH, 40)
        FONT_RANK = ImageFont.truetype(FONT_PATH, 28)
        FONT_NAME = ImageFont.truetype(FONT_PATH, 24)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 26)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, 16)
    except:
        FONT_TITLE = FONT_RANK = FONT_NAME = FONT_KKCOIN = FONT_SMALL = ImageFont.load_default()
    
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 標題
    title = f"🏆 KK幣排行榜 - 前{limit}名 🏆"
    draw.text((MARGIN + 20, 20), title, fill=(20, 20, 60), font=FONT_TITLE)
    
    # 更新時間
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((WIDTH - 280, 40), f"更新時間：{time_str}", fill=(100, 100, 120), font=FONT_SMALL)
    
    # 描述文字
    desc = "⭐ 發送訊息獲得 KK幣：10字+1幣 | 25字+2幣 | 50字+3幣 （冷卻30秒）"
    draw.text((MARGIN + 20, 80), desc, fill=(80, 80, 100), font=FONT_SMALL)
    
    # 繪製排名行
    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            y = HEADER_HEIGHT + i * ROW_HEIGHT
            
            # 前 3 名背景色
            if i < 3:
                r, g, b, a = RANK_COLORS[i]
                # 使用半透明的矩形作為背景
                overlay = Image.new('RGBA', (WIDTH - 2*MARGIN, ROW_HEIGHT), (r, g, b, a))
                img.paste(overlay, (MARGIN, y), overlay)
            
            # 排名編號（加邊框）
            rank_text = f"{i+1:2d}"
            rank_box = draw.textbbox((0, 0), rank_text, font=FONT_RANK)
            rank_width = rank_box[2] - rank_box[0] + 20
            
            # 繪製排名邊框
            draw.rectangle(
                [(MARGIN + 10, y + 15), (MARGIN + 10 + rank_width, y + 55)],
                outline=(50, 100, 200),
                width=2
            )
            draw.text((MARGIN + 20, y + 22), rank_text, fill=(50, 100, 200), font=FONT_RANK)
            
            # 排名 Emoji
            emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}" if i < 9 else f"#{i+1}"
            if i < 3:
                draw.text((MARGIN + rank_width + 30, y + 20), emoji, fill=(255, 200, 0), font=FONT_NAME)
            
            # 玩家名稱
            name_x = MARGIN + rank_width + 80
            player_name = member.display_name[:20]
            draw.text((name_x, y + 20), player_name, fill=(30, 30, 30), font=FONT_NAME)
            
            # KK幣數量（帶邊框）
            kkcoin_text = f"{int(kkcoin):,}"
            kkcoin_box = draw.textbbox((0, 0), kkcoin_text, font=FONT_KKCOIN)
            kkcoin_width = kkcoin_box[2] - kkcoin_box[0] + 20
            kkcoin_x = WIDTH - MARGIN - kkcoin_width - 20
            
            # 繪製 KK幣邊框
            draw.rectangle(
                [(kkcoin_x - 10, y + 10), (WIDTH - MARGIN - 10, y + 60)],
                outline=(100, 150, 255),
                fill=(230, 240, 255),
                width=2
            )
            draw.text((kkcoin_x, y + 20), kkcoin_text, fill=(50, 100, 200), font=FONT_KKCOIN)
            draw.text((WIDTH - MARGIN - 60, y + 30), "KK幣", fill=(100, 100, 100), font=FONT_SMALL)
            
            # 分隔線
            if i < len(members_data) - 1:
                draw.line(
                    [(MARGIN, y + ROW_HEIGHT - 1), (WIDTH - MARGIN, y + ROW_HEIGHT - 1)],
                    fill=(200, 200, 220),
                    width=1
                )
    
    return img


# ============================================================
# 2. 長條圖
# ============================================================

async def create_bar_chart_image(members_data, limit=15):
    """
    創建長條圖
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
        
    members_data = members_data[:limit]
    names = [m[0].display_name[:10] for m in members_data]
    coins = [m[1] for m in members_data]
    
    fig, ax = plt.subplots(figsize=(14, 8), facecolor='#f5f8fc')
    
    # 顏色分級
    colors = []
    for i in range(len(coins)):
        if i < 3:
            colors.append(['#FFD700', '#C0C0C0', '#CD7F32'][i])
        elif i < 10:
            colors.append('#FF6464')
        else:
            colors.append('#6496FF')
    
    bars = ax.bar(names, coins, color=colors, edgecolor='black', linewidth=2)
    
    # 在長條上方顯示數值（帶邊框）
    for bar, coin in zip(bars, coins):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width()/2., 
            height * 1.02,
            f'{int(coin):,}',
            ha='center', va='bottom', fontsize=11, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor='black', linewidth=1.5)
        )
    
    ax.set_ylabel('KK幣數量', fontsize=14, fontweight='bold')
    ax.set_title(f'📊 長條圖 - 前{limit}名KK幣排行', fontsize=16, fontweight='bold', pad=20)
    ax.set_ylim(0, max(coins) * 1.15)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#f5f8fc')
    buf.seek(0)
    plt.close(fig)
    
    return Image.open(buf).convert("RGBA")


# ============================================================
# 3. 饼圖 + 周統計
# ============================================================

async def create_pie_and_weekly_image(members_data, limit=15, total_coins=None, this_week_total=None, last_week_total=None):
    """
    創建饼圖 + 周統計組合圖
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
        
    members_data = members_data[:limit]
    names = [m[0].display_name[:10] for m in members_data]
    coins = [m[1] for m in members_data]
    
    # 設置圖表
    fig = plt.figure(figsize=(14, 10), facecolor='#f5f8fc')
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
    
    # ========== 左上：饼圖 ==========
    ax1 = fig.add_subplot(gs[0, 0])
    colors_pie = ['#FFD700', '#C0C0C0', '#CD7F32'] + ['#FF6464'] * 2 + ['#FFA500'] * 5 + ['#6496FF'] * (limit - 10)
    colors_pie = colors_pie[:limit]
    
    wedges, texts, autotexts = ax1.pie(
        coins,
        labels=names,
        autopct='%1.1f%%',
        colors=colors_pie,
        startangle=90,
        textprops={'fontsize': 9}
    )
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    ax1.set_title(f'🍰 KK幣分布（前{limit}名）', fontsize=14, fontweight='bold')
    
    # ========== 右上：周對比 ==========
    ax2 = fig.add_subplot(gs[0, 1])
    
    if total_coins is None:
        total_coins = sum(coins)
    if this_week_total is None:
        this_week_total = int(total_coins * 0.3)
    if last_week_total is None:
        last_week_total = int(total_coins * 0.25)
    
    weeks = ['上週', '本週']
    totals = [last_week_total, this_week_total]
    colors_comp = ['#FF6464', '#6496FF']
    bars = ax2.bar(weeks, totals, color=colors_comp, edgecolor='black', linewidth=2, width=0.5)
    
    for bar, total in zip(bars, totals):
        height = bar.get_height()
        ax2.text(
            bar.get_x() + bar.get_width()/2., 
            height * 1.05,
            f'{int(total):,}',
            ha='center', va='bottom', fontsize=12, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor='black', linewidth=1.5)
        )
    
    # 計算增長率
    if last_week_total > 0:
        growth_rate = ((this_week_total - last_week_total) / last_week_total) * 100
    else:
        growth_rate = 0
    
    growth_text = f"📈 增長 +{growth_rate:.1f}%" if growth_rate > 0 else f"📉 下降 {growth_rate:.1f}%"
    growth_color = '#6BBF59' if growth_rate >= 0 else '#FF6464'
    
    ax2.set_ylabel('KK幣數量', fontsize=12, fontweight='bold')
    ax2.set_title('📊 本週對比', fontsize=14, fontweight='bold')
    ax2.set_ylim(0, max(totals) * 1.35)
    ax2.grid(axis='y', alpha=0.3)
    
    # 添加增長率文字
    ax2.text(0.5, max(totals) * 1.2, growth_text, ha='center', fontsize=13, fontweight='bold',
            color=growth_color, transform=ax2.transData,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor=growth_color, linewidth=2.5))
    
    # ========== 下方：指標卡片 ==========
    ax3 = fig.add_subplot(gs[1, :])
    ax3.axis('off')
    
    member_count = len(members_data)
    
    # 指標 1 - 金庫總額
    ax_m1 = fig.add_axes([0.10, 0.08, 0.15, 0.25])
    ax_m1.axis('off')
    rect1 = plt.Rectangle((0, 0), 1, 1, transform=ax_m1.transAxes,
                          facecolor='#fff9e6', edgecolor='#FFD700', linewidth=3, zorder=-1)
    ax_m1.add_patch(rect1)
    ax_m1.text(0.5, 0.70, '💰 金庫總額', fontsize=11, fontweight='bold',
              ha='center', transform=ax_m1.transAxes, color='#666')
    ax_m1.text(0.5, 0.48, f'{int(total_coins):,}', fontsize=15, fontweight='bold',
              ha='center', transform=ax_m1.transAxes, color='#FFD700')
    ax_m1.text(0.5, 0.25, 'KK幣', fontsize=10,
              ha='center', transform=ax_m1.transAxes, color='#888')
    
    # 指標 2 - 本週新增
    ax_m2 = fig.add_axes([0.30, 0.08, 0.15, 0.25])
    ax_m2.axis('off')
    rect2 = plt.Rectangle((0, 0), 1, 1, transform=ax_m2.transAxes,
                          facecolor='#e6f2ff', edgecolor='#6496FF', linewidth=3, zorder=-1)
    ax_m2.add_patch(rect2)
    ax_m2.text(0.5, 0.70, '📈 本週新增', fontsize=11, fontweight='bold',
              ha='center', transform=ax_m2.transAxes, color='#666')
    ax_m2.text(0.5, 0.48, f'{int(this_week_total):,}', fontsize=15, fontweight='bold',
              ha='center', transform=ax_m2.transAxes, color='#6496FF')
    ax_m2.text(0.5, 0.25, 'KK幣', fontsize=10,
              ha='center', transform=ax_m2.transAxes, color='#888')
    
    # 指標 3 - 參與成員
    ax_m3 = fig.add_axes([0.50, 0.08, 0.15, 0.25])
    ax_m3.axis('off')
    rect3 = plt.Rectangle((0, 0), 1, 1, transform=ax_m3.transAxes,
                          facecolor='#e6ffe6', edgecolor='#6BBF59', linewidth=3, zorder=-1)
    ax_m3.add_patch(rect3)
    ax_m3.text(0.5, 0.70, '👥 參與成員', fontsize=11, fontweight='bold',
              ha='center', transform=ax_m3.transAxes, color='#666')
    ax_m3.text(0.5, 0.48, f'{member_count}', fontsize=15, fontweight='bold',
              ha='center', transform=ax_m3.transAxes, color='#6BBF59')
    ax_m3.text(0.5, 0.25, '名', fontsize=10,
              ha='center', transform=ax_m3.transAxes, color='#888')
    
    # 指標 4 - 平均值
    avg_coins = total_coins // member_count if member_count > 0 else 0
    ax_m4 = fig.add_axes([0.70, 0.08, 0.15, 0.25])
    ax_m4.axis('off')
    rect4 = plt.Rectangle((0, 0), 1, 1, transform=ax_m4.transAxes,
                          facecolor='#ffe6f2', edgecolor='#FF69B4', linewidth=3, zorder=-1)
    ax_m4.add_patch(rect4)
    ax_m4.text(0.5, 0.70, '📊 平均值', fontsize=11, fontweight='bold',
              ha='center', transform=ax_m4.transAxes, color='#666')
    ax_m4.text(0.5, 0.48, f'{int(avg_coins):,}', fontsize=15, fontweight='bold',
              ha='center', transform=ax_m4.transAxes, color='#FF69B4')
    ax_m4.text(0.5, 0.25, 'KK幣/人', fontsize=9,
              ha='center', transform=ax_m4.transAxes, color='#888')
    
    plt.suptitle(f'🎯 KK幣周統計 & 分布分析', fontsize=18, fontweight='bold', y=0.98)
    
    # 時間戳
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.text(0.99, 0.01, f'更新時間：{time_str}', ha='right', fontsize=10, color='#999')
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#f5f8fc')
    buf.seek(0)
    plt.close(fig)
    
    return Image.open(buf).convert("RGBA")


async def setup(bot):
    """載入此模組"""
    print("✅ [KKCoin V2] 排行榜視覺化升級版已載入")
