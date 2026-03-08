import discord
from discord.ui import Button
import traceback
from datetime import datetime

from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from shop_commands.merchant.cannabis_farming import get_inventory, get_user_plants, add_inventory, remove_inventory, plant_cannabis, harvest_plant
from shop_commands.merchant.database import update_user_kkcoin
from status_dashboard import add_log


class SelectFertilizerView(discord.ui.View):
    """選擇肥料視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, plant, fertilizers, crop_operation_view=None):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.plant = plant
        self.crop_operation_view = crop_operation_view

        for fert_name, quantity in fertilizers.items():
            if quantity > 0:  # 只為有數量的肥料創建按鈕
                config = CANNABIS_SHOP["肥料"][fert_name]
                button = Button(
                    label=f"用 {fert_name} ({quantity}個)",
                    style=discord.ButtonStyle.primary,
                    emoji=config["emoji"],
                    custom_id=f"apply_fert_{fert_name.replace(' ', '_')}"
                )
                button.callback = self.make_apply_callback(fert_name)
                self.add_item(button)

        # 添加返回按鈕
        back_button = discord.ui.Button(
            label="返回",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            custom_id="back_to_plant_select"
        )
        back_button.callback = self.back_to_plant_selection_callback
        self.add_item(back_button)

    async def make_apply_callback(self, fert_name):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer()

                # 施肥
                result = await apply_fertilizer(self.user_id, self.plant["id"], fert_name)

                if result:
                    # 移除肥料
                    await remove_inventory(self.user_id, "肥料", fert_name, 1)

                    config = CANNABIS_SHOP["肥料"][fert_name]
                    embed = discord.Embed(
                        title="✅ 施肥成功",
                        description=f"已使用 {fert_name} 施肥 {self.plant['seed_type']}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="加速", value=f"{config['growth_boost']*100:.0f}%", inline=False)

                    # 記錄事件（暫時移除以避免超時）
                    # user = await self.bot.fetch_user(self.user_id)
                    # await self.cog.record_event(
                    #     'fertilize',
                    #     user,
                    #     f"為{self.plant['seed_type']}施肥"
                    # )

                    # 編輯原始回應顯示結果
                    await interaction.edit_original_response(embed=embed, view=None)
                else:
                    await interaction.followup.send("❌ 施肥失敗", ephemeral=True)

            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

        return callback

    async def back_to_plant_selection_callback(self, interaction: discord.Interaction):
        """返回到植物選擇視圖"""
        try:
            await interaction.response.defer()

            # 重新獲取成長中的植物
            plants_data = await get_user_plants(self.user_id)
            growing = [p for p in plants_data if p.get("status") == "growing"]

            # 創建SelectPlantForFertilizerView
            view = SelectPlantForFertilizerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, growing, self.crop_operation_view)
            embed = discord.Embed(
                title="💧 選擇要施肥的植物",
                description="選擇一棵植物進行施肥",
                color=discord.Color.blue()
            )

            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)


class SelectPlantForFertilizerView(discord.ui.View):
    """選擇植物進行施肥的視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, plants, crop_operation_view=None):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.plants = plants
        self.crop_operation_view = crop_operation_view

        # 創建選擇選項
        options = []
        for plant in plants:
            config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            options.append(discord.SelectOption(
                label=f"{config['emoji']} {plant['seed_type']}",
                description=f"施肥次數: {plant['fertilizer_applied']}",
                value=str(plant['id'])
            ))

        if options:
            select = discord.ui.Select(
                placeholder="選擇要施肥的植物...",
                options=options[:25],  # Discord限制最多25個選項
                custom_id="select_plant_fertilize"
            )
            select.callback = self.select_callback
            self.add_item(select)

        # 添加返回按鈕
        back_button = discord.ui.Button(
            label="返回",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            custom_id="back_to_crop_ops"
        )
        back_button.callback = self.back_to_crop_operations_callback
        self.add_item(back_button)

    async def select_callback(self, interaction: discord.Interaction):
        """處理植物選擇"""
        try:
            await interaction.response.defer()

            plant_id = int(interaction.data['values'][0])
            plant = next((p for p in self.plants if p['id'] == plant_id), None)

            if not plant:
                await interaction.followup.send("❌ 找不到選擇的植物！", ephemeral=True)
                return

            # 檢查肥料
            inventory = await get_inventory(self.user_id)
            fertilizers = inventory.get("肥料", {})

            if not fertilizers:
                await interaction.followup.send("❌ 你沒有任何肥料！", ephemeral=True)
                return

            # 顯示肥料選擇界面
            from .selection_views import SelectFertilizerView
            view = SelectFertilizerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, plant, fertilizers, self.crop_operation_view)
            embed = discord.Embed(
                title="💧 選擇肥料",
                description=f"為 {CANNABIS_SHOP['種子'][plant['seed_type']]['emoji']} {plant['seed_type']} 選擇肥料",
                color=discord.Color.blue()
            )

            # 編輯原始回應而不是創建新的
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def back_to_crop_operations_callback(self, interaction: discord.Interaction):
        """返回到作物操作視圖"""
        try:
            await interaction.response.defer()

            # 使用CropOperationView的類方法創建embed和view
            from uicommands.views.crop_operations import CropOperationView
            embed, view = await CropOperationView.create_crop_info_embed_and_view(
                self.bot, self.cog, self.user_id, self.guild_id, self.channel_id
            )
            
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)


