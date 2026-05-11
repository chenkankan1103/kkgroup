"""KK園區 AI Client (LiteLLM 版本)
===============================================

使用 LiteLLM 統一多個 AI 提供商：
- Gemini 2.0 Flash (主要)
- Gemini 2.0 Flash (備用)
- Groq llama-3.3-70b (降級)
- 未來可輕鬆擴展其他模型

優勢：
- 統一 API 介面
- 自動降級和重試
- 內建速率限制保護
- 詳細使用統計
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

try:
    from litellm import completion, acompletion
    import litellm
    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False
    print("⚠️ LiteLLM 未安裝，將使用傳統API")

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 配置 ────────────────────────────────────────────────────────────────────
GEMINI_KEY    = os.getenv("AI_API_KEY")
GEMINI_KEY_BK = os.getenv("AI_API_KEY_BACKUP")
GEMINI_MODEL  = os.getenv("AI_API_MODEL", "gemini/gemini-2.0-flash")
GROQ_KEY      = os.getenv("GROQ_API_KEY")
GROQ_MODEL    = os.getenv("GROQ_API_MODEL", "groq/llama-3.3-70b-versatile")
SAMBA_KEY     = os.getenv("SAMBA_API_KEY")
SAMBA_MODEL   = os.getenv("SAMBA_API_MODEL", "sambanova/Meta-Llama-3.1-8B-Instruct")

# LiteLLM 模型配置
MODEL_LIST = [
    {
        "model_name": "gemini-main",
        "litellm_params": {
            "model": GEMINI_MODEL,
            "api_key": GEMINI_KEY,
            "temperature": 0.7,
            "max_tokens": 800,
        }
    },
    {
        "model_name": "gemini-backup", 
        "litellm_params": {
            "model": GEMINI_MODEL,
            "api_key": GEMINI_KEY_BK,
            "temperature": 0.7,
            "max_tokens": 800,
        }
    },
    {
        "model_name": "sambanova-coding",
        "litellm_params": {
            "model": SAMBA_MODEL,
            "api_key": SAMBA_KEY,
            "temperature": 0.2,
            "max_tokens": 1000,
        }
    },
    {
        "model_name": "groq-fallback",
        "litellm_params": {
            "model": GROQ_MODEL,
            "api_key": GROQ_KEY,
            "temperature": 0.7,
            "max_tokens": 500,
        }
    }
]

# 設定 LiteLLM
if _LITELLM_AVAILABLE:
    litellm.set_verbose = False  # 關閉詳細日誌
    litellm.drop_params = True   # 自動清理不支援的參數


class LiteLLMClient:
    """統一的 AI 客戶端，使用 LiteLLM 管理多個提供商"""
    
    def __init__(self):
        self._cooldowns: Dict[str, float] = {}
        self._model_list = [m for m in MODEL_LIST if m["litellm_params"].get("api_key")]
        
    def _is_cooling(self, model_name: str) -> bool:
        """檢查模型是否在冷卻期"""
        exp = self._cooldowns.get(model_name, 0)
        if time.time() < exp:
            remaining = int(exp - time.time())
            logger.warning(f"❄️ {model_name} 冷卻中（{remaining}s 後恢復）")
            return True
        self._cooldowns.pop(model_name, None)
        return False
    
    def _cool(self, model_name: str, secs: int = 60):
        """設置模型冷卻"""
        self._cooldowns[model_name] = time.time() + secs
        logger.warning(f"⏸️ {model_name} 進入冷卻 {secs}s")
    
    async def acomplete(
        self,
        messages: List[Dict[str, str]],
        tools_spec: Optional[List[Dict]] = None,
        *,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> Optional[Dict]:
        """異步完成 AI 請求，支援工具調用"""
        
        if not _LITELLM_AVAILABLE:
            return await self._fallback_completion(messages, tools_spec)
        
        for model_config in self._model_list:
            model_name = model_config["model_name"]
            
            if self._is_cooling(model_name):
                continue
            
            # 準備參數
            params = model_config["litellm_params"].copy()
            params["messages"] = messages
            params["timeout"] = timeout
            
            if tools_spec:
                params["tools"] = tools_spec
            
            # 重試機制
            for attempt in range(max_retries):
                try:
                    response = await acompletion(**params)
                    
                    if response and response.choices:
                        content = response.choices[0].message
                        return {
                            "content": content.content or "",
                            "tool_calls": getattr(content, "tool_calls", None),
                            "model": model_name,
                            "usage": response.usage._asdict() if response.usage else {}
                        }
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # 速率限制 - 指數退避
                    if "429" in error_msg or "rate limit" in error_msg:
                        delay = 2 ** attempt + 1
                        logger.warning(f"⏳ {model_name} 速率限制，等待 {delay}s (嘗試 {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(delay)
                            continue
                        else:
                            self._cool(model_name, 60)
                            logger.error(f"❌ {model_name} 速率限制，進入冷卻")
                            break
                    
                    # API Key 錯誤
                    elif "api key" in error_msg or "unauthorized" in error_msg:
                        logger.error(f"❌ {model_name} API Key 無效")
                        break
                    
                    # 其他錯誤
                    else:
                        logger.warning(f"⚠️ {model_name} 錯誤: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        else:
                            break
        
        return None
    
    async def _fallback_completion(self, messages: List[Dict[str, str]], tools_spec: Optional[List[Dict]] = None) -> Optional[Dict]:
        """降級到傳統 API 呼叫"""
        try:
            from .AI import LLMClient
            client = LLMClient()
            
            # 嘗試 Gemini
            if GEMINI_KEY:
                contents = []
                for msg in messages:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": msg["content"]}]})
                
                result = await client.gemini(
                    GEMINI_KEY, 
                    "gemini-2.0-flash",
                    "你是一個 AI 助手",
                    contents,
                    tools_spec
                )
                
                if result:
                    parts = result.get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return {
                            "content": parts[0]["text"],
                            "tool_calls": None,
                            "model": "gemini-fallback",
                            "usage": {}
                        }
            
            # 嘗試 Groq
            if GROQ_KEY:
                result = await client.groq(messages)
                if result:
                    return {
                        "content": result,
                        "tool_calls": None,
                        "model": "groq-fallback", 
                        "usage": {}
                    }
        
        except Exception as e:
            logger.error(f"❌ 降級 API 呼叫失敗: {e}")
        
        return None


# ─── 向後兼容的包裝器 ────────────────────────────────────────────────────────

class LLMClient:
    """向後兼容的 LLM 客戶端包裝器"""
    
    def __init__(self):
        self._litellm_client = LiteLLMClient()
    
    async def gemini(
        self,
        api_key: str,
        model: str,
        system: str,
        contents: List[Dict],
        tools_spec: Optional[List[Dict]] = None,
        *,
        label: str = "Gemini",
    ) -> Optional[Dict]:
        """Gemini API 呼叫（包裝器）"""
        # 轉換格式
        messages = [{"role": "system", "content": system}]
        
        for content in contents:
            role = content["role"]
            parts = content.get("parts", [])
            if parts and "text" in parts[0]:
                messages.append({"role": role, "content": parts[0]["text"]})
            elif parts and "functionCall" in parts[0]:
                # 處理工具調用
                fc = parts[0]["functionCall"]
                messages.append({
                    "role": "assistant", 
                    "content": f"調用工具: {fc['name']}({fc.get('args', {})})"
                })
        
        response = await self._litellm_client.acomplete(messages, tools_spec)
        
        if response:
            # 轉換回原始格式
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": response["content"]}]
                    }
                }]
            }
        
        return None
    
    async def groq(
        self,
        messages: List[Dict],
        model: str = "",
        max_tokens: int = 500,
    ) -> Optional[str]:
        """Groq API 呼叫（包裝器）"""
        response = await self._litellm_client.acomplete(messages)
        return response["content"] if response else None


# ─── 使用統計 ────────────────────────────────────────────────────────────────

def get_usage_stats() -> Dict[str, Any]:
    """獲取使用統計"""
    if not _LITELLM_AVAILABLE:
        return {"status": "LiteLLM 未安裝"}
    
    try:
        return {
            "status": "正常",
            "available_models": [m["model_name"] for m in MODEL_LIST if m["litellm_params"].get("api_key")],
            "litellm_version": litellm.__version__ if hasattr(litellm, "__version__") else "unknown",
        }
    except Exception as e:
        return {"status": f"錯誤: {e}"}


# ─── 測試函數 ────────────────────────────────────────────────────────────────

async def test_ai_client():
    """測試 AI 客戶端"""
    client = LiteLLMClient()
    
    test_messages = [
        {"role": "user", "content": "你好，請用繁體中文回答：2+2等於多少？"}
    ]
    
    response = await client.acomplete(test_messages)
    
    if response:
        print(f"✅ 測試成功")
        print(f"📝 回應: {response['content'][:100]}...")
        print(f"🤖 模型: {response['model']}")
        if response['usage']:
            print(f"📊 使用量: {response['usage']}")
    else:
        print("❌ 測試失敗")
    
    return response


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_ai_client())
