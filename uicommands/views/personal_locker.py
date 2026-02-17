import discord
from discord.ui import Button
from datetime import datetime
import traceback

from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from shop_commands.merchant.cannabis_farming import get_inventory, get_user_plants, add_inventory, remove_inventory, plant_cannabis, harvest_plant
from shop_commands.merchant.database import update_user_kkcoin
from status_dashboard import add_log


class PersonalLockerView(discord.ui.View):
    """個人置物櫃主視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, plants, user_panel):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.plants = plants
        self.user_panel = user_panel

        # 動態添加按鈕
        self.add_buttons()

    def add_buttons(self):
        """根據用戶物品動態添加按鈕"""
        # 作物資訊按鈕 - 永遠顯示
        crop_button = discord.ui.Button(
            label="作物資訊", 
            style=discord.ButtonStyle.primary, 
            emoji="🌾",
            custom_id="crop_info"
        )
        crop_button.callback = self.crop_info_callback
        self.add_item(crop_button)

        # 個人物品按鈕 - 永遠顯示
        items_button = discord.ui.Button(
            label="個人物品", 
            style=discord.ButtonStyle.secondary, 
            emoji="🎒",
            custom_id="personal_items"
        )
        items_button.callback = self.personal_items_callback
        self.add_item(items_button)

        # 變換性別按鈕 - 永久視圖（將工作證的「修改性別」移到置物櫃）
        gender_button = discord.ui.Button(
            label="變換性別",
            style=discord.ButtonStyle.secondary,
            emoji="👤",
            custom_id="locker_change_gender"
        )
        gender_button.callback = self.locker_change_gender_callback
        self.add_item(gender_button)

    async def crop_info_callback(self, interaction: discord.Interaction):
        """作物資訊"""
        await self.crop_info_callback_impl(interaction)

    async def personal_items_callback(self, interaction: discord.Interaction):
        """個人物品"""
        await self.personal_items_callback_impl(interaction)

    async def locker_change_gender_callback(self, interaction: discord.Interaction):
        """從置物櫃彈出性別選擇（永久視圖，立即 defer 以避免 3 秒超時）"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的置物櫃！", ephemeral=True)
            return

        # 立刻 defer，避免 Discord 判定交互失敗（3 秒限制）
        await interaction.response.defer(ephemeral=True)

        # 延遲載入以避免循環 import
        try:
            from uicommands.views.work_card import GenderSelectView
        except Exception as e:
            await interaction.followup.send("❌ 系統錯誤：無法載入性別選擇視圖。", ephemeral=True)
            return

        gender_view = GenderSelectView(self.cog, self.user_id)
        await interaction.followup.send("請選擇你的性別：", view=gender_view, ephemeral=True)

    async def crop_planting_callback(self, interaction: discord.Interaction):
        """作物種植 - 顯示種子選擇介面"""
        try:
            # await interaction.response.defer(ephemeral=True)

            # 獲取用戶種子庫存
            try:
                inventory = await get_inventory(self.user_id)
                if not inventory:
                    print(f"⚠️  [Crop Planting] Failed to get inventory for user {self.user_id}")
                    await interaction.response.send_message("❌ 無法獲取庫存資料！請稍後再試。", ephemeral=True)
                    return
            except Exception as inv_error:
                print(f"❌ [Crop Planting] Inventory error for user {self.user_id}: {inv_error}")
                traceback.print_exc()
                await interaction.response.send_message("❌ 獲取庫存時發生錯誤！請聯繫管理員。", ephemeral=True)
                return

            seeds = inventory.get("種子", {})

            # 檢查是否有種子
            if not seeds or not any(qty > 0 for qty in seeds.values()):
                await interaction.response.send_message("❌ 你沒有種子！請先到商店購買種子。", ephemeral=True)
                return

            # 顯示種子選擇界面
            embed = discord.Embed(
                title="🌱 作物種植 - 選擇種子",
                description="選擇一種種子進行種植",
                color=discord.Color.green()
            )

            for seed_name, qty in seeds.items():
                if qty > 0:
                    try:
                        config = CANNABIS_SHOP["種子"][seed_name]
                        embed.add_field(
                            name=f"{config['emoji']} {seed_name}",
                            value=f"擁有：{qty} 粒\n成長時間：{config['growth_time']//3600}h\n最大產量：{config['max_yield']}",
                            inline=True
                        )
                    except KeyError:
                        print(f"⚠️  [Crop Planting] Seed type '{seed_name}' not found in CANNABIS_SHOP")
                        continue

            from .selection_views import SelectSeedView
            view = SelectSeedView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, seeds)
            # 編輯原始回應而不是發送新訊息
            await interaction.response.edit_message(embed=embed, view=view)
            add_log("ui", f"[Crop Planting] Seed selection view updated for user {self.user_id}")

        except Exception as e:
            add_log("ui", f"[Crop Planting] Unexpected error for user {self.user_id}: {e}")
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
            except:
                pass

    def make_plant_callback(self, seed_name):
        """生成種植回調函數"""
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)

                # 檢查是否有種子
                has_seed = await remove_inventory(self.user_id, "種子", seed_name, 1)
                if not has_seed:
                    await interaction.followup.send("❌ 你沒有這種種子！", ephemeral=True)
                    return

                # 種植
                result = await plant_cannabis(self.user_id, self.guild_id, self.channel_id, seed_name)

                if result and not result.get("success") == False:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    embed = discord.Embed(
                        title="🌱 種植成功",
                        description=f"已種植 {seed_name}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="成長時間", value=f"{config['growth_time']//3600} 小時", inline=False)
                    embed.add_field(name="最大產量", value=f"{config['max_yield']} 個", inline=False)

                    # 記錄事件
                    if self.cog:
                        user = await self.bot.fetch_user(self.user_id)
                        await self.cog.record_event(
                            'plant',
                            user,
                            f"種植{seed_name}"
                        )

                    # 創建包含返回按鈕的view
                    from .selection_views import PlantResultView
                    result_view = PlantResultView(self.user_id, self)

                    await interaction.followup.send(embed=embed, view=result_view, ephemeral=True)
                else:
                    # 種植失敗，退還種子
                    await add_inventory(self.user_id, "種子", seed_name, 1)
                    reason = result.get("reason", "未知原因") if result else "未知原因"
                    await interaction.followup.send(f"❌ 種植失敗：{reason}", ephemeral=True)

            except Exception as e:
                traceback.print_exc()
                # 如果發生錯誤，嘗試退還種子
                try:
                    await add_inventory(self.user_id, "種子", seed_name, 1)
                except Exception as refund_error:
                    print(f"⚠️ 退還種子失敗：{refund_error}", file=__import__('sys').stderr)
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

        return callback

    async def crop_info_callback_impl(self, interaction: discord.Interaction):
        """作物資訊 - 顯示作物狀態和操作選項"""
        try:
            await interaction.response.defer()

            plants = await get_user_plants(self.user_id)
            inventory = await get_inventory(self.user_id)
            seeds = inventory.get("種子", {})
            fertilizers = inventory.get("肥料", {})

            # 分類植物
            growing = [p for p in plants if p["status"] != "harvested"]
            harvested = [p for p in plants if p["status"] == "harvested"]

            embed = discord.Embed(
                title="🌾 作物資訊",
                description=f"已使用 {len(plants)}/5 個位置",
                color=discord.Color.green()
            )

            # 顯示成長中的植物
            if growing:
                embed.add_field(name="🌱 成長中的植物", value="━" * 25, inline=False)
                for idx, plant in enumerate(growing, 1):
                    config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    # 計算進度
                    if plant["status"] == "harvested":
                        progress = 100
                        time_left = "已成熟"
                    else:
                        planted_time = plant["planted_at"]
                        matured_time = plant["matured_at"]

                        # 處理時間戳格式（可能是字符串或float）
                        if isinstance(planted_time, str):
                            planted_time = datetime.fromisoformat(planted_time).timestamp()
                        if isinstance(matured_time, str):
                            matured_time = datetime.fromisoformat(matured_time).timestamp()

                        now = datetime.now().timestamp()
                        elapsed = now - planted_time
                        total = matured_time - planted_time
                        progress = min(100, (elapsed / total * 100)) if total > 0 else 0
                        remaining = max(0, matured_time - now)
                        hours = int(remaining // 3600)
                        mins = int((remaining % 3600) // 60)
                        time_left = f"{hours}h {mins}m"

                    progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
                    value = f"進度：{progress_bar} {progress:.0f}%\n時間：{time_left}"
                    embed.add_field(name=f"#{idx} {config['emoji']} {plant['seed_type']}", value=value, inline=True)

            # 顯示已成熟的植物
            if harvested:
                embed.add_field(name="✅ 已成熟的植物", value="━" * 25, inline=False)
                for idx, plant in enumerate(harvested, 1):
                    config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    embed.add_field(
                        name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                        value="準備收割！✂️",
                        inline=True
                    )

            # 創建作物操作視圖，包含選項
            from .crop_operations import CropOperationView
            view = CropOperationView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, seeds, plants, growing, harvested)

            embed.set_footer(text="💡 使用下方按鈕進行種植、施肥或收割操作")
            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def personal_items_callback_impl(self, interaction: discord.Interaction):
        """個人物品 - 顯示物品庫存"""
        try:
            await interaction.response.defer()

            inventory = await get_inventory(self.user_id)

            embed = discord.Embed(
                title="🎒 個人物品",
                description="你的物品庫存",
                color=discord.Color.blue()
            )

            # 顯示種子
            if inventory.get("種子"):
                seed_info = ""
                for seed_name, qty in inventory["種子"].items():
                    if qty > 0:
                        config = CANNABIS_SHOP["種子"][seed_name]
                        seed_info += f"{config['emoji']} {seed_name}: {qty} 粒\n"
                if seed_info:
                    embed.add_field(name="🌱 種子", value=seed_info.strip(), inline=True)

            # 顯示大麻
            if inventory.get("大麻"):
                cannabis_info = ""
                for seed_name, qty in inventory["大麻"].items():
                    if qty > 0:
                        price = CANNABIS_HARVEST_PRICES[seed_name]
                        cannabis_info += f"💰 {seed_name}: {qty} 個 ({price}/個)\n"
                if cannabis_info:
                    embed.add_field(name="📦 大麻", value=cannabis_info.strip(), inline=True)

            if not any(inventory.values()):
                embed.add_field(name="📦 庫存", value="目前沒有任何物品", inline=False)

            # 返回按鈕
            view = PersonalLockerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.plants, self.user_panel)
            embed.set_footer(text="點擊下方按鈕返回主選項")

            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def back_to_main_callback(self, interaction: discord.Interaction):
        """返回到主選項

        - 如果正在編輯的是論壇中的永久置物櫃訊息（DB 中的 locker_message_id），
          使用 `UserPanel.create_user_embed` 還原完整置物櫃（保留紙娃娃圖片）。
        - 否則顯示簡化的主選單（ephemeral / 非永久上下文）。
        """
        try:
            # 判斷此訊息是否為該使用者的永久置物櫃訊息
            is_permanent_locker_msg = False
            try:
                from db_adapter import get_user
                user_row = get_user(self.user_id)
                locker_msg_id = user_row.get('locker_message_id') if user_row else None
                if interaction.message and locker_msg_id and interaction.message.id == locker_msg_id:
                    is_permanent_locker_msg = True
            except Exception:
                is_permanent_locker_msg = False

            if is_permanent_locker_msg:
                # 還原完整置物櫃 embed（確保保留紙娃娃/合併後物品欄）
                user_panel_cog = self.bot.get_cog('UserPanel')
                if user_panel_cog:
                    user_data = user_panel_cog.get_user_data(self.user_id)
                    user_obj = self.bot.get_user(self.user_id) or await self.bot.fetch_user(self.user_id)
                    embed = await user_panel_cog.create_user_embed(user_data, user_obj)

                    from uicommands.views import LockerPanelView
                    view = LockerPanelView(user_panel_cog, self.user_id, interaction.channel)

                    try:
                        await interaction.message.edit(embed=embed, view=view)
                    except discord.NotFound:
                        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    # fallback：當找不到 UserPanel cog 時仍回覆簡化版（但不覆蓋永久訊息）
                    await interaction.followup.send("❌ 系統暫時無法還原置物櫃內容，請稍後再試。", ephemeral=True)

            else:
                # 非永久訊息 -> 顯示簡化主選單（ephemeral）
                embed = discord.Embed(
                    title="📦 個人置物櫃",
                    description="使用下方按鈕管理你的作物種植、施肥和收割操作。",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="🌱 作物管理",
                    value="• 作物種植：開始種植新的作物\n• 收割：收割成熟的作物\n• 個人物品：查看你的物品庫存",
                    inline=False
                )
                embed.set_footer(text="💡 這個視圖是永久的，按鈕不會過期")

                view = PersonalLockerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.plants, self.user_panel)
                try:
                    # 優先更新原始互動回覆（若為 ephemeral 會編輯成功）
                    await interaction.response.edit_message(embed=embed, view=view)
                except Exception:
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)
            except:
                pass


