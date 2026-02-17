import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import aiohttp
import io
import asyncio
from typing import Optional
from dotenv import load_dotenv
from status_dashboard import add_log
from .personal_items import PersonalItemsView
from PIL import Image
import time
import hashlib
from pathlib import Path
from db_adapter import get_user, set_user_field, get_user_field, get_all_users
import datetime
from shop_commands.merchant.cannabis_farming import (
    get_inventory, plant_cannabis, get_user_plants, apply_fertilizer, 
    harvest_plant, remove_inventory, add_inventory
)
from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES

# 導入拆分出去的模組
from .views import UpdatePanelView, WorkCardModal, WorkCardEditView, WorkCardActionView, LockerPanelView
from .utils import (
    create_progress_bar, generate_locker_grid, get_plant_progress_info,
    create_user_embed, generate_character_cache_key, get_cached_discord_url,
    save_discord_url_cache, upload_image_to_discord_storage,
    get_character_image_url, restore_image_cache_from_storage,
    ensure_user_exists, get_user_data as get_user_data_util
)
from .tasks import LockerTasks

load_dotenv()


class UserPanel(commands.Cog):
    """用戶面板 Cog - 管理置物櫃、角色、和AI評論"""
    
    def __init__(self, bot):
        print("🚀 UserPanel __init__ 開始")
        self.bot = bot
        self.db_path = './user_data.db'
        self.FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
        self.image_storage_channel_id = int(os.getenv('IMAGE_STORAGE_CHANNEL_ID', '0'))
        self.welcome_channel_id = int(os.getenv('WELCOME_CHANNEL_ID', '0'))
        
        # AI 設定
        self.AI_API_KEY = os.getenv('AI_API_KEY')
        self.AI_API_URL = os.getenv('AI_API_URL')
        self.AI_API_MODEL = os.getenv('AI_API_MODEL')
        
        # Groq 備用 API
        self.GROQ_API_KEY = os.getenv('GROQ_API_KEY')
        self.GROQ_API_URL = os.getenv('GROQ_API_URL')
        self.GROQ_API_MODEL = os.getenv('GROQ_API_MODEL', 'mixtral-8x7b-32768')
        
        # 圖片緩存設定
        self.cache_dir = Path('./character_images')
        self.cache_dir.mkdir(exist_ok=True)
        if not hasattr(self, 'image_cache'):
            self.image_cache = {}
        
        # 註冊永久視圖
        self.bot.add_view(UpdatePanelView(self, 0))
        self.bot.add_view(LockerPanelView(self, 0))
        
        # 初始化任務
        self.locker_tasks = LockerTasks(self)
        
        # 啟動embed更新任務（已停用）
        # 由於要求將自動更新停用，改為以 slash (/update_forum_lockers) 手動觸發。
        # 可透過環境變數 DISABLE_LOCKER_AUTOMATIC_UPDATE=0 重新開啟自動更新。
        if os.getenv('DISABLE_LOCKER_AUTOMATIC_UPDATE', '1') == '1':
            print("⚠️ 自動更新已停用（DISABLE_LOCKER_AUTOMATIC_UPDATE=1）。請使用 /update_forum_lockers 手動觸發更新。")
            # 保留屬性以便 cog_unload 或其他檢查不會 crash
            self.update_embeds_task = None
        else:
            print("🔧 初始化 UserPanel，啟動embed更新任務")
            try:
                self.update_embeds_task = self.bot.loop.create_task(self.locker_tasks.update_all_locker_embeds())
                print("✅ embed更新任務已創建")
            except Exception as e:
                print(f"❌ 創建embed更新任務失敗: {e}")
                import traceback
                traceback.print_exc()
    
    def cog_unload(self):
        if hasattr(self, 'update_embeds_task'):
            self.update_embeds_task.cancel()
        if self.weekly_summary.is_running():
            self.weekly_summary.cancel()
        if self.check_member_threads.is_running():
            self.check_member_threads.cancel()
    
    # ============= 工具函數 =============
    
    def get_user_data(self, user_id: int) -> Optional[dict]:
        """獲取用戶資料"""
        try:
            user = get_user(user_id)
            if not user:
                return None
            
            return {
                'user_id': user.get('user_id') or user_id,
                'level': user.get('level', 1),
                'xp': user.get('xp', 0),
                'kkcoin': user.get('kkcoin', 0),
                'title': user.get('title', '新手'),
                'hp': user.get('hp', 100),
                'stamina': user.get('stamina', 100),
                'inventory': user.get('inventory', '{}'),
                'character_config': user.get('character_config', '{}'),
                'face': user.get('face', 20000),
                'hair': user.get('hair', 30000),
                'skin': user.get('skin', 12000),
                'top': user.get('top', 1040010),
                'bottom': user.get('bottom', 1060096),
                'shoes': user.get('shoes', 1072288),
                'is_stunned': user.get('is_stunned', 0),
                'gender': user.get('gender', 'male'),
                'thread_id': user.get('thread_id', 0)
            }
        except Exception:
            return None
    
    async def create_user_embed(self, user_data: dict, user: discord.User) -> discord.Embed:
        """創建用戶置物櫃embed"""
        return await create_user_embed(self, user_data, user)
    
    async def get_character_image_url(self, user_data: dict) -> Optional[str]:
        """獲取角色圖片URL"""
        return await get_character_image_url(
            self.bot, user_data, self.image_cache,
            self.image_storage_channel_id, self.welcome_channel_id
        )
    
    def generate_character_cache_key(self, user_data: dict) -> str:
        """生成角色快取鍵"""
        return generate_character_cache_key(user_data)
    
    def _generate_locker_grid(self, plants, total_slots: int = 5) -> str:
        """生成置物櫃格子視圖"""
        return generate_locker_grid(plants, total_slots)
    
    def _get_growth_stage_emoji(self, progress: float) -> str:
        """根據進度返回生長階段emoji"""
        if progress >= 95:
            return "🌾"
        elif progress >= 75:
            return "🌿"
        elif progress >= 50:
            return "🌱"
        elif progress >= 25:
            return "🌱"
        else:
            return "⚪"
    
    def _calculate_plant_progress(self, plant: dict) -> float:
        """計算植物成長進度"""
        if plant.get("status") == "harvested":
            return 100.0
        
        try:
            planted_time = plant.get("planted_at", 0)
            matured_time = plant.get("matured_at", 0)
            
            if isinstance(planted_time, str):
                planted_time = datetime.datetime.fromisoformat(planted_time).timestamp()
            if isinstance(matured_time, str):
                matured_time = datetime.datetime.fromisoformat(matured_time).timestamp()
            
            now = datetime.datetime.now().timestamp()
            elapsed = now - planted_time
            total = matured_time - planted_time
            
            progress = min(100, (elapsed / total * 100)) if total > 0 else 0
            return progress
        except Exception:
            return 0.0
    
    async def get_plant_progress_info(self, plant: dict) -> dict:
        """獲取植物進度詳細信息"""
        return await get_plant_progress_info(plant)
    
    async def restore_image_cache_from_storage(self):
        """啟動時恢復圖片快取"""
        await restore_image_cache_from_storage(self.bot, self.image_cache, self.image_storage_channel_id)
    
    # ============= 執行緒和用戶管理 =============
    
    def ensure_user_exists(self, user_id: int) -> bool:
        """確保使用者在資料庫中存在"""
        return ensure_user_exists(user_id)
    
    async def create_threads_for_existing_members(self):
        """為現有成員創建論壇執行緒"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            guild = forum_channel.guild
            
            # 檢查機器人權限
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member:
                return
                
            permissions = forum_channel.permissions_for(bot_member)
            if not permissions.send_messages or not permissions.create_public_threads:
                return
            
            all_users = get_all_users()
            
            threads_to_create = []
            existing_threads = 0
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id', 0)
                try:
                    member = guild.get_member(user_id)
                    if not member:
                        continue
                    
                    if thread_id and thread_id != 0:
                        thread = forum_channel.get_thread(thread_id)
                        if thread:
                            existing_threads += 1
                            continue
                        else:
                            set_user_field(user_id, 'thread_id', 0)
                            threads_to_create.append(member)
                    else:
                        threads_to_create.append(member)
                            
                except Exception:
                    continue
            
            if threads_to_create:
                print(f"🔧 發現需要創建的線程: {len(threads_to_create)} 個 (已有線程: {existing_threads})")
                
                for member in threads_to_create:
                    try:
                        thread = await self.get_or_create_user_thread(member, skip_image_on_startup=True)
                        if thread:
                            await asyncio.sleep(1)
                    except discord.HTTPException as e:
                        if e.status == 429:
                            print(f"⚠️ 遇到速率限制，稍候 30 秒...")
                            await asyncio.sleep(30)
                            try:
                                await self.get_or_create_user_thread(member, skip_image_on_startup=True)
                                await asyncio.sleep(3)
                            except Exception:
                                pass
                    except Exception:
                        continue
            else:
                print(f"✅ 所有線程已存在 ({existing_threads} 個)")
            
        except Exception:
            pass

    async def get_or_create_user_thread(self, user: discord.User, skip_image_on_startup: bool = False) -> Optional[discord.Thread]:
        """獲取或創建用戶的論壇執行緒"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return None

            if not self.ensure_user_exists(user.id):
                return None

            user_data = self.get_user_data(user.id)
            if not user_data:
                return None

            thread_id = user_data.get('thread_id', 0)
            if thread_id:
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    return thread
                else:
                    set_user_field(user.id, 'thread_id', 0)
            
            bot_member = forum_channel.guild.get_member(self.bot.user.id)
            if not bot_member:
                return None
                
            permissions = forum_channel.permissions_for(bot_member)
            if not permissions.send_messages or not permissions.create_public_threads:
                return None
            
            embed = await self.create_user_embed(user_data, user)
            
            thread_name = f"📦 {user.display_name or user.name} 的置物櫃"
            
            view = LockerPanelView(self, user.id, thread=None)  # thread稍後會設置
            
            try:
                thread, message = await forum_channel.create_thread(
                    name=thread_name, 
                    embed=embed, 
                    view=view,
                    content="👋 這是你的專屬置物櫃～"
                )
                set_user_field(user.id, 'locker_message_id', message.id)
                try:
                    await thread.add_user(user)
                    print(f"✅ 用戶 {user.id} 已添加到線程 {thread.id}")
                except Exception as e:
                    print(f"⚠️ 將用戶加入線程失敗 {user.id}: {e}")
            except discord.HTTPException as http_e:
                if http_e.status == 400:
                    simple_embed = discord.Embed(
                        title=f"📦 {user.display_name or user.name} 的置物櫃",
                        description="正在載入使用者資料...",
                        color=0x00ff88
                    )
                    thread, message = await forum_channel.create_thread(
                        name=thread_name, 
                        embed=simple_embed,
                        content="👋 這是你的專屬置物櫃～"
                    )
                    try:
                        await thread.add_user(user)
                        print(f"✅ 用戶 {user.id} 已添加到線程 {thread.id}")
                    except Exception as e:
                        print(f"⚠️ 將用戶加入線程失敗 {user.id}: {e}")
                    await message.edit(embed=embed, view=view)
                else:
                    raise

            try:
                set_user_field(user.id, 'thread_id', thread.id)
                print(f"✅ 已保存 thread_id {thread.id} 給用戶 {user.id}")
            except Exception as db_err:
                print(f"⚠️ 保存 thread_id 失敗: {db_err}")
            
            return thread

        except discord.Forbidden as perm_err:
            print(f"⚠️ 權限不足 - 為用戶 {user.id} 創建線程: {perm_err}")
        except discord.HTTPException as http_err:
            print(f"⚠️ HTTP 錯誤 - 為用戶 {user.id} 創建線程: {http_err}")
        except Exception as err:
            print(f"⚠️ 非預期錯誤 - 為用戶 {user.id}: {err}")
        
        return None
    
    # ============= AI 評論生成 =============
    
    async def generate_ai_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        """生成 AI 評論"""
        try:
            if self.AI_API_KEY and self.AI_API_URL:
                comment = await self._generate_google_comment(member, kkcoin_change, xp_change, level_change)
                if comment:
                    return comment
            
            if self.GROQ_API_KEY and self.GROQ_API_URL:
                comment = await self._generate_groq_comment(member, kkcoin_change, xp_change, level_change)
                if comment:
                    return comment
        except Exception:
            pass
        
        return f"本週表現不錯！繼續保持這個節奏 💪"
    
    async def _generate_google_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        """使用 Google Generative AI 生成評論"""
        try:
            if not all([self.AI_API_KEY, self.AI_API_URL, self.AI_API_MODEL]):
                return None
            
            prompt = f"""你是一個友善的遊戲助手，請為玩家 {member.display_name or member.name} 本週的表現寫一段鼓勵性的評論。

本週數據：
- KKCoin 增長: {kkcoin_change}
- 經驗值 增長: {xp_change}
- 等級 提升: {level_change}

請用繁體中文回應，語氣要活潑友善，長度控制在50字以內，可以適當使用表情符號。"""
            
            url = f"{self.AI_API_URL}?key={self.AI_API_KEY}"
            
            data = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 100
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('candidates'):
                            content = result['candidates'][0].get('content', {})
                            if content.get('parts'):
                                return content['parts'][0].get('text', '').strip()
                    elif response.status == 429:
                        return None
        except Exception:
            pass
        
        return None
    
    async def _generate_groq_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        """使用 Groq API 生成評論"""
        try:
            if not all([self.GROQ_API_KEY, self.GROQ_API_URL, self.GROQ_API_MODEL]):
                return None

            prompt = f"""你是一個友善的遊戲助手，請為玩家 {member.display_name or member.name} 本週的表現寫一段鼓勵性的評論。

本週數據：
- KKCoin 增長: {kkcoin_change}
- 經驗值 增長: {xp_change}
- 等級 提升: {level_change}

請用繁體中文回應，語氣要活潑友善，長度控制在50字以內，可以適當使用表情符號。"""
            
            headers = {
                'Authorization': f'Bearer {self.GROQ_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.GROQ_API_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 100,
                'temperature': 0.8
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.GROQ_API_URL, headers=headers, json=data, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content'].strip()
        except Exception:
            pass
        
        return None
    
    # ============= 生命週期 =============
    
    async def cog_load(self):
        """Cog 加載時執行"""
        await self.bot.wait_until_ready()
        
        await self.restore_image_cache_from_storage()
        
        forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
        if forum_channel and isinstance(forum_channel, discord.ForumChannel):
            await self.create_threads_for_existing_members()
        
        if not self.weekly_summary.is_running():
            self.weekly_summary.start()
        
        if not self.check_member_threads.is_running():
            self.check_member_threads.start()
    
    # ============= 定期任務 =============
    
    @tasks.loop(minutes=1)
    async def weekly_summary(self):
        """每週日晚上 23:59 執行週統計"""
        try:
            now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            
            if now.weekday() != 6:
                return
                
            if now.hour != 23 or now.minute != 59:
                return
            
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            all_users = get_all_users()
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id', 0)
                current_kkcoin = user_data.get('kkcoin', 0)
                current_xp = user_data.get('xp', 0)
                current_level = user_data.get('level', 1)
                last_kkcoin = user_data.get('last_kkcoin_snapshot', 0)
                last_xp = user_data.get('last_xp_snapshot', 0)
                last_level = user_data.get('last_level_snapshot', 1)
                
                if not thread_id or thread_id == 0:
                    continue
                try:
                    thread = forum_channel.get_thread(thread_id)
                    member = forum_channel.guild.get_member(user_id)
                    
                    if not thread or not member:
                        continue
                    
                    kkcoin_change = (current_kkcoin or 0) - (last_kkcoin or 0)
                    xp_change = (current_xp or 0) - (last_xp or 0)
                    level_change = (current_level or 1) - (last_level or 1)
                    
                    if kkcoin_change > 0 or xp_change > 0 or level_change > 0:
                        ai_comment = await self.generate_ai_comment(member, kkcoin_change, xp_change, level_change)
                        
                        embed = discord.Embed(
                            title=f"📊 {member.display_name or member.name} 的本週統計",
                            description=f"統計週期：{(now - datetime.timedelta(days=7)).strftime('%m/%d')} - {now.strftime('%m/%d')}",
                            color=0x00ff88,
                            timestamp=discord.utils.utcnow()
                        )
                        embed.set_thumbnail(url=member.display_avatar.url)
                        
                        if kkcoin_change > 0:
                            embed.add_field(name="💰 KKCoin 增長", value=f"+{kkcoin_change}", inline=True)
                        if xp_change > 0:
                            embed.add_field(name="✨ 經驗值 增長", value=f"+{xp_change}", inline=True)
                        if level_change > 0:
                            embed.add_field(name="⭐ 等級 提升", value=f"+{level_change}", inline=True)
                        
                        if ai_comment:
                            embed.add_field(name="🤖 AI 評論", value=ai_comment, inline=False)
                        
                        embed.set_footer(text="🔄 每週日 23:59 自動統計")
                        
                        await thread.send(embed=embed)
                        await asyncio.sleep(1)
                    
                    set_user_field(user_id, 'last_kkcoin_snapshot', current_kkcoin)
                    set_user_field(user_id, 'last_xp_snapshot', current_xp)
                    set_user_field(user_id, 'last_level_snapshot', current_level)
                    
                except Exception:
                    continue
            
        except Exception:
            pass

    @weekly_summary.before_loop
    async def before_weekly_summary(self):
        """等待 bot 準備好"""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def check_member_threads(self):
        """每小時檢查一次論壇帖子對應的成員是否仍在服務器"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return
            
            guild = forum_channel.guild
            
            try:
                for thread in forum_channel.threads:
                    try:
                        if hasattr(thread, 'created_by'):
                            user_id = thread.created_by.id
                            thread_id = thread.id
                            
                            member = guild.get_member(user_id)
                            
                            if not member:
                                try:
                                    await thread.delete()
                                    print(f"🗑️ 已刪除已離開成員 {user_id} 的帖子 (thread_id: {thread_id})")
                                    set_user_field(user_id, 'thread_id', 0)
                                except discord.NotFound:
                                    pass
                    except Exception as e:
                        print(f"❌ 檢查帖子時出錯: {e}")
                
                print("📊 論壇帖子檢查完成")
            except Exception as e:
                print(f"⚠️ 無法遊歷帖子: {e}")
        
        except Exception as e:
            print(f"❌ 論壇帖子檢查失敗: {e}")

    @check_member_threads.before_loop
    async def before_check_member_threads(self):
        """等待 bot 準備好"""
        await self.bot.wait_until_ready()
    
    # ============= 監聽器 =============
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """新成員加入時自動創建資料庫記錄和文章"""
        try:
            if self.ensure_user_exists(member.id):
                await asyncio.sleep(2)
                await self.get_or_create_user_thread(member, skip_image_on_startup=True)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """成員離開時刪除其論壇帖子"""
        try:
            user_data = self.get_user_data(member.id)
            if not user_data or not user_data.get('thread_id'):
                return

            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            thread_id = user_data['thread_id']
            try:
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    await thread.delete()
            except (discord.NotFound, Exception):
                pass

            set_user_field(member.id, 'thread_id', 0)

        except Exception:
            pass


async def setup(bot):
    print("🔧 載入 uibody 擴展")
    try:
        await bot.add_cog(UserPanel(bot))
        print("✅ uibody 擴展載入完成")
        
        # 也加載管理員命令Cog
        from uicommands.commands.admin_commands import AdminCommands
        await bot.add_cog(AdminCommands(bot))
        print("✅ 管理員命令已載入")
    except Exception as e:
        print(f"❌ uibody 擴展載入失敗: {e}")
        import traceback
        traceback.print_exc()

