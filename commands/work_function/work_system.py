import discord
from discord.ext import commands
import json
import random
import traceback
import os
from datetime import datetime
from .database import get_user, update_user

# 等級配置 - 提高獎勵讓玩家更有動力
LEVELS = {
    1: {
        "title": "車手", 
        "actions": ["收贓款"], 
        "salary": 200,  # 基礎薪資
        "xp_required": 0,
        "role_id": int(os.getenv("ROLE_CAR", 0)),
        "description": "園區新人，負責基礎工作"
    },
    2: {
        "title": "收水手", 
        "actions": ["收贓款", "A錢"], 
        "salary": 350,
        "xp_required": 300,
        "role_id": int(os.getenv("ROLE_MONEY_COLLECTOR", 0)),
        "description": "經驗豐富的收款員，薪資提升75%"
    },
    3: {
        "title": "水房", 
        "actions": ["收贓款", "轉移陣地", "洗錢"], 
        "salary": 500,
        "xp_required": 900,
        "role_id": int(os.getenv("ROLE_WATER_ROOM", 0)),
        "description": "負責資金轉移，薪資翻倍"
    },
    4: {
        "title": "帳房", 
        "actions": ["收贓款", "算帳", "A錢", "做假帳"], 
        "salary": 750,
        "xp_required": 1800,
        "role_id": int(os.getenv("ROLE_ACCOUNTING", 0)),
        "description": "管理財務的高階職位，薪資x3.75"
    },
    5: {
        "title": "詐騙機房", 
        "actions": ["詐騙", "挖虛擬幣", "培訓新人", "開發話術"], 
        "salary": 1000,
        "xp_required": 3000,
        "role_id": int(os.getenv("ROLE_SCAM_ROOM", 0)),
        "description": "頂尖詐騙專家，最高薪資！"
    }
}

FIB_DAYS = [2, 3, 5, 8, 13, 21]

def required_days_for_level(level):
    """返回升級所需的連續出勤天數"""
    try:
        days = FIB_DAYS[level - 1] if level <= len(FIB_DAYS) else 999
        return days
    except Exception as e:
        traceback.print_exc()
        return 999

