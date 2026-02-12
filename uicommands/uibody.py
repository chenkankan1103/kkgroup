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

load_dotenv()

class UpdatePanelView(discord.ui.View):
    """更新面板視圖"""
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        if not hasattr(UpdatePanelView, 'last_update'):
            UpdatePanelView.last_update = {}
    
    @discord.ui.button(label="更新面板", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="update_panel_button")
    async def update_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_time = time.time()
        last_update_time = UpdatePanelView.last_update.get(interaction.user.id, 0)
        
        if current_time - last_update_time < 5:
            remaining_time = 5 - (current_time - last_update_time)
            await interaction.response.send_message(f"⏰ 請等待 {remaining_time:.1f} 秒後再更新面板！", ephemeral=True)
            return
        
        # 從訊息的 embed 中提取 user_id（從標題或描述中）
        panel_owner_id = self.user_id
        if panel_owner_id == 0 and interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            # 嘗試從 embed 的 field 中找到使用者 ID
            for field in embed.fields:
                if field.name == "🆔 使用者ID":
                    try:
                        panel_owner_id = int(field.value.strip('`'))
                        break
                    except:
                        pass
        
        # 檢查是否為面板擁有者
        if panel_owner_id != 0 and interaction.user.id != panel_owner_id:
            await interaction.response.send_message("❌ 你只能更新自己的面板！", ephemeral=True)
            return
            
        try:
            await interaction.response.defer(ephemeral=True)
            UpdatePanelView.last_update[interaction.user.id] = current_time
            
            user_data = self.cog.get_user_data(interaction.user.id)
            if not user_data:
                await interaction.followup.send("❌ 沒有找到你的資料！", ephemeral=True)
                return
            
            embed = await self.cog.create_user_embed(user_data, interaction.user)
            character_image_url = await self.cog.get_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)
            
            # 修改搜尋邏輯：直接更新當前訊息
            try:
                await interaction.message.edit(embed=embed, view=self)
                await interaction.followup.send("✅ 面板已更新！", ephemeral=True)
                return
            except Exception as e:
                # 如果直接更新失敗，嘗試搜尋訊息
                async for message in interaction.channel.history(limit=100):
                    if (message.embeds and message.author == self.cog.bot.user and
                        message.embeds[0].title and 
                        "置物櫃" in message.embeds[0].title and
                        str(interaction.user.id) in str(message.embeds[0].description or "")):
                        try:
                            await message.edit(embed=embed, view=self)
                            await interaction.followup.send("✅ 面板已更新！", ephemeral=True)
                            return
                        except:
                            continue
            
            await interaction.followup.send("❌ 找不到面板訊息，請聯繫管理員！", ephemeral=True)
            
        except Exception as e:
            try:
                await interaction.followup.send("❌ 更新面板時發生錯誤！", ephemeral=True)
            except:
                pass

class WorkCardModal(discord.ui.Modal):
    """員工證信息表單"""
    title = "領取員工證"
    
    def __init__(self, cog, user_id: int):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        
        # 5 個輸入欄
        self.pre_job = discord.ui.TextInput(
            label="入園前身份",
            placeholder="如：上班族、學生、無業...",
            max_length=30,
            required=True
        )
        self.hobby = discord.ui.TextInput(
            label="業餘愛好",
            placeholder="如：玩遊戲、看動漫、健身...",
            max_length=50,
            required=True
        )
        
        self.add_item(self.pre_job)
        self.add_item(self.hobby)
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交表單"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 保存到資料庫
            set_user_field(self.user_id, 'pre_job', str(self.pre_job.value))
            set_user_field(self.user_id, 'hobby', str(self.hobby.value))
            set_user_field(self.user_id, 'work_card_enabled', 1)
            
            # 生成工作證 embed
            user_data = get_user(self.user_id)
            user_obj = await self.cog.bot.fetch_user(self.user_id)
            
            embed = await self.create_work_card_embed(user_data, user_obj)
            view = WorkCardEditView(self.cog, self.user_id)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            await interaction.followup.send("✅ 員工證已領取！該卡片已保存到你的置物櫃。", ephemeral=True)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 提交失敗：{str(e)[:100]}", ephemeral=True)
    
    async def create_work_card_embed(self, user_data, user_obj):
        """生成工作證卡片 embed"""
        from commands.work_function.work_system import LEVELS
        
        level = user_data.get('level', 0)
        level_info = LEVELS.get(level, {})
        xp = user_data.get('xp', 0)
        streak = user_data.get('streak', 0)
        
        # 計算下一級 XP
        next_level_xp = LEVELS.get(level + 1, {}).get('xp_required', xp) if level < 6 else xp
        
        # 生成員工編號
        user_id_suffix = str(self.user_id)[-6:].zfill(6)
        
        embed = discord.Embed(
            title="【 KK 園區聯合管理處 - 員工通行證 】",
            color=discord.Color.gold(),
            description=f"姓名：{user_obj.name}\n" +
                       f"員工編號：#{user_id_suffix}\n" +
                       f"職級：{level_info.get('title', '未知')} (Lv.{level})\n" +
                       f"業績：{xp:,} / {next_level_xp:,} XP"
        )
        
        embed.add_field(
            name="【 員工背後故事 】",
            value=(
                f"❖ 入園前身份：{user_data.get('pre_job', 'N/A')}\n"
                f"❖ 業餘愛好：{user_data.get('hobby', 'N/A')}"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 入職統計",
            value=f"連勤天數：{streak} 天 🔥",
            inline=False
        )
        
        embed.set_footer(text="🎫 此證件為 KK 園區正式員工的象徵 | 妥善保管，勿得轉讓")
        embed.timestamp = datetime.datetime.utcnow()
        
        return embed


class WorkCardEditView(discord.ui.View):
    """工作證修改選項視圖"""
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
    
    @discord.ui.button(label="修改設定", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="work_card_edit")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """修改工作證信息"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的員工證！", ephemeral=True)
            return
        
        await interaction.response.send_modal(WorkCardModal(self.cog, self.user_id))


class WorkCardActionView(discord.ui.View):
    """已有工作證時的操作視圖"""
    def __init__(self, cog, user_id: int, user_data: dict):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.user_data = user_data
    
    @discord.ui.button(label="查看我的員工證", style=discord.ButtonStyle.success, emoji="🎫", custom_id="view_my_card")
    async def view_card_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查看員工證"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 这不是你的員工證！", ephemeral=True)
            return
        
        try:
            user_obj = await self.cog.bot.fetch_user(self.user_id)
            embed = await WorkCardModal(self.cog, self.user_id).create_work_card_embed(self.user_data, user_obj)
            view = WorkCardEditView(self.cog, self.user_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="修改設定", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="modify_card_settings")
    async def modify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """修改員工證設定"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的員工證！", ephemeral=True)
            return
        
        await interaction.response.send_modal(WorkCardModal(self.cog, self.user_id))



