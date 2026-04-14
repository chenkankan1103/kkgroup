"""
Prompt-Based Function Calling System
===========================================

這個模塊實現了基於提示的工具呼叫系統，讓不支持 native function calling 的 API
(如 GitHub Models 和 Groq) 也能實現「工具呼叫」功能。

核心思想：
1. 在系統提示中詳細說明可用的工具及其參數
2. 教導模型以特定的 JSON 格式輸出工具呼叫
3. 解析模型輸出中的 <FUNCTION_CALL> 標籤
4. 執行相應的工具並返回結果

使用示例：
    system_with_tools = build_system_prompt_with_tools(base_prompt)
    # 現在系統提示包含工具描述和呼叫格式說明
    
    # 調用模型後
    response = model_response
    calls = extract_function_calls(response)
    # 得到: [{"name": "get_kkcoin_balance", "args": {"user_id": "123"}}]
"""

import re
import json
from typing import List, Dict, Any
from agent_tools import get_gemini_tools_spec


def build_system_prompt_with_tools(base_prompt: str) -> str:
    """
    構建包含工具定義的系統提示
    
    Args:
        base_prompt: 基礎系統提示
        
    Returns:
        包含工具說明的增強系統提示
    """
    try:
        # 獲取工具 spec
        tools_spec = get_gemini_tools_spec()
        if not tools_spec or "functionDeclarations" not in tools_spec[0]:
            return base_prompt
        
        tools = tools_spec[0]["functionDeclarations"]
        
        # 構建工具說明文本
        tools_description = "\n【可用工具】\n"
        for tool in tools:
            tools_description += f"\n工具名: {tool['name']}\n"
            tools_description += f"說明: {tool['description']}\n"
            
            # 添加參數資訊
            if "parameters" in tool and "properties" in tool["parameters"]:
                tools_description += "參數:\n"
                for param_name, param_info in tool["parameters"]["properties"].items():
                    param_desc = param_info.get("description", "")
                    param_type = param_info.get("type", "STRING")
                    tools_description += f"  - {param_name} ({param_type}): {param_desc}\n"
            tools_description += "\n"
        
        # 添加使用說明
        tools_usage = """
【工具呼叫格式】
當你需要呼叫工具時，請按以下格式輸出：

<FUNCTION_CALL>
{
  "name": "工具名",
  "args": {
    "參數1": "值1",
    "參數2": "值2"
  }
}
</FUNCTION_CALL>

例如，查詢 KK幣時：
<FUNCTION_CALL>
{
  "name": "get_kkcoin_balance",
  "args": {
    "user_id": "123456789"
  }
}
</FUNCTION_CALL>

重要：
1. 只在真正需要時呼叫工具
2. 一個回應中可以有多個工具呼叫
3. 工具呼叫後，系統會在下一輪對話中返回結果
4. 始終使用上述格式，不要偏離
"""
        
        return base_prompt + "\n" + tools_description + tools_usage
        
    except Exception as e:
        print(f"⚠️ 構建工具提示失敗: {e}")
        return base_prompt


def extract_function_calls(response: str) -> List[Dict[str, Any]]:
    """
    從模型回應中提取工具呼叫
    
    Args:
        response: 模型的文字回應
        
    Returns:
        工具呼叫列表: [{"name": "...", "args": {...}}, ...]
    """
    calls = []
    
    # 尋找所有 <FUNCTION_CALL>...</FUNCTION_CALL> 標籤
    pattern = r'<FUNCTION_CALL>\s*(\{.*?\})\s*</FUNCTION_CALL>'
    matches = re.findall(pattern, response, re.DOTALL)
    
    for match in matches:
        try:
            call_data = json.loads(match)
            if "name" in call_data and "args" in call_data:
                calls.append(call_data)
        except json.JSONDecodeError:
            print(f"⚠️ 無法解析工具呼叫 JSON: {match[:100]}")
    
    return calls


def extract_response_without_calls(response: str) -> str:
    """
    移除工具呼叫標籤，只保留文本部分
    
    Args:
        response: 原始回應
        
    Returns:
        移除 <FUNCTION_CALL> 標籤後的文本
    """
    return re.sub(r'<FUNCTION_CALL>\s*\{.*?\}\s*</FUNCTION_CALL>', '', response, flags=re.DOTALL).strip()


def execute_extracted_calls(calls: List[Dict[str, Any]], caller_id: int = None) -> Dict[str, str]:
    """
    執行提取的工具呼叫
    
    Args:
        calls: 工具呼叫列表
        caller_id: 呼叫者 ID（用於工具執行時傳遞上下文）
        
    Returns:
        工具結果映射: {call_identifier: result}
    """
    import agent_tools
    
    results = {}
    for i, call in enumerate(calls):
        tool_name = call.get("name", "")
        tool_args = call.get("args", {})
        
        try:
            result = agent_tools.dispatch_tool(
                tool_name, tool_args, caller_id=caller_id
            )
            results[f"call_{i}"] = str(result)
        except Exception as e:
            results[f"call_{i}"] = f"❌ 工具執行失敗: {str(e)}"
    
    return results


def format_call_results_for_context(calls: List[Dict[str, Any]], results: Dict[str, str]) -> str:
    """
    將工具呼叫結果格式化為上下文，用於回傳給模型
    
    Args:
        calls: 原始工具呼叫列表
        results: 工具執行結果
        
    Returns:
        格式化的結果字符串
    """
    context = "\n【工具執行結果】\n"
    for i, call in enumerate(calls):
        tool_name = call.get("name", "")
        call_key = f"call_{i}"
        result = results.get(call_key, "未執行")
        context += f"\n工具: {tool_name}\n結果: {result}\n"
    
    return context
