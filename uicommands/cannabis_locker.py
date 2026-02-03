"""個人置物櫃 - 大麻種植管理 UI"""
import discord
from discord.ext import commands
from discord.ui import View, Button
import traceback
from datetime import datetime
from shop_commands.merchant.cannabis_farming import (
    get_user_plants, plant_cannabis, apply_fertilizer, harvest_plant, get_inventory, remove_inventory
)
from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from shop_commands.merchant.database import update_user_kkcoin, get_user_kkcoin


class PersonalLockerCog(commands.Cog):
    """個人置物櫃 - 大麻種植管理"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        print("[PersonalLocker] 個人置物櫃已載入")
    
    @commands.command(name="置物櫃", description="📦 打開個人置物櫃查看種植狀態")
    async def personal_locker(self, ctx):
        """查看個人置物櫃"""
        try:
            user_id = ctx.author.id
            plants = await get_user_plants(user_id)
            inventory = await get_inventory(user_id)
            
            embed = discord.Embed(
                title=f"📦 {ctx.author.name} 的個人置物櫃",
                description="你的大麻種植狀態",
                color=discord.Color.green()
            )
            
            if not plants:
                embed.add_field(
                    name="🌱 沒有種植中的植物",
                    value="還未開始種植！",
                    inline=False
                )
            else:
                for idx, plant in enumerate(plants, 1):
                    seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    
                    # 計算進度和剩餘時間
                    if plant["status"] == "harvested":
                        status_text = "✅ 已成熟，可以收割！"
                        progress_bar = "████████████████████ 100%"
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
                        progress_bar = "█" * filled + "░" * empty + f" {progress:.0f}%"
                        
                        remaining = max(0, matured_time - now)
                        if remaining > 0:
                            hours = int(remaining // 3600)
                            mins = int((remaining % 3600) // 60)
                            status_text = f"🌱 成長中... 剩餘 {hours}h {mins}m"
                        else:
                            status_text = "✅ 已成熟，可以收割！"
                    
                    field_value = (
                        f"種子：{seed_config['emoji']} {plant['seed_type']}\n"
                        f"進度：{progress_bar}\n"
                        f"狀態：{status_text}\n"
                        f"施肥：{plant['fertilizer_applied']} 次"
                    )
                    
                    embed.add_field(
                        name=f"植物 #{plant['id']}",
                        value=field_value,
                        inline=False
                    )
            
            # 添加庫存信息
            if inventory.get("種子"):
                seeds_info = ""
                for seed_name, qty in inventory["種子"].items():
                    seeds_info += f"  🌱 {seed_name} x{qty}\n"
                embed.add_field(
                    name="🌾 種子庫存",
                    value=seeds_info.strip(),
                    inline=True
                )
            
            if inventory.get("肥料"):
                fert_info = ""
                for fert_name, qty in inventory["肥料"].items():
                    fert_info += f"  💧 {fert_name} x{qty}\n"
                embed.add_field(
                    name="💧 肥料庫存",
                    value=fert_info.strip(),
                    inline=True
                )
            
            cannabis_info = ""
            if inventory.get("大麻"):
                for seed_name, qty in inventory["大麻"].items():
                    price = CANNABIS_HARVEST_PRICES[seed_name]
                    cannabis_info += f"  💰 {seed_name} x{qty} ({price}/個)\n"
                embed.add_field(
                    name="📦 大麻庫存",
                    value=cannabis_info.strip(),
                    inline=False
                )
            
            # 添加按鈕
            view = PersonalLockerView(self.bot, user_id, plants)
            await ctx.send(embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()
            await ctx.send(f"❌ 發生錯誤：{str(e)[:100]}")


class PersonalLockerView(discord.ui.View):
    """個人置物櫃交互菜單"""
    
    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.plants = plants
    
    @discord.ui.button(label="施肥", style=discord.ButtonStyle.success, emoji="💧")
    async def fertilize_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """選擇植物施肥"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            growing_plants = [p for p in self.plants if p["status"] != "harvested"]
            if not growing_plants:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return
            
            inventory = await get_inventory(self.user_id)
            if not inventory.get("肥料"):
                await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                return
            
            view = SelectPlantForFertilizerView(self.bot, self.user_id, growing_plants)
            await interaction.followup.send("選擇要施肥的植物：", view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="收割", style=discord.ButtonStyle.success, emoji="✂️")
    async def harvest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """選擇植物收割"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            harvestable = [p for p in self.plants if p["status"] == "harvested"]
            if not harvestable:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return
            
            view = SelectPlantForHarvestView(self.bot, self.user_id, harvestable)
            await interaction.followup.send("選擇要收割的植物：", view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="查看肥料", style=discord.ButtonStyle.primary, emoji="🧂")
    async def view_fertilizer(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查看可用肥料"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            inventory = await get_inventory(self.user_id)
            fertilizers = inventory.get("肥料", {})
            
            embed = discord.Embed(
                title="🧂 可用肥料",
                color=discord.Color.blue()
            )
            
            if not fertilizers:
                embed.description = "你沒有肥料"
            else:
                for fert_name, qty in fertilizers.items():
                    fert_config = CANNABIS_SHOP["肥料"][fert_name]
                    embed.add_field(
                        name=f"{fert_config['emoji']} {fert_name}",
                        value=f"擁有：{qty} 份\n加速：{fert_config['growth_boost']*100:.0f}%",
                        inline=True
                    )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class SelectPlantForFertilizerView(discord.ui.View):
    """選擇要施肥的植物"""
    
    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        
        for idx, plant in enumerate(plants[:5], 1):  # 限制 5 個
            seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            button = Button(
                label=f"植物 #{plant['id']} - {plant['seed_type']}",
                style=discord.ButtonStyle.secondary,
                emoji=seed_config["emoji"],
                custom_id=f"fert_plant_{plant['id']}"
            )
            button.callback = self.make_fert_callback(plant)
            self.add_item(button)
    
    async def make_fert_callback(self, plant):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                inventory = await get_inventory(self.user_id)
                fertilizers = inventory.get("肥料", {})
                
                if not fertilizers:
                    await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="💧 選擇肥料",
                    color=discord.Color.blue()
                )
                
                for fert_name, qty in fertilizers.items():
                    config = CANNABIS_SHOP["肥料"][fert_name]
                    embed.add_field(
                        name=f"{config['emoji']} {fert_name} (x{qty})",
                        value=f"加速：{config['growth_boost']*100:.0f}%",
                        inline=False
                    )
                
                view = SelectFertilizerView(self.bot, self.user_id, plant, fertilizers)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback


class SelectFertilizerView(discord.ui.View):
    """選擇肥料視圖"""
    
    def __init__(self, bot, user_id, plant, fertilizers):
        super().__init__(timeout=60)
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
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 施肥失敗", ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback


class SelectPlantForHarvestView(discord.ui.View):
    """選擇要收割的植物"""
    
    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        
        for idx, plant in enumerate(plants[:5], 1):  # 限制 5 個
            seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            button = Button(
                label=f"收割植物 #{plant['id']}",
                style=discord.ButtonStyle.danger,
                emoji="✂️",
                custom_id=f"harvest_plant_{plant['id']}"
            )
            button.callback = self.make_harvest_callback(plant)
            self.add_item(button)
    
    async def make_harvest_callback(self, plant):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                # 收割
                result = await harvest_plant(self.user_id, plant["id"])
                
                if result:
                    yield_amount = plant.get("harvested_amount", 0)
                    
                    embed = discord.Embed(
                        title="✅ 收割成功",
                        description=f"你收割了 {plant['seed_type']}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="產量", value=f"{yield_amount}個", inline=False)
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 收割失敗", ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback


class WeeklySummaryCannabisPanelView(discord.ui.View):
    """周統計面板的大麻系統快速訪問"""
    
    def __init__(self, bot, user_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
    
    @discord.ui.button(label="施肥加速", style=discord.ButtonStyle.primary, emoji="💧", custom_id="weekly_fertilize")
    async def fertilize_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """施肥加速"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            plants = await get_user_plants(self.user_id)
            growing_plants = [p for p in plants if p["status"] != "harvested"]
            
            if not growing_plants:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return
            
            inventory = await get_inventory(self.user_id)
            if not inventory.get("肥料"):
                await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                return
            
            # 顯示植物列表
            embed = discord.Embed(
                title="💧 選擇要施肥的植物",
                color=discord.Color.blue()
            )
            
            for idx, plant in enumerate(growing_plants[:5], 1):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                embed.add_field(
                    name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                    value=f"已施肥：{plant['fertilizer_applied']}次",
                    inline=False
                )
            
            view = SelectPlantForFertilizerView(self.bot, self.user_id, growing_plants)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
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
                    f"📊 進度：{progress_text}\n"
                    f"💧 施肥：{plant['fertilizer_applied']}次"
                )
                embed.add_field(name=f"#{idx} {seed_config['emoji']}", value=value, inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(PersonalLockerCog(bot))
