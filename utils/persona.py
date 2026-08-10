import re
from typing import Optional

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
    if (
        re.search(r"\b(1\s*\+?\s*1|你是誰|幾歲|你會做什麼)\b", content)
        or len(content.strip()) < 6
    ):
        return "arrogant"

    # 技術或設定問題 → neutral
    if any(
        word in content
        for word in ["怎麼", "如何", "設定", "伺服器", "功能", "api", "幫我"]
    ):
        return "neutral"

    # 諷刺/玩笑口吻 → sarcastic
    if any(word in content for word in ["笑死", "你行不行", "壞掉", "爛", "廢物"]):
        return "sarcastic"

    # emoji、語助詞 → playful
    if re.search(r"[😂😆🤣🫠⭐️～！？]", content) or any(
        p in content for p in ["啦", "喔", "嘆", "啊"]
    ):
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
    is_joking: bool = False,
) -> str:
    """
    動態構建 Persona 提示詞，風格自然流暢。

    Args:
        bot_name: 機器人名稱
        tone: 情感語調
        user_impression: 對使用者的印象（如 "活躍", "請求幫助多", "喜歡開玩笑"）
        is_urgent: 使用者是否看起來很急
        is_joking: 使用者是否在開玩笑
    """

    # 構建動態上下文 - 自然融入提示詞
    context = []
    if is_urgent:
        context.append("用戶看起來很急，直切重點，言簡意賅")
    if is_joking:
        context.append("用戶在開玩笑，可以打趣回應，增加互動的趣味")
    if user_impression:
        context.append(f"根據以往交互，這位用戶{user_impression}")

    context_text = "；".join(context) + "。" if context else ""

    tone_data = {
        "arrogant": {
            "style": f"你是 {bot_name}，對簡單重複的問題有點不耐煩，但這不是冷漠，而是想推動用戶思考。{context_text}",
            "vibe": "冷靜但有溫度，偶爾毒舌，最終會耐心幫助",
        },
        "neutral": {
            "style": f"你是 {bot_name}，友善、理性、樂於幫忙。像一個靠譜的朋友，清楚明確地指引方向。{context_text}",
            "vibe": "溫和、有邏輯、值得信任",
        },
        "sarcastic": {
            "style": f"你是 {bot_name}，幽默風趣，用諷刺化解尷尬氣氛，但始終是善意的。{context_text}",
            "vibe": "調皮但暖心，不會真傷害人，反而是在互動中製造樂趣",
        },
        "playful": {
            "style": f"你是 {bot_name}，親切活潑，回應時帶著調皮感，適度用表情符號增加親近感。{context_text}",
            "vibe": "輕鬆、有趣、像個朋友",
        },
        "adaptive": {
            "style": f"你是 {bot_name}，能根據用戶的語氣和需求自然切換風格。{context_text}",
            "vibe": "同理心強、觀察敏銳、如朋友般自然",
        },
    }

    data = tone_data.get(tone, tone_data["neutral"])

    return f"""{data['style']}

回應時保持{data['vibe']}的感覺。直接、簡潔，避免冗長和重複。"""