def check_level_up(user):
    """檢查是否滿足升級條件（連續出勤 + 經驗值）"""
    level = user.get('level', 1)
    if level >= 5:
        return False, None
    
    streak = user.get('streak', 0)
    xp = user.get('xp', 0)
    
    # 下一級所需條件
    next_level = level + 1
    required_days = required_days_for_level(next_level)
    required_xp = LEVELS[next_level]["xp_required"]
    
    # 兩個條件都要滿足
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
    """創建工作記錄卡 Embed - 增強版"""
    try:
        level = user['level']
        level_info = LEVELS[level]
        
        # 使用漸變色系表示不同等級
        colors = {1: 0x95a5a6, 2: 0x3498db, 3: 0x9b59b6, 4: 0xe74c3c, 5: 0xf39c12}
        embed = discord.Embed(
            title="🎴【詐騙園區 • 勞動記錄卡】", 
            color=colors.get(level, 0x2f3136)
        )
        
        # 基本資訊
        embed.add_field(
            name="👤 員工資訊", 
            value=(
                f"**姓名**：{user_obj.mention}\n"
                f"**職稱**：{level_info['title']}\n"
                f"**等級**：Lv.{level} ⭐"
            ),
            inline=True
        )
        
        # 財務狀況
        embed.add_field(
            name="💰 財務狀況", 
            value=(
                f"**餘額**：{user['kkcoin']:,} KK幣\n"
                f"**日薪**：{level_info['salary']:,} KK幣\n"
                f"**經驗**：{user['xp']:,} XP"
            ),
            inline=True
        )
        
        # 工作狀態
        embed.add_field(
            name="📊 工作狀態", 
            value=(
                f"**連勤**：{user['streak']} 天 🔥\n"
                f"**行動**：{len(level_info['actions'])} 種\n"
                f"**狀態**：✅ 在職中"
            ),
            inline=True
        )
        
        # 升級進度
        if level < 5:
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
                # 計算進度
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
                    f"• 升級紅包 +{(level + 1) * 200:,} KK幣\n"
                    f"• 解鎖新行動：{len(next_level_info['actions'])} 種"
                )
                
                embed.add_field(name="🔼 升級進度", value=progress_text, inline=False)
        else:
            embed.add_field(
                name="👑 最高等級", 
                value=(
                    "```yaml\n"
                    "你已達到詐騙機房等級！\n"
                    "享受最高薪資和全部權限！\n"
                    "```"
                ),
                inline=False
            )
        
        # 可用行動
        actions_text = " • ".join(level_info['actions'])
        embed.add_field(
            name="🎯 可執行行動",
            value=f"`{actions_text}`",
            inline=False
        )
        
        embed.set_footer(text=f"{level_info['description']} | 每日記得打卡出勤！")
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
        color=0xFFD700  # 金色
    )
    
    # 升級資訊
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
    
    # 升級獎勵
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
    new_actions = set(new_info['actions']) - set(old_info['actions'])
    if new_actions:
        embed.add_field(
            name="🆕 新解鎖行動",
            value=" • ".join(f"`{action}`" for action in new_actions),
            inline=False
        )
    
    # 特殊訊息
    level_messages = {
        2: "🎉 你已經不再是菜鳥了！薪資大幅提升！",
        3: "💪 你的詐騙技能越來越熟練了！解鎖洗錢功能！",
        4: "🏆 你已經是園區的高階管理了！財務自由在望！",
        5: "👑 登峰造極！你已成為詐騙機房的頂尖專家！最高薪資到手！"
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
        
        # 收集所有等級的身分組ID
        all_level_roles = [LEVELS[lvl]["role_id"] for lvl in LEVELS.keys() if LEVELS[lvl]["role_id"]]
        
        # 移除所有等級身分組
        roles_to_remove = []
        for role in member.roles:
            if role.id in all_level_roles:
                roles_to_remove.append(role)
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="升級：移除舊等級身分組")
            print(f"✅ 已移除 {len(roles_to_remove)} 個舊身分組")
        
        # 添加新等級身分組
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
    """處理打卡邏輯"""
    try:
        user = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        level = user.get('level', 1)
        streak = user.get('streak', 0) + 1
        xp_gain = random.randint(15, 50)  # 提高經驗值獲取
        kkcoin_gain = LEVELS[level]["salary"]

        # 檢查是否可以升級
        leveled_up = False
        bonus_coins = 0
        old_level = level
        
        # 先更新連續天數和經驗值，再檢查升級
        temp_user = user.copy()
        temp_user['streak'] = streak
        temp_user['xp'] = user.get('xp', 0) + xp_gain
        
        can_level_up, _ = check_level_up(temp_user)
        
        if can_level_up and level < 5:
            level += 1
            streak = 0  # 升級後重置連續天數
            bonus_coins = 200 * level  # 升級獎勵金幣（更豐厚）
            kkcoin_gain += bonus_coins
            leveled_up = True
            
            # 分配身分組
            role_assigned = await assign_role(guild, user_obj, level)
            if role_assigned:
                print(f"✅ 用戶 {user_obj.name} 升級至 Lv.{level}，已授予身分組")

        # 更新資料庫
        update_user(
            user_id,
            last_work_date=today,
            streak=streak,
            level=level,
            xp=temp_user['xp'],
            kkcoin=user.get('kkcoin', 0) + kkcoin_gain,
            actions_used='{}'
        )

        updated_user = get_user(user_id)
        
        # 如果升級了，顯示升級特效
        if leveled_up:
            level_up_embed = create_level_up_embed(user_obj, old_level, level, bonus_coins)
            work_embed = create_work_embed(updated_user, user_obj)
            return (level_up_embed, work_embed), updated_user
        else:
            embed = create_work_embed(updated_user, user_obj)
            return (embed,), updated_user
            
    except Exception as e:
        traceback.print_exc()
        return None, None

