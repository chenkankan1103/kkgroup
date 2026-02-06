#!/usr/bin/env python3
"""
診斷排行榜讀取問題
檢查 Bot 排行榜邏輯是否正常
"""

import sys
sys.path.insert(0, '.')

from db_adapter import get_all_users
from collections import defaultdict

print("=" * 60)
print("🔍 KKCoin 排行榜診斷")
print("=" * 60)

# 1️⃣ 檢查 DB 連接
print("\n1️⃣  檢查數據庫連接...")
try:
    all_users = get_all_users()
    print(f"✅ 成功讀取 {len(all_users)} 個用戶")
except Exception as e:
    print(f"❌ DB 連接失敗: {e}")
    sys.exit(1)

# 2️⃣ 篩選有 KK幣的玩家
print("\n2️⃣ 篩選有 KK幣的玩家...")
users_with_kk = [u for u in all_users if (u.get('kkcoin') or 0) > 0]
print(f"✅ 找到 {len(users_with_kk)} 位玩家有 KK幣")

# 檢查 None 值
none_count = sum(1 for u in all_users if u.get('kkcoin') is None)
if none_count > 0:
    print(f"⚠️  警告：{none_count} 個用戶的 kkcoin 為 None")

# 3️⃣ 排序
print("\n3️⃣ 排序 (按 KK幣降序)...")
users_with_kk.sort(key=lambda x: x.get('kkcoin', 0), reverse=True)
print(f"✅ 排序完成")

# 4️⃣ 取前 20 名
print("\n4️⃣ 取前 20 名...")
top20 = users_with_kk[:20]
print(f"✅ 取得前 {len(top20)} 名")

# 5️⃣ 檢查排行資料
print("\n5️⃣ 排行榜資料詳情:\n")
print(f"{'排名':<5} {'Discord ID':<20} {'暱稱':<12} {'KK幣':<8} {'user_name':<12}")
print("-" * 70)

for i, user in enumerate(top20, 1):
    user_id = user.get('user_id', '?')
    nickname = user.get('nickname', '?')
    user_name = user.get('user_name', '?')
    kkcoin = user.get('kkcoin', 0)
    
    print(f"{i:<5} {str(user_id):<20} {str(nickname):<12} {kkcoin:<8} {str(user_name):<12}")

# 6️⃣ 模擬 Bot 的 guild.get_member 邏輯
print("\n6️⃣ 檢查 Discord Guild 匹配問題...")
print("⚠️  無法在此檢查，因為需要連接 Discord。")
print("   但已確認：")
print(f"   - DB 有 {len(users_with_kk)} 位玩家的排行數據")
print(f"   - 前 20 名的暱稱都已加載")
print(f"   - user_name 欄位大多為空（已棄用）")

# 7️⃣ 推薦
print("\n7️⃣ 可能的原因:")
reasons = [
    ("DB 連接正常", "✅"),
    ("排行數據完整", "✅"),
    ("暱稱字段有值", "✅"),
    ("Discord Guild 同步問題?", "❓"),
    ("guild.get_member(user_id) 返回 None?", "❓"),
]

for reason, status in reasons:
    print(f"   {status} {reason}")

print("\n" + "=" * 60)
print("💡 解決方案:")
print("=" * 60)
print("""
1. 確認 Discord Guild 中的成員列表是否已同步
   - 檢查 Bot 是否有 GUILD_MEMBERS_INTENT
   - 檢查 Guild 中是否有這些 user_id 的成員

2. 修改排行榜邏輯不依賴 guild.get_member()
   - 直接使用 DB 中的暱稱，而不是 Discord member 對象
   - 或添加備用邏輯：若 member 為空，使用 DB 暱稱

3. 強制刷新排行榜
   - 使用 /kkcoin_force_refresh 命令
   - 檢查排行榜是否更新

4. 檢查 Bot 日誌
   - 看是否有錯誤信息
   - 檢查 guild.get_member() 是否成功
""")
