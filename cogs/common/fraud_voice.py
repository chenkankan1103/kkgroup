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
# 入口語音頻道的 ID，使用者點擊這個頻道時會觸發創建私有語音房間
# TEMP_VC_CATEGORY_ID is actually the ID of the **voice channel** used for triggering
# (not a category).
TEMP_VC_CATEGORY_ID = int(os.getenv("TEMP_VC_CATEGORY_ID", 0))
if TEMP_VC_CATEGORY_ID == 0:
    print("⚠️ 環境變數 TEMP_VC_CATEGORY_ID 未設定，請在 .env 或系統環境中指定入口語音頻道的 ID")
else:
    print(f"✅ 已讀取 TEMP_VC_CATEGORY_ID = {TEMP_VC_CATEGORY_ID} (trigger channel)")

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
        self.room_messages = {}  # 存儲每個語音頻道的消息ID
        self.scam_event_task.start()
        print("[ScamHub] cog initialized, active_rooms cleared")

    def cog_unload(self):
        self.scam_event_task.cancel()
        # 取消所有掛起的刪除任務
        for room_data in self.active_rooms.values():
            if 'deletion_task' in room_data and room_data['deletion_task']:
                room_data['deletion_task'].cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._init_db()
        await self._load_active_rooms()

    async def _init_db(self):
        """建立 scam_rooms 表（如果不存在）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scam_rooms (
                    room_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    room_name TEXT NOT NULL,
                    message_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                    next_event_time DATETIME,
                    is_active INTEGER DEFAULT 1
                )
            """)
            await db.commit()
        print("[ScamHub] scam_rooms 表已初始化")

    async def _load_active_rooms(self):
        """從數據庫加載所有進行中的房間，Bot 啟動時調用"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT room_id, guild_id, owner_id, room_name, message_id, last_active, next_event_time FROM scam_rooms WHERE is_active=1"
                ) as cursor:
                    rows = await cursor.fetchall()

            restored = 0
            for row in rows:
                room_id, guild_id, owner_id, room_name, message_id, last_active_str, next_event_str = row

                # 檢查頻道是否仍然存在
                vc = await self._resolve_voice_channel(room_id)
                if not vc:
                    print(f"[ScamHub] 恢復: 頻道 {room_id} 不存在，標記為非活躍")
                    await self._delete_room_from_db(room_id)
                    continue

                # 解析時間
                try:
                    last_active = datetime.fromisoformat(last_active_str) if last_active_str else datetime.utcnow()
                except (ValueError, TypeError):
                    last_active = datetime.utcnow()

                try:
                    next_event_time = datetime.fromisoformat(next_event_str) if next_event_str else datetime.utcnow() + timedelta(minutes=random.randint(1, 3))
                except (ValueError, TypeError):
                    next_event_time = datetime.utcnow() + timedelta(minutes=random.randint(1, 3))

                self.active_rooms[room_id] = {
                    'owner_id': owner_id,
                    'last_active': last_active,
                    'next_event_time': next_event_time,
                    'deletion_task': None  # ✅ 倒數計時任務
                }

                # 恢復消息對象（透過 message_id 獲取）
                if message_id:
                    try:
                        msg = await vc.fetch_message(message_id)
                        self.room_messages[room_id] = msg
                    except (discord.NotFound, discord.HTTPException):
                        self.room_messages.pop(room_id, None)

                # 如果頻道仍有成員，重啟後立即同步狀態消息
                members = await self._get_voice_members(vc)
                if members:
                    await self.update_voice_status(vc)
                    print(f"[ScamHub] 啟動檢查: 頻道 {room_name} 有 {len(members)} 人，恢復正常運作")
                else:
                    print(f"[ScamHub] 啟動檢查: 頻道 {room_name} 為空，啟動刪除倒數")
                    await self._schedule_deletion(room_id)

                restored += 1
                print(f"[ScamHub] 已恢復房間: {room_name} (ID: {room_id})")

            print(f"[ScamHub] 共恢復 {restored} 個活躍房間")
        except Exception as e:
            print(f"[ScamHub] 加載活躍房間時發生錯誤: {e}")

    async def _resolve_voice_channel(self, channel_id: int):
        """從 cache 或 API 還原語音頻道對象。"""
        vc = self.bot.get_channel(channel_id)
        if vc:
            return vc
        try:
            vc = await self.bot.fetch_channel(channel_id)
            print(f"[ScamHub] 從 API 取得語音頻道 {channel_id}")
            return vc
        except discord.NotFound:
            return None
        except Exception as e:
            print(f"[ScamHub] 嘗試 fetch channel {channel_id} 時失敗: {e}")
            return None

    async def _get_voice_members(self, vc):
        """返回頻道中的成員清單。
        
        注意：使用 fetch_channel 確保獲取最新狀態，避免依賴過期緩存。
        """
        if not vc:
            return []
        
        try:
            # 先嘗試獲取最新頻道狀態
            fresh_vc = await self._resolve_voice_channel(vc.id)
            if fresh_vc:
                vc = fresh_vc
            
            members = list(vc.members) if hasattr(vc, 'members') else []
            print(f"[ScamHub] 🔍 _get_voice_members: 頻道 {vc.name} (ID: {vc.id}) 成員: {[m.name for m in members]}")
            return members
        except Exception as e:
            print(f"[ScamHub] ⚠️ _get_voice_members 取得成員時發生錯誤: {e}")
            return []

    async def _save_room_to_db(self, room_id: int, guild_id: int, owner_id: int, room_name: str, next_event_time: datetime):
        """新房間創建時保存到數據庫"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO scam_rooms
                        (room_id, guild_id, owner_id, room_name, last_active, next_event_time, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (room_id, guild_id, owner_id, room_name,
                      datetime.utcnow().isoformat(), next_event_time.isoformat()))
                await db.commit()
            print(f"[ScamHub] 房間 {room_id} 已保存到數據庫")
        except Exception as e:
            print(f"[ScamHub] 保存房間 {room_id} 到數據庫時發生錯誤: {e}")

    async def _update_room_db(self, room_id: int, next_event_time: datetime = None, message_id: int = None):
        """更新數據庫中的房間狀態"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                if next_event_time is not None and message_id is not None:
                    await db.execute("""
                        UPDATE scam_rooms SET last_active=?, next_event_time=?, message_id=? WHERE room_id=?
                    """, (datetime.utcnow().isoformat(), next_event_time.isoformat(), message_id, room_id))
                elif next_event_time is not None:
                    await db.execute("""
                        UPDATE scam_rooms SET last_active=?, next_event_time=? WHERE room_id=?
                    """, (datetime.utcnow().isoformat(), next_event_time.isoformat(), room_id))
                elif message_id is not None:
                    await db.execute("""
                        UPDATE scam_rooms SET last_active=?, message_id=? WHERE room_id=?
                    """, (datetime.utcnow().isoformat(), message_id, room_id))
                else:
                    await db.execute("""
                        UPDATE scam_rooms SET last_active=? WHERE room_id=?
                    """, (datetime.utcnow().isoformat(), room_id))
                await db.commit()
        except Exception as e:
            print(f"[ScamHub] 更新房間 {room_id} 數據庫狀態時發生錯誤: {e}")

    async def _delete_room_from_db(self, room_id: int):
        """從數據庫中刪除房間記錄"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE scam_rooms SET is_active=0 WHERE room_id=?", (room_id,))
                await db.commit()
        except Exception as e:
            print(f"[ScamHub] 刪除房間 {room_id} 數據庫記錄時發生錯誤: {e}")

    async def _schedule_deletion(self, room_id: int):
        """✅ 新邏輯：啟動 5 分鐘倒數計時，無人則自動刪除"""
        if room_id not in self.active_rooms:
            print(f"[ScamHub] ⚠️ _schedule_deletion: 房間 {room_id} 不在 active_rooms 中，無法啟動刪除倒數")
            return
        
        room_data = self.active_rooms[room_id]
        
        # 如果已經有倒數任務，不要重複啟動
        if room_data.get('deletion_task') and not room_data['deletion_task'].done():
            print(f"[ScamHub] 房間 {room_id} 已有倒數計時中，忽略重複啟動")
            return
        
        async def deletion_countdown():
            start_time = datetime.utcnow()
            room_name = "Unknown"
            try:
                vc = await self._resolve_voice_channel(room_id)
                room_name = vc.name if vc else f"Unknown-{room_id}"
                
                print(f"[ScamHub] 🕐 房間 {room_name} (ID: {room_id}) 無人，5 分鐘後將自動刪除 - 倒數計時已啟動")
                await asyncio.sleep(INACTIVE_TIMEOUT)  # 等待 5 分鐘
                
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                print(f"[ScamHub] 🕐 倒數計時結束 (耗時 {elapsed:.1f} 秒)，檢查房間 {room_id} 是否仍無人")
                
                # 5 分鐘後檢查是否還是無人
                if room_id not in self.active_rooms:
                    print(f"[ScamHub] ⚠️ 房間 {room_id} 已從 active_rooms 中移除，停止刪除程序")
                    return
                
                # 再次獲取最新頻道狀態
                vc = await self._resolve_voice_channel(room_id)
                
                if not vc:
                    print(f"[ScamHub] ⚠️ 房間 {room_id} 不存在或無法取得，清理資料")
                    self.active_rooms.pop(room_id, None)
                    self.room_messages.pop(room_id, None)
                    await self._delete_room_from_db(room_id)
                    return
                
                # 檢查是否確實還是無人 - 使用最新狀態
                members = await self._get_voice_members(vc)
                member_count = len(members)
                
                print(f"[ScamHub] 🔍 檢查結果: 頻道 {room_name} 成員數: {member_count}, 成員列表: {[m.name for m in members]}")
                
                if member_count == 0:
                    print(f"[ScamHub] 🗑️ 執行刪除: {vc.name} (ID: {room_id}) - 無人語音頻道 (成員數: 0)")
                    try:
                        await vc.delete(reason="自動刪除無人語音頻道 (5分鐘)")
                        print(f"[ScamHub] ✅ 成功刪除無人頻道 {vc.name} (ID: {room_id})")
                    except discord.Forbidden:
                        print(f"[ScamHub] ❌ 權限不足：無法刪除頻道 {room_id} (需要 manage_channels 權限)")
                    except discord.HTTPException as e:
                        print(f"[ScamHub] ❌ HTTP 錯誤：刪除頻道 {room_id} 失敗 - {e}")
                    except Exception as e:
                        print(f"[ScamHub] ❌ 刪除頻道 {room_id} 時發生未預期錯誤: {type(e).__name__}: {e}")
                    finally:
                        # 確保清理所有相關數據
                        self.active_rooms.pop(room_id, None)
                        self.room_messages.pop(room_id, None)
                        await self._delete_room_from_db(room_id)
                        print(f"[ScamHub] 🧹 已清理房間 {room_id} 的所有相關數據")
                else:
                    print(f"[ScamHub] ⏸️ 倒數計時完成但檢查到 {member_count} 人在頻道中 {[m.name for m in members]}，取消刪除")
                    # 清空倒數任務標記，以便下次無人時可以重新啟動
                    if room_id in self.active_rooms:
                        self.active_rooms[room_id]['deletion_task'] = None
                    
            except asyncio.CancelledError:
                print(f"[ScamHub] ⏹️ 房間 {room_id} 的刪除倒數計時已被取消 (有人加入)")
                # 確保清理任務引用
                if room_id in self.active_rooms:
                    self.active_rooms[room_id]['deletion_task'] = None
                
            except Exception as e:
                print(f"[ScamHub] ❌ 刪除房間 {room_id} 時發生未預期的錯誤: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                # 確保在錯誤情況下也清理數據
                self.active_rooms.pop(room_id, None)
                self.room_messages.pop(room_id, None)
                await self._delete_room_from_db(room_id)
        
        # 建立並保存倒數任務
        deletion_task = asyncio.create_task(deletion_countdown())
        room_data['deletion_task'] = deletion_task
        print(f"[ScamHub] 🔔 倒數任務已建立: {deletion_task}")

    async def _cancel_deletion(self, room_id: int):
        """✅ 新邏輯：取消倒數計時（有人加入時調用）"""
        if room_id not in self.active_rooms:
            print(f"[ScamHub] ⚠️ _cancel_deletion: 房間 {room_id} 不在 active_rooms 中")
            return
        
        room_data = self.active_rooms[room_id]
        deletion_task = room_data.get('deletion_task')
        
        if deletion_task and not deletion_task.done():
            print(f"[ScamHub] 🔔 房間 {room_id} 有人加入，取消倒數計時任務")
            deletion_task.cancel()
            room_data['deletion_task'] = None
        else:
            print(f"[ScamHub] 📌 房間 {room_id} 沒有進行中的倒數計時任務")

    async def generate_scam_event(self, member_count):
        """使用AI生成詐騙事件（只使用 Groq）"""
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
                    "model": GROQ_API_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一個創意詐騙事件生成器，用於遊戲內容。"},
                        {"role": "user", "content": base_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 150
                }
                
                async with session.post(GROQ_API_URL, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["choices"][0]["message"]["content"].strip()
                    else:
                        error_text = await response.text()
                        print(f"Groq API錯誤 ({response.status}): {error_text}")
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
            owner_mention = owner.mention if owner else f"<@{owner_id}>"

            members = await self._get_voice_members(vc)
            online_count = len(members)

            embed = discord.Embed(
                title="📢 詐騙小組活動狀態",
                description="💰 等待詐騙事件中..." if not event_text else f"💰 **當前詐騙行動**\n{event_text}",
                color=discord.Color.green()
            )
            embed.add_field(name="🏆 組長", value=owner_mention, inline=True)
            embed.add_field(name="👥 在線人數", value=f"{online_count} 人", inline=True)
            
            if rewards:
                reward_text = "**📊 詐騙收入分配**\n"
                for user_id, amount in rewards.items():
                    user = vc.guild.get_member(user_id)
                    display_name = user.display_name if user else f"<@{user_id}>"
                    role = "👑 組長" if user_id == owner_id else "🧑‍🤝‍🧑 組員"
                    reward_text += f"{role} {display_name}: **+{amount} KK幣**\n"
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
            await self._update_room_db(vc.id, message_id=message.id)
            
        except Exception as e:
            print(f"更新語音狀態失敗: {e}")

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
        # Debug: 印出當前頻道和 ID
        print(f"[ScamHub] on_voice_state_update triggered: member={member} ({member.id}), before={getattr(before.channel, 'id', None)}, after={getattr(after.channel, 'id', None)}")
        if after.channel:
            print(f"voice_state_update: member={member.display_name}, after_channel={after.channel.name}, id={after.channel.id}")
        else:
            print(f"voice_state_update: member={member.display_name}, after_channel=None")

        # 當用戶加入詐騙機房入口頻道（TEMP_VC_CATEGORY_ID 只做為觸發 ID）
        if after.channel and after.channel.id == TEMP_VC_CATEGORY_ID:
            guild = after.channel.guild
            # 使用觸發頻道本身的 category（若有）或不指定
            category = after.channel.category

            # 創建私人語音頻道（不需要把 TEMP_VC_CATEGORY_ID 當成 category）
            kwargs = {"name": f"詐騙小組:{member.display_name}", "user_limit": 99}
            if category:
                kwargs["category"] = category

            new_channel = await guild.create_voice_channel(**kwargs)

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
            next_event_time = datetime.utcnow() + timedelta(minutes=random.randint(1, 3))
            self.active_rooms[new_channel.id] = {
                'owner_id': member.id,
                'last_active': datetime.utcnow(),
                'next_event_time': next_event_time,
                'deletion_task': None  # ✅ 初始化倒數計時任務
            }
            await self._save_room_to_db(new_channel.id, guild.id, member.id, new_channel.name, next_event_time)
            
            print(f"創建新的詐騙小組頻道: {new_channel.name} (ID: {new_channel.id}), 房主: {member.display_name}")

            # 移動用戶到新頻道
            await member.move_to(new_channel)

            # 發送歡迎消息
            embed = discord.Embed(
                title="詐騙小組機房開始運作!",
                description="歡迎來到詐騙小組語音機房，在這裡你可以在每30-60分鐘詐騙獲取kk幣，招集組長可獲取1.5倍獎勵，組員越多越有機會幹到一大票！",
                color=discord.Color.blurple()
            )
            try:
                await new_channel.send(content=member.mention, embed=embed, view=RoomControlView())
            except Exception as e:
                print(f"[ScamHub] ⚠️ 發送歡迎消息時發生錯誤: {e}")
            
            # 初始化狀態消息
            await self.update_voice_status(new_channel)
            return  # ✅ 必須 return，否則會繼續執行下面的邏輯導致混亂
        
        # 處理用戶加入現有詐騙小組頻道的情況
        if after.channel and after.channel.id in self.active_rooms:
            current_members = len(await self._get_voice_members(after.channel))
            # 🔧 Fix #2: 移除此處的 last_active 更新
            # 理由：last_active 應只在 5分鐘循環中更新，代表「最後無人」的時間
            # 不應在用戶加入時重置，否則會破壞閒置計時邏輯
            
            # ✅ 新邏輯：有人加入時取消倒數計時
            print(f"[ScamHub] 👥 用戶 {member.display_name} 加入頻道 {after.channel.name}, 目前人數: {current_members}")
            await self._cancel_deletion(after.channel.id)
            
            await self.update_voice_status(after.channel)

        # 處理用戶離開詐騙小組頻道的情況
        if before.channel and before.channel.id in self.active_rooms:
            # 等待一小段時間讓 Discord 狀態同步
            await asyncio.sleep(0.5)
            
            current_members = len(await self._get_voice_members(before.channel))
            print(f"[ScamHub] 👤 用戶 {member.display_name} 離開頻道 {before.channel.name}, 剩餘人數: {current_members}")
            
            if current_members > 0:
                # 更新頻道信息
                await self.update_voice_status(before.channel)
            else:
                # ✅ 頻道空了，啟動 5 分鐘倒數計時
                print(f"[ScamHub] ⚡ 頻道無人! 調用 _schedule_deletion({before.channel.id})")
                await self._schedule_deletion(before.channel.id)
                print(f"[ScamHub] ✏️ 頻道 {before.channel.name} (ID: {before.channel.id}) 已空，倒數計時已啟動")

async def setup(bot):
    await bot.add_cog(ScamHub(bot))