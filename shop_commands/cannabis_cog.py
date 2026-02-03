"""大麻種植指令和交互界面"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
import traceback
from datetime import datetime, timedelta
from .merchant.cannabis_farming import (
    init_cannabis_tables, plant_cannabis, get_user_plants, apply_fertilizer, 
    harvest_plant, get_inventory, remove_inventory, add_inventory
)
from .merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from .merchant.database import get_user_kkcoin, update_user_kkcoin


class CannabisCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.init_cannabis_tables_bg.start()
    
    def cog_unload(self):
        self.init_cannabis_tables_bg.cancel()
    
    @tasks.loop(seconds=10)
    async def init_cannabis_tables_bg(self):
        """後台初始化數據庫表"""
        try:
            await init_cannabis_tables()
        except Exception as e:
            traceback.print_exc()
    
    @init_cannabis_tables_bg.before_loop
    async def before_init(self):
        await self.bot.wait_until_ready()
    
    # ==================== 主命令 ====================
    @app_commands.command(name="種植", description="🌱 開始種植大麻")
    async def planting_menu(self, interaction: discord.Interaction):
        """種植菜單 - 購買種子或施肥"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            kkcoin = await get_user_kkcoin(user_id)
            
            embed = discord.Embed(
                title="🌱 大麻種植系統",
                description=f"💰 當前餘額：{kkcoin} KKcoin\n\n請選擇操作：",
                color=discord.Color.green()
            )
            
            view = CannabisBuyView(self.bot)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @app_commands.command(name="我的植物", description="📋 查看你的所有植物")
    async def my_plants(self, interaction: discord.Interaction):
        """查看用戶的植物列表"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            plants = await get_user_plants(user_id)
            
            if not plants:
                embed = discord.Embed(
                    title="📋 我的植物",
                    description="你還沒有種過任何植物！\n使用 `/種植` 開始吧！",
                    color=discord.Color.grey()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title=f"📋 我的植物 (共 {len(plants)} 棵)",
                color=discord.Color.green()
            )
            
            for idx, plant in enumerate(plants, 1):
                seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                status_emoji = "✅" if plant["status"] == "harvested" else "🌱"
                
                value = (
                    f"{status_emoji} 狀態：{plant['status']}\n"
                    f"🌱 種子：{seed_config['name']}\n"
                    f"📊 成長度：{plant['progress']:.1f}%\n"
                    f"💧 施肥次數：{plant['fertilizer_applied']}\n"
                    f"⏰ 種植時間：<t:{int(datetime.fromisoformat(plant['planted_at']).timestamp())}:R>"
                )
                
                embed.add_field(
                    name=f"植物 #{plant['id']} - {seed_config['emoji']}",
                    value=value,
                    inline=False
                )
            
            # 添加按鈕以交互
            view = CannabisPlantsView(self.bot, plants)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @app_commands.command(name="我的庫存", description="📦 查看你的大麻庫存")
    async def inventory(self, interaction: discord.Interaction):
        """查看用戶庫存"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            inventory = await get_inventory(user_id)
            
            embed = discord.Embed(
                title="📦 我的庫存",
                color=discord.Color.blue()
            )
            
            if not inventory:
                embed.description = "你的庫存是空的！"
            else:
                for item_type, items in inventory.items():
                    item_list = "\n".join([f"  • {name} x{qty}" for name, qty in items.items()])
                    embed.add_field(name=item_type, value=item_list, inline=False)
            
            # 販賣按鈕
            view = CannabisSellView(self.bot, inventory)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


