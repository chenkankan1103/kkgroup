"""
隨機空投物資系統 - 部署在 uibot
每 1-2 小時投放一個神秘空投箱
"""

import discord
from discord.ext import commands, tasks
import random
import asyncio
import aiohttp
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dotenv import load_dotenv
import logging

from db_adapter import get_user_field, set_user_field, add_user_field, get_user

load_dotenv()
logger = logging.getLogger("airdrop_system")

# ==================== 配置 ====================
GEMINI_API_KEY = os.getenv("AI_API_KEY")
GEMINI_API_URL = os.getenv("AI_API_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = os.getenv("GROQ_API_URL")

MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", 0))

# 獎品表
REWARD_TYPES = {
    "kkcoin": {"weight": 40, "range": (1, 500)},
    "heal": {"weight": 20, "range": (20, 50)},
    "stamina": {"weight": 20, "range": (20, 50)},
    "damage": {"weight": 10, "range": (10, 20)},
    "fatigue": {"weight": 10, "range": (10, 20)},
}


class AirdropSystem(commands.Cog):
    """隨機空投物資系統"""
    
    def __init__(self, bot):
        self.bot = bot
        self.next_airdrop_time = None
        self.airdrop_loop.start()
        logger.info("✅ 空投系統已初始化")
    
    def cog_unload(self):
        """卸載時停止任務"""
        self.airdrop_loop.cancel()
        logger.info("❌ 空投系統已卸載")
    
    # ==================== AI API 調用 ====================
    async def call_gemini(self, prompt: str) -> Optional[str]:
        """呼叫 Gemini API"""
        if not GEMINI_API_KEY or not GEMINI_API_URL:
            return None
        
        try:
            url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 200
                }
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "candidates" in data and len(data["candidates"]) > 0:
                            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            logger.warning(f"Gemini API 失敗: {e}")
        
        return None
    
    async def call_groq(self, prompt: str) -> Optional[str]:
        """呼叫 Groq API（文字生成備用）"""
        if not GROQ_API_KEY or not GROQ_API_URL:
            return None
        
        try:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "mixtral-8x7b-32768",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 200
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(GROQ_API_URL, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"Groq API 失敗: {e}")
        
        return None
    
    async def generate_ai_text(self, text_type: str, reward_type: str, value: int) -> str:
        """生成 AI 文本"""
        if text_type == "description" and reward_type in ["heal", "stamina"]:
            prompt = f"生成一句30字內的敘述，描寫發現補充{'生命' if reward_type == 'heal' else '體力'}的東西（真實存在的如：大補丸、能量飲料、人參湯、咖啡等），能恢復{value}點{'HP' if reward_type == 'heal' else '體力'}。只回傳敘述，無需其他文字。"
        elif text_type == "description" and reward_type in ["damage", "fatigue"]:
            prompt = f"生成一句30字內的敘述，描寫打開箱子時發生不幸（如：爆炸、割傷、毒氣、陷阱），失去{value}點{'HP' if reward_type == 'damage' else '體力'}。只回傳敘述，無需其他文字。"
        elif text_type == "description":  # kkcoin
            prompt = f"生成一句20字內的敘述，描寫發現{value}個KK幣。只回傳敘述。"
        elif text_type == "image":
            prompt = "詐騙園區掉落的神秘空投箱，科幻風格，懸念感，高質量"
        else:
            return ""
        
        # 優先 Gemini，備用 Groq
        result = await self.call_gemini(prompt)
        if result:
            return result
        
        result = await self.call_groq(prompt)
        if result:
            return result
        
        # 硬編碼備用
        if text_type == "description":
            if reward_type == "kkcoin":
                return f"找到了{value}個KK幣！"
            elif reward_type == "heal":
                return f"發現補血藥水，恢復{value}點HP"
            elif reward_type == "stamina":
                return f"找到能量飲料，恢復{value}點體力"
            elif reward_type == "damage":
                return f"箱子爆炸了！失去{value}點HP"
            else:
                return f"吸入毒氣，失去{value}點體力"
        return "打開空投箱"
    
    # ==================== 獎品系統 ====================
    def generate_reward(self) -> Tuple[str, int]:
        """生成隨機獎品"""
        total_weight = sum(r["weight"] for r in REWARD_TYPES.values())
        choice = random.randint(0, total_weight - 1)
        current = 0
        
        for reward_type, config in REWARD_TYPES.items():
            current += config["weight"]
            if choice < current:
                value = random.randint(*config["range"])
                return reward_type, value
        
        return "kkcoin", random.randint(1, 500)
    
    async def apply_reward(self, user_id: int, reward_type: str, value: int) -> str:
        """應用獎品到用戶"""
        try:
            if not get_user(user_id):
                return "❌ 用戶不存在"
            
            if reward_type == "kkcoin":
                add_user_field(user_id, "kkcoin", value)
                new_value = get_user_field(user_id, "kkcoin", 0)
                return f"💰 獲得 {value} KK幣！（總計：{new_value}）"
            
            elif reward_type == "heal":
                current = get_user_field(user_id, "hp", 100)
                new_value = (current or 100) + value
                set_user_field(user_id, "hp", new_value)
                return f"❤️ 恢復 {value} HP！（當前：{new_value}）"
            
            elif reward_type == "stamina":
                current = get_user_field(user_id, "stamina") or get_user_field(user_id, "energy", 100)
                new_value = (current or 100) + value
                field = "stamina" if get_user_field(user_id, "stamina") is not None else "energy"
                set_user_field(user_id, field, new_value)
                return f"⚡ 恢復 {value} 體力！（當前：{new_value}）"
            
            elif reward_type == "damage":
                current = get_user_field(user_id, "hp", 100)
                new_value = max(0, (current or 100) - value)
                set_user_field(user_id, "hp", new_value)
                return f"💥 失去 {value} HP！（當前：{new_value}）"
            
            elif reward_type == "fatigue":
                current = get_user_field(user_id, "stamina") or get_user_field(user_id, "energy", 100)
                new_value = max(0, (current or 100) - value)
                field = "stamina" if get_user_field(user_id, "stamina") is not None else "energy"
                set_user_field(user_id, field, new_value)
                return f"😫 失去 {value} 體力！（當前：{new_value}）"
            
            return "✅ 獎品已應用"
        except Exception as e:
            logger.error(f"應用獎品失敗: {e}")
            return f"❌ 錯誤: {e}"
    
    # ==================== Embed 和按鈕 ====================
    async def create_airdrop_embed(self) -> Tuple[discord.Embed, 'AirdropView']:
        """創建空投 embed 和按鈕"""
        
        # 生成圖片 URL（Gemini 圖片生成）
        image_url = None
        if GEMINI_API_KEY and GEMINI_API_URL:
            try:
                # 嘗試調用 Gemini 圖片生成（可能不支持）
                # 暫時設為 None，可後續強化
                pass
            except:
                pass
        
        embed = discord.Embed(
            title="未知的空投箱",
            description="你看到一個緩緩從天而降的空投箱，要打開嗎?",
            color=discord.Color.gold()
        )
        
        if image_url:
            embed.set_image(url=image_url)
        
        embed.set_footer(text="10 分鐘後自動消失")
        
        # 創建按鈕視圖
        view = AirdropView(self)
        return embed, view
    
    # ==================== 後臺任務 ====================
    @tasks.loop(seconds=60)
    async def airdrop_loop(self):
        """後臺空投循環任"""
        try:
            if self.next_airdrop_time is None:
                delay = random.randint(60, 120)  # 1-2 小時
                self.next_airdrop_time = datetime.utcnow() + timedelta(minutes=delay)
                logger.info(f"📦 計劃下一次空投時間：{self.next_airdrop_time}")
                return
            
            if datetime.utcnow() < self.next_airdrop_time:
                return
            
            # 收集可投放的頻道
            eligible_channels = []
            for guild in self.bot.guilds:
                member_role = guild.get_role(MEMBER_ROLE_ID)
                if not member_role:
                    continue
                
                for channel in guild.text_channels:
                    try:
                        perms = channel.permissions_for(member_role)
                        if perms.read_messages and not channel.is_forum():
                            eligible_channels.append(channel)
                    except:
                        pass
            
            if not eligible_channels:
                logger.warning("❌ 沒有可投放的頻道")
                delay = random.randint(60, 120)
                self.next_airdrop_time = datetime.utcnow() + timedelta(minutes=delay)
                return
            
            # 投放空投
            channel = random.choice(eligible_channels)
            embed, view = await self.create_airdrop_embed()
            
            message = await channel.send(embed=embed, view=view)
            logger.info(f"✅ 空投已投放到 #{channel.name}")
            
            # 10 分鐘後自動刪除（如果沒被打開）
            await asyncio.sleep(600)
            try:
                await message.delete()
            except:
                pass
            
            # 計劃下一次空投
            delay = random.randint(60, 120)
            self.next_airdrop_time = datetime.utcnow() + timedelta(minutes=delay)
            logger.info(f"📦 計劃下一次空投時間：{self.next_airdrop_time}")
        
        except Exception as e:
            logger.error(f"空投循環錯誤: {e}")
            delay = random.randint(60, 120)
            self.next_airdrop_time = datetime.utcnow() + timedelta(minutes=delay)
    
    @airdrop_loop.before_loop
    async def before_airdrop_loop(self):
        """等待 bot 準備"""
        await self.bot.wait_until_ready()
        logger.info("✅ 空投系統已啟動")


