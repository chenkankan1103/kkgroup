import os
import sys
sys.path.insert(0, '/home/e193752468/kkgroup')

from dotenv import load_dotenv
load_dotenv('/home/e193752468/kkgroup/.env')

print("=== AI API 測試 ===")

# 檢查環境變數
api_key = os.getenv("AI_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")

print(f"✓ AI_API_KEY 已設定: {bool(api_key)}")
print(f"✓ GROQ_API_KEY 已設定: {bool(groq_key)}")

# 測試 google.generativeai
try:
    import google.generativeai as genai
    print("✓ google.generativeai 導入成功")
    
    genai.configure(api_key=api_key)
    print("✓ Gemini API 配置成功")
    
    # 測試一個簡單的調用
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("說一個笑話")
    print("✅ Gemini API 可以運作！")
    print(f"回應: {response.text[:100]}...")
    
except Exception as e:
    print(f"❌ Gemini API 失敗: {e}")
    print("轉使用 Groq API...")
