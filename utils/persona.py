import re
from typing import Optional, Dict

# 情感 → Emoji 映射（輕量級，減少 token）
EMOTION_EMOJI_MAP = {
    "arrogant": ["😏", "😤", "🙄"],
    "neutral": ["🤔", "✨", "👍"],
    "sarcastic": ["😏", "💀", "🙃"],
    "playful": ["😆", "🎉", "🫡"],
    "dramatic": ["😱", "🎭", "⚡"],
    "tough": ["💪", "🤐", "⚔️"],
    "adaptive": ["👍", "✌️", "💬"],
}

def analyze_tone(message_content: str) -> str:
    """輕量級情感分析 - 減少計算量"""
    content = message_content.lower()

    # 重複或簡單問題 → arrogant
    if re.search(r"\b(1\s*\+?\s*1|你是誰|幾歲|你會做什麼)\b", content) or len(content.strip()) < 6:
        return "arrogant"

    # 技術或設定問題 → neutral
    if any(word in content for word in ["怎麼", "如何", "設定", "伺服器", "功能", "api", "幫我"]):
        return "neutral"

    # 諷刺/玩笑口吻 → sarcastic
    if any(word in content for word in ["笑死", "你行不行", "壞掉", "爛", "廢物"]):
        return "sarcastic"

    # emoji、語助詞 → playful
    if re.search(r"[😂😆🤣🫠⭐️～！？]", content) or any(p in content for p in ["啦", "喔", "嘆", "啊"]):
        return "playful"

    # 否則 → neutral
    return "neutral"


def get_emotion_emoji(tone: str) -> str:
    """根據情感返回隨機 emoji（無外部依賴）"""
    import random
    emojis = EMOTION_EMOJI_MAP.get(tone, ["✨"])
    return random.choice(emojis)


def build_persona_prompt(
    bot_name: str, 
    tone: str = "default",
    user_impression: Optional[str] = None,
    is_urgent: bool = False,
    is_joking: bool = False
) -> str:
    """
    動態構建 Persona 提示詞。
    
    Args:
        bot_name: 機器人名稱
        tone: 情感語調
        user_impression: 對使用者的印象（如 "活躍", "請求幫助多", "喜歡開玩笑"）
        is_urgent: 使用者是否看起來很急
        is_joking: 使用者是否在開玩笑
    """
    
    # 構建動態修飾符 - 減少重複代碼
    modifiers = []
    if user_impression:
        modifiers.append(f"這位使用者：{user_impression}")
    if is_urgent:
        modifiers.append("使用者看起來很急，你應該快速直切重點")
    if is_joking:
        modifiers.append("使用者在開玩笑，你也可以打趣回應")
    
    modifier_text = "（" + "，".join(modifiers) + "）" if modifiers else ""
    
    tone_data = {
        "arrogant": {
            "base": f"你是「{bot_name}」，對重複問題略帶不耐{modifier_text}",
            "traits": "冷靜、偶爾毒舌、但會展現溫度",
            "examples": ["這麼簡單你也問？", "再想想，你一定會的"]
        },
        "neutral": {
            "base": f"你是「{bot_name}」，理性且友善{modifier_text}",
            "traits": "溫和、有條理、樂於幫助",
            "examples": ["這個問題問得不錯", "不用擔心，我來幫你"]
        },
        "sarcastic": {
            "base": f"你是「{bot_name}」，風趣且有毒舌{modifier_text}",
            "traits": "幽默、用諷刺化解尷尬、不會真傷害人",
            "examples": ["這勇氣可嘉", "我就勉強幫你吧"]
        },
        "playful": {
            "base": f"你是「{bot_name}」，親切且調皮{modifier_text}",
            "traits": "有趣、常用 emoji、打趣",
            "examples": ["你這樣問很可愛", "好欸，3 秒解決你"]
        },
        "adaptive": {
            "base": f"你是「{bot_name}」，能根據情境切換風格{modifier_text}",
            "traits": "同理心強、觀察力敏銳、像朋友般自然",
            "examples": ["你是不是有點卡住", "沒關係，這很常見"]
        }
    }
    
    data = tone_data.get(tone, tone_data["neutral"])
    
    return f"""【角色設定】
{data['base']}

【語氣特徵】
{data['traits']}

【回應範例】
{' | '.join(data['examples'])}

【關鍵原則】
- 簡潔直接（減少廢話，減少 token）
- 如果使用者急，立即給重點
- 適度用表情符號增加人味，但不過度
"""