# ==================== 交互界面 ====================
class CannabisBuyView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=60)
        self.bot = bot
    
    @discord.ui.button(label="🌱 購買種子", style=discord.ButtonStyle.success)
    async def buy_seeds(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            
            embed = discord.Embed(
                title="🌱 購買種子",
                description="選擇要購買的種子類型：",
                color=discord.Color.green()
            )
            
            for seed_name, seed_config in CANNABIS_SHOP["種子"].items():
                value = (
                    f"💰 價格：{seed_config['price']} KKcoin\n"
                    f"⏱️ 成長時間：{seed_config['growth_time'] / 3600:.0f} 小時\n"
                    f"🌾 最高產量：{seed_config['max_yield']} 個\n"
                    f"📝 {seed_config['description']}"
                )
                embed.add_field(name=f"{seed_config['emoji']} {seed_name}", value=value, inline=False)
            
            view = SeedSelectView(self.bot, interaction.user.id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="💧 購買肥料", style=discord.ButtonStyle.success)
    async def buy_fertilizer(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            
            embed = discord.Embed(
                title="💧 購買肥料",
                description="選擇要購買的肥料類型：",
                color=discord.Color.blue()
            )
            
            for fertilizer_name, fert_config in CANNABIS_SHOP["肥料"].items():
                value = (
                    f"💰 價格：{fert_config['price']} KKcoin\n"
                    f"⚡ 加速效果：{fert_config['growth_boost'] * 100:.0f}%\n"
                    f"📝 {fert_config['description']}"
                )
                embed.add_field(name=f"{fert_config['emoji']} {fertilizer_name}", value=value, inline=False)
            
            view = FertilizerSelectView(self.bot, interaction.user.id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class SeedSelectView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        
        # 動態添加按鈕
        for seed_name in CANNABIS_SHOP["種子"].keys():
            self.add_item(SeedButton(bot, user_id, seed_name))


class SeedButton(discord.ui.Button):
    def __init__(self, bot, user_id, seed_name):
        self.bot = bot
        self.user_id = user_id
        self.seed_name = seed_name
        seed_config = CANNABIS_SHOP["種子"][seed_name]
        super().__init__(
            label=seed_name,
            style=discord.ButtonStyle.success,
            emoji=seed_config["emoji"]
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            seed_config = CANNABIS_SHOP["種子"][self.seed_name]
            price = seed_config["price"]
            
            # 檢查 KKcoin
            kkcoin = await get_user_kkcoin(self.user_id)
            if kkcoin < price:
                await interaction.followup.send(
                    f"❌ KKcoin 不足！需要 {price}，你有 {kkcoin}",
                    ephemeral=True
                )
                return
            
            # 扣費
            await update_user_kkcoin(self.user_id, -price)
            
            # 種植
            plant_info = await plant_cannabis(
                self.user_id,
                interaction.guild_id,
                interaction.channel_id,
                self.seed_name
            )
            
            matured_dt = datetime.fromisoformat(plant_info["matured_at"])
            embed = discord.Embed(
                title="🌱 種植成功！",
                description=f"{seed_config['emoji']} {self.seed_name} 已種下\n\n"
                           f"⏰ 預計成熟時間：<t:{int(matured_dt.timestamp())}:R>",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class FertilizerSelectView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        
        for fert_name in CANNABIS_SHOP["肥料"].keys():
            self.add_item(FertilizerButton(bot, user_id, fert_name))


class FertilizerButton(discord.ui.Button):
    def __init__(self, bot, user_id, fert_name):
        self.bot = bot
        self.user_id = user_id
        self.fert_name = fert_name
        fert_config = CANNABIS_SHOP["肥料"][fert_name]
        super().__init__(
            label=fert_name,
            style=discord.ButtonStyle.primary,
            emoji=fert_config["emoji"]
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            fert_config = CANNABIS_SHOP["肥料"][self.fert_name]
            price = fert_config["price"]
            
            # 檢查 KKcoin
            kkcoin = await get_user_kkcoin(self.user_id)
            if kkcoin < price:
                await interaction.followup.send(
                    f"❌ KKcoin 不足！需要 {price}，你有 {kkcoin}",
                    ephemeral=True
                )
                return
            
            # 扣費並添加到庫存
            await update_user_kkcoin(self.user_id, -price)
            await add_inventory(self.user_id, "肥料", self.fert_name, 1)
            
            embed = discord.Embed(
                title="💧 購買成功！",
                description=f"{fert_config['emoji']} {self.fert_name} x1 已添加到庫存",
                color=discord.Color.blue()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class CannabisPlantsView(discord.ui.View):
    def __init__(self, bot, plants):
        super().__init__(timeout=60)
        self.bot = bot
        self.plants = plants
        
        for plant in plants[:5]:  # 限制 5 個按鈕
            self.add_item(PlantActionButton(bot, plant))


class PlantActionButton(discord.ui.Button):
    def __init__(self, bot, plant):
        self.bot = bot
        self.plant = plant
        seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
        
        status = "✅收割" if plant["status"] == "harvested" else f"{plant['progress']:.0f}%"
        super().__init__(
            label=status,
            style=discord.ButtonStyle.success if plant["status"] == "harvested" else discord.ButtonStyle.secondary,
            custom_id=f"plant_{plant['id']}"
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            if self.plant["status"] == "harvested":
                # 收割
                result = await harvest_plant(self.plant["id"])
                if result["success"]:
                    embed = discord.Embed(
                        title="🎉 收割成功！",
                        description=f"獲得：{result['seed_type']} x{result['yield_amount']}\n"
                                   f"可賣價：{result['sell_price']} KKcoin",
                        color=discord.Color.gold()
                    )
                else:
                    embed = discord.Embed(
                        title="❌ 收割失敗",
                        description=result["reason"],
                        color=discord.Color.red()
                    )
            else:
                # 施肥
                inventory = await get_inventory(interaction.user.id)
                fertilizers = inventory.get("肥料", {})
                
                if not fertilizers:
                    await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                    return
                
                # 顯示施肥選項
                view = ApplyFertilizerView(self.bot, self.plant["id"], fertilizers)
                await interaction.followup.send("選擇肥料施用：", view=view, ephemeral=True)
                return
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class ApplyFertilizerView(discord.ui.View):
    def __init__(self, bot, plant_id, fertilizers):
        super().__init__(timeout=60)
        self.bot = bot
        self.plant_id = plant_id
        
        for fert_name in fertilizers.keys():
            self.add_item(ApplyFertilizerButton(bot, plant_id, fert_name))


class ApplyFertilizerButton(discord.ui.Button):
    def __init__(self, bot, plant_id, fert_name):
        self.bot = bot
        self.plant_id = plant_id
        self.fert_name = fert_name
        fert_config = CANNABIS_SHOP["肥料"][fert_name]
        super().__init__(
            label=fert_name,
            style=discord.ButtonStyle.primary,
            emoji=fert_config["emoji"]
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 施肥
            success = await apply_fertilizer(self.plant_id, self.fert_name)
            
            if success:
                # 移除肥料
                await remove_inventory(interaction.user.id, "肥料", self.fert_name, 1)
                
                embed = discord.Embed(
                    title="💧 施肥成功！",
                    description=f"已使用 {self.fert_name}，加速了植物成長",
                    color=discord.Color.blue()
                )
            else:
                embed = discord.Embed(
                    title="❌ 施肥失敗",
                    description="植物狀態不適合施肥",
                    color=discord.Color.red()
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class CannabisSellView(discord.ui.View):
    def __init__(self, bot, inventory):
        super().__init__(timeout=60)
        self.bot = bot
        self.inventory = inventory
        
        if "大麻" in inventory:
            for seed_name in inventory["大麻"].keys():
                self.add_item(SellCannabisButton(bot, seed_name))


class SellCannabisButton(discord.ui.Button):
    def __init__(self, bot, seed_name):
        self.bot = bot
        self.seed_name = seed_name
        super().__init__(
            label=f"賣 {seed_name}",
            style=discord.ButtonStyle.danger,
            emoji="💰"
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(SellCannabisModal(self.bot, interaction.user.id, self.seed_name))
        except Exception as e:
            traceback.print_exc()
            await interaction.response.send_message(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class SellCannabisModal(discord.ui.Modal):
    def __init__(self, bot, user_id, seed_name):
        super().__init__(title=f"賣出 {seed_name}")
        self.bot = bot
        self.user_id = user_id
        self.seed_name = seed_name
        
        self.quantity_input = discord.ui.TextInput(
            label="數量",
            placeholder="輸入要賣出的數量",
            required=True
        )
        self.add_item(self.quantity_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            quantity = int(self.quantity_input.value)
            if quantity <= 0:
                await interaction.followup.send("❌ 數量必須大於 0", ephemeral=True)
                return
            
            # 檢查庫存並出售
            if not await remove_inventory(self.user_id, "大麻", self.seed_name, quantity):
                await interaction.followup.send("❌ 數量不足", ephemeral=True)
                return
            
            # 計算收入
            unit_price = CANNABIS_HARVEST_PRICES[self.seed_name]
            total_price = unit_price * quantity
            
            # 增加 KKcoin
            await update_user_kkcoin(self.user_id, total_price)
            
            embed = discord.Embed(
                title="💰 出售成功！",
                description=f"賣出：{self.seed_name} x{quantity}\n"
                           f"單價：{unit_price} KKcoin\n"
                           f"總收入：{total_price} KKcoin",
                color=discord.Color.gold()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ 請輸入有效的數字", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CannabisCog(bot))