class AirdropView(discord.ui.View):
    """空投箱交互按鈕"""
    
    def __init__(self, cog):
        super().__init__(timeout=600)  # 10 分鐘超時
        self.cog = cog
        self.opened = False
        self.opened_by = None
    
    @discord.ui.button(label="打開", style=discord.ButtonStyle.success, emoji="📦")
    async def open_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """打開按鈕"""
        await interaction.response.defer()
        
        if self.opened:
            await interaction.followup.send("❌ 這個空投箱已經被開啟了", ephemeral=True)
            return
        
        self.opened = True
        self.opened_by = interaction.user.id
        
        # 生成獎品
        reward_type, value = self.cog.generate_reward()
        
        # 生成 AI 敘述
        description = await self.cog.generate_ai_text("description", reward_type, value)
        
        # 應用獎品
        reward_result = await self.cog.apply_reward(interaction.user.id, reward_type, value)
        
        # 創建結果 embed
        result_embed = discord.Embed(
            title="✨ 空投箱已開啟",
            description=description,
            color=discord.Color.green()
        )
        result_embed.add_field(name="獲得", value=reward_result, inline=False)
        result_embed.set_footer(text="將在一分鐘後註銷")
        
        # 編輯原消息
        try:
            await interaction.message.edit(embed=result_embed, view=None)
            
            # 1 分鐘後刪除
            await asyncio.sleep(60)
            try:
                await interaction.message.delete()
            except:
                pass
        except Exception as e:
            logger.error(f"編輯消息失敗: {e}")
    
    @discord.ui.button(label="銷毀", style=discord.ButtonStyle.danger, emoji="💣")
    async def destroy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """銷毀按鈕"""
        await interaction.response.defer()
        
        try:
            await interaction.message.delete()
        except:
            pass


async def setup(bot):
    """設置 cog"""
    await bot.add_cog(AirdropSystem(bot))
    logger.info("✅ 空投系統已載入")