class SelectPlantForHarvestView(discord.ui.View):
    """選擇植物進行收割的視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, plants, crop_operation_view=None):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.plants = plants
        self.crop_operation_view = crop_operation_view

        # 創建選擇選項
        options = []
        for plant in plants:
            config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            # Prefer yield_amount, then harvested_amount, then yield to support multiple naming variants
            yield_display = plant.get("yield_amount", plant.get("harvested_amount", plant.get("yield", config["max_yield"])))
            options.append(discord.SelectOption(
                label=f"{config['emoji']} {plant['seed_type']}",
                description=f"產量: {yield_display} 個",
                value=str(plant['id'])
            ))

        if options:
            select = discord.ui.Select(
                placeholder="選擇要收割的植物...",
                options=options[:25],  # Discord限制最多25個選項
                custom_id="select_plant_harvest"
            )
            select.callback = self.select_callback
            self.add_item(select)

        # 添加返回按鈕
        back_button = discord.ui.Button(
            label="返回",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            custom_id="back_to_crop_ops"
        )
        back_button.callback = self.back_to_crop_operations_callback
        self.add_item(back_button)

    async def select_callback(self, interaction: discord.Interaction):
        """處理植物選擇"""
        try:
            await interaction.response.defer()

            plant_id = int(interaction.data['values'][0])
            plant = next((p for p in self.plants if p['id'] == plant_id), None)

            if not plant:
                await interaction.followup.send("❌ 找不到選擇的植物！", ephemeral=True)
                return

            # 收割植物
            result = await harvest_plant(self.user_id, plant_id)

            if result and result.get("success"):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                # Prefer yield_amount, then harvested_amount, then yield to support multiple naming variants
                yield_amount = result.get("yield_amount", result.get("harvested_amount", result.get("yield", 0)))
                price = CANNABIS_HARVEST_PRICES[plant["seed_type"]]
                total_value = yield_amount * price

                embed = discord.Embed(
                    title="✂️ 收割成功",
                    description=f"已收割 {config['emoji']} {plant['seed_type']}",
                    color=discord.Color.gold()
                )
                embed.add_field(name="收割數量", value=f"{yield_amount} 個", inline=True)
                embed.add_field(name="單價", value=f"{price} KK幣", inline=True)
                embed.add_field(name="總價值", value=f"{total_value} KK幣", inline=True)

                # 更新用戶KK幣
                await update_user_kkcoin(self.user_id, total_value)

                # 創建包含返回按鈕的view
                result_view = HarvestResultView(self.user_id, plant_id, self.crop_operation_view)

                # 編輯原始回應顯示結果
                await interaction.edit_original_response(embed=embed, view=result_view)
            else:
                reason = result.get("reason", "未知原因") if result else "未知原因"
                await interaction.followup.send(f"❌ 收割失敗：{reason}", ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def back_to_crop_operations_callback(self, interaction: discord.Interaction):
        """返回到作物操作視圖"""
        try:
            await interaction.response.defer()

            # 重新獲取用戶數據
            plants = await get_user_plants(self.user_id)
            inventory = await get_inventory(self.user_id)
            seeds = inventory.get("種子", {})
            growing = [p for p in plants if p["status"] != "harvested"]
            harvested = [p for p in plants if p["status"] == "harvested"]

            # 創建CropOperationView
            from uicommands.views.crop_operations import CropOperationView
            view = CropOperationView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, seeds, plants, growing, harvested)

            embed = discord.Embed(
                title="🌾 作物資訊",
                description=f"已使用 {len(plants)}/5 個位置",
                color=discord.Color.green()
            )

            # 顯示成長中的植物
            if growing:
                embed.add_field(name="🌱 成長中的植物", value="━" * 25, inline=False)
                for idx, plant in enumerate(growing, 1):
                    from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
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
                    from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
                    config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    embed.add_field(
                        name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                        value="準備收割！✂️",
                        inline=True
                    )

            embed.set_footer(text="💡 使用下方按鈕進行種植、施肥或收割操作")

            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)


class SelectSeedView(discord.ui.View):
    """選擇種子視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        # 保留種子快照以便一鍵種植使用
        self.seeds = dict(seeds)

        # 為每個種子添加按鈕
        for seed_name, qty in seeds.items():
            if qty > 0:
                from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
                config = CANNABIS_SHOP["種子"][seed_name]
                button = discord.ui.Button(
                    label=f"{config['emoji']} {seed_name}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"plant_seed_{seed_name.replace(' ', '_')}"
                )
                button.callback = self.make_plant_callback(seed_name)
                self.add_item(button)

        # 添加一鍵種植按鈕（種植所有類型的所有種子）
        mass_button = discord.ui.Button(
            label="一鍵種植",
            style=discord.ButtonStyle.success,
            emoji="🌾",
            custom_id="plant_all_seeds"
        )
        mass_button.callback = self.plant_all_callback
        self.add_item(mass_button)

        # 添加返回按鈕
        back_button = discord.ui.Button(
            label="返回",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            custom_id="seed_select_back"
        )
        back_button.callback = self.back_to_crop_operations_callback
        self.add_item(back_button)

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
                    from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
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
                    result_view = PlantResultView(self.user_id, self.crop_operation_view)

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

    async def plant_all_callback(self, interaction: discord.Interaction):
        """一鍵種植：嘗試種植所有持有的種子"""
        try:
            await interaction.response.defer(ephemeral=True)

            # 檢查使用者是否為該視圖的擁有者
            if interaction.user.id != self.user_id:
                await interaction.followup.send("❌ 這不是你的置物櫃！", ephemeral=True)
                return

            results = []  # 儲存種植結果
            # 遍歷快照的種子數量
            for seed_name, qty in list(self.seeds.items()):
                for _ in range(qty):
                    has_seed = await remove_inventory(self.user_id, "種子", seed_name, 1)
                    if not has_seed:
                        results.append((seed_name, False, "庫存不足"))
                        break
                    result = await plant_cannabis(self.user_id, self.guild_id, self.channel_id, seed_name)
                    if result and not result.get("success") == False:
                        # 成功
                        if self.cog:
                            user = await self.bot.fetch_user(self.user_id)
                            await self.cog.record_event('plant', user, f"種植{seed_name}")
                        results.append((seed_name, True, ""))
                    else:
                        # 失敗，退還種子
                        await add_inventory(self.user_id, "種子", seed_name, 1)
                        reason = result.get("reason", "未知原因") if result else "未知原因"
                        results.append((seed_name, False, reason))
                        # 如果種植失敗可以繼續下一種
                        continue

            # 建立結果 embed
            embed = discord.Embed(title="🌱 一鍵種植結果", color=discord.Color.green())
            for seed_name, success, reason in results:
                emoji = ""
                try:
                    from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
                    emoji = CANNABIS_SHOP["種子"][seed_name]["emoji"]
                except Exception:
                    pass
                if success:
                    embed.add_field(name=f"{emoji} {seed_name}", value="種植成功", inline=True)
                else:
                    embed.add_field(name=f"{emoji} {seed_name}", value=f"失敗：{reason}", inline=True)

            # 顯示結果，並附帶返回按鈕
            result_view = PlantResultView(self.user_id, self.crop_operation_view)
            await interaction.followup.send(embed=embed, view=result_view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 一鍵種植時發生錯誤：{str(e)[:100]}", ephemeral=True)

    async def back_to_crop_operations_callback(self, interaction: discord.Interaction):
        """返回到作物操作視圖"""
        try:
            await interaction.response.defer()

            # 重新獲取用戶數據
            plants = await get_user_plants(self.user_id)
            inventory = await get_inventory(self.user_id)
            seeds = inventory.get("種子", {})
            growing = [p for p in plants if p["status"] != "harvested"]
            harvested = [p for p in plants if p["status"] == "harvested"]

            # 創建CropOperationView
            from uicommands.views.crop_operations import CropOperationView
            view = CropOperationView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, seeds, plants, growing, harvested)

            embed = discord.Embed(
                title="🌾 作物資訊",
                description=f"已使用 {len(plants)}/5 個位置",
                color=discord.Color.green()
            )

            # 顯示成長中的植物
            if growing:
                embed.add_field(name="🌱 成長中的植物", value="━" * 25, inline=False)
                for idx, plant in enumerate(growing, 1):
                    from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
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
                    from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
                    config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    embed.add_field(
                        name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                        value="準備收割！✂️",
                        inline=True
                    )

            embed.set_footer(text="💡 使用下方按鈕進行種植、施肥或收割操作")

            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)

