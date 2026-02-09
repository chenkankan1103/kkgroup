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

# ============================================================
# 共通配置 - 繼承初版設定 (必須先定義, 才能被 matplotlib 使用)
# ============================================================

# 字型配置（與初版 kcoin.py 相同）
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")

# 資源路徑
TROPHY_PATH = os.path.join(ASSETS_PATH, "trophy.png")
MEDAL_PATHS = [
    os.path.join(ASSETS_PATH, "1.png"),  # 金牌
    os.path.join(ASSETS_PATH, "2.png"),  # 銀牌
    os.path.join(ASSETS_PATH, "3.png"),  # 銅牌
]

# 配色方案 - 初版設定
COLOR_BG_MAIN = (255, 255, 255)       # 主背景：白色
COLOR_RANK_GOLD = (240, 200, 80)      # 排名號碼：金色
COLOR_TEXT_TITLE = (60, 60, 60)       # 標題：深灰
COLOR_TEXT_NAME = (30, 30, 30)        # 名字：黑
COLOR_TEXT_KKCOIN = (50, 110, 210)    # KK幣數字：藍
COLOR_TEXT_DESC = (100, 100, 100)     # 描述：灰

# matplotlib HEX 顏色版本
COLOR_HEX_TITLE = '#3c3c3c'           # 標題：深灰
COLOR_HEX_KKCOIN = '#326ed2'          # KK幣數字：藍
COLOR_HEX_DESC = '#646464'            # 描述：灰

# 字型大小（初版設定）
FONT_SIZE_BIG = 28
FONT_SIZE_SMALL = 22
FONT_SIZE_KKCOIN = 24
FONT_SIZE_DESC = 16

# 確保 matplotlib 可用 - 在配置後初始化
MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager
    import numpy as np
    
    # 配置 matplotlib 中文字型 - FONT_PATH 已定義
    try:
        font_mpl = matplotlib.font_manager.FontProperties(fname=FONT_PATH)
        matplotlib.rc('font', family=font_mpl.get_name())
        print(f"✅ matplotlib 字型已設置: {FONT_PATH}")
    except Exception as e:
        print(f"⚠️ matplotlib 字型設置失敗: {e}")
    
    MATPLOTLIB_AVAILABLE = True
    print("✅ matplotlib 已正確載入")
except ImportError as e:
    print(f"❌ matplotlib/numpy 未安裝: {e}")
    print("   請執行: pip install matplotlib numpy")

# ============================================================
# 1. 改進版排行榜 - 15名 + 特殊底色
# ============================================================

