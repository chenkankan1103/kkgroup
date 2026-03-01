import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import asyncio
import aiosqlite
import os
import random
import aiohttp
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "user_data.db")
TEMP_VC_CATEGORY_ID = int(os.getenv("TEMP_VC_CATEGORY_ID", 0))
GUILD_ID = int(os.getenv("GUILD_ID", 0))
INACTIVE_TIMEOUT = 300  # 5分鐘 = 300秒
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", 0))

# AI 相關設定
AI_API_KEY = os.getenv("AI_API_KEY", "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")
AI_API_URL = os.getenv("AI_API_URL", "https://api.groq.com/openai/v1/chat/completions")
AI_API_MODEL = os.getenv("AI_API_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# 🔘 按鈕教學提示
class RoomControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

class ScamHub(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_rooms = {}
        self.room_messages = {}  # 存储每个语音频道的消息ID
        self.scam_event_task.start()

    def cog_unload(self):
        self.scam_event_task.cancel()

    async def generate_scam_event(self, member_count):
        """使用AI生成詐騙事件"""
        try:
            base_prompt = f"""生成一個詐騙事件的簡短描述（50-100字），讓{member_count}人參與的詐騙小組去執行。
            請包含：
            1. 詐騙類型（例如：電話詐騙、網路釣魚、假投資等）
            2. 目標受害者
            3. 使用的手法
            
            格式要簡潔，不要使用引號或多餘的標點符號。只需返回事件描述本身，不要添加額外的解釋或回應。
            """
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": AI_API_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一個創意詐騙事件生成器，用於遊戲內容。"},
                        {"role": "user", "content": base_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 150
                }
                
                async with session.post(AI_API_URL, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["choices"][0]["message"]["content"].strip()
                    else:
                        error_text = await response.text()
                        print(f"AI API錯誤 ({response.status}): {error_text}")
                        return f"詐騙團隊執行了一場經典的電話詐騙行動，冒充銀行客服誘騙受害者透露個人資料。"
        except Exception as e:
            print(f"生成詐騙事件時發生錯誤: {e}")
            return f"詐騙團隊進行了一次成功的網路釣魚攻擊，透過假冒的購物網站騙取了信用卡資訊。"

    async def update_voice_status(self, vc, event_text=None, rewards=None):
        """更新語音頻道的嵌入式消息"""
        try:
            if vc.id not in self.active_rooms:
                return
                
            owner_id = self.active_rooms[vc.id]['owner_id']
            owner = vc.guild.get_member(owner_id)

            embed = discord.Embed(
                title="📢 詐騙小組活動狀態",
                description="💰 等待詐騙事件中..." if not event_text else f"💰 **當前詐騙行動**\n{event_text}",
                color=discord.Color.green()
            )
            embed.add_field(name="🏆 組長", value=f"{owner.mention}", inline=True)
            embed.add_field(name="👥 在線人數", value=f"{len(vc.members)} 人", inline=True)
            
            if rewards:
                reward_text = "**📊 詐騙收入分配**\n"
                for user_id, amount in rewards.items():
                    user = vc.guild.get_member(user_id)
                    role = "👑 組長" if user_id == owner_id else "🧑‍🤝‍🧑 組員"
                    reward_text += f"{role} {user.display_name}: **+{amount} KK幣**\n"
                embed.add_field(name="🎁 詐騙所得", value=reward_text, inline=False)
            else:
                embed.add_field(
                    name="🎁 詐騙收入機制",
                    value="每30-60分鐘觸發一次詐騙事件\n👑 組長: **基礎獎勵 x 1.5倍**\n🧑‍🤝‍🧑 組員: **平分剩餘獎勵**",
                    inline=False
                )
            
            embed.set_footer(text="⚠️ 若此頻道閒置 5 分鐘將自動刪除")

            # 檢查是否已經有消息，如果有就編輯，沒有就發送新的
            if vc.id in self.room_messages:
                try:
                    message = self.room_messages[vc.id]
                    await message.edit(embed=embed)
                    return
                except (discord.NotFound, discord.HTTPException, AttributeError) as e:
                    print(f"無法編輯消息，錯誤: {e}")
                    # 消息不存在，將發送新消息
                    self.room_messages.pop(vc.id, None)
            
            # 發送新消息
            message = await vc.send(embed=embed)
            self.room_messages[vc.id] = message
            print(f"為頻道 {vc.id} 發送了新的狀態消息 ID: {message.id}")
            
        except Exception as e:
            print(f"更新語音狀態失敗: {e}")

    @tasks.loop(seconds=15)
    async def scam_event_task(self):
        """定期檢查是否觸發詐騙事件和刪除閒置頻道"""
        now = datetime.utcnow()
        
        for vc_id, data in list(self.active_rooms.items()):
            try:
                vc = self.bot.get_channel(vc_id)
                if not vc:
                    print(f"頻道 {vc_id} 不存在，從活動房間列表中移除")
                    self.active_rooms.pop(vc_id, None)
                    self.room_messages.pop(vc_id, None)
                    continue

                # 檢查是否有人在頻道中
                current_members = len(vc.members)
                
                if current_members == 0:
                    # 頻道無人，檢查是否超過閒置時間
                    idle_seconds = (now - data['last_active']).total_seconds()
                    print(f"頻道 {vc.name} (ID: {vc_id}) 無人已 {idle_seconds:.1f} 秒")
                    
                    if idle_seconds >= INACTIVE_TIMEOUT:
                        try:
                            print(f"刪除閒置頻道: {vc.name} (ID: {vc_id})")
                            await vc.delete(reason="自動刪除閒置語音頻道")
                            self.active_rooms.pop(vc_id, None)
                            self.room_messages.pop(vc_id, None)
                            print(f"成功刪除閒置頻道 {vc_id}")
                        except discord.NotFound:
                            print(f"頻道 {vc_id} 已經不存在")
                            self.active_rooms.pop(vc_id, None)
                            self.room_messages.pop(vc_id, None)
                        except Exception as e:
                            print(f"刪除頻道 {vc_id} 時發生錯誤: {e}")
                    continue
                
                # 有人在頻道中，更新最後活動時間
                data['last_active'] = now
                
                # 檢查是否需要觸發詐騙事件
                if 'next_event_time' not in data or now >= data['next_event_time']:
                    print(f"觸發詐騙事件 - 頻道: {vc.name}, 人數: {current_members}")
                    
                    # 根據人數計算獎勵（人越多，獎勵越高）
                    max_reward = min(current_members * 40, 500)  # 最多500KK幣
                    total_reward = random.randint(max(0, max_reward - 100), max_reward)
                    
                    # 生成詐騙事件描述
                    event_text = await self.generate_scam_event(current_members)
                    
                    # 計算每個人的獎勵
                    rewards = {}
                    owner_id = data['owner_id']
                    
                    if current_members == 1:
                        # 如果只有組長一人
                        rewards[owner_id] = total_reward
                    else:
                        # 組長獎勵（1.5倍於普通成員）
                        leader_portion = 1.5 / (current_members - 1 + 1.5)
                        leader_reward = round(total_reward * leader_portion)
                        rewards[owner_id] = leader_reward
                        
                        # 剩餘獎勵平分給成員
                        remaining_reward = total_reward - leader_reward
                        member_reward = round(remaining_reward / (current_members - 1)) if current_members > 1 else 0
                        
                        for member in vc.members:
                            if member.id != owner_id:
                                rewards[member.id] = member_reward
                    
                    # 更新數據庫
                    for user_id, amount in rewards.items():
                        await self.update_kkcoin(user_id, amount)
                    
                    # 更新頻道狀態
                    await self.update_voice_status(vc, event_text, rewards)
                    
                    # 設定下一次事件時間（30-60分鐘後）
                    next_event_minutes = random.randint(30, 60)
                    data['next_event_time'] = now + timedelta(minutes=next_event_minutes)
                    print(f"下一次詐騙事件將在 {next_event_minutes} 分鐘後觸發")
                
            except Exception as e:
                print(f"處理詐騙事件時發生錯誤 (頻道 {vc_id}): {e}")

    async def update_kkcoin(self, user_id: int, amount: int):
        """更新用戶的KK幣"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO users (user_id, kkcoin)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET kkcoin = kkcoin + ?
                """, (user_id, amount, amount))
                await db.commit()
                print(f"用戶 {user_id} 獲得 {amount} KK幣")
        except Exception as e:
            print(f"更新KK幣時發生錯誤: {e}")

    @app_commands.command(name="setup_scam_hub", description="建立詐騙機房語音入口")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_scam_hub(self, interaction: discord.Interaction):
        guild = interaction.guild
        channel = await guild.create_voice_channel("詐騙KK幣機房開啟", user_limit=1)
        await interaction.response.send_message(f"✅ 語音入口已建立：{channel.mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # 當用戶加入詐騙機房入口頻道
        if after.channel and after.channel.id == TEMP_VC_CATEGORY_ID:
            guild = after.channel.guild
            category = guild.get_channel(TEMP_VC_CATEGORY_ID) or after.channel.category

            # 創建私人語音頻道
            new_channel = await guild.create_voice_channel(
                name=f"詐騙小組:{member.display_name}",
                category=category,
                user_limit=99
            )

            # 設定頻道權限 - 私人頻道，僅MEMBER_ROLE_ID能看見
            member_role = guild.get_role(MEMBER_ROLE_ID)
            
            # 首先拒絕所有人看到頻道
            await new_channel.set_permissions(guild.default_role, view_channel=False)
            
            # 允許會員身分組看到和加入頻道
            if member_role:
                await new_channel.set_permissions(member_role, view_channel=True, connect=True)
                print(f"設定頻道 {new_channel.name} 為私人頻道，僅 {member_role.name} 身分組可見")
            else:
                print(f"警告: 找不到身分組 ID {MEMBER_ROLE_ID}")
                # 如果會員身分組不存在，暫時允許所有人加入（可根據需求調整）
                await new_channel.set_permissions(guild.default_role, view_channel=True, connect=True)
            
            # 給予房主管理權限
            await new_channel.set_permissions(member, connect=True, manage_channels=True)

            # 記錄新房間信息
            self.active_rooms[new_channel.id] = {
                'owner_id': member.id,
                'last_active': datetime.utcnow(),
                'next_event_time': datetime.utcnow() + timedelta(minutes=random.randint(1, 3))
            }
            
            print(f"創建新的詐騙小組頻道: {new_channel.name} (ID: {new_channel.id}), 房主: {member.display_name}")

            # 移動用戶到新頻道
            await member.move_to(new_channel)

            # 發送歡迎消息
            embed = discord.Embed(
                title="詐騙小組機房開始運作!",
                description="歡迎來到詐騙小組語音機房，在這裡你可以在每30-60分鐘詐騙獲取kk幣，招集組長可獲取1.5倍獎勵，組員越多越有機會幹到一大票！",
                color=discord.Color.blurple()
            )
            await new_channel.send(content=member.mention, embed=embed, view=RoomControlView())
            
            # 初始化狀態消息
            await self.update_voice_status(new_channel)
        
        # 處理用戶離開詐騙小組頻道的情況
        if before.channel and before.channel.id in self.active_rooms:
            current_members = len(before.channel.members)
            print(f"用戶 {member.display_name} 離開頻道 {before.channel.name}, 剩餘人數: {current_members}")
            
            if current_members > 0:
                # 更新頻道信息
                await self.update_voice_status(before.channel)
            else:
                # 頻道空了，更新最後活動時間開始計時
                self.active_rooms[before.channel.id]['last_active'] = datetime.utcnow()
                print(f"頻道 {before.channel.name} 已空，開始計算閒置時間")

async def setup(bot):
    await bot.add_cog(ScamHub(bot))