class HarvestResultView(discord.ui.View):
    def __init__(self, user_id, plant_id, crop_operation_view):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.plant_id = plant_id
        self.crop_operation_view = crop_operation_view

    @discord.ui.button(label='返回作物資訊', style=discord.ButtonStyle.secondary, emoji='🔙')
    async def back_to_crop_info_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('這不是你的操作！', ephemeral=True)
            return

        # 立即響應以避免超時
        await interaction.response.defer()

        try:
            # 使用CropOperationView的類方法創建embed和view
            from uicommands.views.crop_operations import CropOperationView
            embed, view = await CropOperationView.create_crop_info_embed_and_view(
                self.crop_operation_view.bot,
                self.crop_operation_view.cog,
                self.user_id,
                self.crop_operation_view.guild_id,
                self.crop_operation_view.channel_id
            )

            # 先嘗試編輯原始回應，若失敗則退回到 followup.send（例如原始回應不可編輯時）
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except Exception:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:200]}", ephemeral=True)


class PlantResultView(discord.ui.View):
    """種植成功後的返回按鈕視圖"""
    def __init__(self, user_id, crop_operation_view):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.crop_operation_view = crop_operation_view

    @discord.ui.button(label='返回作物資訊', style=discord.ButtonStyle.secondary, emoji='🔙')
    async def back_to_crop_info_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('這不是你的操作！', ephemeral=True)
            return

        # 立即響應以避免超時
        await interaction.response.defer()

        try:
            # 使用CropOperationView的類方法創建embed和view
            from uicommands.views.crop_operations import CropOperationView
            embed, view = await CropOperationView.create_crop_info_embed_and_view(
                self.crop_operation_view.bot,
                self.crop_operation_view.cog,
                self.user_id,
                self.crop_operation_view.guild_id,
                self.crop_operation_view.channel_id
            )

            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except Exception:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:200]}", ephemeral=True)
