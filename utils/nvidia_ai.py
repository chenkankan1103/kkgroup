"""
NVIDIA AI API 封装模块
提供與 OpenAI 相容的介面，專門用於 GitHub debug 和錯誤分析
"""

import asyncio
import logging
import os
import aiohttp
import json
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)

class NVIDIAAIClient:
    """NVIDIA AI 用戶端"""
    _last_timeout_log_key = ""
    _last_timeout_log_at = 0.0
    _timeout_log_cooldown_sec = 300
    
    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY")
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.timeout = int(os.getenv("NVIDIA_API_TIMEOUT", "120"))
        
        # 推薦的強大模型，適用於 debug 和代碼分析
        self.models = {
            "deepseek-v4-pro": "deepseek-ai/deepseek-v4-pro",  # 最強的編程模型
            "nemotron-super": "nvidia/nemotron-3-super-120b-a12b",  # NVIDIA 最強模型
            "mistral-medium": "mistralai/mistral-medium-3.5-128b",  # 平衡性能
            "deepseek-flash": "deepseek-ai/deepseek-v4-flash"  # 快速版本
        }
        
        # 預設使用 deepseek-v4-pro（最強的編程模型）
        self.model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-pro")
        
        if not self.api_key:
            print("❌ NVIDIA_API_KEY 未設置")
    
    async def call_api(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.3,
        max_tokens: int = 2000,
        model: str = None,
        **kwargs
    ) -> Optional[str]:
        """
        調用 NVIDIA API
        
        Args:
            messages: 訊息列表 [{'role': 'user'/'assistant', 'content': '...'}, ...]
            temperature: 溫度參數 (0-1)
            max_tokens: 最大輸出 tokens
            model: 使用的模型，若未指定則使用預設模型
        
        Returns:
            生成的文本或 None
        """
        try:
            if not self.api_key:
                logger.warning("NVIDIA_API_KEY 未設置")
                return None
            
            # 使用指定模型或預設模型
            selected_model = model or self.model
            request_timeout = int(kwargs.get("timeout") or self.timeout)
            
            url = f"{self.base_url}/chat/completions"
            
            payload = {
                "model": selected_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=request_timeout)) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        # 提取生成的文本
                        if result.get('choices'):
                            content = result['choices'][0].get('message', {}).get('content', '')
                            return content
                        return None
                    else:
                        error_text = await response.text()
                        logger.warning(f"NVIDIA API 錯誤 {response.status}: {error_text}")
                        return None

        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError):
            self._log_timeout_once(selected_model, request_timeout)
            return None
        except Exception as e:
            logger.warning(f"NVIDIA API 調用失敗: {type(e).__name__}: {e}")
            return None

    @classmethod
    def _log_timeout_once(cls, model: str, timeout_sec: int):
        loop = asyncio.get_running_loop()
        now = loop.time()
        log_key = f"{model}:{timeout_sec}"
        if log_key == cls._last_timeout_log_key and now - cls._last_timeout_log_at < cls._timeout_log_cooldown_sec:
            return

        cls._last_timeout_log_key = log_key
        cls._last_timeout_log_at = now
        logger.warning(
            f"NVIDIA API timeout / model={model} / timeout={timeout_sec}s；本次已改走 fallback，5 分鐘內不重複刷同類 timeout"
        )
    
    async def analyze_error_logs(
        self, 
        error_logs: str,
        system_info: str = ""
    ) -> Optional[Dict]:
        """
        使用 AI 分析錯誤日誌，專門為 GitHub debug 設計
        
        Args:
            error_logs: 錯誤日誌文本
            system_info: 系統資訊
        
        Returns:
            分析結果字典或 None
        """
        analysis_prompt = f"""
你是KKGroup Discord Bot系統的AI除錯專家。

系統環境：
- GCP VM: e2-micro (1GB RAM + 4GB swap)
- 三個Bot服務: bot.service, shopbot.service, uibot.service
- 技術棧: Python 3.11 + Discord.py + systemd

{system_info}

錯誤日誌：
{error_logs}

請分析：
1. 根本原因分析
2. 影響範圍評估
3. 具體修復步驟
4. 預防措施建議

請以JSON格式回覆：
{{
    "root_cause": "主要原因",
    "impact": "影響評估",
    "fix_steps": ["步驟1", "步驟2"],
    "prevention": ["預防措施1", "預防措施2"],
    "confidence": 0.85,
    "urgency": "high/medium/low"
}}
"""
        
        messages = [
            {"role": "system", "content": "你是KKGroup Discord Bot系統的AI除錯專家，請以JSON格式回覆分析結果。"},
            {"role": "user", "content": analysis_prompt}
        ]
        
        result = await self.call_api(messages, temperature=0.3, max_tokens=1500)
        
        if result:
            try:
                # 嘗試解析 JSON
                return json.loads(result)
            except json.JSONDecodeError:
                # 如果解析失敗，返回原始文本
                return {"raw_analysis": result}
        
        return None
    
    async def generate_fix_code(
        self, 
        analysis_result: Dict,
        error_context: str = ""
    ) -> Optional[str]:
        """
        根據分析結果生成修復代碼
        
        Args:
            analysis_result: AI 分析結果
            error_context: 錯誤上下文
        
        Returns:
            修復代碼或 None
        """
        fix_prompt = f"""
基於以下AI分析結果，生成修復代碼：

分析結果：
{json.dumps(analysis_result, ensure_ascii=False, indent=2)}

錯誤上下文：
{error_context}

請生成：
1. 具體的修復腳本
2. 修復後的驗證方法
3. 預防措施建議

請以JSON格式回覆：
{{
    "fix_script": "修復代碼",
    "verification": "驗證方法",
    "prevention": "預防措施"
}}
"""
        
        messages = [
            {"role": "system", "content": "你是KKGroup Discord Bot系統的修復專家，請以JSON格式回覆修復代碼。"},
            {"role": "user", "content": fix_prompt}
        ]
        
        result = await self.call_api(messages, temperature=0.2, max_tokens=2000)
        
        if result:
            try:
                # 嘗試解析 JSON
                fix_data = json.loads(result)
                return fix_data.get("fix_script", result)
            except json.JSONDecodeError:
                # 如果解析失敗，返回原始文本
                return result
        
        return None
    
    def get_available_models(self) -> Dict[str, str]:
        """獲取可用模型列表"""
        return self.models


