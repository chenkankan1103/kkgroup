import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
import asyncio
import aiohttp
import logging
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class StaminaItemView(discord.ui.View):
    def __init__(self, merchant_cog, user_id: int):
        super().__init__(timeout=600)
        self.merchant_cog = merchant_cog
        self.user_id = user_id

    @discord.ui.button(label="維他命C軟糖 +5體力", style=discord.ButtonStyle.blurple, emoji="🍬")
    async def buy_small(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的購買選項！")
            return
        await self.merchant_cog.process_purchase(interaction, self.user_id, "small")

    @discord.ui.button(label="紅牛能量飲 +10體力", style=discord.ButtonStyle.green, emoji="🥛")
    async def buy_medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的購買選項！")
            return
        await self.merchant_cog.process_purchase(interaction, self.user_id, "medium")

    @discord.ui.button(label="靈芝人蔘燉雞湯 +20體力", style=discord.ButtonStyle.danger, emoji="🍲")
    async def buy_large(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的購買選項！")
            return
        await self.merchant_cog.process_purchase(interaction, self.user_id, "large")


# 永久視圖類（用於按鈕永久註冊）
class PersistentStaminaView(discord.ui.View):
    def __init__(self, merchant_cog):
        super().__init__(timeout=None)  # 永不過期
        self.merchant_cog = merchant_cog

    @discord.ui.button(label="維他命C軟糖 +5體力", style=discord.ButtonStyle.blurple, emoji="🍬", custom_id="stamina_small")
    async def buy_small(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.merchant_cog.process_purchase(interaction, interaction.user.id, "small")

    @discord.ui.button(label="紅牛能量飲 +10體力", style=discord.ButtonStyle.green, emoji="🥛", custom_id="stamina_medium")
    async def buy_medium(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.merchant_cog.process_purchase(interaction, interaction.user.id, "medium")

    @discord.ui.button(label="靈芝人蔘燉雞湯 +20體力", style=discord.ButtonStyle.danger, emoji="🍲", custom_id="stamina_large")
    async def buy_large(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.merchant_cog.process_purchase(interaction, interaction.user.id, "large")


class HospitalMerchant(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.hospital_channel_id = int(os.getenv("HOSPITAL_CHANNEL_ID", 0))
        self.injured_role_id = int(os.getenv("INJURED_ROLE_ID", 0))
        self.member_role_id = int(os.getenv("MEMBER_ROLE_ID", 0))
        self.db_path = "./user_data.db"
        self.ai_api_key = os.getenv("AI_API_KEY", "")
        self.ai_api_url = os.getenv("AI_API_URL", "")
        self.ai_model = os.getenv("AI_API_MODEL", "")
        
        # 商品定義
        self.products = {
            "small": {"stamina": 5, "price": 500, "name": "維他命 C 軟糖", "emoji": "🍬"},
            "medium": {"stamina": 10, "price": 1000, "name": "紅牛能量飲", "emoji": "🥛"},
            "large": {"stamina": 20, "price": 2000, "name": "靈芝人蔘燉雞湯", "emoji": "🍲"}
        }
        
        # 儲存醫院訊息 ID
        self.merchant_message_id = None
        self.init_database()
        asyncio.create_task(self.setup_merchant_message())
        
        # 注冊永久視圖
        self.bot.add_view(PersistentStaminaView(self))

    def init_database(self):
        """初始化資料庫"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 檢查並添加交易記錄表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS merchant_transactions (
                    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_type TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    stamina_gained INTEGER NOT NULL,
                    transaction_time INTEGER NOT NULL
                )
            ''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"醫院商人資料庫初始化錯誤: {e}")

    async def generate_merchant_message(self, user_data_sample: dict = None) -> discord.Embed:
        """使用 AI 生成嘲諷的商人訊息"""
        try:
            prompt = """你是一位在醫院駐紮的黑市商人，專門販賣恢復體力的藥劑。請用輕鬆、幽默、帶點嘲諷的語氣生成一個商人的自介訊息。
            
要求：
1. 語言：繁體中文
2. 長度：3-5句話
3. 要點：
   - 嘲笑來醫院的人很狼狽
   - 暗示藥劑可能有奇怪的效果或來源
   - 誘導他們購買商品
   - 帶點黑色幽默

範例風格參考：「看你這狼狽的樣子，肯定是又被打得服服貼貼了。別急，我這邊有最新鮮的進口藥劑，保證讓你起死回生...或至少能走動。怎麼樣，要來點嗎？」"""

            headers = {
                "Authorization": f"Bearer {self.ai_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.ai_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 200
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.ai_api_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        message = data['choices'][0]['message']['content'].strip()
                        return message
                    else:
                        logging.warning(f"AI API 回應狀態碼: {response.status}")
                        
        except asyncio.TimeoutError:
            logging.warning("AI API 請求超時")
        except Exception as e:
            logging.error(f"生成商人訊息錯誤: {e}")
        
        # 預設訊息
        return "看你這狼狽的樣子...又被打成這樣啊？嘻嘻。別急，我這邊有特效藥劑，保證讓你活蹦亂跳...或至少能動。"

    async def create_merchant_embed(self) -> discord.Embed:
        """創建商人訊息 Embed"""
        merchant_msg = await self.generate_merchant_message()
        
        embed = discord.Embed(
            title="🏥 醫院黑市商人 - 地下藥房",
            description=f"> *{merchant_msg}*\n\n💰 **商品列表** 💰",
            color=0x2F4F4F
        )
        
        for key, product in self.products.items():
            embed.add_field(
                name=f"{product['emoji']} {product['name']}",
                value=f"體力恢復: **+{product['stamina']}**\n價格: **{product['price']} KKCoin**",
                inline=False
            )
        
        embed.add_field(
            name="⚠️ 注意事項",
            value="• 購買即視為同意可能的副作用\n• 恢復體力後將自動出院",
            inline=False
        )
        
        embed.set_footer(text="🔐 交易需要謹慎，但活著總是第一優先")
        # 使用商人圖片作為大圖
        embed.set_image(url="https://cdn.discordapp.com/attachments/1275688788806467635/1427730328792989788/image.png")
        
        return embed

    async def setup_merchant_message(self):
        """啟動時檢查或創建商人訊息"""
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)
        
        try:
            channel = self.bot.get_channel(self.hospital_channel_id)
            if not channel:
                logging.warning(f"找不到醫院頻道: {self.hospital_channel_id}")
                return
            
            # 檢查資料庫中是否有存儲的訊息 ID
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS merchant_config (
                    config_key TEXT PRIMARY KEY,
                    config_value TEXT
                )
            ''')
            
            cursor.execute("SELECT config_value FROM merchant_config WHERE config_key = 'message_id'")
            result = cursor.fetchone()
            
            if result:
                message_id = int(result[0])
                try:
                    # 嘗試取得既有訊息
                    existing_msg = await channel.fetch_message(message_id)
                    self.merchant_message_id = message_id
                    logging.info(f"✅ 找到既有商人訊息: {message_id}")
                    conn.close()
                    return
                except discord.NotFound:
                    logging.info("既有商人訊息已被刪除，重新創建")
                    cursor.execute("DELETE FROM merchant_config WHERE config_key = 'message_id'")
            
            # 創建新訊息（使用永久視圖）
            embed = await self.create_merchant_embed()
            view = PersistentStaminaView(self)
            
            msg = await channel.send(embed=embed, view=view)
            
            # 儲存訊息 ID
            cursor.execute('''
                INSERT OR REPLACE INTO merchant_config (config_key, config_value)
                VALUES ('message_id', ?)
            ''', (str(msg.id),))
            
            conn.commit()
            conn.close()
            
            self.merchant_message_id = msg.id
            logging.info(f"✅ 創建新商人訊息: {msg.id}")
            
        except Exception as e:
            logging.error(f"設置商人訊息錯誤: {e}")
            if conn:
                conn.close()

    async def process_purchase(self, interaction: discord.Interaction, user_id: int, product_type: str):
        """處理購買"""
        try:
            product = self.products.get(product_type)
            if not product:
                await interaction.followup.send("❌ 商品不存在！", ephemeral=True)
                return
            
            # 檢查用戶金錢和狀態
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT kkcoin, stamina, is_stunned FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                await interaction.followup.send("❌ 無法找到你的資料！", ephemeral=True)
                conn.close()
                return
            
            kkcoin, current_stamina, is_stunned = result
            price = product['price']
            stamina_gain = product['stamina']
            
            # 檢查金錢是否足夠
            if kkcoin < price:
                deficit = price - kkcoin
                await interaction.followup.send(
                    f"❌ 金錢不足！\n"
                    f"你有: {kkcoin} KKCoin\n"
                    f"所需: {price} KKCoin\n"
                    f"差額: {deficit} KKCoin",
                    ephemeral=True
                )
                conn.close()
                return
            
            # 執行購買
            new_stamina = min(current_stamina + stamina_gain, 100)
            new_kkcoin = kkcoin - price
            new_is_stunned = 0 if new_stamina >= 100 else is_stunned
            
            # 更新資料庫
            cursor.execute('''
                UPDATE users 
                SET kkcoin = ?, stamina = ?, is_stunned = ?
                WHERE user_id = ?
            ''', (new_kkcoin, new_stamina, new_is_stunned, user_id))
            
            # 記錄交易
            current_time = int(datetime.now().timestamp())
            cursor.execute('''
                INSERT INTO merchant_transactions 
                (user_id, product_type, cost, stamina_gained, transaction_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, product_type, price, stamina_gain, current_time))
            
            conn.commit()
            conn.close()
            
            # 準備回應
            purchase_embed = discord.Embed(
                title="💰 購買成功！",
                description=f"你購買了 **{product['name']}**",
                color=0x00FF00
            )
            
            purchase_embed.add_field(name="消費", value=f"-{price} KKCoin", inline=True)
            purchase_embed.add_field(name="體力恢復", value=f"+{stamina_gain}", inline=True)
            purchase_embed.add_field(name="剩餘金錢", value=f"{new_kkcoin} KKCoin", inline=True)
            purchase_embed.add_field(name="當前體力", value=f"{new_stamina}/100", inline=True)
            
            if new_stamina >= 100:
                purchase_embed.add_field(
                    name="✨ 出院通知",
                    value="你的體力已完全恢復！正在辦理出院手續...",
                    inline=False
                )
                purchase_embed.color = 0xFFD700
            
            # 購買通知僅個人可見
            await interaction.followup.send(embed=purchase_embed, ephemeral=True)
            
            # 如果體力已滿，觸發恢復完成事件
            if new_stamina >= 100:
                await self.complete_hospital_recovery(interaction, user_id)
            
        except Exception as e:
            logging.error(f"處理購買錯誤: {e}")
            await interaction.followup.send(f"❌ 購買過程中發生錯誤: {e}", ephemeral=True)

    async def complete_hospital_recovery(self, interaction: discord.Interaction, user_id: int):
        """完成醫院恢復，移除身分組並恢復紙娃娃"""
        try:
            guild = interaction.guild
            member = guild.get_member(user_id)
            
            if not member:
                return
            
            # 移除 injured 身分組，恢復 member 身分組
            injured_role = guild.get_role(self.injured_role_id)
            member_role = guild.get_role(self.member_role_id)
            
            if injured_role and injured_role in member.roles:
                await member.remove_roles(injured_role, reason="體力完全恢復，出院")
            
            if member_role and member_role not in member.roles:
                await member.add_roles(member_role, reason="體力完全恢復，恢復正式成員身分")
            
            # 恢復紙娃娃狀態 (hp 和 stamina 已在資料庫更新為 100)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET is_stunned = 0
                WHERE user_id = ?
            ''', (user_id,))
            
            conn.commit()
            conn.close()
            
            # 發送出院通知（僅個人可見）
            recovery_embed = discord.Embed(
                title="✨ 恭喜出院！",
                description=f"{member.mention} 已成功出院",
                color=0x00FF00
            )
            
            recovery_embed.add_field(name="健康狀態", value="✅ 完全恢復", inline=False)
            recovery_embed.add_field(name="身分更新", value="✅ 恢復正式成員身分\n✅ 移除傷病狀態", inline=False)
            recovery_embed.add_field(name="醫生的話", value="*「好好照顧自己，別再來醫院了。」*", inline=False)
            
            recovery_embed.set_thumbnail(url=member.display_avatar.url)
            
            channel = self.bot.get_channel(self.hospital_channel_id)
            if channel:
                await channel.send(embed=recovery_embed, content=member.mention, delete_after=None)
            
            logging.info(f"用戶 {user_id} 已完成醫院恢復")
            
        except Exception as e:
            logging.error(f"完成醫院恢復錯誤: {e}")

    @commands.Cog.listener()
    async def on_user_injured(self, user_id: int):
        """監聽用戶進入傷病狀態"""
        try:
            guild_id = int(os.getenv("GUILD_ID", 0))
            guild = self.bot.get_guild(guild_id)
            
            if not guild:
                logging.warning(f"找不到伺服器: {guild_id}")
                return
            
            member = guild.get_member(user_id)
            if not member:
                return
            
            # 添加 injured 身分組
            injured_role = guild.get_role(self.injured_role_id)
            member_role = guild.get_role(self.member_role_id)
            
            if injured_role and injured_role not in member.roles:
                await member.add_roles(injured_role, reason="進入傷病狀態")
            
            if member_role and member_role in member.roles:
                await member.remove_roles(member_role, reason="進入傷病狀態")
            
            # 在醫院頻道發送僅個人可見的住院通知
            channel = self.bot.get_channel(self.hospital_channel_id)
            if channel:
                personal_embed = discord.Embed(
                    title="🏥 住院通知",
                    description=f"{member.mention} 你好，歡迎來到醫院",
                    color=0xFF6B6B
                )
                
                personal_embed.add_field(
                    name="📋 當前狀態",
                    value="💫 已擊暈\n❤️ HP: 0/100\n⚡ 體力: 0/100",
                    inline=False
                )
                
                personal_embed.add_field(
                    name="⏱️ 自然恢復",
                    value="• 每小時恢復 **25 點體力**\n• 需達到 **100 點體力**才能出院\n• 預計需要 **4 小時**完全恢復",
                    inline=False
                )
                
                personal_embed.add_field(
                    name="💊 快速出院",
                    value="若想及早出院，請使用上方按鈕購買恢復產品",
                    inline=False
                )
                
                personal_embed.set_footer(text="💡 購買產品可立即恢復體力並出院")
                
                await channel.send(embed=personal_embed, content=member.mention, delete_after=None)
            
            logging.info(f"用戶 {user_id} 已進入傷病狀態")
            
        except Exception as e:
            logging.error(f"處理傷病狀態錯誤: {e}")

    @commands.Cog.listener()
    async def on_user_recovery_complete(self, user_id: int):
        """監聽用戶完全恢復（來自 recovery_loop 的自動恢復）"""
        try:
            guild_id = int(os.getenv("GUILD_ID", 0))
            guild = self.bot.get_guild(guild_id)
            
            if not guild:
                return
            
            member = guild.get_member(user_id)
            if not member:
                return
            
            # 移除身分組並恢復狀態
            injured_role = guild.get_role(self.injured_role_id)
            member_role = guild.get_role(self.member_role_id)
            
            if injured_role and injured_role in member.roles:
                await member.remove_roles(injured_role, reason="體力完全恢復")
            
            if member_role and member_role not in member.roles:
                await member.add_roles(member_role, reason="體力完全恢復")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_stunned = 0 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            
            channel = self.bot.get_channel(self.hospital_channel_id)
            if channel:
                recovery_embed = discord.Embed(
                    title="✨ 自然恢復完成",
                    description=f"{member.mention} 體力已自然恢復",
                    color=0x00FF00
                )
                recovery_embed.add_field(name="狀態", value="✅ 已出院\n✅ 恢復正式成員身分", inline=False)
                await channel.send(embed=recovery_embed)
            
            logging.info(f"用戶 {user_id} 已通過自然恢復完成")
            
        except Exception as e:
            logging.error(f"處理自動恢復完成錯誤: {e}")

    @app_commands.command(name="醫院狀態", description="查看醫院中的傷病用戶")
    @app_commands.default_permissions(administrator=True)
    async def hospital_status(self, interaction: discord.Interaction):
        """查看醫院狀態"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id, hp, stamina, injury_recovery_time 
                FROM users 
                WHERE is_stunned = 1
            ''')
            
            injured_users = cursor.fetchall()
            conn.close()
            
            if not injured_users:
                await interaction.followup.send("✅ 醫院目前沒有傷病患者")
                return
            
            embed = discord.Embed(
                title="🏥 醫院患者列表",
                description=f"目前有 {len(injured_users)} 位傷病患者",
                color=0xFF0000
            )
            
            for user_id, hp, stamina, injury_time in injured_users:
                member = interaction.guild.get_member(user_id)
                member_name = member.mention if member else f"用戶 {user_id}"
                
                embed.add_field(
                    name=member_name,
                    value=f"HP: {hp}/100 | 體力: {stamina}/100",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 查詢醫院狀態錯誤: {e}")

async def setup(bot):
    await bot.add_cog(HospitalMerchant(bot))
    logging.info("HospitalMerchant Cog 已成功載入")
