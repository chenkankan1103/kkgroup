#!/usr/bin/env python3
"""
驗證AI智能模型選擇功能
"""

# 簡單複製ComplexityDetector邏輯來測試
class ComplexityDetector:
    """檢測問題複雜度，以決定使用哪個模型"""
    
    SIMPLE_KEYWORDS = [
        "1+1", "幾歲", "你是誰", "叫什麼", "幾點", "今天天氣",
        "是什麼", "的英文", "縮寫", "歌詞", "名字", "怎麼唸",
        "好不好", "行不行", "要不要", "可不可以"
    ]
    
    COMPLEX_KEYWORDS = [
        "為什麼", "怎麼樣", "應該", "可能", "分析", "比較", "建議",
        "計劃", "策略", "問題", "困擾", "煩惱", "如何", "怎麼辦",
        "設計", "改進", "優化", "邏輯", "推理", "思考", "深入"
    ]
    
    @staticmethod
    def is_complex(message: str) -> bool:
        """判斷問題是否複雜（需要使用gemini-2.5-pro）"""
        message_lower = message.lower()
        
        if len(message) < 20:
            return False
        
        if "。" in message or "，" in message:
            complex_count = sum(1 for kw in ComplexityDetector.COMPLEX_KEYWORDS if kw in message_lower)
            simple_count = sum(1 for kw in ComplexityDetector.SIMPLE_KEYWORDS if kw in message_lower)
            
            if complex_count > simple_count or message.count("?") > 1 or len(message) > 50:
                return True
        
        return False


# 測試案例
test_messages = [
    ("你是誰", False, "簡單問題"),
    ("1+1是多少", False, "簡單算術"),
    ("為什麼園區要這樣設計？你覺得這樣的邏輯是否合理，我們應該如何改進？", True, "複雜分析"),
    ("怎麼辦我遇到了一個比較困擾的問題，需要你的建議。", True, "複雜問題"),
    ("你好，請問一下", False, "短訊息"),
    ("我想深入了解一下園區的運作邏輯，你能分析一下優化策略嗎？", True, "深度思考"),
]

print("=== AI 智能模型選擇驗證 ===\n")
for msg, expected, description in test_messages:
    is_complex = ComplexityDetector.is_complex(msg)
    model = "gemini-2.5-pro (深度思考)" if is_complex else "gemini-2.5-flash (快速回應)"
    checkmark = "✅" if is_complex == expected else "❌"
    print(f"{checkmark} [{description}]")
    print(f"   訊息: {msg}")
    print(f"   模型: {model}")
    print(f"   長度: {len(msg)} 字\n")
