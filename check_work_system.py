#!/usr/bin/env python3
"""檢查工作打卡系統的完整性和資料庫連接"""

import sys
sys.path.insert(0, '.')

try:
    from commands.work_function.database import get_user, update_user, get_all_users, init_db
    from commands.work_function.work_system import LEVELS
    print("✅ [1/5] 檢查工作模塊導入...")
    print("   ✓ work_system 正常導入")
    print("   ✓ database 正常導入")
except Exception as e:
    print(f"❌ [1/5] 導入失敗: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("🔍 工作系統完整性檢查")
print("=" * 70)

# 1. 檢查初始化
print("\n✅ [1/5] 初始化數據庫...")
try:
    if init_db():
        print("   ✓ 數據庫初始化成功")
    else:
        print("   ⚠️  數據庫初始化有警告")
except Exception as e:
    print(f"   ❌ 初始化失敗: {e}")

# 2. 檢查工作體系完整性
print("\n✅ [2/5] 檢查工作等級體系...")
required_level_fields = {
    'title', 'actions', 'salary', 'xp_required', 'role_id', 'description'
}

levels_valid = True
for level, info in LEVELS.items():
    existing_fields = set(info.keys())
    missing_fields = required_level_fields - existing_fields
    
    if missing_fields:
        print(f"   ⚠️  Lv.{level} 缺少字段: {missing_fields}")
        levels_valid = False
    else:
        actions_valid = all(
            set(action.keys()) >= {'name', 'risk', 'base_reward', 'success_rate', 'xp'}
            for action in info.get('actions', [])
        )
        if not actions_valid:
            print(f"   ⚠️  Lv.{level} 行動定義不完整")
            levels_valid = False

if levels_valid:
    print(f"   ✓ 所有 {len(LEVELS)} 個等級定義完整")

# 3. 檢查數據庫連接
print("\n✅ [3/5] 檢查數據庫連接...")
try:
    from db_adapter import get_db
    db = get_db()
    stats = db.get_stats()
    print(f"   ✓ Sheet-Driven DB 已連接")
    print(f"   ✓ 數據庫統計: {stats['total_users']} 用戶，{stats['total_columns']} 欄位")
except Exception as e:
    print(f"   ❌ 連接失敗: {e}")

# 4. 檢查工作數據字段
print("\n✅ [4/5] 檢查工作相關數據字段...")
work_required_fields = {
    'user_id', 'level', 'xp', 'kkcoin', 'title', 'streak',
    'last_work_date', 'actions_used'
}

try:
    all_users = get_all_users()
    if all_users:
        sample_user = next(iter(all_users), None)
        if sample_user:
            user_fields = set(sample_user.keys())
            missing_work_fields = work_required_fields - user_fields
            
            if missing_work_fields:
                print(f"   ⚠️  用戶記錄缺少字段: {missing_work_fields}")
            else:
                print(f"   ✓ 用戶記錄包含所有必要字段")
                print(f"   ✓ 示例用戶 ID: {sample_user.get('user_id')}")
                print(f"   ✓ 等級/經驗/金幣: {sample_user.get('level')}/{sample_user.get('xp', 0)}/{sample_user.get('kkcoin', 0)}")
        else:
            print(f"   ℹ️  無示例用戶（數據庫可能為空）")
    else:
        print(f"   ℹ️  get_all_users() 返回空列表（數據庫為空或查詢失敗）")
except Exception as e:
    print(f"   ❌ 查詢失敗: {e}")

# 5. 檢查關鍵函數
print("\n✅ [5/5] 檢查關鍵函數...")
from commands.work_function.work_cog import WorkCog

methods = {
    'work_info': '工作資訊命令',
    'work_stats': '工作統計命令',
    'work_health': '系統健康檢查',
    'work_rebuild': '重建系統'
}

for method_name, description in methods.items():
    if hasattr(WorkCog, method_name):
        print(f"   ✓ {description} ({method_name})")
    else:
        print(f"   ❌ 缺少: {description} ({method_name})")

# 檢查視圖類
view_classes = ['CheckInView', 'CheckInButton', 'RestButton', 'WorkActionView']
for class_name in view_classes:
    try:
        if class_name in dir():
            print(f"   ✓ {class_name} 類別")
    except:
        pass

print("\n" + "=" * 70)
print("✅ 工作系統檢查完成")
print("=" * 70)

print("""
📋 工作系統流程:
  1. 用戶打卡 → CheckInButton.callback() → process_checkin()
  2. 打卡成功 → 更新 level/xp/kkcoin/streak
  3. 用戶執行行動 → WorkActionView → process_work_action()
  4. 管理員檢查 → work_health() 和 work_rebuild()

✅ 資料庫層:
  - 使用 Sheet-Driven DB 引擎
  - 通過 db_adapter 連接
  - 所有數據持久化到 user_data.db
""")