async def create_enhanced_leaderboard_image(members_data, limit=15):
    """
    創建增強版排行榜圖像 - 高級美化版
    使用初版設定的中文字型和配色方案
    - 前 3 名有漸變背景 + 光暈效果（金/銀/銅）
    - 顯示 15 名而不是 20 名
    - 數字加邊框，避免被長條覆蓋
    - 改進的陰影和排版
    
    Args:
        members_data: [(member, kkcoin), ...]
        limit: 顯示人數 (預設 15)
    """
    members_data = members_data[:limit]
    
    WIDTH = 1300
    ROW_HEIGHT = 75
    HEADER_HEIGHT = 140
    HEIGHT = HEADER_HEIGHT + (len(members_data) * ROW_HEIGHT) + 80
    
    MARGIN = 25
    # 美化背景 - 使用初版的白色底
    BG_COLOR = COLOR_BG_MAIN
    
    # 前 3 名的漸變顏色 (RGB) - 保留金銀銅的經典配色
    RANK_COLORS = {
        0: {'main': (255, 215, 0), 'light': (255, 240, 100), 'shadow': (200, 160, 0)},      # 🥇 金色
        1: {'main': (192, 192, 192), 'light': (230, 230, 230), 'shadow': (140, 140, 140)},  # 🥈 銀色
        2: {'main': (205, 127, 50), 'light': (240, 180, 100), 'shadow': (150, 90, 30)},     # 🥉 銅色
    }
    
    # 加載字體 - 用初版相同的字型
    try:
        FONT_TITLE = ImageFont.truetype(FONT_PATH, 44)
        FONT_RANK = ImageFont.truetype(FONT_PATH, FONT_SIZE_KKCOIN)      # 用 FONT_SIZE_KKCOIN (24)
        FONT_NAME = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL)       # 用 FONT_SIZE_SMALL (22)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, FONT_SIZE_SMALL + 2) # 小高些 (24)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, FONT_SIZE_DESC)       # 用 FONT_SIZE_DESC (16)
    except Exception as e:
        print(f"❌ 載入字型失敗: {e}")
        FONT_TITLE = FONT_RANK = FONT_NAME = FONT_KKCOIN = FONT_SMALL = ImageFont.load_default()
    
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img, 'RGBA')
    
    # === 標題區塊 ===
    # 標題背景 - 深藍邊框
    draw.rectangle(
        [(MARGIN, 15), (WIDTH - MARGIN, 125)],
        fill=(255, 255, 255),
        outline=(50, 100, 200),
        width=3
    )
    
    # 標題 - 使用初版的標題顏色
    title = f"🏆 KK幣排行榜 - 前{limit}名 🏆"
    draw.text((MARGIN + 25, 28), title, fill=COLOR_TEXT_TITLE, font=FONT_TITLE)
    
    # 更新時間
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((WIDTH - MARGIN - 280, 50), f"⏰ 更新時間：{time_str}", fill=COLOR_TEXT_DESC, font=FONT_SMALL)
    
    # 描述文字 - 美化
    desc = "✨ 發送訊息獲得 KK幣：10字+1幣 | 25字+2幣 | 50字+3幣 （冷卻30秒）"
    draw.text((MARGIN + 25, 85), desc, fill=COLOR_TEXT_DESC, font=FONT_SMALL)
    
    # === 繪製排名行 ===
    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            y = HEADER_HEIGHT + i * ROW_HEIGHT
            row_height = ROW_HEIGHT
            
            # === 背景 - 前3名特殊設計 ===
            if i < 3:
                colors = RANK_COLORS[i]
                # 漸變效果 - 使用半透明矩形模擬
                overlay = Image.new('RGBA', (WIDTH - 2*MARGIN - 4, row_height - 2), 
                                   colors['light'] + (80,))
                img.paste(overlay, (MARGIN + 2, y + 1), overlay)
                
                # 光暈邊框
                draw.rectangle(
                    [(MARGIN + 2, y + 1), (WIDTH - MARGIN - 2, y + row_height - 1)],
                    outline=colors['shadow'],
                    width=4
                )
                draw.rectangle(
                    [(MARGIN + 4, y + 3), (WIDTH - MARGIN - 4, y + row_height - 3)],
                    outline=colors['main'],
                    width=2
                )
            else:
                # 普通行 - 淡灰背景
                draw.rectangle(
                    [(MARGIN + 2, y + 2), (WIDTH - MARGIN - 2, y + row_height - 2)],
                    fill=(255, 255, 255),
                    outline=(220, 220, 235),
                    width=1
                )
            
            # === 排名徽章（大圓形） ===
            rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i+1)
            rank_circle_x = MARGIN + 30
            rank_circle_y = y + row_height // 2
            
            # 徽章圓形背景
            if i < 3:
                colors = RANK_COLORS[i]
                draw.ellipse(
                    [(rank_circle_x - 20, rank_circle_y - 20), 
                     (rank_circle_x + 20, rank_circle_y + 20)],
                    fill=colors['main'],
                    outline=colors['shadow'],
                    width=3
                )
                draw.text((rank_circle_x - 10, rank_circle_y - 16), rank_emoji, 
                         fill=(255, 255, 255), font=ImageFont.truetype(FONT_PATH, 28))
            else:
                # 普通排名圓 - 使用初版的排名顏色
                draw.ellipse(
                    [(rank_circle_x - 18, rank_circle_y - 18), 
                     (rank_circle_x + 18, rank_circle_y + 18)],
                    fill=(200, 220, 255),
                    outline=(100, 150, 200),
                    width=2
                )
                draw.text((rank_circle_x - 8, rank_circle_y - 13), str(i+1), 
                         fill=COLOR_RANK_GOLD, font=FONT_RANK)
            
            # === 玩家名稱 - 用初版的名字顏色 ===
            name_x = rank_circle_x + 50
            player_name = member.display_name[:22]
            draw.text((name_x, y + 23), player_name, fill=COLOR_TEXT_NAME, font=FONT_NAME)
            
            # === KK幣數量（漂亮的邊框卡片） - 用初版的 KK幣顏色===
            kkcoin_text = f"{int(kkcoin):,}"
            kkcoin_box = draw.textbbox((0, 0), kkcoin_text, font=FONT_KKCOIN)
            kkcoin_width = kkcoin_box[2] - kkcoin_box[0] + 30
            kkcoin_x = WIDTH - MARGIN - kkcoin_width - 15
            
            # KK幣背景卡片
            if i < 3:
                colors = RANK_COLORS[i]
                card_fill = colors['light'] + (100,)
                card_outline = colors['main']
            else:
                card_fill = (220, 240, 255, 120)
                card_outline = (100, 150, 255)
            
            draw.rectangle(
                [(kkcoin_x - 15, y + 12), (WIDTH - MARGIN - 10, y + row_height - 12)],
                fill=card_fill,
                outline=card_outline,
                width=2
            )
            
            # KK幣數字 - 用初版的藍色
            draw.text((kkcoin_x + 5, y + 22), kkcoin_text, fill=COLOR_TEXT_KKCOIN, font=FONT_KKCOIN)
            draw.text((WIDTH - MARGIN - 55, y + 33), "KK幣", fill=COLOR_TEXT_DESC, font=FONT_SMALL)
            
            # === 分隔線 ===
            if i < len(members_data) - 1:
                draw.line(
                    [(MARGIN + 10, y + row_height), (WIDTH - MARGIN - 10, y + row_height)],
                    fill=(200, 210, 230),
                    width=1
                )
    
    return img