async def process_work_action(user_id, user_obj, action):
    """處理工作行動"""
    try:
        user = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        actions_used = json.loads(user.get('actions_used', '{}'))
        if action in actions_used:
            return None, None, "你今天已經執行過這個行動了！"
        
        # 提高行動獎勵
        level = user['level']
        base_salary = LEVELS[level]["salary"]
        xp_gain = random.randint(30, 150)  # 提高經驗值
        kk_gain = random.randint(base_salary // 3, base_salary)  # 更高的金幣獎勵
        
        actions_used[action] = today
        update_user(
            user_id, 
            xp=user['xp'] + xp_gain, 
            kkcoin=user['kkcoin'] + kk_gain,
            actions_used=json.dumps(actions_used)
        )
        
        updated_user = get_user(user_id)
        embed = create_work_embed(updated_user, user_obj)
        
        # 更豐富的結果文案
        outcomes = {
            "收贓款": [
                f"成功收到一筆贓款，入袋 {kk_gain:,} KK幣！💰",
                f"這批貨很乾淨，順利收款 {kk_gain:,} KK幣！",
                f"交易完成！獲得 {kk_gain:,} KK幣，記得銷毀證據！"
            ],
            "A錢": [
                f"趁老闆不注意，悄悄A了 {kk_gain:,} KK幣！🤫",
                f"帳目對不上？沒關係，反正A到 {kk_gain:,} KK幣了！",
                f"神不知鬼不覺，{kk_gain:,} KK幣到手！"
            ],
            "轉移陣地": [
                f"成功轉移資金，賺取手續費 {kk_gain:,} KK幣！",
                f"順利完成轉移，獲得 {kk_gain:,} KK幣報酬！",
                f"資金已安全轉移，收入 {kk_gain:,} KK幣！"
            ],
            "洗錢": [
                f"完美的洗錢操作！淨賺 {kk_gain:,} KK幣！💸",
                f"資金洗得乾乾淨淨，獲利 {kk_gain:,} KK幣！",
                f"洗錢技術一流，收益 {kk_gain:,} KK幣！"
            ],
            "算帳": [
                f"帳算得漂亮，順便撈了 {kk_gain:,} KK幣！📊",
                f"數字遊戲玩得好，賺到 {kk_gain:,} KK幣！",
                f"這筆帳只有你知我知，{kk_gain:,} KK幣入袋！"
            ],
            "做假帳": [
                f"假帳做得天衣無縫，收益 {kk_gain:,} KK幣！",
                f"稽查員都看不出來，賺了 {kk_gain:,} KK幣！",
                f"完美的假帳，淨賺 {kk_gain:,} KK幣！"
            ],
            "詐騙": [
                f"今天騙到大肥羊！進帳 {kk_gain:,} KK幣！🎯",
                f"話術運用得當，輕鬆賺 {kk_gain:,} KK幣！",
                f"受害者完全相信你，獲得 {kk_gain:,} KK幣！"
            ],
            "挖虛擬幣": [
                f"礦機全速運轉，挖到 {kk_gain:,} KK幣！⛏️",
                f"今天幣價不錯，收益 {kk_gain:,} KK幣！",
                f"算力全開！產出 {kk_gain:,} KK幣！"
            ],
            "培訓新人": [
                f"成功培訓一批新人，獲得獎金 {kk_gain:,} KK幣！👥",
                f"新人都學會了，提成 {kk_gain:,} KK幣！",
                f"培訓完成，收入 {kk_gain:,} KK幣！"
            ],
            "開發話術": [
                f"新話術效果拔群！獎勵 {kk_gain:,} KK幣！💬",
                f"這套話術一定能騙到更多人，獲得 {kk_gain:,} KK幣研發費！",
                f"話術開發成功，收益 {kk_gain:,} KK幣！"
            ]
        }
        
        action_outcomes = outcomes.get(action, [f"行動完成，獲得 {kk_gain:,} KK幣！"])
        result_text = random.choice(action_outcomes)
        
        embed.add_field(
            name=f"📦 行動結果 - {action}", 
            value=(
                f"{result_text}\n\n"
                f"**收益**：💰 +{kk_gain:,} KK幣 | 📈 +{xp_gain} XP"
            ),
            inline=False
        )
        
        # 檢查是否接近升級
        level_up_message = None
        can_level_up, info = check_level_up(updated_user)
        
        if can_level_up:
            next_salary = LEVELS[updated_user['level'] + 1]["salary"]
            level_up_message = f"🎉 **升級條件已達成！**\n下次打卡即可升級，日薪將提升至 **{next_salary:,} KK幣**！"
        elif updated_user['level'] < 5:
            missing_days = info['required_days'] - info['current_days']
            missing_xp = info['required_xp'] - info['current_xp']
            
            if not info['days_met'] and not info['xp_met']:
                level_up_message = f"💪 再接再厲！還需連續出勤 **{missing_days}** 天和 **{missing_xp:,}** XP"
            elif not info['xp_met']:
                level_up_message = f"📈 出勤天數已達標！再累積 **{missing_xp:,}** XP 即可升級"
            elif not info['days_met']:
                level_up_message = f"🗓️ 經驗值已足夠！再連續出勤 **{missing_days}** 天即可升級"
        
        return embed, updated_user, level_up_message
    except Exception as e:
        traceback.print_exc()
        return None, None, "處理失敗，請稍後再試"

async def setup(bot):
    """載入擴展時會被調用的函數"""
    print("Work system utilities loaded successfully!")
