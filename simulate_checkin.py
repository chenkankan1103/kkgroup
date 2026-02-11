#!/usr/bin/env python3
"""
模擬打卡流程 - 逐步檢查邏輯是否正確
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import random
import json

# 台灣時區（UTC+8）
TAIWAN_TZ = timezone(timedelta(hours=8))

def get_taiwan_time():
    """獲取台灣時間"""
    return datetime.now(TAIWAN_TZ)

# 簡化的等級體系
LEVELS = {
    1: {"title": "新手", "salary": 100, "xp_threshold": 100, "xp_boost": 1.0, "salary_boost": 1.0},
    2: {"title": "員工", "salary": 150, "xp_threshold": 200, "xp_boost": 1.1, "salary_boost": 1.1},
    3: {"title": "主管", "salary": 250, "xp_threshold": 400, "xp_boost": 1.2, "salary_boost": 1.2},
}

def simulate_user_data(user_id=123) -> Dict[str, Any]:
    """模擬一個用戶的初始數據"""
    return {
        'user_id': user_id,
        'user_name': 'TestUser',
        'level': 1,
        'title': 'TestTitle',
        'xp': 50,
        'kkcoin': 1000,
        'streak': 3,
        'pre_job': True,  # 已領取工作證
        'last_work_date': None,  # 從未打過卡
    }

def check_step_1_user_data(user: Dict) -> bool:
    """步驟 1: 檢查用戶數據是否成功取得"""
    print("\n▶ 步驟 1: 檢查用戶數據")
    print(f"  使用者: {user.get('user_name')} (ID: {user['user_id']})")
    
    if not user:
        print("  ❌ 失敗: 無法獲取用戶資料")
        return False
    
    print(f"  ✅ 成功: Lv.{user['level']} {user.get('title')}")
    return True

def check_step_2_pre_job(user: Dict) -> bool:
    """步驟 2: 檢查是否已領取工作證"""
    print("\n▶ 步驟 2: 檢查工作證")
    
    if not user.get('pre_job'):
        print("  ❌ 失敗: 未領取工作證")
        return False
    
    print("  ✅ 成功: 已領取工作證")
    return True

def check_step_3_duplicate_checkin(user: Dict) -> bool:
    """步驟 3: 檢查是否已打過卡（台灣時区）"""
    print("\n▶ 步驟 3: 檢查重複打卡（使用台灣時間）")
    
    today = get_taiwan_time().strftime("%Y-%m-%d")
    taiwan_time = get_taiwan_time().strftime("%Y-%m-%d %H:%M:%S")
    last_work_date = user.get('last_work_date', None)
    
    print(f"  目前台灣時間: {taiwan_time}")
    print(f"  今日日期: {today}")
    print(f"  上次打卡: {last_work_date if last_work_date else '從未打卡'}")
    
    if last_work_date == today:
        print(f"  ❌ 失敗: 今日已打卡")
        return False
    
    print(f"  ✅ 成功: 允許打卡")
    return True

def check_step_4_xp_calculation(user: Dict) -> tuple:
    """步驟 4: 計算 XP 獲得"""
    print("\n▶ 步驟 4: 計算 XP 獲得")
    
    level = user.get('level', 1)
    current_xp = user.get('xp', 0)
    
    # XP 計算：隨機 20-60 + 倍率加成
    xp_gain = random.randint(20, 60)
    xp_boost = LEVELS[level].get("xp_boost", 1.0)
    xp_gain = int(xp_gain * xp_boost)
    
    new_xp = current_xp + xp_gain
    
    print(f"  等級: Lv.{level}")
    print(f"  原始 XP: {current_xp}")
    print(f"  獲得 XP: {xp_gain} (基數 {int(xp_gain/xp_boost):.0f} × {xp_boost})")
    print(f"  新增 XP: {new_xp}")
    
    return xp_gain, new_xp

def check_step_5_salary_calculation(user: Dict) -> tuple:
    """步驟 5: 計算薪資（浮動）"""
    print("\n▶ 步驟 5: 計算薪資獲得")
    
    level = user.get('level', 1)
    current_kkcoin = user.get('kkcoin', 0)
    
    # 薪資計算：隨機 0-100% + 倍率加成
    base_salary = LEVELS[level]["salary"]
    salary_multiplier = random.uniform(0, 1)
    salary_boost = LEVELS[level].get("salary_boost", 1.0)
    kkcoin_gain = int(base_salary * salary_multiplier * salary_boost)
    
    new_kkcoin = current_kkcoin + kkcoin_gain
    salary_percent = int(salary_multiplier * 100)
    
    print(f"  等級: Lv.{level}")
    print(f"  基礎薪資: {base_salary}")
    print(f"  倍率: {salary_percent}% × {salary_boost} = {salary_percent*salary_boost:.0f}%")
    print(f"  獲得金幣: {kkcoin_gain}")
    print(f"  原始金幣: {current_kkcoin}")
    print(f"  新增金幣: {new_kkcoin}")
    
    return kkcoin_gain, new_kkcoin, salary_multiplier

def check_step_6_level_up(user: Dict, new_xp: int) -> tuple:
    """步驟 6: 檢查升級"""
    print("\n▶ 步驟 6: 檢查升級")
    
    level = user.get('level', 1)
    streak = user.get('streak', 0) + 1  # 打卡後連勤 +1
    original_streak = streak - 1  # 升級前的連勤
    
    # 升級檢查：簡化版邏輯
    next_threshold = LEVELS[level].get("xp_threshold", 100)
    
    print(f"  目前等級: Lv.{level}")
    print(f"  升級所需 XP: {next_threshold}")
    print(f"  目前 XP: {new_xp}")
    print(f"  原始連勤: {original_streak} 天")
    print(f"  新連勤: {streak} 天")
    
    if new_xp >= next_threshold and level < 3:
        # 升級！
        new_level = level + 1
        new_xp = 0  # XP 歸零
        streak = 0  # 連勤歸零（規則）
        bonus_coins = 300 * new_level  # 升級獎勵
        
        print(f"  🎊 升級了! Lv.{level} → Lv.{new_level}")
        print(f"  升級獎勵: {bonus_coins} 金幣")
        print(f"  新連勤已歸零: 0 天")
        
        return True, new_level, new_xp, streak, bonus_coins
    else:
        print(f"  📊 升級進度: {new_xp} / {next_threshold}")
        return False, level, new_xp, streak, 0

def check_step_7_data_save(user: Dict, new_level: int, new_xp: int, new_streak: int, 
                           new_kkcoin: int, bonus_coins: int) -> Dict:
    """步驟 7: 保存數據到數據庫"""
    print("\n▶ 步驟 7: 保存數據")
    
    today = get_taiwan_time().strftime("%Y-%m-%d")
    
    # 模擬數據庫更新
    updated_user = user.copy()
    updated_user['level'] = new_level
    updated_user['xp'] = new_xp
    updated_user['kkcoin'] = new_kkcoin
    updated_user['streak'] = new_streak
    updated_user['last_work_date'] = today
    updated_user['actions_used'] = '{}'
    
    print(f"  💾 保存欄位:")
    print(f"    - last_work_date: {today}")
    print(f"    - level: Lv.{new_level}")
    print(f"    - xp: {new_xp}")
    print(f"    - kkcoin: {new_kkcoin}")
    print(f"    - streak: {new_streak}")
    print(f"  ✅ 數據已保存")
    
    return updated_user

def simulate_checkin(user: Dict) -> bool:
    """完整的打卡流程模擬"""
    print("=" * 60)
    print("🕐 【打卡流程模擬】")
    print("=" * 60)
    
    # 步驟 1: 檢查用戶數據
    if not check_step_1_user_data(user):
        return False
    
    # 步驟 2: 檢查工作證
    if not check_step_2_pre_job(user):
        return False
    
    # 步驟 3: 檢查重複打卡
    if not check_step_3_duplicate_checkin(user):
        return False
    
    # 步驟 4: 計算 XP
    xp_gain, new_xp = check_step_4_xp_calculation(user)
    
    # 步驟 5: 計算薪資
    kkcoin_gain, new_kkcoin, salary_multiplier = check_step_5_salary_calculation(user)
    
    # 步驟 6: 檢查升級
    leveled_up, new_level, new_xp, new_streak, bonus_coins = check_step_6_level_up(user, new_xp)
    
    # 調整金幣（升級獎勵）
    new_kkcoin += bonus_coins
    
    # 步驟 7: 保存數據
    updated_user = check_step_7_data_save(user, new_level, new_xp, new_streak, new_kkcoin, bonus_coins)
    
    # 結果摘要
    print("\n" + "=" * 60)
    print("✅ 【打卡完成】")
    print("=" * 60)
    print(f"薪資獲得: {kkcoin_gain:,} KK幣 ({int(salary_multiplier*100)}%)")
    print(f"XP 獲得: {xp_gain}")
    if leveled_up:
        print(f"🎊 升級獎勵: {bonus_coins} KK幣")
    print()
    print("最終數據:")
    print(f"  • 等級: Lv.{updated_user['level']} ({updated_user.get('title')})")
    print(f"  • XP: {updated_user['xp']}")
    print(f"  • 金幣: {updated_user['kkcoin']:,}")
    print(f"  • 連勤: {updated_user['streak']} 天")
    print(f"  • 最後打卡: {updated_user['last_work_date']}")
    print("=" * 60)
    
    return True

def simulate_duplicate_checkin_fail(user: Dict):
    """模擬重複打卡失敗"""
    print("\n\n")
    print("=" * 60)
    print("🚫 【重複打卡測試】")
    print("=" * 60)
    
    # 模擬用戶已打過卡
    today = get_taiwan_time().strftime("%Y-%m-%d")
    user['last_work_date'] = today
    
    print(f"用戶 {user['user_name']} 今日已打卡: {today}")
    print()
    
    if not check_step_3_duplicate_checkin(user):
        print("✅ 系統正確拒絕了重複打卡")
    else:
        print("❌ 系統錯誤地允許了重複打卡！")

if __name__ == "__main__":
    # 測試 1: 正常打卡流程
    user = simulate_user_data(12345)
    simulate_checkin(user)
    
    # 測試 2: 重複打卡失敗
    simulate_duplicate_checkin_fail(user)