# 全局客戶端實例
_nvidia_client = None

def get_nvidia_client() -> NVIDIAAIClient:
    """獲取 NVIDIA AI 客戶端單例"""
    global _nvidia_client
    if _nvidia_client is None:
        _nvidia_client = NVIDIAAIClient()
    return _nvidia_client


async def call_nvidia_ai(
    messages: List[Dict[str, str]], 
    temperature: float = 0.3,
    max_tokens: int = 2000,
    model: str = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    簡便函數：調用 NVIDIA AI
    """
    client = get_nvidia_client()
    kwargs = {"timeout": timeout} if timeout is not None else {}
    return await client.call_api(messages, temperature, max_tokens, model, **kwargs)


async def analyze_github_error(
    error_logs: str,
    system_info: str = ""
) -> Optional[Dict]:
    """
    簡便函數：分析 GitHub 錯誤日誌
    """
    client = get_nvidia_client()
    return await client.analyze_error_logs(error_logs, system_info)


async def generate_auto_fix(
    analysis_result: Dict,
    error_context: str = ""
) -> Optional[str]:
    """
    簡便函數：生成自動修復代碼
    """
    client = get_nvidia_client()
    return await client.generate_fix_code(analysis_result, error_context)


# 測試函數
async def test_nvidia_api():
    """測試 NVIDIA API 連接性和模型性能"""
    print("🚀 開始測試 NVIDIA API...")
    
    # 確保載入環境變數
    from dotenv import load_dotenv
    load_dotenv()
    
    client = get_nvidia_client()
    
    if not client.api_key:
        print("❌ NVIDIA_API_KEY 未設置，請先設置環境變數")
        return
    
    print(f"✅ API Key 已設置")
    print(f"🤖 可用模型: {list(client.models.keys())}")
    
    # 測試各個模型的性能
    test_message = "你好，請簡單介紹一下你自己，並說明你擅長的領域。"
    
    for model_name, model_id in client.models.items():
        print(f"\n🧪 測試模型: {model_name} ({model_id})")
        
        messages = [
            {"role": "user", "content": test_message}
        ]
        
        try:
            result = await client.call_api(messages, model=model_id, max_tokens=200)
            
            if result:
                print(f"✅ {model_name} 測試成功")
                print(f"📝 回應: {result[:100]}...")
            else:
                print(f"❌ {model_name} 測試失敗")
                
        except Exception as e:
            print(f"❌ {model_name} 測試錯誤: {e}")
    
    # 測試錯誤分析功能
    print(f"\n🔍 測試錯誤分析功能...")
    
    sample_error_log = """
    [ERROR] 2024-05-12 12:00:00 - Discord bot disconnected
    Traceback (most recent call last):
      File "/home/e193752468/kkgroup/bots/bot.py", line 150, in on_ready
        await tree.sync()
    discord.errors.HTTPException: 429 Too Many Requests
    """
    
    analysis = await client.analyze_error_logs(sample_error_log)
    
    if analysis:
        print("✅ 錯誤分析測試成功")
        print(f"📊 分析結果: {json.dumps(analysis, ensure_ascii=False, indent=2)[:200]}...")
    else:
        print("❌ 錯誤分析測試失敗")
    
    print("\n🎯 推薦模型用於 GitHub debug:")
    print("1. deepseek-v4-pro - 最強的編程和邏輯分析能力")
    print("2. nemotron-super - NVIDIA 自家最強模型，綜合性能最佳")
    print("3. mistral-medium - 平衡性能和速度")


if __name__ == "__main__":
    import asyncio
    
    async def main():
        await test_nvidia_api()
    
    asyncio.run(main())