class LockerPanelView(discord.ui.View):
    """置物櫃面板 - 包含更新和大麻系統按鈕"""
    def __init__(self, cog, user_id: int, thread=None):
        super().__init__(timeout=60)  # 設置60秒超時
        self.cog = cog
        self.user_id = user_id
        self.thread = thread
        self.current_view = "locker"
        if not hasattr(LockerPanelView, 'last_update'):
            LockerPanelView.last_update = {}
    
    async def get_owner_user_id(self, interaction: discord.Interaction) -> int:
        """根據 thread_id 從資料庫獲取論壇帖子的所有者 user_id"""
        try:
            import sqlite3
            conn = sqlite3.connect('./user_data.db')
            cursor = conn.cursor()
            
            # 如果在 thread 中，使用 thread 的 id
            thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
            if thread:
                cursor.execute('SELECT user_id FROM users WHERE thread_id = ?', (thread.id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return row[0]
            
            conn.close()
        except Exception as e:
            print(f"⚠️ 查詢 thread 所有者失敗: {e}")
        
        # 後備方案：使用 self.user_id（可能不準確，但至少不會都是 0）
        return self.user_id if self.user_id != 0 else interaction.user.id
        
    @discord.ui.button(label="更新面板", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="locker_update_panel")
    async def update_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_time = time.time()
        last_update_time = LockerPanelView.last_update.get(interaction.user.id, 0)
        
        if current_time - last_update_time < 5:
            remaining_time = 5 - (current_time - last_update_time)
            await interaction.response.send_message(f"⏰ 請等待 {remaining_time:.1f} 秒後再更新面板！", ephemeral=True)
            return
        
        # 根據 thread_id 獲取正確的所有者 user_id
        owner_user_id = await self.get_owner_user_id(interaction)
        if interaction.user.id != owner_user_id:
            await interaction.response.send_message("❌ 你只能更新自己的面板！", ephemeral=True)
            return
            
        try:
            await interaction.response.defer(ephemeral=True)
            LockerPanelView.last_update[interaction.user.id] = current_time
            
            # 重新獲取最新的用戶資料（確保數據是最新的）
            user_data = self.cog.get_user_data(owner_user_id)
            if not user_data:
                await interaction.followup.send("❌ 沒有找到你的資料！", ephemeral=True)
                return
            
            # 使用 interaction.user 而非從數據中提取用戶信息
            user = self.cog.bot.get_user(owner_user_id) or await self.cog.bot.fetch_user(owner_user_id)
            embed = await self.cog.create_user_embed(user_data, user)
            character_image_url = await self.cog.get_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)
            
            # 直接編輯當前消息
            try:
                await interaction.message.edit(embed=embed, view=self)
                await interaction.followup.send("✅ 面板已更新！", ephemeral=True)
            except Exception as e:
                print(f"❌ 編輯消息失敗: {e}")
                await interaction.followup.send("❌ 更新失敗，請聯繫管理員！", ephemeral=True)
                
        except Exception as e:
            print(f"❌ 更新面板出錯: {e}")
            try:
                await interaction.followup.send("❌ 更新面板時發生錯誤！", ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="作物資訊", style=discord.ButtonStyle.success, emoji="🌾", custom_id="locker_crop_info")
    async def crop_info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """作物資訊 - 整合種植、施肥、收割、查看狀態"""
        try:
            owner_user_id = await self.get_owner_user_id(interaction)
            if interaction.user.id != owner_user_id:
                await interaction.response.send_message("❌ 這不是你的置物櫃！", ephemeral=True)
                return
                
            await interaction.response.defer(ephemeral=True)
            
            plants = await get_user_plants(owner_user_id)
            inventory = await get_inventory(owner_user_id)
            seeds = inventory.get("種子", {})
            
            if not plants:
                await interaction.followup.send("❌ 你還沒有種植任何植物！\n點擊操作按鈕開始種植。", ephemeral=True)
                return
            
            # 計算統計信息
            total_slots = 5
            harvested = [p for p in plants if p["status"] == "harvested"]
            growing = [p for p in plants if p["status"] != "harvested"]
            
            embed = discord.Embed(
                title="🌾 作物資訊",
                description=f"已使用 {len(plants)}/{total_slots} 個位置",
                color=discord.Color.green()
            )
            
            # 生成格子視圖
            grid = self.cog._generate_locker_grid(plants, total_slots)
            embed.add_field(name="📍 置物櫃布局", value=grid, inline=False)
            
            # 按進度分類顯示
            if growing:
                embed.add_field(name="🌱 成長中的植物", value="━" * 25, inline=False)
                for idx, plant in enumerate(growing, 1):
                    seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    progress_info = await self.cog.get_plant_progress_info(plant)
                    
                    stage_emoji = self._get_growth_stage_emoji(progress_info['progress'])
                    value = (
                        f"{stage_emoji} {progress_info['stage_name']}\n"
                        f"進度：{progress_info['progress_bar']}\n"
                        f"時間：{progress_info['time_left']}\n"
                        f"施肥：{plant['fertilizer_applied']}次"
                    )
                    embed.add_field(name=f"#{idx} {seed_config['emoji']} {plant['seed_type']}", value=value, inline=True)
            
            if harvested:
                embed.add_field(name="✂️ 已成熟可收割", value="━" * 25, inline=False)
                for idx, plant in enumerate(harvested, 1):
                    seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    yield_amount = plant.get('harvested_amount', 0)
                    value = (
                        f"📊 產量：{yield_amount}\n"
                        f"準備好收割! 🎉"
                    )
                    embed.add_field(name=f"#{idx} {seed_config['emoji']} {plant['seed_type']}", value=value, inline=True)
            
            # 添加操作按鈕
            from uicommands.cannabis_locker import CropOperationView
            guild_id = interaction.guild.id if interaction.guild else 0
            channel_id = interaction.channel.id
            view = CropOperationView(self.cog.bot, self.cog, owner_user_id, guild_id, channel_id, seeds, plants, growing, harvested)
            
            embed.set_footer(text="💡 使用下方按鈕進行種植、施肥或收割操作")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="個人置物櫃", style=discord.ButtonStyle.primary, emoji="📦", custom_id="locker_personal_view")
    async def personal_locker_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """個人置物櫃 - 打開永久按鈕視圖"""
        try:
            owner_user_id = await self.get_owner_user_id(interaction)
            if interaction.user.id != owner_user_id:
                await interaction.response.send_message("❌ 這不是你的置物櫃！", ephemeral=True)
                return
                
            await interaction.response.defer(ephemeral=True)
            
            # 獲取用戶的植物數據
            plants = await get_user_plants(owner_user_id)
            
            # 創建PersonalLockerView
            from uicommands.cannabis_locker import PersonalLockerView
            guild_id = interaction.guild.id if interaction.guild else 0
            channel_id = interaction.channel.id
            # 獲取 PersonalLockerCog 實例
            add_log("ui", f"Available cogs: {list(self.cog.bot.cogs.keys())}")
            locker_cog = self.cog.bot.get_cog('PersonalLockerCog')
            add_log("ui", f"locker_cog: {locker_cog}, type: {type(locker_cog)}")
            if not locker_cog:
                await interaction.followup.send("❌ 置物櫃系統未載入，請聯繫管理員。", ephemeral=True)
                return
            if not hasattr(locker_cog, 'record_event'):
                await interaction.followup.send("❌ 置物櫃系統缺少必要方法，請聯繫管理員。", ephemeral=True)
                return
            view = PersonalLockerView(self.cog.bot, locker_cog, owner_user_id, guild_id, channel_id, plants, user_panel=self.cog)
            
            embed = discord.Embed(
                title="📦 個人置物櫃",
                description="使用下方按鈕管理你的作物種植、施肥和收割操作。",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🌱 作物管理",
                value="• 作物種植：開始種植新的作物\n• 施肥：為成長中的植物施肥\n• 收割：收割成熟的作物\n• 查看肥料：檢查你的肥料庫存",
                inline=False
            )
            
            embed.set_footer(text="💡 這個視圖是永久的，按鈕不會過期")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="領取員工證", style=discord.ButtonStyle.danger, emoji="🎫", custom_id="locker_work_card")
    async def work_card_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """領取或修改員工證（紅色按鈕）"""
        try:
            owner_user_id = await self.get_owner_user_id(interaction)
            if interaction.user.id != owner_user_id:
                await interaction.response.send_message("❌ 這不是你的置物櫃！", ephemeral=True)
                return
            
            user_data = get_user(owner_user_id)
            
            # 檢查是否已填寫工作證信息（pre_job 存在表示已領取）
            if user_data and user_data.get('pre_job'):
                # 已有工作證，顯示修改選項並移除按鈕
                view = WorkCardActionView(self.cog, owner_user_id, user_data)
                await interaction.response.send_message("✅ 你已經有員工證了！", view=view, ephemeral=True)
            else:
                # 首次領取，顯示表單
                await interaction.response.send_modal(WorkCardModal(self.cog, owner_user_id))
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.response.send_message(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

class UserPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'
        self.FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
        self.image_storage_channel_id = int(os.getenv('IMAGE_STORAGE_CHANNEL_ID', '0'))
        self.welcome_channel_id = int(os.getenv('WELCOME_CHANNEL_ID', '0'))
        
        # AI 設定
        self.AI_API_KEY = os.getenv('AI_API_KEY')
        self.AI_API_URL = os.getenv('AI_API_URL')
        self.AI_API_MODEL = os.getenv('AI_API_MODEL')
        
        # Groq 備用 API（備選方案）
        self.GROQ_API_KEY = os.getenv('GROQ_API_KEY')
        self.GROQ_API_URL = os.getenv('GROQ_API_URL')
        self.GROQ_API_MODEL = os.getenv('GROQ_API_MODEL', 'mixtral-8x7b-32768')
        
        # 判斷優先使用的 API（Google / Gemini > Groq）
        self.use_google_api = True
        if self.AI_API_KEY and 'generativelanguage.googleapis.com' in (self.AI_API_URL or ''):
            # 有 Google/Gemini API，使用它作為主要 API
            self.use_google_api = True
        else:
            # 沒有 Gemini，改用 Groq
            self.use_google_api = False
        
        # 圖片緩存設定
        self.cache_dir = Path('./character_images')
        self.cache_dir.mkdir(exist_ok=True)
        
        # 註冊永久視圖
        self.bot.add_view(UpdatePanelView(self, 0))
        self.bot.add_view(LockerPanelView(self, 0))
        
        self.init_database()

    def init_database(self):
        """Initialize database - only image_cache table needed (users managed by db_adapter)"""
        try:
            # Initialize in-memory image cache (replaces SQLite table)
            if not hasattr(self, 'image_cache'):
                self.image_cache = {}
            
        except Exception:
            pass

    def generate_character_cache_key(self, user_data: dict) -> str:
        key_parts = [
            str(user_data.get('face', 20000)), str(user_data.get('hair', 30000)),
            str(user_data.get('skin', 12000)), str(user_data.get('top', 1040010)),
            str(user_data.get('bottom', 1060096)), str(user_data.get('shoes', 1072288)),
            str(user_data.get('is_stunned', 0))
        ]
        key_string = "_".join(key_parts)
        return f"char_{hashlib.md5(key_string.encode()).hexdigest()}"

    def get_cached_discord_url(self, cache_key: str) -> Optional[str]:
        try:
            # Clean up expired cache entries
            thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
            expired_keys = [key for key, data in self.image_cache.items() 
                           if data.get('created_at', 0) < thirty_days_ago]
            for key in expired_keys:
                del self.image_cache[key]
            
            # Retrieve cached URL
            if cache_key in self.image_cache:
                return self.image_cache[cache_key].get('discord_url')
            return None
            
        except Exception:
            return None

    def save_discord_url_cache(self, cache_key: str, discord_url: str, message_id: int = None):
        try:
            current_time = int(time.time())
            self.image_cache[cache_key] = {
                'discord_url': discord_url,
                'created_at': current_time,
                'message_id': message_id
            }
            
        except Exception:
            pass

    async def upload_image_to_discord_storage(self, image_data: bytes, cache_key: str) -> Optional[str]:
        """上傳圖片到 Discord 存儲頻道 - 保持訊息以維持 URL 永久有效"""
        try:
            # 優先使用 IMAGE_STORAGE_CHANNEL_ID（專用存儲頻道）
            # 如果未配置，回退到歡迎頻道
            storage_channel_id = self.image_storage_channel_id or self.welcome_channel_id
            
            channel = self.bot.get_channel(storage_channel_id)
            if not channel:
                print(f"❌ 找不到存儲頻道: {storage_channel_id}")
                return None
            
            file_obj = discord.File(io.BytesIO(image_data), filename=f'{cache_key}.png')
            
            if self.image_storage_channel_id and self.image_storage_channel_id != self.welcome_channel_id:
                # 【推薦】使用專用存儲頻道：保留訊息以維持 URL 永久有效
                storage_msg = await channel.send(content=f"🖼️ **角色圖片** - {cache_key}", file=file_obj)
                if storage_msg.attachments:
                    discord_url = storage_msg.attachments[0].url
                    self.save_discord_url_cache(cache_key, discord_url, storage_msg.id)
                    print(f"✅ 圖片已存儲至存儲頻道: {storage_msg.id}")
                    return discord_url
            else:
                # 【備用】歡迎頻道：臨時訊息（發送後刪除）
                temp_msg = await channel.send(file=file_obj)
                if temp_msg.attachments:
                    discord_url = temp_msg.attachments[0].url
                    self.save_discord_url_cache(cache_key, discord_url, temp_msg.id)
                    try:
                        await asyncio.sleep(0.5)
                        await temp_msg.delete()
                    except discord.NotFound:
                        pass
                    return discord_url
            
        except Exception as e:
            print(f"❌ 上傳圖片失敗: {e}")
        return None

    async def get_character_image_url(self, user_data: dict) -> Optional[str]:
        """獲取角色圖片 URL（優先使用快取，再用 API）"""
        cache_key = self.generate_character_cache_key(user_data)
        user_id = user_data.get('user_id')
        
        # 1️⃣ 先檢查記憶體快取
        cached_url = self.get_cached_discord_url(cache_key)
        if cached_url:
            return cached_url
        
        # 2️⃣ 檢查數據庫中是否有已存儲的圖片 URL（持久化快取）
        try:
            cached_char_data = get_user_field(user_id, 'cached_character_image', default=None)
            if cached_char_data:
                try:
                    char_cache = json.loads(cached_char_data)
                    # 驗證快取有效性（配置沒有改變）
                    current_key = self.generate_character_cache_key(user_data)
                    if char_cache.get('cache_key') == current_key and char_cache.get('discord_url'):
                        stored_url = char_cache['discord_url']
                        # 同步到記憶體快取
                        self.save_discord_url_cache(cache_key, stored_url)
                        return stored_url
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        
        # 3️⃣ 調用 API 獲取圖片（帶超時保護）
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

            if user_data.get('is_stunned', 0) == 1:
                items.append({"itemId": 1005411, "region": "GMS", "version": "217"})

            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
            url = f"https://maplestory.io/api/character/{item_path}/{pose}/animated?showears=false&resize=2&flipX=true"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:  # 降低超時到 10 秒
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            discord_url = await self.upload_image_to_discord_storage(image_data, cache_key)
                            if discord_url:
                                # 🔒 保存到數據庫以供持久化快取
                                char_cache = {
                                    'cache_key': cache_key,
                                    'discord_url': discord_url,
                                    'timestamp': int(time.time())
                                }
                                try:
                                    set_user_field(user_id, 'cached_character_image', json.dumps(char_cache))
                                except Exception:
                                    pass
                                return discord_url

        except asyncio.TimeoutError:
            print(f"⏱️ 楓之谷 API 超時 (用戶 {user_id})")
        except Exception as e:
            print(f"❌ 獲取角色圖片失敗: {e}")
        
        return None

    async def restore_image_cache_from_storage(self):
        """🔄 啟動時掃描存儲頻道，恢復快取 URL（避免重新上傳）"""
        try:
            if not self.image_storage_channel_id:
                return
            
            channel = self.bot.get_channel(self.image_storage_channel_id)
            if not channel:
                print(f"⚠️ 無法找到存儲頻道: {self.image_storage_channel_id}")
                return
            
            print(f"🔄 正在掃描存儲頻道以恢復圖片快取...")
            recovered_count = 0
            
            # 掃描最近的訊息（限制 500 條以避免超時）
            async for message in channel.history(limit=500):
                try:
                    # 檢查訊息是否有附件
                    if not message.attachments:
                        continue
                    
                    for attachment in message.attachments:
                        # 從檔名中提取 cache_key（例如：20001520000...png）
                        filename = attachment.filename or ""
                        if filename.endswith('.png') and len(filename) > 10:
                            cache_key = filename.replace('.png', '')
                            
                            # 驗證格式（cache_key 應該都是數字和逗號）
                            if cache_key.replace(',', '').isdigit():
                                discord_url = attachment.url
                                self.save_discord_url_cache(cache_key, discord_url, message.id)
                                recovered_count += 1
                
                except Exception as e:
                    continue
            
            print(f"✅ 成功恢復 {recovered_count} 個圖片快取")
        
        except Exception as e:
            print(f"⚠️ 恢復快取時出錯: {e}")

    async def cog_load(self):
        await self.bot.wait_until_ready()
        
        # 👇 新增：啟動時恢復圖片快取（避免重新上傳）
        await self.restore_image_cache_from_storage()
        
        forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
        if forum_channel and isinstance(forum_channel, discord.ForumChannel):
            await self.create_threads_for_existing_members()
        
        # 啟動週統計任務
        if not self.weekly_summary.is_running():
            self.weekly_summary.start()
        
        # 啟動論壇帖子清理檢查任務
        if not self.check_member_threads.is_running():
            self.check_member_threads.start()

    def cog_unload(self):
        if self.weekly_summary.is_running():
            self.weekly_summary.cancel()
        if self.check_member_threads.is_running():
            self.check_member_threads.cancel()

    @tasks.loop(minutes=1)
    async def weekly_summary(self):
        """每週日晚上 23:59 執行週統計"""
        try:
            # 獲取當前時間（使用台灣時區 UTC+8）
            now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            
            # 檢查是否為週日 23:59
            if now.weekday() != 6:  # 6 = 週日 (0=週一, 6=週日)
                return
                
            if now.hour != 23 or now.minute != 59:
                return
            
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return

            # Use db_adapter to get all users with thread
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
                    
                    # 計算週增長量
                    kkcoin_change = (current_kkcoin or 0) - (last_kkcoin or 0)
                    xp_change = (current_xp or 0) - (last_xp or 0)
                    level_change = (current_level or 1) - (last_level or 1)
                    
                    # 只有當有變化時才發送統計
                    if kkcoin_change > 0 or xp_change > 0 or level_change > 0:
                        # 生成 AI 評論
                        ai_comment = await self.generate_ai_comment(member, kkcoin_change, xp_change, level_change)
                        
                        # 創建統計嵌入
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
                        
                        # 發送統計訊息
                        await thread.send(embed=embed)
                        
                        await asyncio.sleep(1)
                    
                    # 快照數據（無論是否有變化都要，避免累積誤差）
                    cursor.execute('''
                        UPDATE users 
                        SET last_kkcoin_snapshot = ?, last_xp_snapshot = ?, last_level_snapshot = ?
                        WHERE user_id = ?
                    ''', (current_kkcoin, current_xp, current_level, user_id))
                    
                except Exception:
                    continue
            
            conn.commit()
            conn.close()
            
        except Exception:
            pass

    @weekly_summary.before_loop
    async def before_weekly_summary(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def check_member_threads(self):
        """每小時檢查一次：驗證論壇帖子對應的成員是否仍在服務器
        如果成員已離開，自動刪除該帖子並清空記錄"""
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return
            
            guild = forum_channel.guild
            
            # 從資料庫獲取所有有帖子的成員（使用 db_adapter）
            # Note: 由於 db_adapter 基於 SHEET，我們需要掃描所有用戶
            # 這是一個簡化實現 - 在生產環境中應該使用更高效的方法
            try:
                # 如果 db_adapter 提供遍歷功能，使用它；否則只檢查論壇中的存在帖子
                for thread in forum_channel.threads:
                    try:
                        # 從帖子標籤或名稱推斷 user_id（根據你的實現）
                        # 或者查詢所有用戶
                        if hasattr(thread, 'created_by'):
                            user_id = thread.created_by.id
                            thread_id = thread.id
                            
                            # 檢查成員是否仍在伺服器
                            member = guild.get_member(user_id)
                            
                            if not member:
                                # 成員已離開，刪除帖子
                                try:
                                    await thread.delete()
                                    print(f"🗑️ 已刪除已離開成員 {user_id} 的帖子 (thread_id: {thread_id})")
                                    # 清空資料庫記錄
                                    set_user_field(user_id, 'thread_id', 0)
                                except discord.NotFound:
                                    pass
                    except Exception as e:
                        print(f"❌ 檢查帖子時出錯: {e}")
                
                print("📊 論壇帖子檢查完成")
            except Exception as e:
                print(f"⚠️ 無法遊歷帖子: {e}")
            
            conn.commit()
            conn.close()
        
        except Exception as e:
            print(f"❌ 論壇帖子檢查失敗: {e}")

    @check_member_threads.before_loop
    async def before_check_member_threads(self):
        """等待 bot 準備好後再開始檢查"""
        await self.bot.wait_until_ready()

    async def generate_ai_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        """生成 AI 評論（優先 Google/Gemini，備用 Groq）"""
        try:
            # 優先嘗試 Google/Gemini
            if self.AI_API_KEY and self.AI_API_URL:
                comment = await self._generate_google_comment(member, kkcoin_change, xp_change, level_change)
                if comment:
                    return comment
            
            # Google 失敗（包括 429），降級到 Groq
            if self.GROQ_API_KEY and self.GROQ_API_URL:
                comment = await self._generate_groq_comment(member, kkcoin_change, xp_change, level_change)
                if comment:
                    return comment
        except Exception:
            pass
        
        return f"本週表現不錯！繼續保持這個節奏 💪"
    
    async def _generate_google_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        """使用 Google Generative AI 生成評論（若配額超限則無聲返回 None，上層會自動降級）"""
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
                        # 配額超限（無聲返回 None，上層會降級到 Groq）
                        return None
        except Exception:
            # 任何錯誤都無聲返回 None，讓上層嘗試 Groq
            pass
        
        return None
    
    async def _generate_groq_comment(self, member: discord.Member, kkcoin_change: int, xp_change: int, level_change: int) -> str:
        """使用 Groq API 生成評論（備用方案）"""
        try:
            if not all([self.GROQ_API_KEY, self.GROQ_API_URL, self.GROQ_API_MODEL]):
                return None

            prompt = f"""你是一個友善的遊戲助手，請為玩家 {member.display_name or member.name} 本週的表現寫一段鼓勵性的評論。

本週數據：
- KKCoin 增長: {kkcoin_change}
- 經驗值 增長: {xp_change}
- 等級 提升: {level_change}

請用繁體中文回應，語氣要活潑友善，長度控制在50字以內，可以適當使用表情符號。
"""
            
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
            # 任何錯誤都無聲返回 None
            pass
        
        return None

    def ensure_user_exists(self, user_id: int) -> bool:
        """確保使用者在資料庫中存在，如果不存在則創建"""
        try:
            # 使用 db_adapter 檢查和創建用戶
            user_data = get_user(user_id)
            
            if user_data:
                return True
            
            # 創建新使用者
            from db_adapter import set_user
            set_user(user_id, {
                'user_id': user_id,
                'level': 1,
                'xp': 0,
                'kkcoin': 0,
                'title': '新手',
                'hp': 100,
                'stamina': 100,
                'inventory': '[]',
                'character_config': '{}',
                'face': 20000,
                'hair': 30000,
                'skin': 12000,
                'top': 1040010,
                'bottom': 1060096,
                'shoes': 1072288,
                'is_stunned': 0,
                'gender': 'male',
                'thread_id': 0
            })
            
            return True
            
        except Exception:
            return False

    async def create_threads_for_existing_members(self):
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
            
            # Get all users using db_adapter
            all_users = get_all_users()
            
            # 統計：有效/需要創建的線程
            threads_to_create = []
            existing_threads = 0
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id', 0)
                try:
                    member = guild.get_member(user_id)
                    if not member:
                        continue
                    
                    # 檢查現有文章是否存在
                    if thread_id and thread_id != 0:
                        thread = forum_channel.get_thread(thread_id)
                        if thread:
                            existing_threads += 1
                            continue  # ✅ 線程已存在，跳過不重新創建
                        else:
                            # 線程已被刪除，重置 thread_id
                            set_user_field(user_id, 'thread_id', 0)
                            threads_to_create.append(member)
                    else:
                        # 用戶從未創建線程
                        threads_to_create.append(member)
                            
                except Exception:
                    continue
            
            # 【優化】只在確實需要時才創建線程
            if threads_to_create:
                print(f"🔧 發現需要創建的線程: {len(threads_to_create)} 個 (已有線程: {existing_threads})")
                
                # 遍歷需要創建的線程
                for member in threads_to_create:
                    try:
                        thread = await self.get_or_create_user_thread(member, skip_image_on_startup=True)
                        if thread:
                            await asyncio.sleep(1)  # 降低速率，減少 API 壓力
                    except discord.HTTPException as e:
                        if e.status == 429:  # Rate limit
                            print(f"⚠️ 遇到速率限制，稍候 30 秒...")
                            await asyncio.sleep(30)
                            # 重試一次
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

    def get_user_data(self, user_id: int) -> Optional[dict]:
        try:
            # Use db_adapter to get user data
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

    def create_progress_bar(self, current: int, maximum: int, length: int = 10) -> str:
        if maximum == 0:
            percentage = 0
        else:
            percentage = max(0, min(1, current / maximum))
        filled = int(length * percentage)
        return '█' * filled + '░' * (length - filled)

    async def create_user_embed(self, user_data: dict, user: discord.User) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊 {user.display_name or user.name} 的置物櫃",
            color=0x00ff88,
            timestamp=discord.utils.utcnow()
        )
        
        try:
            embed.set_thumbnail(url=user.display_avatar.url)
        except:
            pass
            
        embed.add_field(name="🆔 使用者ID", value=f"`{user_data['user_id']}`", inline=True)
        embed.add_field(name="⭐ 等級", value=f"**{user_data['level'] or 1}**", inline=True)
        embed.add_field(name="✨ 經驗值", value=f"{user_data['xp'] or 0} XP", inline=True)
        embed.add_field(name="💰 金錢", value=f"{user_data['kkcoin'] or 0} KKCoin", inline=True)
        embed.add_field(name="🏆 職位", value=user_data['title'] or '新手', inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        hp = user_data['hp'] or 100
        stamina = user_data['stamina'] or 100
        hp_bar = self.create_progress_bar(hp, 100)
        stamina_bar = self.create_progress_bar(stamina, 100)
        embed.add_field(name="❤️ 血量", value=f"{hp_bar} {hp}/100", inline=False)
        embed.add_field(name="⚡ 體力", value=f"{stamina_bar} {stamina}/100", inline=False)

        embed.add_field(name="👔 上身裝備", value=f"ID: {user_data['top']}", inline=True)
        embed.add_field(name="👖 下身裝備", value=f"ID: {user_data['bottom']}", inline=True)
        embed.add_field(name="👟 鞋子", value=f"ID: {user_data['shoes']}", inline=True)
        
        embed.add_field(name="💇 髮型", value=f"ID: {user_data['hair']}", inline=True)
        embed.add_field(name="😊 臉型", value=f"ID: {user_data['face']}", inline=True)
        embed.add_field(name="🎨 膚色", value=f"ID: {user_data['skin']}", inline=True)

        inventory = '空的'
        if user_data['inventory']:
            try:
                items = json.loads(user_data['inventory'])
                if isinstance(items, list) and len(items) > 0:
                    inventory = ', '.join(str(item) for item in items[:5])
                    if len(items) > 5:
                        inventory += f"... 等 {len(items)} 項物品"
            except json.JSONDecodeError:
                inventory_str = str(user_data['inventory'])
                inventory = inventory_str[:50] + '...' if len(inventory_str) > 50 else inventory_str
        embed.add_field(name="🎒 物品欄", value=inventory, inline=False)
        
        embed.set_footer(text="💫 由 MapleStory.io API 提供角色外觀")
        return embed

    def _generate_locker_grid(self, plants, total_slots: int = 5) -> str:
        """生成置物櫃格子視圖"""
        grid_rows = []
        
        # 轉換植物為網格位置
        plant_positions = {}
        for idx, plant in enumerate(plants):
            if idx < total_slots:
                plant_positions[idx] = plant
        
        # 生成置物櫃視圖
        grid = ""
        for i in range(total_slots):
            if i in plant_positions:
                plant = plant_positions[i]
                progress_percent = self._calculate_plant_progress(plant)
                stage_emoji = self._get_growth_stage_emoji(progress_percent)
                grid += f"[{stage_emoji}]  "
            else:
                grid += "[⬜]  "
        
        return f"`{grid}`\n位置 1-5"

    def _get_growth_stage_emoji(self, progress: float) -> str:
        """根據進度返回生長階段emoji"""
        if progress >= 95:
            return "🌾"  # 成熟/即將收割
        elif progress >= 75:
            return "🌿"  # 茁壯期
        elif progress >= 50:
            return "🌱"  # 發芽期
        elif progress >= 25:
            return "🌱"  # 嫩芽期
        else:
            return "⚪"  # 初始階段

    def _calculate_plant_progress(self, plant: dict) -> float:
        """計算植物的成長進度百分比"""
        if plant.get("status") == "harvested":
            return 100.0
        
        try:
            from datetime import datetime
            planted_time = plant.get("planted_at", 0)
            matured_time = plant.get("matured_at", 0)
            
            if isinstance(planted_time, str):
                planted_time = datetime.fromisoformat(planted_time).timestamp()
            if isinstance(matured_time, str):
                matured_time = datetime.fromisoformat(matured_time).timestamp()
            
            now = datetime.now().timestamp()
            elapsed = now - planted_time
            total = matured_time - planted_time
            
            progress = min(100, (elapsed / total * 100)) if total > 0 else 0
            return progress
        except Exception:
            return 0.0

    async def get_plant_progress_info(self, plant: dict) -> dict:
        """獲取植物的進度詳細信息"""
        from datetime import datetime
        import asyncio
        
        try:
            if plant.get("status") == "harvested":
                return {
                    'progress': 100.0,
                    'stage_name': '已成熟',
                    'progress_bar': '█████████████████████ 100%',
                    'time_left': '準備收割',
                    'fertilizer': plant.get('fertilizer_applied', 0)
                }
            
            planted_time = plant.get("planted_at", 0)
            matured_time = plant.get("matured_at", 0)
            
            if isinstance(planted_time, str):
                planted_time = datetime.fromisoformat(planted_time).timestamp()
            if isinstance(matured_time, str):
                matured_time = datetime.fromisoformat(matured_time).timestamp()
            
            now = datetime.now().timestamp()
            elapsed = now - planted_time
            total = matured_time - planted_time
            progress = min(100, (elapsed / total * 100)) if total > 0 else 0
            
            # 生成進度條
            filled = int(progress / 5)
            empty = 20 - filled
            progress_bar_text = f"{'█' * filled}{'░' * empty} {progress:.0f}%"
            
            # 計算剩餘時間
            remaining = max(0, matured_time - now)
            if remaining > 0:
                hours = int(remaining // 3600)
                mins = int((remaining % 3600) // 60)
                time_left = f"剩餘 {hours}h {mins}m"
            else:
                time_left = "✅ 已成熟"
            
            # 確定生長階段名稱
            if progress >= 75:
                stage_name = "茁壯中 🌿"
            elif progress >= 40:
                stage_name = "發芽中 🌱"
            else:
                stage_name = "嫩芽期 🌱"
            
            return {
                'progress': progress,
                'stage_name': stage_name,
                'progress_bar': progress_bar_text,
                'time_left': time_left,
                'fertilizer': plant.get('fertilizer_applied', 0)
            }
        except Exception as e:
            print(f"⚠️ 計算植物進度失敗: {e}")
            return {
                'progress': 0.0,
                'stage_name': '未知',
                'progress_bar': '░░░░░░░░░░░░░░░░░░░░ 0%',
                'time_left': '未知',
                'fertilizer': 0
            }

    async def get_or_create_user_thread(self, user: discord.User, skip_image_on_startup: bool = False) -> Optional[discord.Thread]:
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return None

            # 確保使用者在資料庫中存在
            if not self.ensure_user_exists(user.id):
                return None

            user_data = self.get_user_data(user.id)
            if not user_data:
                return None

            # 檢查是否已有文章
            thread_id = user_data.get('thread_id', 0)
            if thread_id:
                thread = forum_channel.get_thread(thread_id)
                if thread:
                    return thread
                else:
                    set_user_field(user.id, 'thread_id', 0)
            
            # 檢查機器人權限
            bot_member = forum_channel.guild.get_member(self.bot.user.id)
            if not bot_member:
                return None
                
            permissions = forum_channel.permissions_for(bot_member)
            if not permissions.send_messages or not permissions.create_public_threads:
                return None
            
            # 創建面板
            embed = await self.create_user_embed(user_data, user)
            
            # 獲取角色圖片 - 重啟時跳過 API 調用
            try:
                if skip_image_on_startup:
                    # 只使用快取，不調用 API
                    cache_key = self.generate_character_cache_key(user_data)
                    character_image_url = self.get_cached_discord_url(cache_key)
                else:
                    character_image_url = await self.get_character_image_url(user_data)
                if character_image_url:
                    embed.set_image(url=character_image_url)
            except Exception:
                pass

            # 創建文章標題
            thread_name = f"📦 {user.display_name or user.name} 的置物櫃"
            
            # 創建 View - 使用 LockerPanelView 包含大麻系統按鈕
            view = LockerPanelView(self, user.id)
            
            # 嘗試創建文章
            try:
                thread, message = await forum_channel.create_thread(
                    name=thread_name, 
                    embed=embed, 
                    view=view,
                    content="👋 這是你的專屬置物櫃～"
                )
                # 強制將用戶加入線程
                try:
                    await thread.add_user(user)
                    print(f"✅ 用戶 {user.id} 已添加到線程 {thread.id}")
                except Exception as e:
                    print(f"⚠️ 將用戶加入線程失敗 {user.id}: {e}")
            except discord.HTTPException as http_e:
                if http_e.status == 400:
                    # 可能是 embed 或 view 問題，嘗試只用基本內容
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
                    # 強制將用戶加入線程
                    try:
                        await thread.add_user(user)
                        print(f"✅ 用戶 {user.id} 已添加到線程 {thread.id}")
                    except Exception as e:
                        print(f"⚠️ 將用戶加入線程失敗 {user.id}: {e}")
                    # 然後更新為完整內容
                    await message.edit(embed=embed, view=view)
                else:
                    raise

            # 更新資料庫 - 使用 db_adapter
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

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """當有新成員加入時自動創建資料庫記錄和文章 - 重啟期間跳過圖片加載"""
        try:
            # 確保使用者在資料庫中存在
            if self.ensure_user_exists(member.id):
                # 等待一下讓成員完全加入
                await asyncio.sleep(2)
                
                # 嘗試創建文章 - 避免重啟期間重複上傳圖片
                await self.get_or_create_user_thread(member, skip_image_on_startup=True)
                
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
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
    await bot.add_cog(UserPanel(bot))

