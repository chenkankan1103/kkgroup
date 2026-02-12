import discord
import time
import sqlite3
from db_adapter import set_user_field, get_user
from shop_commands.merchant.cannabis_farming import get_user_plants, get_inventory
from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
from .work_card import WorkCardModal, WorkCardEditView, WorkCardActionView


class LockerPanelView(discord.ui.View):
    """置物櫃面板 - 包含更新和大麻系統按鈕"""
    def __init__(self, cog, user_id: int, thread=None):
        super().__init__(timeout=None)  # 永久View
        self.cog = cog
        self.user_id = user_id
        self.thread = thread
        self.current_view = "locker"
        if not hasattr(LockerPanelView, 'last_update'):
            LockerPanelView.last_update = {}
    
    async def get_owner_user_id(self, interaction: discord.Interaction) -> int:
        """根據 thread_id 從資料庫獲取論壇帖子的所有者 user_id"""
        try:
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
        
        # 後備方案：使用 self.user_id
        return self.user_id if self.user_id != 0 else interaction.user.id
    
    def _get_growth_stage_emoji(self, progress: int) -> str:
        """根據進度獲取階段 emoji"""
        if progress < 25:
            return "🌱"
        elif progress < 50:
            return "🌿"
        elif progress < 75:
            return "🌾"
        else:
            return "🌲"
        
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
            
            # 更新最後活動時間
            set_user_field(owner_user_id, 'last_activity', int(time.time()))
            
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
            
            # 更新最後活動時間
            set_user_field(owner_user_id, 'last_activity', int(time.time()))
            
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
            
            # 更新最後活動時間
            set_user_field(owner_user_id, 'last_activity', int(time.time()))
            
            # 獲取用戶的植物數據
            plants = await get_user_plants(owner_user_id)
            
            # 創建PersonalLockerView
            from uicommands.cannabis_locker import PersonalLockerView
            guild_id = interaction.guild.id if interaction.guild else 0
            channel_id = interaction.channel.id
            # 獲取 PersonalLockerCog 實例
            from status_dashboard import add_log
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
            
            # 更新最後活動時間
            set_user_field(owner_user_id, 'last_activity', int(time.time()))
            
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
