#!/usr/bin/env python3
"""
圖片功能關鍵詞檢測測試
"""

import sys
sys.path.insert(0, '/home/e193752468/kkgroup')

# 模擬ImageHandler的關鍵詞檢測邏輯
IMAGE_KEYWORDS = {
    "生圖": ["生", "生圖", "生成圖", "畫", "畫圖"],
    "編圖": ["編", "P圖", "編輯圖", "改", "修改", "調整", "改圖"],
    "看圖": ["看", "看圖", "分析圖", "檢查圖", "掃描圖", "檢查", "掃描"]
}

def detect_image_request(message_content: str):
    """偵測訊息是否包含圖片相關請求"""
    content_lower = message_content.lower()
    
    for request_type, keywords in IMAGE_KEYWORDS.items():
        # 將所有關鍵詞轉為小寫進行比較
        if any(kw.lower() in content_lower for kw in keywords):
            return request_type
    
    return None

# 測試案例
test_cases = [
    ("生圖 一個監控室", "生圖"),
    ("幫我畫個圖", "生圖"),
    ("生成一張園區地圖", "生圖"),
    ("P圖一下這個logo", "編圖"),
    ("編輯這張圖", "編圖"),
    ("把背景改暗", "編圖"),
    ("調整一下顏色", "編圖"),
    ("看看這張圖", "看圖"),
    ("分析圖片內容", "看圖"),
    ("掃描這個二維碼", "看圖"),
    ("檢查轉帳截圖", "看圖"),
    ("你好機器人", None),
    ("幫我查個排行榜", None),
    ("", None),
]

print("=" * 60)
print("🖼️  圖片功能關鍵詞檢測測試")
print("=" * 60)

passed = 0
failed = 0

for message, expected in test_cases:
    result = detect_image_request(message)
    status = "✅" if result == expected else "❌"
    
    if result == expected:
        passed += 1
    else:
        failed += 1
    
    print(f"{status} 訊息: '{message}'")
    print(f"   預期: {expected}, 得到: {result}\n")

print("=" * 60)
print(f"測試結果: {passed} 通過, {failed} 失敗")
print(f"成功率: {passed}/{len(test_cases)} = {100*passed/len(test_cases):.1f}%")
print("=" * 60)

if failed == 0:
    print("✅ 所有測試通過！")
    sys.exit(0)
else:
    print("❌ 有測試失敗")
    sys.exit(1)
