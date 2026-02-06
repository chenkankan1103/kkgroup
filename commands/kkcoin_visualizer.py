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
    創建豪華排行榜圖像 - 現代遊戲 UI 風格
    
    特色：
    - 前3名視覺強化（頭像放大、邊框、背景）
    - 顏色分級（金/銀/銅 -> 紫 -> 白）
    - 進度條顯示與第1名的差距
    - 排名趨勢箭頭
    - 交替背景分組
    
    Args:
        members_data: [(member, kkcoin), ...]
        limit: 顯示的排名限制 (3, 5, 10, 20)
    """
    members_data = members_data[:limit]
    
    # 計算最高KK幣用於進度條
    max_kkcoin = members_data[0][1] if members_data else 1
    
    DESCRIPTION_HEIGHT = 120
    WIDTH, HEIGHT = 1100, 100 + 80 * len(members_data) + DESCRIPTION_HEIGHT
    MARGIN = 20
    BG_COLOR = (240, 242, 245)  # 淡藍背景
    
    # 加載字體
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, 36)
        FONT_RANK = ImageFont.truetype(FONT_PATH, 28)
        FONT_NAME = ImageFont.truetype(FONT_PATH, 24)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 26)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, 16)
        FONT_DESC = ImageFont.truetype(FONT_PATH, 15)
    except:
        FONT_BIG = FONT_RANK = FONT_NAME = FONT_KKCOIN = FONT_SMALL = FONT_DESC = ImageFont.load_default()
    
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 標題
    title = f"🏆 KK幣排行榜 - 前{limit}名 🏆"
    draw.text((MARGIN, 20), title, fill=(20, 20, 60), font=FONT_BIG)
    
    # 時間戳
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((WIDTH - 240, 30), f"更新時間：{time_str}", fill=(100, 100, 120), font=FONT_SMALL)
    
    # 繪製排名行
    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            rank = i + 1
            y = 85 + i * 80
            
            # ========== 判斷排名等級 ==========
            is_top3 = rank <= 3
            is_top10 = rank <= 10
            
            # ========== 背景顏色（交替） ==========
            if rank % 2 == 0:
                row_bg_color = (235, 238, 245)
            else:
                row_bg_color = (245, 247, 252)
            
            # 每5名加分隔線
            if rank > 1 and rank % 5 == 1:
                draw.line([(MARGIN, y - 5), (WIDTH - MARGIN, y - 5)], fill=(150, 160, 180), width=2)
            
            # 繪製背景
            if is_top3:
                # 前3名特殊背景
                if rank == 1:
                    # 第1名：金黃漸層背景
                    for j in range(75):
                        alpha = int(50 * (1 - j / 75))
                        draw.rectangle(
                            [(MARGIN, y + j), (WIDTH - MARGIN, y + j + 1)],
                            fill=(255, 230, 100, alpha)
                        )
                    border_color = (255, 215, 0)  # 金色邊框
                else:
                    # 第2-3名背景
                    bg_fill = (220, 225, 240) if rank == 2 else (225, 230, 245)
                    draw.rectangle([(MARGIN, y), (WIDTH - MARGIN, y + 75)], fill=bg_fill)
                    border_color = (192, 192, 192) if rank == 2 else (205, 127, 50)  # 銀/銅
            else:
                # 其他排名背景
                draw.rectangle([(MARGIN, y), (WIDTH - MARGIN, y + 75)], fill=row_bg_color)
                border_color = None
            
            # 繪製邊框（前3名）
            if is_top3:
                draw.rectangle(
                    [(MARGIN + 2, y + 2), (WIDTH - MARGIN - 2, y + 73)],
                    outline=border_color,
                    width=3
                )
            else:
                draw.rectangle(
                    [(MARGIN, y), (WIDTH - MARGIN, y + 75)],
                    outline=(180, 190, 210),
                    width=1
                )
            
            # ========== 排名號 ==========
            medal_text = MEDAL_EMOJI.get(rank, f"#{rank}")
            medal_color = (255, 215, 0) if rank == 1 else (192, 192, 192) if rank == 2 else (205, 127, 50) if rank == 3 else (100, 80, 200)
            draw.text((MARGIN + 10, y + 12), medal_text, fill=medal_color, font=FONT_RANK)
            
            # ========== 頭像 ==========
            avatar_size = 68 if is_top3 else 56
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
                            avatar = avatar.resize((avatar_size, avatar_size))
                            
                            # 前3名：圓形頭像 + 彩色光暈
                            if is_top3:
                                # 建立圓形遮罩
                                mask = Image.new('L', (avatar_size, avatar_size), 0)
                                mask_draw = ImageDraw.Draw(mask)
                                mask_draw.ellipse([(0, 0), (avatar_size, avatar_size)], fill=255)
                                avatar.putalpha(mask)
                                
                                # 光暈背景
                                halo_color = (255, 215, 0, 80) if rank == 1 else (192, 192, 192, 60) if rank == 2 else (205, 127, 50, 60)
                                halo = Image.new("RGBA", (avatar_size + 8, avatar_size + 8), halo_color)
                                halo_mask = Image.new('L', (avatar_size + 8, avatar_size + 8), 0)
                                halo_mask_draw = ImageDraw.Draw(halo_mask)
                                halo_mask_draw.ellipse([(0, 0), (avatar_size + 8, avatar_size + 8)], fill=255)
                                halo.putalpha(halo_mask)
                                
                                img.paste(halo, (avatar_x - 4, y + 5 - 4), halo)
                                img.paste(avatar, (avatar_x, y + 5), avatar)
                            else:
                                # 其他排名：方形頭像 + 邊框
                                img.paste(avatar, (avatar_x, y + 10), avatar)
                                draw.rectangle(
                                    [(avatar_x - 2, y + 8), (avatar_x + avatar_size + 2, y + avatar_size + 12)],
                                    outline=(150, 160, 180),
                                    width=2
                                )
            except:
                pass
            
            # ========== 玩家信息區域 ==========
            name_x = avatar_x + avatar_size + 15
            
            # 玩家名稱
            draw.text((name_x, y + 8), member.display_name[:18], fill=(20, 20, 40), font=FONT_NAME)
            
            # ========== KK幣金額 + 顏色分級 ==========
            if rank <= 3:
                kkcoin_color = (255, 215, 0)  # 金色
            elif rank <= 10:
                kkcoin_color = (150, 100, 200)  # 紫色
            else:
                kkcoin_color = (100, 180, 220)  # 青色
            
            kkcoin_text = f"{kkcoin:,} KK幣"
            draw.text((name_x, y + 32), kkcoin_text, fill=kkcoin_color, font=FONT_KKCOIN)
            
            # ========== 進度條（與第1名的相對比例） ==========
            bar_y = y + 55
            bar_width = WIDTH - (name_x + 80)
            bar_height = 8
            
            # 背景條
            draw.rectangle(
                [(name_x, bar_y), (name_x + bar_width, bar_y + bar_height)],
                fill=(200, 210, 230),
                outline=(150, 160, 180),
                width=1
            )
            
            # 進度條
            progress_width = int(bar_width * (kkcoin / max_kkcoin))
            if progress_width > 0:
                # 根據排名選擇進度條顏色
                if rank == 1:
                    bar_color = (255, 215, 0)  # 金色
                elif rank <= 3:
                    bar_color = (220, 160, 100)  # 淺銅色
                elif rank <= 10:
                    bar_color = (150, 100, 200)  # 紫色
                else:
                    bar_color = (100, 200, 220)  # 青色
                
                draw.rectangle(
                    [(name_x, bar_y), (name_x + progress_width, bar_y + bar_height)],
                    fill=bar_color
                )
            
            # ========== 排名趨勢箭頭 (模擬) ==========
            # 這裡可以根據實際趨勢數據修改，目前用隨機
            import random
            trend = random.choice(['▲', '▼', '→'])
            trend_color = (100, 200, 100) if trend == '▲' else (100, 150, 200) if trend == '▼' else (180, 180, 180)
            draw.text((WIDTH - MARGIN - 25, y + 28), trend, fill=trend_color, font=FONT_RANK)
    
    # ========== 說明區域 ==========
    desc_y = 85 + len(members_data) * 80
    draw.line([(MARGIN, desc_y), (WIDTH - MARGIN, desc_y)], fill=(180, 190, 210), width=2)
    
    draw.text((MARGIN + 10, desc_y + 15), "💡 KK幣獲得方法", fill=(30, 30, 80), font=FONT_RANK)
    descriptions = [
        "• 發送訊息：10字+1幣 | 25字+2幣 | 50字+3幣（冷卻30秒）",
        "• 限制：重複訊息、純表情不給幣 | 語音掛機可獲得額外獎勵",
        "• 顏色代碼：金色(前3名) 紫色(4-10名) 青色(11+名)"
    ]
    for i, desc in enumerate(descriptions):
        draw.text((MARGIN + 20, desc_y + 40 + i * 20), desc, fill=(60, 60, 100), font=FONT_DESC)
    
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


async def create_comprehensive_dashboard(members_data, limit=10, total_coins=None, this_week_total=None, last_week_total=None):
    """
    創建綜合仪表板 - 長條圖 + 圓餅圖 + 周統計
    
    Args:
        members_data: [(member, kkcoin), ...] 
        limit: 顯示人數
        total_coins: 總KK幣
        this_week_total: 本週新增
        last_week_total: 上週新增
    """
    if not MATPLOTLIB_AVAILABLE:
        raise RuntimeError("matplotlib 未安裝，無法生成圖表。請執行: pip install matplotlib numpy")
    
    members_data = members_data[:limit]
    names = [m[0].display_name[:12] for m in members_data]
    coins = [m[1] for m in members_data]
    
    # 設置大圖表
    fig = plt.figure(figsize=(16, 10), facecolor='#f5f8fc')
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.25)
    
    # ========== 左上：長條圖 ==========
    ax1 = fig.add_subplot(gs[0, 0])
    colors = []
    for i in range(len(coins)):
        if i < 3:
            colors.append(['#FFD700', '#C0C0C0', '#CD7F32'][i])
        elif i < 5:
            colors.append('#FF6464')
        elif i < 10:
            colors.append('#FFA500')
        else:
            colors.append('#6496FF')
    
    bars = ax1.bar(names, coins, color=colors, edgecolor='black', linewidth=1.5)
    
    # 長條上方顯示數值
    for bar, coin in zip(bars, coins):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(coin):,}',
                ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax1.set_ylabel('KK幣數量', fontsize=11, fontweight='bold')
    ax1.set_title('📊 KK幣排行 - 長條圖', fontsize=13, fontweight='bold')
    ax1.set_ylim(0, max(coins) * 1.2)
    ax1.grid(axis='y', alpha=0.3)
    ax1.tick_params(axis='x', rotation=45)
    
    # ========== 右上：圓餅圖 ==========
    ax2 = fig.add_subplot(gs[0, 1])
    colors_pie = ['#FFD700', '#C0C0C0', '#CD7F32'] + ['#FF6464'] * 2 + ['#FFA500'] * 5 + ['#6496FF'] * (limit - 10)
    colors_pie = colors_pie[:limit]
    
    wedges, texts, autotexts = ax2.pie(
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
    
    ax2.set_title(f'🍰 KK幣分布圖', fontsize=13, fontweight='bold')
    
    # ========== 下方：周統計 + 指標 ==========
    ax3 = fig.add_subplot(gs[1, :])
    ax3.axis('off')
    
    # 計算數據
    if total_coins is None:
        total_coins = sum(coins)
    if this_week_total is None:
        this_week_total = int(total_coins * 0.3)
    if last_week_total is None:
        last_week_total = int(total_coins * 0.25)
    
    member_count = len(members_data)
    
    # 計算增長率
    if last_week_total > 0:
        growth_rate = ((this_week_total - last_week_total) / last_week_total) * 100
    else:
        growth_rate = 0
    
    # 左邊：本週vs上週對比
    ax_compare = fig.add_axes([0.08, 0.08, 0.28, 0.25])
    weeks = ['上週', '本週']
    totals = [last_week_total, this_week_total]
    colors_comp = ['#FF6464', '#6496FF']
    bars = ax_compare.bar(weeks, totals, color=colors_comp, edgecolor='black', linewidth=1.5, width=0.5)
    
    for bar, total in zip(bars, totals):
        height = bar.get_height()
        ax_compare.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(total):,}',
                       ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    growth_text = f"增長 +{growth_rate:.1f}%" if growth_rate > 0 else f"下降 {growth_rate:.1f}%"
    growth_color = '#6BBF59' if growth_rate >= 0 else '#FF6464'
    
    ax_compare.text(0.5, max(totals) * 0.9, growth_text,
                   ha='center', fontsize=11, fontweight='bold', color=growth_color,
                   transform=ax_compare.transData,
                   bbox=dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor=growth_color, linewidth=2))
    
    ax_compare.set_ylabel('KK幣數量', fontsize=10, fontweight='bold')
    ax_compare.set_title('📈 本週對比', fontsize=12, fontweight='bold')
    ax_compare.set_ylim(0, max(totals) * 1.3)
    ax_compare.grid(axis='y', alpha=0.3)
    
    # 中間：指標卡片 1 - 金庫總額
    ax_metrics1 = fig.add_axes([0.40, 0.08, 0.12, 0.25])
    ax_metrics1.axis('off')
    
    # 背景
    rect1 = plt.Rectangle((0, 0), 1, 1, transform=ax_metrics1.transAxes,
                          facecolor='#fff9e6', edgecolor='#FFD700', linewidth=2, zorder=-1)
    ax_metrics1.add_patch(rect1)
    
    ax_metrics1.text(0.5, 0.72, '金庫總額', fontsize=10, fontweight='bold',
                    ha='center', transform=ax_metrics1.transAxes, color='#666')
    ax_metrics1.text(0.5, 0.50, f'{int(total_coins):,}', fontsize=14, fontweight='bold',
                    ha='center', transform=ax_metrics1.transAxes, color='#FFD700')
    ax_metrics1.text(0.5, 0.28, 'KK幣', fontsize=9,
                    ha='center', transform=ax_metrics1.transAxes, color='#888')
    
    # 指標卡片 2 - 本週新增
    ax_metrics2 = fig.add_axes([0.58, 0.08, 0.12, 0.25])
    ax_metrics2.axis('off')
    
    rect2 = plt.Rectangle((0, 0), 1, 1, transform=ax_metrics2.transAxes,
                          facecolor='#e6f2ff', edgecolor='#6496FF', linewidth=2, zorder=-1)
    ax_metrics2.add_patch(rect2)
    
    ax_metrics2.text(0.5, 0.72, '本週新增', fontsize=10, fontweight='bold',
                    ha='center', transform=ax_metrics2.transAxes, color='#666')
    ax_metrics2.text(0.5, 0.50, f'{int(this_week_total):,}', fontsize=14, fontweight='bold',
                    ha='center', transform=ax_metrics2.transAxes, color='#6496FF')
    ax_metrics2.text(0.5, 0.28, 'KK幣', fontsize=9,
                    ha='center', transform=ax_metrics2.transAxes, color='#888')
    
    # 指標卡片 3 - 參與成員
    ax_metrics3 = fig.add_axes([0.76, 0.08, 0.12, 0.25])
    ax_metrics3.axis('off')
    
    rect3 = plt.Rectangle((0, 0), 1, 1, transform=ax_metrics3.transAxes,
                          facecolor='#e6ffe6', edgecolor='#6BBF59', linewidth=2, zorder=-1)
    ax_metrics3.add_patch(rect3)
    
    ax_metrics3.text(0.5, 0.72, '參與成員', fontsize=10, fontweight='bold',
                    ha='center', transform=ax_metrics3.transAxes, color='#666')
    ax_metrics3.text(0.5, 0.50, f'{member_count}', fontsize=14, fontweight='bold',
                    ha='center', transform=ax_metrics3.transAxes, color='#6BBF59')
    ax_metrics3.text(0.5, 0.28, '名', fontsize=9,
                    ha='center', transform=ax_metrics3.transAxes, color='#888')
    
    plt.suptitle('📊 KK幣綜合仪表板', fontsize=18, fontweight='bold', y=0.98)
    
    # 時間戳
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.text(0.99, 0.01, f'更新時間：{time_str}', ha='right', fontsize=9, color='#999')
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#f5f8fc')
    buf.seek(0)
    plt.close(fig)
    
    return Image.open(buf).convert("RGBA")


async def setup(bot):
    """載入此模組"""
    print("✅ [KKCoin] 排行榜視覺化模組已載入")
