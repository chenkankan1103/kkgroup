import os
from dotenv import load_dotenv

load_dotenv('/home/e193752468/kkgroup/.env')
api_key = os.getenv("AI_API_KEY")

import google.generativeai as genai
genai.configure(api_key=api_key)

print("=== 測試 gemini-2.5-flash ===")
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content("用一句臺灣俗語說說你的看法")
    print(f"✅ 成功！")
    print(f"回應: {response.text}")
except Exception as e:
    print(f"❌ 失敗: {e}")
