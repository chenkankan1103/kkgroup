import discord
from discord.ui import Button
import traceback
from datetime import datetime

from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from shop_commands.merchant.cannabis_farming import get_inventory, get_user_plants, add_inventory, remove_inventory, plant_cannabis, harvest_plant
from shop_commands.merchant.database import update_user_kkcoin
from status_dashboard import add_log


class CropOperationView(discord.ui.View):
    """作物操作視圖 - 提供種植、施肥、收割選項"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds, plants, growing, harvested):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.seeds = seeds
        self.plants = plants
        self.growing = growing
        self.harvested = harvested

        # 添加種植按鈕（如果有種子且有空位）
        if seeds and len(plants) < 3:
            plant_button = discord.ui.Button(
                label="🌱 種植",
                style=discord.ButtonStyle.success,
                custom_id="crop_planting"
            )
            plant_button.callback = self.crop_planting_callback
            self.add_item(plant_button)

        # 添加收割按鈕（如果有成熟的植物）
        if harvested:
            harvest_button = discord.ui.Button(
                label="✂️ 收割",
                style=discord.ButtonStyle.danger,
                custom_id="crop_harvest"
            )
            harvest_button.callback = self.crop_harvest_callback
            self.add_item(harvest_button)
            
            # 添加一鍵收割按鈕（如果有多個成熟植物）
            if len(harvested) > 1:
                harvest_all_button = discord.ui.Button(
                    label="一鍵收割",
                    style=discord.ButtonStyle.danger,
                    emoji="⚡",
                    custom_id="crop_harvest_all"
                )
                harvest_all_button.callback = self.crop_harvest_all_callback
                self.add_item(harvest_all_button)

        # 添加返回按鈕
        back_button = discord.ui.Button(
            label="返回",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            custom_id="crop_back"
        )
        back_button.callback = self.back_to_locker_callback
        self.add_item(back_button)

    async def crop_planting_callback(self, interaction: discord.Interaction):
        """種植作物"""
        try:
            await interaction.response.defer()

            # 創建種子選擇下拉選單
            options = []
            for seed_name, qty in self.seeds.items():
                if qty > 0:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    options.append(discord.SelectOption(
                        label=f"{config['emoji']} {seed_name}",
                        description=f"數量: {qty} | 時間: {config['growth_time']//3600}小時",
                        value=seed_name
                    ))

            if not options:
                await interaction.followup.send("❌ 你沒有任何種子！", ephemeral=True)
                return

            view = CropPlantingView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, options, self.seeds, self)
            embed = discord.Embed(
                title="🌱 選擇要種植的種子",
                description="從下方選單選擇一種子進行種植",
                color=discord.Color.green()
            )

            # 編輯原始回應而不是創建新的
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def crop_harvest_callback(self, interaction: discord.Interaction):
        """收割作物"""
        try:
            await interaction.response.defer()

            # 創建植物選擇下拉選單
            options = []
            for plant in self.harvested:
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                options.append(discord.SelectOption(
                    label=f"{config['emoji']} {plant['seed_type']}",
                    description="已成熟，準備收割",
                    value=str(plant['id'])
                ))

            if not options:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return

            from .selection_views import SelectPlantForHarvestView
            view = SelectPlantForHarvestView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.harvested, self)
            embed = discord.Embed(
                title="✂️ 選擇要收割的植物",
                description="選擇一棵成熟的植物進行收割",
                color=discord.Color.orange()
            )

            # 編輯原始回應而不是創建新的
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def crop_harvest_all_callback(self, interaction: discord.Interaction):
        """一鍵收割所有成熟植物"""
        try:
            await interaction.response.defer(ephemeral=True)

            if not self.harvested:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return

            total_earnings = 0
            harvest_results = []
            
            # 依次收割所有成熟的植物
            for plant in self.harvested:
                try:
                    result = await harvest_plant(self.user_id, plant["id"])
                    
                    if result.get("success"):
                        plant_name = plant["seed_type"]
                        yield_amount = result.get("yield_amount", 0)
                        earnings = result.get("sell_price", 0)
                        
                        harvest_results.append({
                            "plant": plant_name,
                            "yield": yield_amount,
                            "price": earnings
                        })
                        total_earnings += earnings
                        
                        # 記錄事件
                        if self.cog:
                            user = await self.bot.fetch_user(self.user_id)
                            await self.cog.record_event(
                                'harvest',
                                user,
                                f"收割{plant_name}獲得{yield_amount}個，可售{earnings} KK幣"
                            )
                except Exception as harvest_error:
                    print(f"⚠️ 收割單株植物失敗：{harvest_error}")
                    harvest_results.append({
                        "plant": plant.get("seed_type", "未知"),
                        "error": str(harvest_error)
                    })
            
            # 創建結果embed
            embed = discord.Embed(
                title="⚡ 一鍵收割完成",
                description=f"共收割 {len(harvest_results)} 棵植物",
                color=discord.Color.gold()
            )
            
            for result in harvest_results:
                if "error" in result:
                    embed.add_field(
                        name=f"❌ {result['plant']}",
                        value=f"失敗：{result['error']}",
                        inline=True
                    )
                else:
                    embed.add_field(
                        name=f"✅ {result['plant']}",
                        value=f"產出 {result['yield']} 個，獲得 {result['price']} KK幣",
                        inline=True
                    )
            
            if total_earnings > 0:
                embed.add_field(
                    name="💰 總收入",
                    value=f"{total_earnings} KK幣",
                    inline=False
                )
            
            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=None)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 一鍵收割時發生錯誤：{str(e)[:100]}", ephemeral=True)

    async def back_to_locker_callback(self, interaction: discord.Interaction):
        """返回到個人儲物櫃"""
        try:
            await interaction.response.defer()

            # 重新獲取用戶數據
            plants = await get_user_plants(self.user_id)
            inventory = await get_inventory(self.user_id)

            # 創建PersonalLockerView
            from .personal_locker import PersonalLockerView
            view = PersonalLockerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, plants, None)

            embed = discord.Embed(
                title="🔒 個人儲物櫃",
                description="管理您的作物和物品",
                color=discord.Color.blue()
            )

            # 顯示作物資訊
            if plants:
                growing = [p for p in plants if p["status"] != "harvested"]
                harvested = [p for p in plants if p["status"] == "harvested"]

                embed.add_field(
                    name="🌾 作物狀態",
                    value=f"成長中: {len(growing)} | 已成熟: {len(harvested)} | 總計: {len(plants)}/3",
                    inline=False
                )

            # 顯示庫存
            seeds = inventory.get("種子", {})
            fertilizers = inventory.get("肥料", {})

            if seeds:
                seed_info = ", ".join([f"{k}: {v}" for k, v in seeds.items() if v > 0])
                embed.add_field(name="🌱 種子", value=seed_info[:1000], inline=False)

            if fertilizers:
                fert_info = ", ".join([f"{k}: {v}" for k, v in fertilizers.items() if v > 0])
                embed.add_field(name="💧 肥料", value=fert_info[:1000], inline=False)

            embed.set_footer(text="💡 使用下方按鈕管理您的作物")

            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)

    @classmethod
    async def create_crop_info_embed_and_view(cls, bot, cog, user_id, guild_id, channel_id):
        """創建作物資訊embed和view（CropOperationView 類方法）"""
        # 重新獲取作物數據
        seeds = await get_inventory(user_id)
        seeds = seeds.get("種子", {}) if seeds else {}
        
        plants = await get_user_plants(user_id)
        growing = [p for p in plants if p.get("status") == "growing"]
        harvested = [p for p in plants if p.get("status") == "harvested"]
        
        # 創建作物資訊embed
        embed = discord.Embed(
            title="🌱 作物管理",
            description="管理你的農場作物",
            color=discord.Color.green()
        )
        
        # 顯示種子庫存
        if seeds:
            seed_list = []
            for seed_name, qty in seeds.items():
                if qty > 0:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    seed_list.append(f"{config['emoji']} {seed_name}: {qty}")
            if seed_list:
                embed.add_field(name="🌱 種子庫存", value="\n".join(seed_list), inline=False)
        
        # 顯示成長中的植物
        if growing:
            embed.add_field(name="🌿 成長中的植物", value="━" * 25, inline=False)
            for idx, plant in enumerate(growing, 1):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
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
        
        # 創建CropOperationView
        view = cls(bot, cog, user_id, guild_id, channel_id, seeds, plants, growing, harvested)
        
        embed.set_footer(text="💡 使用下方按鈕進行種植、施肥或收割操作")
        
        return embed, view


class CropPlantingView(discord.ui.View):
    """種植作物選擇視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, options, seeds_dict=None, crop_operation_view=None):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.seeds_dict = seeds_dict or {}  # 保留完整種子字典用於一鍵種植
        self.crop_operation_view = crop_operation_view

        # 添加種子選擇下拉選單
        if options:
            select = discord.ui.Select(
                placeholder="選擇要種植的種子...",
                options=options[:25],  # Discord限制最多25個選項
                custom_id="seed_select"
            )
            select.callback = self.seed_select_callback
            self.add_item(select)

        # 添加一鍵種植按鈕
        mass_button = discord.ui.Button(
            label="一鍵種植",
            style=discord.ButtonStyle.success,
            emoji="🌾",
            custom_id="plant_all_seeds"
        )
        mass_button.callback = self.plant_all_callback
        self.add_item(mass_button)

    async def seed_select_callback(self, interaction: discord.Interaction):
        """處理種子選擇 - 顯示確認視圖，不自動種植"""
        try:
            await interaction.response.defer(ephemeral=True)

            selected_seed = interaction.data["values"][0]
            config = CANNABIS_SHOP["種子"][selected_seed]
            inventory = await get_inventory(self.user_id)
            seed_qty = inventory.get("種子", {}).get(selected_seed, 0)

            # 創建確認視圖
            view = discord.ui.View(timeout=60)
            
            # 種植該種子按鈕
            plant_single_btn = discord.ui.Button(
                label=f"種植 {selected_seed}",
                style=discord.ButtonStyle.success,
                emoji=config["emoji"]
            )
            
            async def plant_single_callback(btn_interaction: discord.Interaction):
                """種植單株選中的種子"""
                try:
                    await btn_interaction.response.defer(ephemeral=True)
                    
                    has_seed = await remove_inventory(self.user_id, "種子", selected_seed, 1)
                    if not has_seed:
                        await btn_interaction.followup.send("❌ 種子不足！", ephemeral=True)
                        return
                    
                    result = await plant_cannabis(self.user_id, self.guild_id, self.channel_id, selected_seed)
                    
                    if result and not result.get("success") == False:
                        embed = discord.Embed(
                            title="🌱 種植成功",
                            description=f"已種植 {selected_seed}",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="成長時間", value=f"{config['growth_time']//3600} 小時", inline=False)
                        embed.add_field(name="最大產量", value=f"{config['max_yield']} 個", inline=False)
                        
                        if self.cog:
                            await self.cog.record_event(
                                'plant',
                                btn_interaction.user,
                                f"種植{selected_seed}"
                            )
                        
                        await btn_interaction.edit_original_response(embed=embed, view=None)
                    else:
                        await add_inventory(self.user_id, "種子", selected_seed, 1)
                        reason = result.get("reason", "未知原因") if result else "未知原因"
                        await btn_interaction.followup.send(f"❌ 種植失敗：{reason}", ephemeral=True)
                
                except Exception as e:
                    traceback.print_exc()
                    if 'selected_seed' in locals():
                        try:
                            await add_inventory(self.user_id, "種子", selected_seed, 1)
                        except:
                            pass
                    await btn_interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
            
            plant_single_btn.callback = plant_single_callback
            view.add_item(plant_single_btn)
            
            # 一鍵種植按鈕
            plant_all_btn = discord.ui.Button(
                label="一鍵種植所有",
                style=discord.ButtonStyle.secondary,
                emoji="🌾"
            )
            
            async def plant_all_from_select_callback(btn_interaction: discord.Interaction):
                """從選擇視圖呼叫一鍵種植"""
                # 複用一鍵種植邏輯
                await self.plant_all_callback(btn_interaction)
            
            plant_all_btn.callback = plant_all_from_select_callback
            view.add_item(plant_all_btn)
            
            # 取消按鈕
            cancel_btn = discord.ui.Button(
                label="返回",
                style=discord.ButtonStyle.secondary,
                emoji="⬅️"
            )
            
            async def cancel_callback(btn_interaction: discord.Interaction):
                await btn_interaction.response.defer(ephemeral=True)
                await btn_interaction.delete_original_response()
            
            cancel_btn.callback = cancel_callback
            view.add_item(cancel_btn)
            
            embed = discord.Embed(
                title=f"🌱 {selected_seed}",
                description=f"數量：{seed_qty} | 成長時間：{config['growth_time']//3600}小時",
                color=discord.Color.green()
            )
            embed.add_field(name="選項", value="選擇下方按鈕", inline=False)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def plant_all_callback(self, interaction: discord.Interaction):
        """一鍵種植：嘗試種植所有持有的種子（限制3個植物）"""
        try:
            await interaction.response.defer(ephemeral=True)

            if not self.seeds_dict:
                await interaction.followup.send("❌ 沒有可用的種子信息！", ephemeral=True)
                return

            # ⭐ 檢查當前植物數量，確保不超過3個
            current_plants = await get_user_plants(self.user_id)
            remaining_slots = 3 - len(current_plants)
            
            if remaining_slots <= 0:
                await interaction.followup.send("❌ 植物格位已滿（3/3），無法再種植！請先收割成熟的植物。", ephemeral=True)
                return

            results = []  # 儲存種植結果
            plants_count = 0
            
            # 遍歷所有種子
            for seed_name, qty in list(self.seeds_dict.items()):
                for _ in range(qty):
                    # ⭐ 檢查是否還有空位
                    if plants_count >= remaining_slots:
                        results.append((seed_name, False, "格位已滿"))
                        break
                    
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
                        plants_count += 1  # ⭐ 計數成功的植物
                    else:
                        # 失敗，退還種子
                        await add_inventory(self.user_id, "種子", seed_name, 1)
                        reason = result.get("reason", "未知原因") if result else "未知原因"
                        results.append((seed_name, False, reason))
                        continue

            # 建立結果 embed
            embed = discord.Embed(title="🌱 一鍵種植結果", color=discord.Color.green())
            embed.add_field(name="📊 種植進度", value=f"{plants_count}/{remaining_slots} 個植物已種植", inline=False)
            
            for seed_name, success, reason in results:
                emoji = ""
                try:
                    emoji = CANNABIS_SHOP["種子"][seed_name]["emoji"]
                except Exception:
                    pass
                if success:
                    embed.add_field(name=f"{emoji} {seed_name}", value="✅ 種植成功", inline=True)
                else:
                    embed.add_field(name=f"{emoji} {seed_name}", value=f"❌ {reason}", inline=True)

            # 顯示結果，並附帶返回按鈕
            from .selection_views import PlantResultView
            result_view = PlantResultView(self.user_id, self.crop_operation_view if self.crop_operation_view else self)
            await interaction.followup.send(embed=embed, view=result_view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 一鍵種植時發生錯誤：{str(e)[:100]}", ephemeral=True)


class SelectSeedView(discord.ui.View):
    """選擇要種植的種子"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds, crop_operation_view=None):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.crop_operation_view = crop_operation_view
        # 保留種子快照以便一鍵種植使用
        self.seeds = dict(seeds)

        for idx, (seed_name, qty) in enumerate(seeds.items(), 1):
            if qty > 0:
                config = CANNABIS_SHOP["種子"][seed_name]
                button = Button(
                    label=f"種植 {seed_name}",
                    style=discord.ButtonStyle.success,
                    emoji=config["emoji"],
                    custom_id=f"plant_seed_{seed_name.replace(' ', '_')}"
                )
                button.callback = self.make_plant_callback(seed_name)
                self.add_item(button)

        # 添加一鍵種植按鈕
        mass_button = discord.ui.Button(
            label="一鍵種植",
            style=discord.ButtonStyle.success,
            emoji="🌾",
            custom_id="plant_all_seeds"
        )
        mass_button.callback = self.plant_all_callback
        self.add_item(mass_button)

    def make_plant_callback(self, seed_name):
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
                        continue

            # 建立結果 embed
            embed = discord.Embed(title="🌱 一鍵種植結果", color=discord.Color.green())
            for seed_name, success, reason in results:
                emoji = ""
                try:
                    emoji = CANNABIS_SHOP["種子"][seed_name]["emoji"]
                except Exception:
                    pass
                if success:
                    embed.add_field(name=f"{emoji} {seed_name}", value="種植成功", inline=True)
                else:
                    embed.add_field(name=f"{emoji} {seed_name}", value=f"失敗：{reason}", inline=True)

            # 顯示結果，並附帶返回按鈕
            from .selection_views import PlantResultView
            result_view = PlantResultView(self.user_id, self.crop_operation_view)
            await interaction.followup.send(embed=embed, view=result_view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 一鍵種植時發生錯誤：{str(e)[:100]}", ephemeral=True)

    async def back_to_locker_callback(self, interaction: discord.Interaction):
        """返回到個人置物櫃主選項"""
        try:
            await interaction.response.defer()

            # 創建PersonalLockerView
            from .personal_locker import PersonalLockerView
            plants = await get_user_plants(self.user_id)
            view = PersonalLockerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, plants, user_panel=None)

            embed = discord.Embed(
                title="📦 個人置物櫃",
                description="使用下方按鈕管理你的作物種植、施肥和收割操作。",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="🌱 作物管理",
                value="• 作物資訊：查看作物狀態和操作選項\n• 個人物品：查看你的物品庫存",
                inline=False
            )

            embed.set_footer(text="💡 這個視圖是永久的，按鈕不會過期")

            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)

        return callback

    