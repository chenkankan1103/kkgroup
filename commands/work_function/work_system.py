import discord
from discord.ext import commands
import json
import random
import traceback
from datetime import datetime
from .database import get_user, update_user

LEVELS = {
    1: {"title": "車手", "actions": ["收贓款"], "salary": 30},
    2: {"title": "收水手", "actions": ["收贓款", "A錢"], "salary": 50},
    3: {"title": "水房", "actions": ["收贓款", "轉移陣地"], "salary": 80},
    4: {"title": "帳房", "actions": ["收贓款", "算帳", "A錢"], "salary": 120},
    5: {"title": "詐騙機房", "actions": ["詐騙", "挖虛擬幣"], "salary": 200}
}

FIB_DAYS = [2, 3, 5, 8, 13, 21]

def required_days_for_level(level):
    try:
        days = FIB_DAYS[level - 1] if level <= len(FIB_DAYS) else 999
        return days
    except Exception as e:
        traceback.print_exc()
        return 999

def create_work_embed(user, user_obj):
    try:
        level = user['level']
        embed = discord.Embed(title="🎴【詐騙園區 • 勞動記錄卡】", color=0x2f3136)
        embed.add_field(name="👤 使用者", value=user_obj.mention, inline=True)
        embed.add_field(name="📛 職稱", value=LEVELS[level]["title"], inline=True)
        embed.add_field(name="💰 餘額", value=f"{user['kkcoin']} KK幣", inline=True)
        embed.add_field(name="📈 經驗值", value=f"{user['xp']} XP", inline=True)
        embed.add_field(name="🗓️ 連續出勤", value=f"{user['streak']} 天", inline=True)
        
        if level < 5:
            days_needed = required_days_for_level(level + 1)
            streak = user['streak'] if user['streak'] is not None else 0
            remaining_days = days_needed - streak

            if remaining_days > 0:
                embed.add_field(name="🔼 升級進度", value=f"再連續出勤 {remaining_days} 天可升級", inline=False)
            else:
                embed.add_field(name="🔼 升級進度", value="已達成升級條件！下次打卡將升級", inline=False)
        else:
            embed.add_field(name="🔼 升級進度", value="已達最高等級", inline=False)
        
        return embed
    except Exception as e:
        traceback.print_exc()
        return discord.Embed(title="⚠️ 資訊顯示錯誤", description="無法載入完整資訊，請聯絡管理員")

async def process_checkin(user_id, user_obj):
    try:
        user = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        level = user.get('level', 1)
        streak = user.get('streak', 0) + 1
        xp_gain = random.randint(10, 30)
        kkcoin_gain = LEVELS[level]["salary"]

        if level < 5:
            next_level_days = required_days_for_level(level + 1)
            if streak >= next_level_days:
                level += 1
                streak = 0

        update_user(
            user_id,
            last_work_date=today,
            streak=streak,
            level=level,
            xp=user.get('xp', 0) + xp_gain,
            kkcoin=user.get('kkcoin', 0) + kkcoin_gain,
            actions_used='{}'
        )

        updated_user = get_user(user_id)
        embed = create_work_embed(updated_user, user_obj)
        
        return embed, updated_user
    except Exception as e:
        traceback.print_exc()
        return None, None

async def process_work_action(user_id, user_obj, action):
    try:
        user = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        actions_used = json.loads(user.get('actions_used', '{}'))
        if action in actions_used:
            return None, None, "你今天已經執行過這個行動了！"
        
        xp_gain = random.randint(20, 100)
        kk_gain = random.randint(10, LEVELS[user['level']]["salary"] // 2)
        
        actions_used[action] = today
        update_user(
            user_id, 
            xp=user['xp'] + xp_gain, 
            kkcoin=user['kkcoin'] + kk_gain,
            actions_used=json.dumps(actions_used)
        )
        
        updated_user = get_user(user_id)
        embed = create_work_embed(updated_user, user_obj)
        
        outcomes = [
            f"哼哼～騙子真好當，輕輕鬆鬆就{kk_gain}幣入袋～",
            f"今天運氣不錯，竟然騙到{kk_gain}幣！",
            f"良心有點痛...但是{kk_gain}幣實在太香了！",
            f"這次行動不太順利，還好還是拿到了{kk_gain}幣。",
            f"呼～差點被警察抓到，還好順利脫身且帶走{kk_gain}幣！"
        ]
        
        result_text = random.choice(outcomes)
        embed.add_field(name=f"📦 行動結果 - {action}", value=f"{result_text}\n\n獲得：📈 +{xp_gain} XP | 💰 +{kk_gain} KK幣", inline=False)
        
        level_up_message = None
        xp_threshold = 300 * updated_user['level']
        if updated_user['xp'] >= xp_threshold and updated_user['level'] < 5:
            level_up_message = "🎉 你的經驗值已經足夠升級了！繼續連續出勤以提升等級。"
        
        return embed, updated_user, level_up_message
    except Exception as e:
        traceback.print_exc()
        return None, None, "處理失敗，請稍後再試"

async def setup(bot):
    """載入擴展時會被調用的函數 - 這個文件只提供工具函數"""
    print("Work system utilities loaded successfully!")