class WeeklySummaryCannabisPanelView(discord.ui.View):
    """周統計面板的大麻系統快速訪問"""

    def __init__(self, bot, user_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id

    @discord.ui.button(label="收割成熟", style=discord.ButtonStyle.success, emoji="✂️", custom_id="weekly_harvest")
    async def harvest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """收割成熟植物"""
        try:
            await interaction.response.defer(ephemeral=True)

            plants = await get_user_plants(self.user_id)
            harvestable = [p for p in plants if p["status"] == "harvested"]

            if not harvestable:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return

            # 顯示可收割的植物
            embed = discord.Embed(
                title="🔪 選擇要收割的植物",
                color=discord.Color.gold()
            )

            for idx, plant in enumerate(harvestable[:5], 1):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                yield_amount = plant.get("harvested_amount", 0)
                embed.add_field(
                    name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                    value=f"產量：{yield_amount}",
                    inline=False
                )

            from .selection_views import SelectPlantForHarvestView
            view = SelectPlantForHarvestView(self.bot, self.user_id, harvestable)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    @discord.ui.button(label="查看狀態", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="weekly_view_plants")
    async def view_plants_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查看植物狀態"""
        try:
            await interaction.response.defer(ephemeral=True)

            plants = await get_user_plants(self.user_id)

            if not plants:
                await interaction.followup.send("❌ 你還沒有種植任何植物！", ephemeral=True)
                return

            embed = discord.Embed(
                title="🌱 我的植物狀態",
                color=discord.Color.green()
            )

            for idx, plant in enumerate(plants, 1):
                seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]

                # 計算進度
                if plant["status"] == "harvested":
                    progress_text = "✅ 已成熟 100%"
                else:
                    planted_time = plant["planted_at"] if isinstance(plant["planted_at"], float) else plant["planted_at"]
                    matured_time = plant["matured_at"] if isinstance(plant["matured_at"], float) else plant["matured_at"]

                    if isinstance(planted_time, str):
                        planted_time = datetime.fromisoformat(planted_time).timestamp()
                    if isinstance(matured_time, str):
                        matured_time = datetime.fromisoformat(matured_time).timestamp()

                    now = datetime.now().timestamp()
                    elapsed = now - planted_time
                    total = matured_time - planted_time
                    progress = min(100, (elapsed / total * 100)) if total > 0 else 0

                    filled = int(progress / 5)
                    empty = 20 - filled
                    progress_text = f"{'█' * filled}{'░' * empty} {progress:.0f}%"

                    remaining = max(0, matured_time - now)
                    if remaining > 0:
                        hours = int(remaining // 3600)
                        mins = int((remaining % 3600) // 60)
                        status_info = f"剩餘 {hours}h {mins}m"
                    else:
                        status_info = "✅ 已成熟"

                    progress_text += f"\n{status_info}"

                value = (
                    f"🌾 種類：{plant['seed_type']}\n"
                    f"📊 進度：{progress_text}"
                )
                embed.add_field(name=f"#{idx} {seed_config['emoji']}", value=value, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)