"""
Google Generative AI API 封装模块
提供與 Groq OpenAI 相容的介面
"""

import os
import aiohttp
import json
from typing import List, Dict, Optional

class GoogleAIClient:
    """Google Generative AI 用戶端"""
    
    def __init__(self):
        self.api_key = os.getenv("AI_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1"
        self.model = "gemini-pro"
        
        if not self.api_key:
            print("❌ AI_API_KEY 未設置")
    
    async def call_api(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> Optional[str]:
        """
        調用 Google Generative AI API
        
        Args:
            messages: 訊息列表 [{'role': 'user'/'assistant', 'content': '...'}, ...]
            temperature: 溫度參數 (0-1)
            max_tokens: 最大輸出 tokens
        
        Returns:
            生成的文本或 None
        """
        try:
            if not self.api_key:
                print("❌ AI_API_KEY 未設置")
                return None
            
            # 將訊息轉換為 Google 格式
            contents = self._convert_messages(messages)
            
            url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                }
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        result = await response.json()
                        # 提取生成的文本
                        if result.get('candidates'):
                            content = result['candidates'][0].get('content', {})
                            if content.get('parts'):
                                return content['parts'][0].get('text', '')
                        return None
                    else:
                        error_text = await response.text()
                        print(f"❌ Google API 錯誤 {response.status}: {error_text}")
                        return None
        
        except Exception as e:
            print(f"❌ Google API 調用失敗: {e}")
            return None
    
    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[Dict]:
        """
        將 OpenAI 格式的訊息轉換為 Google 格式
        
        OpenAI 格式: [{'role': 'user'/'assistant', 'content': '...'}]
        Google 格式: [{'role': 'user'/'model', 'parts': [{'text': '...'}]}]
        """
        converted = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            # 轉換 role
            google_role = 'model' if role == 'assistant' else 'user'
            
            converted.append({
                'role': google_role,
                'parts': [{'text': content}]
            })
        
        return converted


# 全局客戶端實例
_google_client = None

def get_google_client() -> GoogleAIClient:
    """獲取 Google AI 客戶端單例"""
    global _google_client
    if _google_client is None:
        _google_client = GoogleAIClient()
    return _google_client


async def call_google_ai(
    messages: List[Dict[str, str]], 
    temperature: float = 0.7,
    max_tokens: int = 2000
) -> Optional[str]:
    """
    簡便函數：調用 Google Generative AI
    """
    client = get_google_client()
    return await client.call_api(messages, temperature, max_tokens)


async def translate_with_google(text: str) -> Optional[str]:
    """
    使用 Google AI 翻譯文本
    
    Args:
        text: 要翻譯的文本
    
    Returns:
        翻譯結果或原文本
    """
    messages = [
        {
            'role': 'system',
            'content': 'You are a translator. Translate Chinese to English for image generation prompts. Keep it concise and descriptive.'
        },
        {
            'role': 'user',
            'content': f'Translate this to English for image generation: {text}'
        }
    ]
    
    result = await call_google_ai(messages, temperature=0.3, max_tokens=100)
    return result if result else text
