import discord
from discord.ui import Button
import traceback
from datetime import datetime

from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from shop_commands.merchant.cannabis_farming import get_inventory, get_user_plants, add_inventory, remove_inventory, plant_cannabis, apply_fertilizer, harvest_plant
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
        if seeds and len(plants) < 5:
            plant_button = discord.ui.Button(
                label="🌱 種植",
                style=discord.ButtonStyle.success,
                custom_id="crop_planting"
            )
            plant_button.callback = self.crop_planting_callback
            self.add_item(plant_button)

        # 添加施肥按鈕（如果有成長中的植物且有肥料）
        if growing:
            fertilizer_button = discord.ui.Button(
                label="💧 施肥",
                style=discord.ButtonStyle.primary,
                custom_id="crop_fertilize"
            )
            fertilizer_button.callback = self.crop_fertilize_callback
            self.add_item(fertilizer_button)

        # 添加收割按鈕（如果有成熟的植物）
        if harvested:
            harvest_button = discord.ui.Button(
                label="✂️ 收割",
                style=discord.ButtonStyle.danger,
                custom_id="crop_harvest"
            )
            harvest_button.callback = self.crop_harvest_callback
            self.add_item(harvest_button)

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

            view = CropPlantingView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, options)
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

    async def crop_fertilize_callback(self, interaction: discord.Interaction):
        """施肥作物"""
        try:
            await interaction.response.defer()

            # 檢查是否有肥料
            inventory = await get_inventory(self.user_id)
            fertilizers = inventory.get("肥料", {})

            if not fertilizers:
                await interaction.followup.send("❌ 你沒有任何肥料！", ephemeral=True)
                return

            # 創建植物選擇下拉選單
            options = []
            for plant in self.growing:
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                options.append(discord.SelectOption(
                    label=f"{config['emoji']} {plant['seed_type']}",
                    description=f"施肥次數: {plant['fertilizer_applied']}",
                    value=str(plant['id'])
                ))

            if not options:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return

            from .selection_views import SelectPlantForFertilizerView
            view = SelectPlantForFertilizerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.growing)
            embed = discord.Embed(
                title="💧 選擇要施肥的植物",
                description="選擇一棵植物進行施肥",
                color=discord.Color.blue()
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
                    value=f"成長中: {len(growing)} | 已成熟: {len(harvested)} | 總計: {len(plants)}/5",
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


class CropPlantingView(discord.ui.View):
    """種植作物選擇視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, options):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id

        # 添加種子選擇下拉選單
        if options:
            select = discord.ui.Select(
                placeholder="選擇要種植的種子...",
                options=options[:25],  # Discord限制最多25個選項
                custom_id="seed_select"
            )
            select.callback = self.seed_select_callback
            self.add_item(select)

    async def seed_select_callback(self, interaction: discord.Interaction):
        """處理種子選擇"""
        try:
            await interaction.response.defer(ephemeral=True)

            selected_seed = interaction.data["values"][0]

            # 檢查是否有種子
            has_seed = await remove_inventory(self.user_id, "種子", selected_seed, 1)
            if not has_seed:
                await interaction.followup.send("❌ 你沒有這種種子！", ephemeral=True)
                return

            # 種植
            result = await plant_cannabis(self.user_id, self.guild_id, self.channel_id, selected_seed)

            if result and not result.get("success") == False:
                config = CANNABIS_SHOP["種子"][selected_seed]
                embed = discord.Embed(
                    title="🌱 種植成功",
                    description=f"已種植 {selected_seed}",
                    color=discord.Color.green()
                )
                embed.add_field(name="成長時間", value=f"{config['growth_time']//3600} 小時", inline=False)
                embed.add_field(name="最大產量", value=f"{config['max_yield']} 個", inline=False)

                # 記錄事件
                if self.cog:
                    await self.cog.record_event(
                        'plant',
                        interaction.user,
                        f"種植{selected_seed}"
                    )

                # 編輯原始回應顯示結果
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                # 種植失敗，退還種子
                await add_inventory(self.user_id, "種子", selected_seed, 1)
                reason = result.get("reason", "未知原因") if result else "未知原因"
                await interaction.followup.send(f"❌ 種植失敗：{reason}", ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            # 如果發生錯誤，嘗試退還種子
            if 'selected_seed' in locals():
                try:
                    await add_inventory(self.user_id, "種子", selected_seed, 1)
                except Exception as refund_error:
                    print(f"⚠️ 退還種子失敗：{refund_error}", file=__import__('sys').stderr)
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


class SelectSeedView(discord.ui.View):
    """選擇要種植的種子"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id

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

                    await interaction.followup.send(embed=embed, ephemeral=True)
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
                value="• 作物資訊：查看作物狀態和操作選項\n• 個人物品：查看你的物品庫存\n• 查看肥料：檢查你的肥料庫存",
                inline=False
            )

            embed.set_footer(text="💡 這個視圖是永久的，按鈕不會過期")

            # 編輯原始回應
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)

        return callback

    @classmethod
    async def create_crop_info_embed_and_view(cls, bot, cog, user_id, guild_id, channel_id):
        """創建作物資訊embed和view"""
        # 重新獲取作物數據
        seeds = await get_inventory(user_id)
        seeds = seeds.get("種子", {}) if seeds else {}
        
        plants_data = await get_user_plants(user_id)
        plants = plants_data.get("plants", [])
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
                value = f"進度：{progress_bar} {progress:.0f}%\n時間：{time_left}\n施肥：{plant['fertilizer_applied']}次"
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