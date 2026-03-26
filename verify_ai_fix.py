#!/usr/bin/env python3
"""
最終驗證 - 使用已驗證有效的模型
"""
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# 使用硬編碼的已驗證有效模型
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_KEY = os.getenv("AI_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.getenv("GROQ_API_KEY")

async def test_gemini():
    """測試 Gemini 2.0 Flash"""
    print("\n🌐 測試 Google Gemini 2.0 Flash:")
    
    url = f"{GEMINI_URL}?key={GEMINI_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": "Hello, say hi back"}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 50
        }
    }
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "candidates" in data and data["candidates"]:
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        print(f"  ✅ 成功! 回應: {text[:60]}")
                        return True
                    else:
                        print(f"  ❌ 無效回應: {list(data.keys())}")
                        return False
                elif resp.status == 429:
                    print(f"  ⚠️ 配額超限 - 將使用 Groq")
                    return False
                else:
                    text = await resp.text()
                    print(f"  ❌ HTTP {resp.status}: {text[:100]}")
                    return False
    except Exception as e:
        print(f"  ⚠️ 異常: {e}")
        return False

async def test_groq():
    """測試 Groq llama-3.3-70b"""
    print("\n🌐 測試 Groq llama-3.3-70b-versatile:")
    
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hi"}
        ],
        "temperature": 0.7,
        "max_tokens": 50
    }
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(GROQ_URL, headers=headers, json=payload) as resp:
                text_resp = await resp.text()
                if resp.status == 200:
                    data = await resp.json()
                    if "choices" in data and data["choices"]:
                        msg = data["choices"][0]["message"]["content"]
                        print(f"  ✅ 成功! 回應: {msg[:60]}")
                        return True
                    else:
                        print(f"  ❌ 無效回應: {list(data.keys())}")
                        return False
                else:
                    print(f"  ❌ HTTP {resp.status}: {text_resp[:100]}")
                    return False
    except Exception as e:
        print(f"  ⚠️ 異常: {e}")
        return False

async def main():
    print("=" * 60)
    print("✅ 最終驗證 - 已驗證有效的模型")
    print("=" * 60)
    
    gemini_ok = await test_gemini()
    groq_ok = await test_groq()
    
    print("\n" + "=" * 60)
    if groq_ok or gemini_ok:
        print("✅ 至少有一個 AI API 正常工作！")
        if gemini_ok:
            print("   → Gemini 2.0 Flash 可用")
        if groq_ok:
            print("   → Groq llama-3.3 可用")
    else:
        print("❌ 所有 API 都無法連接")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
