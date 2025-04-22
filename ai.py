import discord
from discord.ext import commands
import aiohttp
import os
from utils.persona import build_persona_prompt, analyze_tone
from utils.memory import add_to_history, get_history
from dotenv import load_dotenv
load_dotenv()
AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_API_MODEL = os.getenv("AI_API_MODEL", "gpt-3.5-turbo")

async def setup_ai(tree, client):
    @client.event
    async def on_message(message: discord.Message):
        # 忽略機器人自己的消息
        if message.author.bot:
            return
        # 檢查是否提到機器人
        if not client.user.mentioned_in(message):
            return
        # 分析語氣，決定機器人回應風格
        tone = analyze_tone(message.content)
        # 根據語氣與內容構建人設
        prompt = build_persona_prompt(bot_name="KK園區中控室", tone=tone)
        user_id = message.author.id
        user_input = message.clean_content.replace(f"<@{client.user.id}>", "").strip()
        # 儲存使用者輸入
        add_to_history(user_id, user_input)
        # 嘗試取得前一則對話
        past_messages = get_history(user_id)
        last_prompt = past_messages[-2] if len(past_messages) >= 2 else None
        # 判斷是否需要上下文（太短就需要）
        use_context = len(user_input) <= 6 or any(kw in user_input.lower() for kw in ["然後", "所以", "呢", "咧", "?"])
        if use_context and last_prompt:
            full_prompt = last_prompt + "\n" + user_input
        else:
            full_prompt = user_input
        # 建構人設
        persona = build_persona_prompt(client.user.name, tone=tone)
        # 向 AI API 發送請求
        async with message.channel.typing():
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": AI_API_MODEL,
                    "messages": [
                        {"role": "system", "content": persona},
                        {"role": "user", "content": full_prompt}
                    ]
                }
                async with session.post(AI_API_URL, headers=headers, json=payload) as resp:
                    data = await resp.json()
            # 處理回應
            if "choices" in data and len(data["choices"]) > 0:
                reply = data["choices"][0]["message"]["content"]
            else:
                reply = "中控室接收不到有意義的訊號，請再問一次。"
        # 回覆訊息
        await message.reply(reply)