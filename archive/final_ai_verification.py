#!/usr/bin/env python3
"""
最終驗證 - AI 調用鏈測試
確認 Groq llama-3.3-70b-versatile 正常工作
"""
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API_KEY")

async def test_groq_final():
    """測試已驗證有效的 Groq 模型"""
    print("=" * 70)
    print("✅ 最終驗證 - Groq llama-3.3-70b-versatile")
    print("=" * 70)
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello from Groq! KKGroup AI is working!' in 10 words or less"}
        ],
        "temperature": 0.7,
        "max_tokens": 50
    }
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "choices" in data and data["choices"]:
                        msg = data["choices"][0]["message"]["content"]
                        print(f"\n✅ Groq API 正常工作！")
                        print(f"\n📢 回應: {msg}")
                        print("\n" + "=" * 70)
                        print("✅ 中控室已恢復！AI 現在可以正常回應。")
                        print("   - Gemini 1.5 Flash: 配額已用完（待恢復）")
                        print("   - Groq llama-3.3-70b: ✅ 正常（當前備用）")
                        print("=" * 70)
                        return True
                    else:
                        print(f"\n❌ 回應異常: {list(data.keys())}")
                        return False
                else:
                    text = await resp.text()
                    print(f"\n❌ HTTP {resp.status}: {text[:200]}")
                    return False
    except Exception as e:
        print(f"\n⚠️ 異常: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_groq_final())
    exit(0 if success else 1)
