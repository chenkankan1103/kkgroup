#!/usr/bin/env python3
"""
測試更新後的圖片功能邏輯
驗證模型選擇和參數處理是否正確
"""

import sys
import os

# 添加項目根目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("🧪 圖片功能邏輯測試")
print("=" * 60)

# 測試 1: 檢查 ImageHandler 類別可以被導入
print("\n1️⃣ 測試導入 ImageHandler 類別...")
try:
    from commands.image import ImageHandler
    print("✅ ImageHandler 成功導入")
except ImportError as e:
    print(f"❌ 導入失敗: {e}")
    sys.exit(1)

# 測試 2: 檢查關鍵詞檢測功能
print("\n2️⃣ 測試關鍵詞檢測...")
test_cases = [
    ("@機器人 生圖 一張美麗的風景", "生圖"),
    ("@機器人 看圖", "看圖"),
    ("@機器人 編圖 把背景改成藍色", "編圖"),
    ("@機器人 畫一張圖", "生圖"),
    ("@機器人 P圖", "編圖"),
    ("@機器人 分析圖", "看圖"),
    ("@機器人 你好", None),
]

all_passed = True
for message, expected in test_cases:
    result = ImageHandler.detect_image_request(message)
    if result == expected:
        print(f"✅ '{message[:30]}...' -> {result}")
    else:
        print(f"❌ '{message[:30]}...' -> 預期 {expected}, 實際 {result}")
        all_passed = False

if not all_passed:
    print("\n⚠️ 部分關鍵詞檢測測試失敗")
    sys.exit(1)

# 測試 3: 驗證模型名稱常數
print("\n3️⃣ 驗證使用的模型名稱...")
import inspect
import commands.image as image_module

source = inspect.getsource(image_module.ImageHandler.generate_image)
if "gemini-2.5-flash-image" in source:
    print("✅ generate_image 使用正確的 gemini-2.5-flash-image 模型")
else:
    print("❌ generate_image 未使用 gemini-2.5-flash-image 模型")
    all_passed = False

source = inspect.getsource(image_module.ImageHandler.edit_image)
if "gemini-2.5-flash-image" in source:
    print("✅ edit_image 使用正確的 gemini-2.5-flash-image 模型")
else:
    print("❌ edit_image 未使用 gemini-2.5-flash-image 模型")
    all_passed = False

source = inspect.getsource(image_module.ImageHandler.analyze_image)
if "gemini-2.5-flash" in source:
    print("✅ analyze_image 使用正確的 gemini-2.5-flash 模型")
else:
    print("❌ analyze_image 未使用 gemini-2.5-flash 模型")
    all_passed = False

# 測試 4: 檢查 requirements.txt
print("\n4️⃣ 檢查 requirements.txt...")
with open("requirements.txt", "r") as f:
    requirements = f.read()
    if "google-generativeai" in requirements:
        print("✅ requirements.txt 包含 google-generativeai")
    else:
        print("❌ requirements.txt 缺少 google-generativeai")
        all_passed = False

# 測試 5: 檢查錯誤處理邏輯
print("\n5️⃣ 檢查錯誤處理...")
source_gen = inspect.getsource(image_module.ImageHandler.generate_image)
source_edit = inspect.getsource(image_module.ImageHandler.edit_image)
source_analyze = inspect.getsource(image_module.ImageHandler.analyze_image)

checks = [
    (source_gen, "try:", "generate_image 有 try-except"),
    (source_gen, "except Exception", "generate_image 捕獲異常"),
    (source_edit, "try:", "edit_image 有 try-except"),
    (source_edit, "except Exception", "edit_image 捕獲異常"),
    (source_analyze, "try:", "analyze_image 有 try-except"),
    (source_analyze, "except Exception", "analyze_image 捕獲異常"),
]

for source, pattern, desc in checks:
    if pattern in source:
        print(f"✅ {desc}")
    else:
        print(f"❌ {desc} - 未找到")
        all_passed = False

# 最終結果
print("\n" + "=" * 60)
if all_passed:
    print("✅ 所有邏輯測試通過！")
    print("=" * 60)
    print("\n📝 注意事項：")
    print("   - 實際 API 調用需要在生產環境測試")
    print("   - 需要有效的 AI_API_KEY 環境變數")
    print("   - 需要確認 gemini-2.5-flash-image 模型在 API 中可用")
    sys.exit(0)
else:
    print("❌ 部分測試失敗")
    print("=" * 60)
    sys.exit(1)