# ============================================================
# 2. 長條圖
# ============================================================

async def create_bar_chart_image(members_data, limit=15):
    """
    創建高級美化長條圖
    使用初版配色方案
    - 漸變色長條
    - 立體陰影效果
    - 優化的網格和標籤
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
        
    members_data = members_data[:limit]
    names = [m[0].display_name[:10] for m in members_data]
    coins = [m[1] for m in members_data]
    
    fig, ax = plt.subplots(figsize=(15, 8.5), facecolor='#ffffff')
    
    # 配置background - 用初版白色背景
    ax.set_facecolor('#ffffff')
    
    # 顏色分級（更豐富的漸變）- 使用 HEX 顏色
    colors = []
    for i in range(len(coins)):
        if i == 0:
            colors.append('#FFD700')  # 金 - 初版的排名金色
        elif i == 1:
            colors.append('#C0C0C0')  # 銀
        elif i == 2:
            colors.append('#CD7F32')  # 銅
        elif i < 8:
            # 漸變紅
            intensity = int(255 - (i - 3) * 15)
            hex_color = f'#{intensity:02x}5050'
            colors.append(hex_color)
        else:
            # 漸變藍
            intensity = int(200 - (i - 8) * 10)
            hex_color = f'#{intensity//2:02x}8080{intensity:02x}'
            colors.append(hex_color)
    
    # 繪製長條 - 帶陰影
    bars = ax.bar(range(len(names)), coins, color=colors, edgecolor='#333333', linewidth=2.5,
                  alpha=0.85, zorder=3)
    
    # 添加陰影效果（在長條下方）
    for i, bar in enumerate(bars):
        # 陰影：在bar後面繪製灰色長條
        shadow = ax.bar(i, coins[i] * 0.95, color='#999999', alpha=0.2, width=0.9, zorder=1)
    
    # 在長條上方顯示數值（帶漂亮的邊框和陰影）
    for i, (bar, coin) in enumerate(zip(bars, coins)):
        height = bar.get_height()
        value_text = f'{int(coin):,}'
        
        # 文本陰影
        ax.text(
            bar.get_x() + bar.get_width()/2., 
            height * 1.04,
            value_text,
            ha='center', va='bottom', fontsize=12, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.6', facecolor='white', 
                     edgecolor='#333333', linewidth=2, alpha=0.95),
            color='#000000'
        )
    
    # X軸標籤 - 優化旋轉和對齐 - 需要用中文字型
    try:
        font_mpl = matplotlib.font_manager.FontProperties(fname=FONT_PATH)
        ax.set_xticklabels(names, rotation=45, ha='right', fontsize=11, fontweight='bold', 
                          fontproperties=font_mpl)
    except:
        ax.set_xticklabels(names, rotation=45, ha='right', fontsize=11, fontweight='bold')
    
    ax.set_xticks(range(len(names)))
    
    # ✅ 配置字型用於所有中文文本
    try:
        font_mpl = matplotlib.font_manager.FontProperties(fname=FONT_PATH)
        
        # Y軸標籤 - 用初版的藍色文字（HEX 版本） + 中文字型
        ylabel = ax.set_ylabel('KK幣數量', fontsize=14, fontweight='bold', labelpad=10, 
                              color=COLOR_HEX_KKCOIN, fontproperties=font_mpl)
        
        # 標題 - 用初版的標題顏色（HEX 版本） + 中文字型
        ax.set_title(f'📊 【長條圖排行】前{limit}名KK幣總額', fontsize=17, fontweight='bold', 
                    pad=20, color=COLOR_HEX_TITLE, fontproperties=font_mpl)
    except Exception as e:
        print(f"⚠️ matplotlib Y軸字型設置失敗: {e}")
        # 如果字型失敗，至少還能顯示英文或符號
        ylabel = ax.set_ylabel('KK Coins', fontsize=14, fontweight='bold', labelpad=10, 
                              color=COLOR_HEX_KKCOIN)
        ax.set_title(f'Bar Chart Top {limit}', fontsize=17, fontweight='bold', 
                    pad=20, color=COLOR_HEX_TITLE)
    
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
    
    # 設定Y軸範圍
    ax.set_ylim(0, max(coins) * 1.2)
    
    # 網格線 - 美化
    ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=1, color='#cccccc', zorder=0)
    ax.set_axisbelow(True)
    
    # 邊框
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(1.5)
    ax.spines['left'].set_color('#333333')
    ax.spines['bottom'].set_linewidth(1.5)
    ax.spines['bottom'].set_color('#333333')
    
    # 刻度
    ax.tick_params(axis='both', labelsize=10, width=1.5, length=5)
    
    plt.tight_layout()
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#ffffff')
    buf.seek(0)
    plt.close(fig)
    
    return Image.open(buf).convert("RGBA")


# ============================================================
# 3. 饼圖 + 周統計
# ============================================================

async def create_pie_and_weekly_image(members_data, limit=15, total_coins=None, this_week_total=None, last_week_total=None):
    """
    創建高級美化 饼圖 + 周統計組合圖
    - 更好的配色和漸變
    - 立體效果和陰影
    - 優雅的指標卡片設計
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
        
    members_data = members_data[:limit]
    names = [m[0].display_name[:10] for m in members_data]
    coins = [m[1] for m in members_data]
    
    # 設置圖表 - 用初版的白色背景
    fig = plt.figure(figsize=(15, 10.5), facecolor='#ffffff')
    gs = fig.add_gridspec(2, 2, hspace=0.35, wspace=0.35)
    
    # ✅ 提前載入字型以供所有圖表使用
    try:
        font_mpl = matplotlib.font_manager.FontProperties(fname=FONT_PATH)
    except:
        font_mpl = None
    
    # ========== 左上：饼圖（美化版） ==========
    ax1 = fig.add_subplot(gs[0, 0])
    
    # 豐富的配色方案（漸變效果）
    colors_pie = [
        '#FFD700',  # 0 - 金
        '#C0C0C0',  # 1 - 銀
        '#CD7F32',  # 2 - 銅
        '#FF8C42', '#FF6B6B', '#FF4444',  # 3-5 - 紅色系
        '#FFA500', '#FFB347', '#FFD090',  # 6-8 - 橙色系
        '#FFE082', '#FFED4E',  # 9-10 - 黃色系
        '#6BA3FF', '#5B9FFF', '#4A9FFF'  # 11-14 - 藍色系
    ]
    colors_pie = colors_pie[:limit]
    
    # 饼圖 - 美化版 - 設置字型
    textprops = {'fontsize': 9, 'fontweight': 'bold'}
    if font_mpl:
        textprops['fontproperties'] = font_mpl
    
    wedges, texts, autotexts = ax1.pie(
        coins,
        labels=names,
        autopct='%1.1f%%',
        colors=colors_pie,
        startangle=90,
        textprops=textprops,
        wedgeprops={'edgecolor': 'white', 'linewidth': 2},
        pctdistance=0.85,
        explode=[0.05 if i < 3 else 0 for i in range(limit)]  # 前3名突出
    )
    
    # 美化百分比文本
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(8)
    
    # 美化標籤
    for text in texts:
        text.set_fontsize(9)
        text.set_fontweight('bold')
        if font_mpl:
            text.set_fontproperties(font_mpl)
    
    # Pie 圖標題 - 加入字型
    if font_mpl:
        ax1.set_title(f'🍰 KK幣分布圖（前{limit}名）', fontsize=14, fontweight='bold', pad=10, fontproperties=font_mpl)
    else:
        ax1.set_title(f'Pie Chart Top {limit}', fontsize=14, fontweight='bold', pad=10)
    
    # ========== 右上：周對比（美化版） ==========
    ax2 = fig.add_subplot(gs[0, 1])
    
    if total_coins is None:
        total_coins = sum(coins)
    if this_week_total is None:
        this_week_total = int(total_coins * 0.3)
    if last_week_total is None:
        last_week_total = int(total_coins * 0.25)
    
    weeks = ['📅 上週', '📅 本週']
    totals = [last_week_total, this_week_total]
    colors_comp = ['#FF8A65', '#66BB6A']  # 溫暖紅色 vs 綠色
    
    # 長條圖с陰影
    bars = ax2.bar(weeks, totals, color=colors_comp, edgecolor='#333333', linewidth=2.5, width=0.6, alpha=0.85)
    
    # 添加陰影
    for i, bar in enumerate(bars):
        shadow = ax2.bar(i, totals[i] * 0.95, color='#999999', alpha=0.15, width=0.6, zorder=1)
    
    # 數值標籤
    for bar, total in zip(bars, totals):
        height = bar.get_height()
        ax2.text(
            bar.get_x() + bar.get_width()/2., 
            height * 1.08,
            f'{int(total):,}',
            ha='center', va='bottom', fontsize=13, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.6', facecolor='white', 
                     edgecolor='#333333', linewidth=2, alpha=0.95),
            color='#000000'
        )
    
    # 計算增長率
    if last_week_total > 0:
        growth_rate = ((this_week_total - last_week_total) / last_week_total) * 100
    else:
        growth_rate = 100 if this_week_total > 0 else 0
    
    # 增長率展示
    if growth_rate > 0:
        growth_text = f"📈 成長 +{growth_rate:.1f}%"
        growth_color = '#4CAF50'
    elif growth_rate < 0:
        growth_text = f"📉 下降 {growth_rate:.1f}%"
        growth_color = '#FF5252'
    else:
        growth_text = "➡️ 持平 ±0%"
        growth_color = '#FFC107'
    
    # Y軸 - 添加字型
    if font_mpl:
        ax2.set_ylabel('KK幣數量', fontsize=12, fontweight='bold', fontproperties=font_mpl)
        ax2.set_title('📊 本週數據對比', fontsize=14, fontweight='bold', pad=10, fontproperties=font_mpl)
    else:
        ax2.set_ylabel('KK Coins', fontsize=12, fontweight='bold')
        ax2.set_title('Weekly Comparison', fontsize=14, fontweight='bold', pad=10)
    
    ax2.set_ylim(0, max(totals) * 1.4)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
    ax2.grid(axis='y', alpha=0.3, linestyle='--', linewidth=1, color='#cccccc')
    ax2.set_axisbelow(True)
    
    # 移除不需要的邊框
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    
    # 添加增長率文字
    ax2.text(0.5, max(totals) * 1.25, growth_text, ha='center', fontsize=13, fontweight='bold',
            color='white', transform=ax2.transData,
            bbox=dict(boxstyle='round,pad=0.7', facecolor=growth_color, alpha=0.85, edgecolor='white', linewidth=2))
    
    # ========== 下方：指標卡片（美化版） ==========
    ax3 = fig.add_subplot(gs[1, :])
    ax3.axis('off')
    
    member_count = len(members_data)
    avg_coins = total_coins // member_count if member_count > 0 else 0
    
    # 指標 1 - 金庫總額
    ax_m1 = fig.add_axes([0.08, 0.06, 0.18, 0.28])
    ax_m1.axis('off')
    ax_m1.set_xlim(0, 1)
    ax_m1.set_ylim(0, 1)
    
    from matplotlib.patches import FancyBboxPatch
    
    rect1 = FancyBboxPatch((0.05, 0.05), 0.9, 0.9, transform=ax_m1.transAxes,
                          facecolor='#FFFACD', edgecolor='#FFD700', linewidth=4, zorder=1,
                          boxstyle='round,pad=0.05')
    ax_m1.add_patch(rect1)
    
    # 陰影
    shadow1 = FancyBboxPatch((0.08, 0.02), 0.84, 0.84, transform=ax_m1.transAxes,
                           facecolor='#DAA520', alpha=0.1, zorder=0,
                           boxstyle='round,pad=0.05')
    ax_m1.add_patch(shadow1)
    
    ax_m1.text(0.5, 0.73, '💰 金庫總額', fontsize=12, fontweight='bold',
              ha='center', transform=ax_m1.transAxes, color='#8B6914',
              fontproperties=font_mpl if font_mpl else None)
    ax_m1.text(0.5, 0.50, f'{int(total_coins):,}', fontsize=18, fontweight='bold',
              ha='center', transform=ax_m1.transAxes, color='#FFD700')
    ax_m1.text(0.5, 0.25, 'KK幣', fontsize=11,
              ha='center', transform=ax_m1.transAxes, color='#999999',
              fontproperties=font_mpl if font_mpl else None)
    
    # 指標 2 - 本週新增
    ax_m2 = fig.add_axes([0.29, 0.06, 0.18, 0.28])
    ax_m2.axis('off')
    ax_m2.set_xlim(0, 1)
    ax_m2.set_ylim(0, 1)
    
    rect2 = FancyBboxPatch((0.05, 0.05), 0.9, 0.9, transform=ax_m2.transAxes,
                          facecolor='#E3F2FD', edgecolor='#2196F3', linewidth=4, zorder=1,
                          boxstyle='round,pad=0.05')
    ax_m2.add_patch(rect2)
    
    shadow2 = FancyBboxPatch((0.08, 0.02), 0.84, 0.84, transform=ax_m2.transAxes,
                           facecolor='#1976D2', alpha=0.1, zorder=0,
                           boxstyle='round,pad=0.05')
    ax_m2.add_patch(shadow2)
    
    ax_m2.text(0.5, 0.73, '📈 本週新增', fontsize=12, fontweight='bold',
              ha='center', transform=ax_m2.transAxes, color='#0D47A1',
              fontproperties=font_mpl if font_mpl else None)
    ax_m2.text(0.5, 0.50, f'{int(this_week_total):,}', fontsize=18, fontweight='bold',
              ha='center', transform=ax_m2.transAxes, color='#2196F3')
    ax_m2.text(0.5, 0.25, 'KK幣', fontsize=11,
              ha='center', transform=ax_m2.transAxes, color='#999999',
              fontproperties=font_mpl if font_mpl else None)
    
    # 指標 3 - 參與成員
    ax_m3 = fig.add_axes([0.50, 0.06, 0.18, 0.28])
    ax_m3.axis('off')
    ax_m3.set_xlim(0, 1)
    ax_m3.set_ylim(0, 1)
    
    rect3 = FancyBboxPatch((0.05, 0.05), 0.9, 0.9, transform=ax_m3.transAxes,
                          facecolor='#F1F8E9', edgecolor='#66BB6A', linewidth=4, zorder=1,
                          boxstyle='round,pad=0.05')
    ax_m3.add_patch(rect3)
    
    shadow3 = FancyBboxPatch((0.08, 0.02), 0.84, 0.84, transform=ax_m3.transAxes,
                           facecolor='#388E3C', alpha=0.1, zorder=0,
                           boxstyle='round,pad=0.05')
    ax_m3.add_patch(shadow3)
    
    ax_m3.text(0.5, 0.73, '👥 參與成員', fontsize=12, fontweight='bold',
              ha='center', transform=ax_m3.transAxes, color='#1B5E20',
              fontproperties=font_mpl if font_mpl else None)
    ax_m3.text(0.5, 0.50, f'{member_count}', fontsize=18, fontweight='bold',
              ha='center', transform=ax_m3.transAxes, color='#66BB6A')
    ax_m3.text(0.5, 0.25, '名', fontsize=11,
              ha='center', transform=ax_m3.transAxes, color='#999999',
              fontproperties=font_mpl if font_mpl else None)
    
    # 指標 4 - 平均值
    ax_m4 = fig.add_axes([0.71, 0.06, 0.18, 0.28])
    ax_m4.axis('off')
    ax_m4.set_xlim(0, 1)
    ax_m4.set_ylim(0, 1)
    
    rect4 = FancyBboxPatch((0.05, 0.05), 0.9, 0.9, transform=ax_m4.transAxes,
                          facecolor='#FCE4EC', edgecolor='#EC407A', linewidth=4, zorder=1,
                          boxstyle='round,pad=0.05')
    ax_m4.add_patch(rect4)
    
    shadow4 = FancyBboxPatch((0.08, 0.02), 0.84, 0.84, transform=ax_m4.transAxes,
                           facecolor='#C2185B', alpha=0.1, zorder=0,
                           boxstyle='round,pad=0.05')
    ax_m4.add_patch(shadow4)
    
    ax_m4.text(0.5, 0.73, '📊 平均值', fontsize=12, fontweight='bold',
              ha='center', transform=ax_m4.transAxes, color='#880E4F',
              fontproperties=font_mpl if font_mpl else None)
    ax_m4.text(0.5, 0.50, f'{int(avg_coins):,}', fontsize=18, fontweight='bold',
              ha='center', transform=ax_m4.transAxes, color='#EC407A')
    ax_m4.text(0.5, 0.25, 'KK幣/人', fontsize=10,
              ha='center', transform=ax_m4.transAxes, color='#999999',
              fontproperties=font_mpl if font_mpl else None)
    
    # ✅ 標題 - 加入字型
    if font_mpl:
        plt.suptitle(f'🎯 KK幣社群統計分析面板', fontsize=19, fontweight='bold', y=0.985, color='#1a1a1a', fontproperties=font_mpl)
    else:
        plt.suptitle(f'Analysis Panel', fontsize=19, fontweight='bold', y=0.985, color='#1a1a1a')
    
    # 時間戳 - 加入字型
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.text(0.99, 0.005, f'📆 更新時間：{time_str}', ha='right', fontsize=10, color='#999999',
            fontproperties=font_mpl if font_mpl else None)
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#ffffff')
    buf.seek(0)
    plt.close(fig)
    
    return Image.open(buf).convert("RGBA")


async def setup(bot):
    """載入此模組"""
    print("✅ [KKCoin V2] 排行榜視覺化升級版已載入")
