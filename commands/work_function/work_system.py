import discord
from discord.ext import commands
import json
import random
import traceback
import os
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from .database import get_user, update_user

# 台灣時區（UTC+8）
TAIWAN_TZ = timezone(timedelta(hours=8))

def get_taiwan_time():
    """獲取台灣時間"""
    return datetime.now(TAIWAN_TZ)

# AI API 設定
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_API_URL = os.getenv("AI_API_URL", "")
AI_API_MODEL = os.getenv("AI_API_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# 等級配置 - Lv.0 至 Lv.6
LEVELS = {
    0: {
        "title": "待宰豬仔",
        "actions": [
            {"name": "領錢", "risk": 0.1, "base_reward": 50, "success_rate": 0.95, "xp": 10}
        ],
        "salary": 25,
        "days_required": 0,
        "xp_required": 0,
        "role_id": 0,
        "salary_boost": 1.0,
        "xp_boost": 1.0,
        "description": "起始身份。"
    },
    1: {
        "title": "基層狗推(車手)",
        "actions": [
            {"name": "領錢", "risk": 0.1, "base_reward": 100, "success_rate": 0.9, "xp": 20}
        ],
        "salary": 150,
        "days_required": 7,
        "xp_required": 500,
        "role_id": int(os.getenv("ROLE_CAR", 0)),
        "salary_boost": 1.0,
        "xp_boost": 1.0,
        "description": "基層執行人員。"
    },
    2: {
        "title": "一線聊手",
        "actions": [
            {"name": "領錢", "risk": 0.1, "base_reward": 100, "success_rate": 0.9, "xp": 20},
            {"name": "詐騙", "risk": 0.2, "base_reward": 200, "success_rate": 0.85, "xp": 35},
            {"name": "談判", "risk": 0.3, "base_reward": 300, "success_rate": 0.75, "xp": 50}
        ],
        "salary": 275,
        "days_required": 14,
        "xp_required": 1500,
        "role_id": int(os.getenv("ROLE_CHAT_WORKER", 0)),
        "salary_boost": 1.0,
        "xp_boost": 1.0,
        "description": "資深文案撰寫。"
    },
    3: {
        "title": "收水/車頭",
        "actions": [
            {"name": "領錢", "risk": 0.1, "base_reward": 100, "success_rate": 0.9, "xp": 20},
            {"name": "收水", "risk": 0.2, "base_reward": 200, "success_rate": 0.85, "xp": 35},
            {"name": "轉移陣地", "risk": 0.25, "base_reward": 400, "success_rate": 0.8, "xp": 60},
            {"name": "洗錢", "risk": 0.4, "base_reward": 600, "success_rate": 0.7, "xp": 80}
        ],
        "salary": 450,
        "days_required": 28,
        "xp_required": 4000,
        "role_id": int(os.getenv("ROLE_TEAM_LEAD", 0)),
        "salary_boost": 1.0,
        "xp_boost": 1.0,
        "description": "負責調度車手提款。"
    },
    4: {
        "title": "水房會計",
        "actions": [
            {"name": "領錢", "risk": 0.1, "base_reward": 100, "success_rate": 0.9, "xp": 20},
            {"name": "算帳", "risk": 0.2, "base_reward": 350, "success_rate": 0.85, "xp": 45},
            {"name": "偷A錢", "risk": 0.3, "base_reward": 300, "success_rate": 0.75, "xp": 50},
            {"name": "做假帳", "risk": 0.5, "base_reward": 800, "success_rate": 0.65, "xp": 100},
            {"name": "挪用公款", "risk": 0.6, "base_reward": 1000, "success_rate": 0.6, "xp": 120}
        ],
        "salary": 750,
        "days_required": 42,
        "xp_required": 8500,
        "role_id": int(os.getenv("ROLE_ACCOUNTING", 0)),
        "salary_boost": 1.1,
        "xp_boost": 1.0,
        "description": "掌管金流。特權：薪資加成 +10%。"
    },
    5: {
        "title": "機房主任",
        "actions": [
            {"name": "詐騙", "risk": 0.35, "base_reward": 700, "success_rate": 0.75, "xp": 90},
            {"name": "挖虛擬幣", "risk": 0.15, "base_reward": 400, "success_rate": 0.88, "xp": 55},
            {"name": "培訓新人", "risk": 0.1, "base_reward": 300, "success_rate": 0.92, "xp": 40},
            {"name": "開發話術", "risk": 0.25, "base_reward": 500, "success_rate": 0.82, "xp": 70},
            {"name": "大單詐騙", "risk": 0.7, "base_reward": 1500, "success_rate": 0.5, "xp": 150}
        ],
        "salary": 1250,
        "days_required": 60,
        "xp_required": 18000,
        "role_id": int(os.getenv("ROLE_SCAM_ROOM", 0)),
        "salary_boost": 1.0,
        "xp_boost": 1.2,
        "description": "帶領整個分隊。特權：每日經驗 +20%。"
    },
    6: {
        "title": "小區代理人",
        "actions": [
            {"name": "詐騙", "risk": 0.35, "base_reward": 700, "success_rate": 0.75, "xp": 90},
            {"name": "挖虛擬幣", "risk": 0.15, "base_reward": 400, "success_rate": 0.88, "xp": 55},
            {"name": "培訓新人", "risk": 0.1, "base_reward": 300, "success_rate": 0.92, "xp": 40},
            {"name": "開發話術", "risk": 0.25, "base_reward": 500, "success_rate": 0.82, "xp": 70},
            {"name": "大單詐騙", "risk": 0.7, "base_reward": 1500, "success_rate": 0.5, "xp": 150}
        ],
        "salary": 2100,
        "days_required": 90,
        "xp_required": 40000,
        "role_id": int(os.getenv("ROLE_REGIONAL_DIRECTOR", 0)),
        "salary_boost": 1.0,
        "xp_boost": 1.0,
        "description": "半管理層，可擁有自訂職稱。特權：解鎖高風險任務。"
    }
}

# 升級所需天數 (Lv.0 不升級，Lv.1-6 分別需要 7, 14, 28, 42, 60, 90 天)
REQUIRED_DAYS = [0, 7, 14, 28, 42, 60, 90]

def required_days_for_level(level):
    """返回升級所需的連續出勤天數"""
    try:
        if level < 0 or level >= len(REQUIRED_DAYS):
            return 999
        return REQUIRED_DAYS[level]
    except Exception as e:
        traceback.print_exc()
        return 999

def check_level_up(user):
    """檢查是否滿足升級條件（連續出勤 + 經驗值）"""
    level = user.get('level', 0)
    if level >= 6:
        return False, None
    
    streak = user.get('streak', 0)
    xp = user.get('xp', 0)
    
    next_level = level + 1
    required_days = LEVELS[next_level]["days_required"]
    required_xp = LEVELS[next_level]["xp_required"]
    
    days_met = streak >= required_days
    xp_met = xp >= required_xp
    
    if days_met and xp_met:
        return True, {"days": required_days, "xp": required_xp}
    else:
        return False, {
            "days_met": days_met,
            "xp_met": xp_met,
            "required_days": required_days,
            "required_xp": required_xp,
            "current_days": streak,
            "current_xp": xp
        }

def create_progress_bar(current, total, length=10):
    """創建進度條"""
    filled = int((current / total) * length) if total > 0 else 0
    filled = min(filled, length)
    bar = "█" * filled + "░" * (length - filled)
    percentage = int((current / total) * 100) if total > 0 else 0
    return f"{bar} {percentage}%"

def create_work_embed(user, user_obj):
    """創建工作記錄卡 Embed"""
    try:
        level = user['level']
        level_info = LEVELS[level]
        
        colors = {0: 0x7f8c8d, 1: 0x95a5a6, 2: 0x3498db, 3: 0x9b59b6, 4: 0xe74c3c, 5: 0xf39c12, 6: 0xdaa520}
        embed = discord.Embed(
            title="🎴【詐騙園區 • 勞動記錄卡】", 
            color=colors.get(level, 0x2f3136)
        )
        
        embed.add_field(
            name="👤 員工資訊", 
            value=(
                f"**姓名**：{user_obj.mention}\n"
                f"**職稱**：{level_info['title']}\n"
                f"**等級**：Lv.{level} ⭐"
            ),
            inline=True
        )
        
        embed.add_field(
            name="💰 財務狀況", 
            value=(
                f"**餘額**：{user['kkcoin']:,} KK幣\n"
                f"**日薪**：{level_info['salary']:,} KK幣\n"
                f"**經驗**：{user['xp']:,} XP"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📊 工作狀態", 
            value=(
                f"**連勤**：{user['streak']} 天 🔥\n"
                f"**行動**：{len(level_info['actions'])} 種\n"
                f"**狀態**：✅ 在職中"
            ),
            inline=True
        )
        
        if level < 6:
            can_level_up, info = check_level_up(user)
            
            if can_level_up:
                embed.add_field(
                    name="🎉 升級通知", 
                    value=(
                        "```diff\n"
                        "+ 恭喜！已達成所有升級條件！\n"
                        "+ 下次打卡將自動升級\n"
                        "```"
                    ),
                    inline=False
                )
            else:
                days_progress = create_progress_bar(info['current_days'], info['required_days'])
                xp_progress = create_progress_bar(info['current_xp'], info['required_xp'])
                
                next_level_info = LEVELS[level + 1]
                salary_increase = next_level_info['salary'] - level_info['salary']
                
                progress_text = (
                    f"**下一階段：{next_level_info['title']}** (Lv.{level + 1})\n\n"
                    f"📅 **連續出勤**：{info['current_days']}/{info['required_days']} 天\n"
                    f"{days_progress}\n\n"
                    f"📈 **經驗累積**：{info['current_xp']:,}/{info['required_xp']:,} XP\n"
                    f"{xp_progress}\n\n"
                    f"💎 **升級獎勵預覽**：\n"
                    f"• 日薪提升 +{salary_increase:,} KK幣\n"
                    f"• 升級紅包 +{(level + 1) * 300:,} KK幣\n"
                    f"• 解鎖新行動：{len(next_level_info['actions'])} 種"
                )
                
                embed.add_field(name="🔼 升級進度", value=progress_text, inline=False)
        else:
            embed.add_field(
                name="👑 最高等級 - 小區代理人", 
                value=(
                    "```yaml\n"
                    "恭喜！你已達到園區最高層級！\n"
                    "享受最高薪資和全部管理權限！\n"
                    "```"
                ),
                inline=False
            )
        
        # 顯示可用行動及其資訊
        actions_text = ""
        for action in level_info['actions']:
            risk_emoji = "🟢" if action['risk'] <= 0.2 else "🟡" if action['risk'] <= 0.4 else "🔴"
            actions_text += f"{risk_emoji} **{action['name']}** - 成功率 {int(action['success_rate']*100)}% | 最高 {action['base_reward']} 幣\n"
        
        embed.add_field(
            name="🎯 可執行行動",
            value=actions_text,
            inline=False
        )
        
        embed.set_footer(text=f"{level_info['description']} | 風險越高，報酬越大！")
        embed.timestamp = datetime.utcnow()
        
        return embed
    except Exception as e:
        traceback.print_exc()
        return discord.Embed(title="⚠️ 資訊顯示錯誤", description="無法載入完整資訊，請聯絡管理員")

def create_level_up_embed(user_obj, old_level, new_level, bonus_coins):
    """創建升級特效 Embed"""
    old_info = LEVELS[old_level]
    new_info = LEVELS[new_level]
    
    embed = discord.Embed(
        title="",
        description=(
            "# 🎊 ═══════════════════════════ 🎊\n"
            "# 　　　　✨ 恭喜升級！✨\n"
            "# 🎊 ═══════════════════════════ 🎊"
        ),
        color=0xFFD700
    )
    
    embed.add_field(
        name="📊 升級資訊",
        value=(
            f"👤 **員工**：{user_obj.mention}\n"
            f"📛 **職稱**：~~{old_info['title']}~~ ➜ **{new_info['title']}**\n"
            f"⭐ **等級**：Lv.{old_level} ➜ **Lv.{new_level}**\n"
            f"💼 **新薪資**：{new_info['salary']:,} KK幣/天 📈"
        ),
        inline=False
    )
    
    salary_diff = new_info['salary'] - old_info['salary']
    embed.add_field(
        name="🎁 升級獎勵大禮包",
        value=(
            f"```diff\n"
            f"+ 升級紅包：+{bonus_coins:,} KK幣\n"
            f"+ 日薪提升：+{salary_diff:,} KK幣/天\n"
            f"+ 解鎖行動：{len(new_info['actions'])} 種\n"
            f"+ 專屬身分組：@{new_info['title']}\n"
            f"```"
        ),
        inline=False
    )
    
    # 新解鎖的行動
    old_action_names = {a['name'] for a in old_info['actions']}
    new_actions = [a for a in new_info['actions'] if a['name'] not in old_action_names]
    
    if new_actions:
        new_actions_text = ""
        for action in new_actions:
            new_actions_text += f"• **{action['name']}** (成功率 {int(action['success_rate']*100)}%, 最高 {action['base_reward']} 幣)\n"
        
        embed.add_field(
            name="🆕 新解鎖行動",
            value=new_actions_text,
            inline=False
        )
    
    level_messages = {
        1: "🆙 你已晉升至園區正式員工！開始你的詐騙之旅吧！",
        2: "🎉 你已經不再是菜鳥了！開始接觸資金流動！",
        3: "💪 你的詐騙技能越來越熟練了！解鎖洗錢功能！",
        4: "🏆 你已經是園區的高階管理了！掌握金流命脈！",
        5: "👑 登峰造極！你已成為詐騙機房的頂尖專家！",
        6: "💎 恭喜！你已成為園區代理人，擁有最高決策權！"
    }
    
    embed.add_field(
        name="💬 園區主管的話",
        value=f"*「{level_messages.get(new_level, '繼續努力，更高的職位在等你！')}」*",
        inline=False
    )
    
    embed.set_footer(text="🎴 KK園區 | 持續出勤，再創高峰！")
    embed.timestamp = datetime.utcnow()
    
    return embed

async def assign_role(guild, user, new_level):
    """分配對應等級的身分組，並移除其他等級的身分組"""
    try:
        member = guild.get_member(user.id)
        if not member:
            print(f"⚠️ 找不到成員：{user.id}")
            return False
        
        all_level_roles = [LEVELS[lvl]["role_id"] for lvl in LEVELS.keys() if LEVELS[lvl]["role_id"]]
        
        roles_to_remove = []
        for role in member.roles:
            if role.id in all_level_roles:
                roles_to_remove.append(role)
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="升級：移除舊等級身分組")
            print(f"✅ 已移除 {len(roles_to_remove)} 個舊身分組")
        
        new_role_id = LEVELS[new_level]["role_id"]
        if new_role_id:
            new_role = guild.get_role(new_role_id)
            if new_role:
                await member.add_roles(new_role, reason=f"升級至 {LEVELS[new_level]['title']}")
                print(f"✅ 已授予身分組：{new_role.name}")
                return True
            else:
                print(f"⚠️ 找不到身分組ID：{new_role_id}")
        else:
            print(f"⚠️ 等級 {new_level} 未設定身分組ID")
        
        return False
    except discord.Forbidden:
        print("❌ 機器人沒有權限管理身分組")
        return False
    except Exception as e:
        print(f"❌ 分配身分組時發生錯誤：{e}")
        traceback.print_exc()
        return False

async def process_checkin(user_id, user_obj, guild):
    """處理打卡邏輯 - 加入 AI 生成的每日情境"""
    try:
        user = get_user(user_id)
        
        # 檢查用戶是否成功取得
        if not user:
            print(f"❌ [process_checkin] 無法找到或建立用戶: {user_id}")
            return None, None, None, None
        
        today = get_taiwan_time().strftime("%Y-%m-%d")
        
        level = user.get('level', 1)
        current_xp = user.get('xp', 0)
        current_kkcoin = user.get('kkcoin', 0)
        streak = user.get('streak', 0) + 1
        
        print(f"  📊 初始數據 - Lv.{level}, XP: {current_xp}, 金幣: {current_kkcoin}, 連勤: {streak-1}")
        
        # 隨機經驗值 + 經驗倍數加成
        xp_gain = random.randint(20, 60)
        xp_boost = LEVELS[level].get("xp_boost", 1.0)
        xp_gain = int(xp_gain * xp_boost)
        print(f"  📈 XP 獲得: {xp_gain} (基數: {xp_gain//int(xp_boost) if xp_boost else xp_gain}, 倍率: {xp_boost})")
        
        # 浮動薪資 (0-100%) + 薪資倍數加成
        base_salary = LEVELS[level]["salary"]
        salary_multiplier = random.uniform(0, 1)
        salary_boost = LEVELS[level].get("salary_boost", 1.0)
        kkcoin_gain = int(base_salary * salary_multiplier * salary_boost)
        print(f"  💰 薪資計算: {int(salary_multiplier*100)}% × {base_salary} × {salary_boost} = {kkcoin_gain} KK幣")

        leveled_up = False
        bonus_coins = 0
        old_level = level
        original_streak = streak  # 保存升級前的連勤值
        
        temp_user = user.copy()
        temp_user['streak'] = streak
        temp_user['xp'] = user.get('xp', 0) + xp_gain
        
        can_level_up, next_threshold = check_level_up(temp_user)
        
        if can_level_up and level < 6:
            level += 1
            streak = 0
            bonus_coins = 300 * level
            kkcoin_gain += bonus_coins
            leveled_up = True
            print(f"  🎊 等級提升! Lv.{old_level} → Lv.{level}, 獲得升級獎勵: {bonus_coins} KK幣")
            
            role_assigned = await assign_role(guild, user_obj, level)
            if role_assigned:
                print(f"  ✅ 身分組已分配: {user_obj.name} → Lv.{level}")
        else:
            progress = temp_user.get('xp', 0)
            print(f"  📊 升級進度: {progress} / {next_threshold if next_threshold else '計算中'} XP")

        print(f"  💾 保存資料...")
        success = update_user(
            user_id,
            last_work_date=today,
            streak=streak,
            level=level,
            xp=temp_user['xp'],
            kkcoin=user.get('kkcoin', 0) + kkcoin_gain,
            actions_used='{}'
        )
        if not success:
            print(f"  ❌ 保存用戶資料失敗")
            return None, None, None, None
        print(f"  ✓ 資料已保存")

        updated_user = get_user(user_id)
        if not updated_user:
            print(f"  ❌ 獲取更新後的用戶資料失敗")
            return None, None, None, None
        print(f"  ✓ 更新後資料: Lv.{updated_user['level']}, XP: {updated_user['xp']}, 金幣: {updated_user['kkcoin']}")
        
        # 使用 AI 生成每日情境描述（升級時使用升級前的 streak）
        daily_story = await generate_daily_checkin_story(
            level_title=LEVELS[updated_user['level']]['title'],
            salary_percent=salary_multiplier,
            streak=original_streak if leveled_up else streak,  # 升級時用升級前的值
            user_name=user_obj.display_name
        )
        
        if leveled_up:
            print(f"  🎨 生成升級 Embed...")
            level_up_embed = create_level_up_embed(user_obj, old_level, level, bonus_coins)
            work_embed = create_work_embed(updated_user, user_obj)
            print(f"  ✅ [process_checkin] 打卡程序完成 (升級 Lv.{old_level}→{level})")
            return (level_up_embed, work_embed), updated_user, salary_multiplier, daily_story
        else:
            print(f"  🎨 生成打卡 Embed...")
            embed = create_work_embed(updated_user, user_obj)
            print(f"  ✅ [process_checkin] 打卡程序完成")
            return (embed,), updated_user, salary_multiplier, daily_story
            
    except Exception as e:
        print(f"  ❌ [process_checkin] 發生例外: {e}")
        traceback.print_exc()
        return None, None, None, None

async def generate_daily_checkin_story(level_title, salary_percent, streak, user_name):
    """使用 AI 生成每日打卡情境描述"""
    try:
        if not AI_API_KEY or not AI_API_URL:
            return get_fallback_checkin_story(salary_percent)
        
        # 根據薪資比例判斷今日狀況
        if salary_percent >= 0.8:
            situation = "非常順利，大豐收"
        elif salary_percent >= 0.5:
            situation = "普通，正常營運"
        else:
            situation = "不太順利，有些波折"
        
        prompt = f"""你是詐騙園區的故事敘述者。請描述今日打卡情境：

角色職位：{level_title}
今日狀況：{situation}（薪資達成率 {int(salary_percent*100)}%）
連續出勤：{streak} 天

請生成一段 1-2 句的簡短情境描述，說明今天為什麼會有這樣的收入。要求：
1. 使用第二人稱「你」
2. 符合詐騙園區的風格
3. 反映今日業績的好壞
4. 簡潔有力，不超過 50 字
5. 不要提到具體金額

直接輸出情境描述，不需要任何前綴。"""

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": AI_API_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一個創作詐騙園區日常情境的作家。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 150
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(AI_API_URL, headers=headers, json=data, timeout=8) as response:
                if response.status == 200:
                    result = await response.json()
                    story = result['choices'][0]['message']['content'].strip()
                    return story.strip('"').strip("'").strip()
                else:
                    return get_fallback_checkin_story(salary_percent)
                    
    except Exception as e:
        print(f"⚠️ AI 生成打卡故事失敗: {e}")
        return get_fallback_checkin_story(salary_percent)

def get_fallback_checkin_story(salary_percent):
    """打卡故事的備用文本"""
    if salary_percent >= 0.8:
        stories = [
            "今天受害者特別好騙，業績爆棚！",
            "老闆心情好，發了不少獎金！",
            "這批客戶很有錢，收穫滿滿！"
        ]
    elif salary_percent >= 0.5:
        stories = [
            "今天營運正常，平穩度過。",
            "業績普通，維持基本收入。",
            "沒什麼特別的，日常工作而已。"
        ]
    else:
        stories = [
            "今天運氣不好，很多單都失敗了。",
            "警方巡邏加強，大家都很緊張。",
            "受害者警覺性提高，不好騙了。"
        ]
    return random.choice(stories)

# 工作行動故事生成器
ACTION_STORIES = {
    "領錢": {
        "success": [
            "你戴上口罩和帽子，在ATM前快速操作，成功領出 {reward} KK幣。監視器？那是什麼？",
            "人頭帳戶的密碼正確，你迅速提款 {reward} KK幣後轉身離開，沒有留下任何痕跡。",
            "銀行很安靜，你順利領出 {reward} KK幣。警衛只是瞄了你一眼，什麼也沒說。"
        ],
        "fail": [
            "ATM突然顯示「卡片被吞」！你嚇得落荒而逃，一毛錢都沒拿到...",
            "銀行警衛走過來查看，你緊張地假裝打電話，最後放棄領錢逃離現場。",
            "提款機故障，你的臉已經被監視器拍下。上頭說這次算了，但要小心。"
        ]
    },
    "收水": {
        "success": [
            "車手準時送達，你清點完 {reward} KK幣後迅速裝袋，整個過程不到3分鐘。",
            "在便利商店停車場，你假裝買東西，順手接過車手的背包。裡面有 {reward} KK幣。",
            "車手有點緊張，但交易順利。{reward} KK幣到手，你拍拍他肩膀：「做得好。」"
        ],
        "fail": [
            "車手遲到了一小時，等到的時候發現他已經被條子盯上了。你立刻撤退，兩手空空。",
            "收水地點附近有巡邏車，你不敢現身，只能眼睜睜看著車手離開。",
            "車手說帳戶被凍結了，根本領不出錢。這趟白跑了。"
        ]
    },
    "偷A錢": {
        "success": [
            "趁主管不注意，你在系統上動了手腳。{reward} KK幣神不知鬼不覺地進了你的口袋。",
            "對帳的時候，你「不小心」把 {reward} KK幣分配到自己名下。沒人發現。",
            "帳目有誤差？你裝作很驚訝，然後默默把 {reward} KK幣收進口袋。"
        ],
        "fail": [
            "主管突然檢查帳本！你來不及掩飾，被罵了一頓。錢是別想了。",
            "系統日誌記錄太詳細，你不敢亂動。這次放棄了。",
            "財務突然說要交叉比對，你嚇得把錢退回去了。"
        ]
    },
    "轉移陣地": {
        "success": [
            "你帶著團隊在深夜撤離，所有設備在 2 小時內搬到新據點。賺了 {reward} KK幣搬運費。",
            "警方消息說會來檢查，你提前 6 小時完成轉移。老闆很滿意，給了 {reward} KK幣。",
            "新地點在偏遠工業區，網路訊號不錯。轉移順利，收入 {reward} KK幣。"
        ],
        "fail": [
            "搬運車在半路拋錨，設備來不及移走。老闆很不爽，你分文未得。",
            "新據點被舉報了，還沒開工就要再搬一次。白忙一場。",
            "搬運工太多嘴，引起鄰居懷疑。這次轉移失敗。"
        ]
    },
    "洗錢": {
        "success": [
            "透過虛擬貨幣交易所來回轉帳，{reward} KK幣洗得乾乾淨淨，完全查不到來源。",
            "用人頭公司開立發票，把黑錢洗成合法收入。淨賺 {reward} KK幣。",
            "分散到 20 個帳戶小額轉帳，最後匯總到安全帳戶。{reward} KK幣到手。"
        ],
        "fail": [
            "銀行突然加強審查，你的轉帳被凍結了。這批錢暫時動不了。",
            "虛擬貨幣價格暴跌，洗到一半就賠了。血本無歸。",
            "人頭帳戶被警方監控了，你趕緊中止操作。錢沒洗成。"
        ]
    },
    "算帳": {
        "success": [
            "你精確計算每個人的分潤，順便「算錯」了一些數字。{reward} KK幣進了你的口袋。",
            "帳本平衡，所有人都拿到錢，但你的那份特別多。{reward} KK幣。",
            "上頭說你算得快又準，額外給了 {reward} KK幣獎金。"
        ],
        "fail": [
            "有人質疑帳目，你被要求重新計算。這次不敢動手腳了。",
            "算錯了，反而少了一筆錢。你得自己補上。",
            "老闆親自核對帳目，你根本沒機會做手腳。"
        ]
    },
    "做假帳": {
        "success": [
            "你偽造了完美的進出帳記錄，稽查員看都沒看就通過了。{reward} KK幣到手。",
            "假發票、假合約、假收據一應俱全。這套假帳連會計師都挑不出毛病。賺了 {reward} KK幣。",
            "用專業軟體製作帳本，數字完美對齊。{reward} KK幣輕鬆入袋。"
        ],
        "fail": [
            "稽查員經驗老道，一眼就看出破綻。你緊張得滿頭大汗。",
            "印表機卡紙，假帳來不及印出來。這次失敗了。",
            "有人檢舉帳目有問題，你趕緊銷毀證據。錢是沒了。"
        ]
    },
    "挪用公款": {
        "success": [
            "利用職權，你「借用」了公司的 {reward} KK幣。反正月底就能補回來... 吧？",
            "老闆出國，你趁機把 {reward} KK幣轉到私人帳戶。只要下週還回去就沒事。",
            "帳上有一筆 {reward} KK幣的「預付款」，其實是你挪用的。完美。"
        ],
        "fail": [
            "財務突擊檢查，你來不及把錢轉回去。這下慘了。",
            "老闆提前回國，要看帳本。你嚇得趕緊從私房錢補上。",
            "銀行通知異常交易，你不敢繼續操作了。"
        ]
    },
    "詐騙": {
        "success": [
            "目標是退休老人，你用「投資」話術騙到 {reward} KK幣。他完全相信你。",
            "假冒檢察官打電話，對方嚇得立刻匯款 {reward} KK幣到「安全帳戶」。",
            "網路交友詐騙成功！對方為了「愛情」送你 {reward} KK幣。"
        ],
        "fail": [
            "對方識破你的話術，還要報警。你趕緊掛電話。",
            "目標太窮了，根本沒錢可以騙。白費力氣。",
            "對方是臥底警察！你嚇得立刻切斷聯繫。一毛錢都沒騙到。"
        ]
    },
    "挖虛擬幣": {
        "success": [
            "礦機全速運轉 24 小時，電費老闆出，你賺 {reward} KK幣。",
            "今天幣價上漲，挖到的幣立刻賣出，淨賺 {reward} KK幣。",
            "用公司電腦偷偷挖礦，效能不錯。{reward} KK幣入帳。"
        ],
        "fail": [
            "礦機過熱當機了，這個月白挖了。",
            "幣價暴跌，挖到的幣根本不值錢。虧本。",
            "老闆發現電費異常，你趕緊關掉礦機。沒賺到錢。"
        ]
    },
    "培訓新人": {
        "success": [
            "你教新人如何使用話術，他們學得很快。培訓獎金 {reward} KK幣到手。",
            "新人培訓完成，第一個月業績不錯。你抽成 {reward} KK幣。",
            "你分享了實戰經驗，新人們聽得津津有味。收入 {reward} KK幣。"
        ],
        "fail": [
            "新人太笨了，怎麼教都不會。浪費時間。",
            "培訓到一半，新人說要離職。白教了。",
            "新人第一次詐騙就被抓，連累你被罵。沒錢還被扣分。"
        ]
    },
    "開發話術": {
        "success": [
            "你設計的新話術效果拔群，成功率提升 20%。獎金 {reward} KK幣。",
            "模仿最新詐騙手法，開發出本土化版本。研發費 {reward} KK幣。",
            "你的話術讓其他機房也想買，光授權費就賺了 {reward} KK幣。"
        ],
        "fail": [
            "新話術太複雜，大家都不會用。開發失敗。",
            "話術被警方公布了，完全沒用。白費功夫。",
            "測試的時候被識破，這套話術不能用。"
        ]
    },
    "大單詐騙": {
        "success": [
            "鎖定企業老闆，假冒供應商詐騙成功！{reward} KK幣入帳，這是本月最大單！",
            "商務郵件詐騙得手，對方會計毫無懷疑地匯了 {reward} KK幣。",
            "假投資案談成了，富豪投入 {reward} KK幣。這波賺翻了！"
        ],
        "fail": [
            "目標起疑心了，要求面對面交易。你不敢去，單子吹了。",
            "對方會計很謹慎，打電話確認。你的假身分被識破了。",
            "談到一半，對方找律師審查合約。你趕緊收手，免得被告。"
        ]
    }
}

async def generate_daily_checkin_story(level_title, salary_percent, streak, user_name):
    """生成每日打卡故事"""
    try:
        if not AI_API_KEY or not AI_API_URL:
            # 如果沒有 AI API，使用簡單的故事
            salary_desc = "大豐收" if salary_percent > 0.8 else "普通" if salary_percent > 0.5 else "不太順利"
            return f"今天的工作表現{salary_desc}，連續出勤已達 {streak} 天。"
        
        prompt = f"""你是一個詐騙園區的日報編輯。請為員工 {user_name} 生成一段簡短的打卡日誌。

員工資訊：
- 職稱：{level_title}
- 今日薪資表現：{int(salary_percent * 100)}% 
- 連續出勤：{streak} 天

請生成一段 1-2 句的簡短描述，描述這位員工今天的工作表現和心情。要求：
1. 使用第一人稱「我」來描述員工的視角
2. 貼合詐騙園區的黑色幽默風格
3. 提到薪資表現和連續出勤
4. 保持簡潔，不超過 60 字
5. 不要有任何多餘的格式

直接輸出故事內容。"""

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": AI_API_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一個詐騙園區的日報編輯，擅長用風趣的文字記錄員工的工作表現。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 100
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(AI_API_URL, headers=headers, json=data, timeout=10) as response:
                if response.status == 200:
                    result = await response.json()
                    story = result['choices'][0]['message']['content'].strip()
                    
                    # 清理可能的引號
                    story = story.strip('"').strip("'").strip()
                    
                    return story
                else:
                    print(f"⚠️ AI API 回應錯誤: {response.status}")
                    return f"今天的工作表現{int(salary_percent * 100)}%，連續出勤已達 {streak} 天。"
                    
    except asyncio.TimeoutError:
        print("⚠️ AI API 請求超時")
        return f"今天的工作表現{int(salary_percent * 100)}%，連續出勤已達 {streak} 天。"
    except Exception as e:
        print(f"⚠️ AI 生成打卡故事失敗: {e}")
        traceback.print_exc()
        return f"今天的工作表現{int(salary_percent * 100)}%，連續出勤已達 {streak} 天。"

async def generate_story_with_ai(action_name, level_title, success, reward, user_name):
    """使用 AI API 生成行動故事"""
    try:
        if not AI_API_KEY or not AI_API_URL:
            # 如果沒有設定 AI API，使用預設故事
            return get_fallback_story(action_name, success, reward)
        
        # 根據成功或失敗設定提示詞
        result_type = "成功" if success else "失敗"
        
        prompt = f"""你是一個詐騙園區的故事敘述者。請用第二人稱描述以下情境：

角色職位：{level_title}
執行行動：{action_name}
行動結果：{result_type}
{"獲得金額：" + str(reward) + " KK幣" if success else "未獲得金額"}

請生成一段 2-3 句的簡短故事，描述這次行動的過程和結果。要求：
1. 使用第二人稱「你」來描述
2. 貼合詐騙園區的黑色幽默風格
3. 如果成功，描述順利的過程並提到獲得 {reward if success else 0} KK幣
4. 如果失敗，描述遭遇的意外或失誤
5. 保持簡潔，不超過 80 字
6. 不要有任何多餘的對話或旁白

直接輸出故事內容，不需要任何前綴或標題。"""

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": AI_API_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一個擅長創作詐騙園區故事的作家，擅長用簡潔生動的文字描述各種詐騙行動。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.8,
            "max_tokens": 200
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(AI_API_URL, headers=headers, json=data, timeout=10) as response:
                if response.status == 200:
                    result = await response.json()
                    story = result['choices'][0]['message']['content'].strip()
                    
                    # 清理可能的引號或多餘格式
                    story = story.strip('"').strip("'").strip()
                    
                    return story
                else:
                    print(f"⚠️ AI API 回應錯誤: {response.status}")
                    return get_fallback_story(action_name, success, reward)
                    
    except asyncio.TimeoutError:
        print("⚠️ AI API 請求超時")
        return get_fallback_story(action_name, success, reward)
    except Exception as e:
        print(f"⚠️ AI 生成故事失敗: {e}")
        traceback.print_exc()
        return get_fallback_story(action_name, success, reward)

def get_fallback_story(action_name, success, reward):
    """當 AI API 不可用時的備用故事"""
    if success:
        stories = {
            "領錢": f"你快速完成提款，{reward} KK幣順利入袋。",
            "收水": f"車手準時送達，你收到 {reward} KK幣。",
            "偷A錢": f"趁主管不注意，{reward} KK幣神不知鬼不覺地進了口袋。",
            "轉移陣地": f"團隊順利轉移到新據點，賺了 {reward} KK幣。",
            "洗錢": f"透過多次轉帳，{reward} KK幣洗得乾乾淨淨。",
            "算帳": f"帳本完美平衡，順便撈了 {reward} KK幣。",
            "做假帳": f"假帳天衣無縫，輕鬆賺到 {reward} KK幣。",
            "挪用公款": f"職權在手，{reward} KK幣暫時「借用」。",
            "詐騙": f"話術完美，受害者心甘情願送上 {reward} KK幣。",
            "挖虛擬幣": f"礦機全速運轉，產出 {reward} KK幣。",
            "培訓新人": f"新人培訓完成，獲得 {reward} KK幣獎金。",
            "開發話術": f"新話術效果絕佳，研發費 {reward} KK幣到手。",
            "大單詐騙": f"大魚上鉤！這筆大單進帳 {reward} KK幣！"
        }
        return stories.get(action_name, f"行動成功，獲得 {reward} KK幣！")
    else:
        stories = {
            "領錢": "ATM 突然故障，你嚇得落荒而逃。",
            "收水": "車手遲到太久，你不敢繼續等待。",
            "偷A錢": "主管突然檢查帳本，你來不及動手腳。",
            "轉移陣地": "搬運車拋錨，設備來不及移走。",
            "洗錢": "銀行加強審查，轉帳被凍結了。",
            "算帳": "有人質疑帳目，你不敢做手腳。",
            "做假帳": "稽查員經驗老道，一眼看出破綻。",
            "挪用公款": "財務突擊檢查，你來不及把錢轉回去。",
            "詐騙": "對方識破話術，還威脅要報警。",
            "挖虛擬幣": "礦機過熱當機，這個月白挖了。",
            "培訓新人": "新人太笨學不會，浪費時間。",
            "開發話術": "新話術測試時被識破，不能用。",
            "大單詐騙": "目標起疑心，要求面對面交易，你不敢去。"
        }
        return stories.get(action_name, "行動失敗，什麼都沒得到。")

async def process_work_action(user_id, user_obj, action):
    """處理工作行動 - 使用 AI 生成故事"""
    try:
        user = get_user(user_id)
        
        # 檢查用戶是否成功取得
        if not user:
            print(f"❌ 無法找到或建立用戶: {user_id}")
            return None, None, "❌ 無法獲取用戶資料"
        
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # 安全地解析 actions_used（可能是字典或JSON字符串）
        actions_used_raw = user.get('actions_used', '{}')
        try:
            if isinstance(actions_used_raw, dict):
                actions_used = actions_used_raw
            else:
                actions_used = json.loads(actions_used_raw)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"⚠️ 解析 actions_used 失敗: {e}, 使用空字典")
            actions_used = {}
        
        if action in actions_used:
            return None, None, "你今天已經執行過這個行動了！"
        
        level = user.get('level', 1)
        if level not in LEVELS:
            print(f"❌ 無效的等級: {level}")
            return None, None, "❌ 用戶資料有誤"
        
        level_info = LEVELS[level]
        
        # 找到對應的行動資料
        action_data = None
        for act in level_info['actions']:
            if act['name'] == action:
                action_data = act
                break
        
        if not action_data:
            return None, None, "此行動不存在！"
        
        # 判定成功或失敗
        success = random.random() < action_data['success_rate']
        
        if success:
            # 成功：獲得 0-100% 的獎勵
            reward_multiplier = random.uniform(0, 1)
            kk_gain = int(action_data['base_reward'] * reward_multiplier)
            xp_gain = action_data['xp']
            result_color = 0x00ff00  # 綠色
            result_title = f"✅ {action} - 成功"
        else:
            # 失敗：沒有獎勵
            kk_gain = 0
            xp_gain = action_data['xp'] // 4  # 失敗只給 25% 經驗
            result_color = 0xff0000  # 紅色
            result_title = f"❌ {action} - 失敗"
        
        # 使用 AI 生成故事
        story = await generate_story_with_ai(
            action_name=action,
            level_title=level_info['title'],
            success=success,
            reward=kk_gain,
            user_name=user_obj.display_name
        )
        
        # 更新資料庫
        actions_used[action] = today
        success = update_user(
            user_id, 
            xp=user['xp'] + xp_gain, 
            kkcoin=user['kkcoin'] + kk_gain,
            actions_used=json.dumps(actions_used)
        )
        
        if not success:
            print(f"❌ 更新用戶資料失敗: {user_id}")
            return None, None, "❌ 資料保存失敗，請稍後再試"
        
        updated_user = get_user(user_id)
        
        # 檢查更新後的用戶資料
        if not updated_user:
            print(f"⚠️ 無法重新取得用戶 {user_id} 的資料")
            return None, None, "⚠️ 資料同步異常"
        
        # 創建結果 embed
        result_embed = discord.Embed(
            title=result_title,
            description=f"*{story}*",
            color=result_color
        )
        
        result_embed.add_field(
            name="📊 行動資訊",
            value=(
                f"**成功率**：{int(action_data['success_rate']*100)}%\n"
                f"**風險等級**：{'🟢 低' if action_data['risk'] <= 0.2 else '🟡 中' if action_data['risk'] <= 0.4 else '🔴 高'}\n"
                f"**最高報酬**：{action_data['base_reward']:,} KK幣"
            ),
            inline=True
        )
        
        result_embed.add_field(
            name="💰 實際收益",
            value=(
                f"**獲得金幣**：{kk_gain:,} KK幣\n"
                f"**獲得經驗**：+{xp_gain} XP\n"
                f"**當前餘額**：{updated_user['kkcoin']:,} KK幣"
            ),
            inline=True
        )
        
        result_embed.set_footer(text=f"由 AI 生成故事 | {user_obj.name}")
        result_embed.timestamp = datetime.utcnow()
        
        # 檢查是否接近升級
        level_up_message = None
        can_level_up, info = check_level_up(updated_user)
        
        if can_level_up:
            next_salary = LEVELS[updated_user['level'] + 1]["salary"]
            level_up_message = f"🎉 **升級條件已達成！**\n下次打卡即可升級，日薪將提升至 **{next_salary:,} KK幣**！"
        elif updated_user['level'] < 5:
            missing_days = info['required_days'] - info['current_days']
            missing_xp = info['required_xp'] - info['current_xp']
            missing_weeks = missing_days // 7
            
            if not info['days_met'] and not info['xp_met']:
                level_up_message = f"💪 再接再厲！還需連續出勤 **{missing_days}** 天 ({missing_weeks} 周) 和 **{missing_xp:,}** XP"
            elif not info['xp_met']:
                level_up_message = f"📈 出勤天數已達標！再累積 **{missing_xp:,}** XP 即可升級"
            elif not info['days_met']:
                level_up_message = f"🗓️ 經驗值已足夠！再連續出勤 **{missing_days}** 天 ({missing_weeks} 周) 即可升級"
        
        # 創建工作記錄卡
        work_embed = create_work_embed(updated_user, user_obj)
        
        return (result_embed, work_embed), updated_user, level_up_message
    except Exception as e:
        traceback.print_exc()
        return None, None, "處理失敗，請稍後再試"

async def setup(bot):
    """載入擴展時會被調用的函數"""
    print("Work system utilities loaded successfully!")
