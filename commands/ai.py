import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
import random
import sqlite3
import json
import io
from typing import Optional
from utils.persona import build_persona_prompt, analyze_tone
from utils.memory import add_to_history, get_history
from dotenv import load_dotenv

load_dotenv()

AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_API_MODEL = os.getenv("AI_API_MODEL", "gpt-3.5-turbo")
MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID"))
PUNISHMENT_CHANNEL_ID = int(os.getenv("PUNISHMENT_CHANNEL_ID"))

class Ai(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.punishment_tasks = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not self.bot.user.mentioned_in(message):
            return

        tone = analyze_tone(message.content)
        persona_prompt = build_persona_prompt(bot_name="KK園區中控室", tone=tone)
        user_id = message.author.id
        user_input = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()

        add_to_history(user_id, user_input)
        past_messages = get_history(user_id)
        last_prompt = past_messages[-2] if len(past_messages) >= 2 else None

        use_context = len(user_input) <= 6 or any(kw in user_input.lower() for kw in ["然後", "所以", "呢", "咧", "?"])
        if use_context and last_prompt:
            full_prompt = last_prompt + "\n" + user_input
        else:
            full_prompt = user_input

        async with message.channel.typing():
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": AI_API_MODEL,
                    "messages": [
                        {"role": "system", "content": persona_prompt},
                        {"role": "user", "content": full_prompt}
                    ]
                }
                async with session.post(AI_API_URL, headers=headers, json=payload) as resp:
                    data = await resp.json()

            if "choices" in data and len(data["choices"]) > 0:
                reply = data["choices"][0]["message"]["content"]
            else:
                reply = "中控室接收不到有意義的訊號，請再問一次。"

        await message.reply(reply)

    def get_user_data(self, user_id: int) -> dict:
        """從資料庫獲取使用者資料"""
        try:
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return {}
        except Exception as e:
            print(f"獲取使用者資料錯誤: {e}")
            return {}

    def update_user_stats(self, user_id: int, hp_damage: int = 0, stamina_damage: int = 0) -> dict:
        """更新使用者的HP和體力值"""
        try:
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            
            # 獲取當前數值
            cursor.execute("SELECT hp, stamina FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if result:
                current_hp, current_stamina = result
                new_hp = max(0, current_hp - hp_damage)
                new_stamina = max(0, current_stamina - stamina_damage)
                
                cursor.execute("UPDATE users SET hp = ?, stamina = ? WHERE user_id = ?", 
                             (new_hp, new_stamina, user_id))
                conn.commit()
                conn.close()
                
                return {'hp': new_hp, 'stamina': new_stamina, 'old_hp': current_hp, 'old_stamina': current_stamina}
            
            conn.close()
            return {}
        except Exception as e:
            print(f"更新使用者數據錯誤: {e}")
            return {}

    async def fetch_character_image(self, user_data: dict, is_damaged: bool = False) -> Optional[discord.File]:
        """使用與歡迎訊息相同的 MapleStory.io API 獲取角色圖片"""
        try:
            items = [
                {"itemId": 2000, "region": "GMS", "version": "217"},
                {"itemId": user_data.get('skin', 12000), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('face', 20005), "animationName": "default", "region": "GMS", "version": "217"},
                {"itemId": user_data.get('hair', 30120), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('top', 1040014), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('bottom', 1060096), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('shoes', 1072005), "region": "GMS", "version": "217"}
            ]
            
            # 檢查是否被擊暈或受傷，添加對應效果
            if user_data.get('is_stunned', 0) == 1 or is_damaged:
                items.append({"itemId": 1005411, "region": "GMS", "version": "217"})
            
            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            
            # 根據狀態選擇姿勢
            if user_data.get('is_stunned', 0) == 1:
                pose = "prone"
            elif is_damaged:
                pose = "alert"  # 受傷警戒姿勢
            else:
                pose = "stand1"
                
            # 嘗試獲取GIF動畫（如果API支援）
            gif_url = f"https://maplestory.io/api/character/{item_path}/{pose}/0.gif?showears=false&resize=2&flipX=true"
            static_url = f"https://maplestory.io/api/character/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                # 先嘗試GIF
                try:
                    async with session.get(gif_url) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            if len(image_data) > 100:
                                return discord.File(io.BytesIO(image_data), filename='character.gif')
                except:
                    pass
                
                # 回退到靜態圖片
                async with session.get(static_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            return discord.File(io.BytesIO(image_data), filename='character.png')
        except Exception as e:
            print(f"獲取角色圖片錯誤: {e}")
        return None

    def create_punishment_embed(self, member: discord.Member, user_data: dict, damage_info: dict, attack_message: str) -> discord.Embed:
        """創建懲罰狀態的 Embed"""
        # 根據HP狀態決定顏色
        if damage_info.get('hp', 100) <= 0:
            color = 0xff0000  # 紅色 - 重傷
        elif damage_info.get('hp', 100) <= 30:
            color = 0xff8800  # 橙色 - 危險
        elif damage_info.get('hp', 100) <= 60:
            color = 0xffff00  # 黃色 - 警告
        else:
            color = 0x00ff00  # 綠色 - 安全

        embed = discord.Embed(
            title="🚨 禁閉室精神折磨中 🚨",
            description=f"**{member.display_name}** 正在接受中控室的制裁...",
            color=color
        )

        # 狀態欄
        hp_bar = self.create_health_bar(damage_info.get('hp', 100), 100)
        stamina_bar = self.create_health_bar(damage_info.get('stamina', 100), 100)
        
        embed.add_field(
            name="❤️ 生命值",
            value=f"{hp_bar} `{damage_info.get('hp', 100)}/100`",
            inline=False
        )
        
        embed.add_field(
            name="⚡ 體力值", 
            value=f"{stamina_bar} `{damage_info.get('stamina', 100)}/100`",
            inline=False
        )

        # 傷害訊息
        if damage_info.get('old_hp', 100) > damage_info.get('hp', 100):
            hp_damage = damage_info.get('old_hp', 100) - damage_info.get('hp', 100)
            embed.add_field(
                name="💥 造成傷害",
                value=f"生命值 -{hp_damage}",
                inline=True
            )
            
        if damage_info.get('old_stamina', 100) > damage_info.get('stamina', 100):
            stamina_damage = damage_info.get('old_stamina', 100) - damage_info.get('stamina', 100)
            embed.add_field(
                name="😵 體力耗盡",
                value=f"體力值 -{stamina_damage}",
                inline=True
            )

        # AI羞辱訊息
        embed.add_field(
            name="🤖 中控室訊息",
            value=f"*{attack_message}*",
            inline=False
        )

        # 狀態提示
        if damage_info.get('hp', 100) <= 0:
            embed.add_field(
                name="💀 重傷狀態",
                value="生命值歸零！開始消耗體力值！",
                inline=False
            )
        
        embed.set_footer(text=f"禁閉時間：每分鐘持續攻擊 | {member.display_name} 的末日")
        
        return embed

    def create_health_bar(self, current: int, maximum: int, length: int = 20) -> str:
        """創建血條顯示"""
        if maximum <= 0:
            return "▱" * length
            
        percentage = current / maximum
        filled_length = int(length * percentage)
        
        if percentage > 0.6:
            bar_char = "▰"  # 綠色滿血條
        elif percentage > 0.3:
            bar_char = "▰"  # 黃色警告
        else:
            bar_char = "▰"  # 紅色危險
            
        empty_char = "▱"
        
        return bar_char * filled_length + empty_char * (length - filled_length)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if MUTE_ROLE_ID in [role.id for role in after.roles] and MUTE_ROLE_ID not in [role.id for role in before.roles]:
            await self.start_punishment(after)

    async def start_punishment(self, member: discord.Member):
        if member.id in self.punishment_tasks:
            return
        self.punishment_tasks[member.id] = self.bot.loop.create_task(self.send_punishment(member))

    async def send_punishment(self, member: discord.Member):
        channel = self.bot.get_channel(PUNISHMENT_CHANNEL_ID)
        if not channel:
            return

        persona_prompt = build_persona_prompt(bot_name="KK園區中控室", tone="嚴厲")
        
        # 預設的羞辱話語模板
        punishment_templates = [
            f"請用一句帶著譏諷和鄙視的話，嘲笑 {member.display_name} 因為行為不當被關禁閉，血量正在下降。",
            f"請用一句充滿嘲弄的話，諷刺 {member.display_name} 這種水準居然還敢在群裡亂來，現在被攻擊活該。",
            f"請用一句輕蔑且帶點挖苦的話，告訴 {member.display_name} 這就是不守規矩的下場，繼續失血吧。",
            f"請用一句帶著冷嘲熱諷的話，羞辱 {member.display_name} 連基本禮貌都不懂，現在嚐到痛苦了。",
            f"請用一句嘲諷且帶點瞧不起的話，告誡 {member.display_name} 這種行為的代價就是持續受傷。",
            f"請用一句帶著鄙夷和諷刺的話，嘲笑 {member.display_name} 現在終於知道什麼叫做後果。",
            f"請用一句充滿不屑和嘲弄的話，諷刺 {member.display_name} 以為自己很厲害，現在被制裁了。",
            f"請用一句輕蔑且帶點教訓意味的話，告訴 {member.display_name} 每一秒都在為愚蠢付出代價。",
            f"請用一句嘲諷且帶點幸災樂禍的話，'安慰' {member.display_name} 正在經歷的痛苦。",
            f"請用一句帶著冷漠諷刺的話，告訴 {member.display_name} 這就是挑戰權威的下場。"
        ]

        async with aiohttp.ClientSession() as session:
            while MUTE_ROLE_ID in [role.id for role in member.roles]:
                try:
                    # 獲取使用者資料
                    user_data = self.get_user_data(member.id)
                    
                    # 計算傷害
                    current_hp = user_data.get('hp', 100)
                    hp_damage = 5 if current_hp > 0 else 0
                    stamina_damage = 10 if current_hp <= 0 else 0
                    
                    # 更新數值
                    damage_info = self.update_user_stats(member.id, hp_damage, stamina_damage)
                    
                    # 隨機選擇一個模板
                    template = random.choice(punishment_templates)
                    
                    headers = {
                        "Authorization": f"Bearer {AI_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": AI_API_MODEL,
                        "messages": [
                            {"role": "system", "content": persona_prompt},
                            {"role": "user", "content": template}
                        ]
                    }
                    async with session.post(AI_API_URL, headers=headers, json=payload) as resp:
                        data = await resp.json()

                    if "choices" in data and len(data["choices"]) > 0:
                        attack_message = data["choices"][0]["message"]["content"].strip()
                    else:
                        # 備用的羞辱話語
                        backup_responses = [
                            f"{member.display_name} 血量下降中，這就是作亂的代價。",
                            f"{member.display_name} 感受痛苦吧，這是你應得的懲罰。",
                            f"{member.display_name} 每一滴血都在提醒你的愚蠢。",
                            f"{member.display_name} 現在知道疼了？太遲了。",
                            f"{member.display_name} 繼續受苦吧，直到你學會教訓。"
                        ]
                        attack_message = random.choice(backup_responses)

                    # 創建 Embed
                    embed = self.create_punishment_embed(member, user_data, damage_info, attack_message)
                    
                    # 獲取角色圖片
                    character_image = await self.fetch_character_image(user_data, is_damaged=True)
                    
                    # 發送訊息
                    if character_image:
                        embed.set_image(url="attachment://character.gif")
                        await channel.send(embed=embed, file=character_image)
                    else:
                        await channel.send(embed=embed)
                    
                    # 等待一分鐘 (57秒避免速率限制)
                    await asyncio.sleep(57)

                except Exception as e:
                    print(f"精神訓話錯誤：{e}")
                    break

        if member.id in self.punishment_tasks:
            del self.punishment_tasks[member.id]

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.id in self.punishment_tasks:
            self.punishment_tasks[member.id].cancel()
            del self.punishment_tasks[member.id]

async def setup(bot):
    await bot.add_cog(Ai(bot))