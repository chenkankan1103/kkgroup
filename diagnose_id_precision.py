"""
診斷 Discord ID 精度損失問題

當 Google Sheets 返回大整數時，API 可能以浮點數格式返回，
導致精度損失。例如：
- 原始: 776464975551660123
- JSON: 7.764649755516601e+17
- 轉換: 776464975551660160 (精度損失！)
"""

# 驗證浮點數精度損失

original_ids = [
    776464975551660123,  # 凱文
    260266786719531008,  # 夜神獅獅
    564156950913351680,  # 自在天外天
    344018672056139776,  # 赤月
    1209509919699505152, # 餒餒補給站
    1296436778021945344, # 梅川イブ
]

print("=" * 80)
print("Discord ID 精度損失診斷")
print("=" * 80)

print("\n【驗證浮點數精度損失】\n")

for original_id in original_ids:
    # 模擬 Google Sheets 返回浮點數的情況
    float_val = float(original_id)
    recovered_id = int(float_val)
    is_equal = recovered_id == original_id
    
    if not is_equal:
        print(f"❌ ID: {original_id}")
        print(f"   浮點數: {float_val:.17e}")
        print(f"   恢復ID: {recovered_id}")
        print(f"   差異: {original_id - recovered_id}\n")
    else:
        print(f"✓ ID: {original_id} (保持精度)")

print("\n" + "=" * 80)
print("【根本原因】")
print("=" * 80)
print("""
Discord ID 是 18-19 位數字，超出浮點數精確表示的 15-16 位範圍。
當 Google Sheets API 以 JSON 數字（浮點）返回時，精度會損失。

解決方案：
1. 在 sheet_driven_db.py _convert_value() 中修復 ID 轉換
2. 優先使用字符串解析而不是浮點數中間步驟
3. 驗證轉換後的 user_id 是否有匹配的 nickname（去重）
""")
