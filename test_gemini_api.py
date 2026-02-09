#!/usr/bin/env python3
"""
Google Gemini API 存活測試腳本
用於診斷 API Key 和環境設置是否正確
"""

import os
import sys
from dotenv import load_dotenv

print("=" * 60)
print("🔍 Google Gemini API 診斷工具")
print("=" * 60)

# 載入 .env
load_dotenv()

# 1️⃣ 檢查 API Key 是否被讀取
print("\n1️⃣ 檢查環境變數...")
api_key = os.getenv("AI_API_KEY")
if not api_key:
    print("❌ 錯誤：找不到 AI_API_KEY 環境變數！")
    print("   請確認 .env 檔案中有以下行：")
    print("   AI_API_KEY=YOUR_API_KEY_HERE")
    sys.exit(1)
else:
    print(f"✅ 找到 API Key: {api_key[:20]}...{api_key[-10:]}")

# 2️⃣ 嘗試導入 google.generativeai
print("\n2️⃣ 檢查 google.generativeai 套件...")
try:
    import google.generativeai as genai
    print("✅ google.generativeai 已安裝")
except ImportError:
    print("❌ 未安裝 google.generativeai")
    print("   請執行: pip install google-generativeai")
    sys.exit(1)

# 3️⃣ 嘗試配置 API Key
print("\n3️⃣ 配置 API Key...")
try:
    genai.configure(api_key=api_key)
    print("✅ API Key 配置成功")
except Exception as e:
    print(f"❌ API Key 配置失敗: {e}")
    sys.exit(1)

# 4️⃣ 列出可用模型
print("\n4️⃣ 列出可用的 Gemini 模型...")
try:
    models = genai.list_models()
    gemini_models = [m for m in models if 'gemini' in m.name.lower()]
    if gemini_models:
        print("✅ 找到以下 Gemini 模型:")
        for model in gemini_models:
            print(f"   - {model.name}")
    else:
        print("⚠️ 未找到 Gemini 模型")
except Exception as e:
    print(f"❌ 列舉模型失敗: {e}")
    print("   這可能意味著 GCP 專案未啟用 Generative Language API")
    sys.exit(1)

# 5️⃣ 嘗試調用 API
print("\n5️⃣ 測試 API 調用（簡單提示）...")
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("請用one word簡短回答：你是什麼？")
    
    if response.text:
        print(f"✅ API 調用成功！")
        print(f"   回應: {response.text[:100]}")
    else:
        print("❌ API 未返回文本")
except Exception as e:
    print(f"❌ API 調用失敗: {e}")
    print(f"   錯誤類型: {type(e).__name__}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ 所有測試通過！API 應該可以正常運作")
print("=" * 60)
