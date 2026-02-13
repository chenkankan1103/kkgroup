import discord
from discord.ui import Button
import traceback

from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from shop_commands.merchant.cannabis_farming import get_inventory, get_user_plants, add_inventory, remove_inventory, plant_cannabis, apply_fertilizer, harvest_plant
from shop_commands.merchant.database import update_user_kkcoin
from status_dashboard import add_log


class SelectFertilizerView(discord.ui.View):
    """選擇肥料視圖"""

    def __init__(self, bot, user_id, plant, fertilizers):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.user_id = user_id
        self.plant = plant

        for fert_name in fertilizers.keys():
            config = CANNABIS_SHOP["肥料"][fert_name]
            button = Button(
                label=f"用 {fert_name}",
                style=discord.ButtonStyle.primary,
                emoji=config["emoji"],
                custom_id=f"apply_fert_{fert_name.replace(' ', '_')}"
            )
            button.callback = self.make_apply_callback(fert_name)
            self.add_item(button)

    async def make_apply_callback(self, fert_name):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)

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

                    # 記錄事件
                    if hasattr(self, 'cog'):
                        user = await self.bot.fetch_user(self.user_id)
                        await self.cog.record_event(
                            'fertilize',
                            user,
                            f"為{self.plant['seed_type']}施肥"
                        )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 施肥失敗", ephemeral=True)

            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

        return callback


class SelectPlantForFertilizerView(discord.ui.View):
    """選擇植物進行施肥的視圖"""

    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.user_id = user_id
        self.plants = plants

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

    async def select_callback(self, interaction: discord.Interaction):
        """處理植物選擇"""
        try:
            await interaction.response.defer(ephemeral=True)

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

            # 應用肥料
            result = await apply_fertilizer(plant_id, fert_name)

            if result and result.get("success"):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                embed = discord.Embed(
                    title="💧 施肥成功",
                    description=f"已為 {config['emoji']} {plant['seed_type']} 施肥",
                    color=discord.Color.green()
                )
                embed.add_field(name="施肥次數", value=f"{result['fertilizer_applied']} 次", inline=True)
                embed.add_field(name="效果", value="成長速度加快 20%", inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                reason = result.get("reason", "未知原因") if result else "未知原因"
                await interaction.followup.send(f"❌ 施肥失敗：{reason}", ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


class SelectPlantForHarvestView(discord.ui.View):
    """選擇植物進行收割的視圖"""

    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.user_id = user_id
        self.plants = plants

        # 創建選擇選項
        options = []
        for plant in plants:
            config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            yield_amount = plant.get("yield", config["max_yield"])
            options.append(discord.SelectOption(
                label=f"{config['emoji']} {plant['seed_type']}",
                description=f"產量: {yield_amount} 個",
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

    async def select_callback(self, interaction: discord.Interaction):
        """處理植物選擇"""
        try:
            await interaction.response.defer(ephemeral=True)

            plant_id = int(interaction.data['values'][0])
            plant = next((p for p in self.plants if p['id'] == plant_id), None)

            if not plant:
                await interaction.followup.send("❌ 找不到選擇的植物！", ephemeral=True)
                return

            # 收割植物
            result = await harvest_plant(plant_id)

            if result and result.get("success"):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                yield_amount = result.get("yield", 0)
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

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                reason = result.get("reason", "未知原因") if result else "未知原因"
                await interaction.followup.send(f"❌ 收割失敗：{reason}", ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)