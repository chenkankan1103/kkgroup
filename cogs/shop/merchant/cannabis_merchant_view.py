"""黑市商人 - 大麻商品購買視圖"""
import discord
from discord.ui import View, Button, Modal, TextInput
import traceback
from shop_commands.merchant.database import get_user_kkcoin, update_user_kkcoin
from shop_commands.merchant.cannabis_farming import add_inventory, remove_inventory, get_inventory
from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES


class CannabisMerchantView(View):
    """黑市商人 - 大麻購買選單"""
    
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.button(label="購買種子", style=discord.ButtonStyle.success, emoji="🌱", custom_id="cannabis_buy_seeds")
    async def buy_seeds(self, interaction: discord.Interaction, button: discord.ui.Button):
        """購買種子選擇"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            embed = discord.Embed(
                title="🌱 購買種子",
                description="選擇要購買的種子類型：",
                color=discord.Color.green()
            )
            
            for seed_name, config in CANNABIS_SHOP["種子"].items():
                value = (
                    f"💰 價格：{config['price']} KKcoin\n"
                    f"⏱️ 成長：{config['growth_time']/3600:.0f}h\n"
                    f"🌾 產量：最多 {config['max_yield']} 個"
                )
                embed.add_field(name=f"{config['emoji']} {seed_name}", value=value, inline=False)
            
            view = SeedCategoryView(self.cog)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="購買肥料", style=discord.ButtonStyle.primary, emoji="💧", custom_id="cannabis_buy_fertilizer")
    async def buy_fertilizer(self, interaction: discord.Interaction, button: discord.ui.Button):
        """購買肥料選擇"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            embed = discord.Embed(
                title="💧 購買肥料",
                description="選擇要購買的肥料類型：",
                color=discord.Color.blue()
            )
            
            for fert_name, config in CANNABIS_SHOP["肥料"].items():
                value = (
                    f"💰 價格：{config['price']} KKcoin\n"
                    f"⚡ 加速：{config['growth_boost']*100:.0f}%"
                )
                embed.add_field(name=f"{config['emoji']} {fert_name}", value=value, inline=False)
            
            view = FertilizerCategoryView(self.cog)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="出售大麻", style=discord.ButtonStyle.danger, emoji="💰", custom_id="cannabis_sell")
    async def sell_cannabis(self, interaction: discord.Interaction, button: discord.ui.Button):
        """出售大麻"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            inventory = await get_inventory(user_id)
            
            if "大麻" not in inventory or not inventory["大麻"]:
                await interaction.followup.send("❌ 你沒有大麻可以出售！", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="💰 出售大麻",
                description="選擇要出售的大麻類型：",
                color=discord.Color.gold()
            )
            
            for seed_name, quantity in inventory["大麻"].items():
                price = CANNABIS_HARVEST_PRICES[seed_name]
                total = price * quantity
                embed.add_field(
                    name=f"{seed_name} x{quantity}",
                    value=f"單價：{price} KKcoin\n總價：{total} KKcoin",
                    inline=False
                )
            
            view = SellCannabisCategoryView(self.cog, inventory["大麻"])
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="返回", style=discord.ButtonStyle.grey, custom_id="cannabis_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回主菜單"""
        try:
            from shop_commands.merchant.views import ExploreView
            embed = discord.Embed(
                title="黑市商人出現了",
                description="竟然被你發現了，想要買些什麼，還是..."
            )
            await interaction.response.edit_message(embed=embed, view=ExploreView(self.cog))
        except Exception as e:
            traceback.print_exc()


class SeedCategoryView(View):
    """種子購買選擇"""
    
    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog
        
        for seed_name in CANNABIS_SHOP["種子"].keys():
            config = CANNABIS_SHOP["種子"][seed_name]
            button = discord.ui.Button(
                label=f"購買 {seed_name}",
                style=discord.ButtonStyle.success,
                emoji=config["emoji"],
                custom_id=f"buy_seed_{seed_name.replace(' ', '_')}"
            )
            button.callback = self.make_buy_callback(seed_name)
            self.add_item(button)
    
    async def make_buy_callback(self, seed_name):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.show_modal(BuySeedModal(self.cog, seed_name))
            except Exception as e:
                traceback.print_exc()
                await interaction.response.send_message(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        return callback


class BuySeedModal(Modal):
    """購買種子數量模態"""
    
    def __init__(self, cog, seed_name):
        super().__init__(title=f"購買 {seed_name}")
        self.cog = cog
        self.seed_name = seed_name
        self.quantity_input = TextInput(
            label="購買數量",
            placeholder="輸入要購買的種子數量",
            required=True,
            min_length=1,
            max_length=3
        )
        self.add_item(self.quantity_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            quantity = int(self.quantity_input.value)
            if quantity <= 0:
                await interaction.followup.send("❌ 數量必須大於 0", ephemeral=True)
                return
            
            config = CANNABIS_SHOP["種子"][self.seed_name]
            total_cost = config['price'] * quantity
            
            user_id = interaction.user.id
            current_kkcoin = await get_user_kkcoin(user_id)
            
            if current_kkcoin < total_cost:
                await interaction.followup.send(
                    f"❌ KKcoin 不足！\n"
                    f"需要：{total_cost} KKcoin\n"
                    f"擁有：{current_kkcoin} KKcoin",
                    ephemeral=True
                )
                return
            
            # 扣除 KKcoin
            await update_user_kkcoin(user_id, current_kkcoin - total_cost)
            
            # 添加到庫存
            await add_inventory(user_id, "種子", self.seed_name, quantity)
            
            embed = discord.Embed(
                title="✅ 購買成功",
                description=f"你購買了 {quantity} 個 {self.seed_name}",
                color=discord.Color.green()
            )
            embed.add_field(name="花費", value=f"{total_cost} KKcoin", inline=False)
            embed.add_field(name="剩餘 KKcoin", value=f"{current_kkcoin - total_cost} KKcoin", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ 請輸入有效的數字", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class FertilizerCategoryView(View):
    """肥料購買選擇"""
    
    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog
        
        for fert_name in CANNABIS_SHOP["肥料"].keys():
            config = CANNABIS_SHOP["肥料"][fert_name]
            button = discord.ui.Button(
                label=f"購買 {fert_name}",
                style=discord.ButtonStyle.primary,
                emoji=config["emoji"],
                custom_id=f"buy_fert_{fert_name.replace(' ', '_')}"
            )
            button.callback = self.make_buy_callback(fert_name)
            self.add_item(button)
    
    async def make_buy_callback(self, fert_name):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.show_modal(BuyFertilizerModal(self.cog, fert_name))
            except Exception as e:
                traceback.print_exc()
                await interaction.response.send_message(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        return callback


class BuyFertilizerModal(Modal):
    """購買肥料數量模態"""
    
    def __init__(self, cog, fert_name):
        super().__init__(title=f"購買 {fert_name}")
        self.cog = cog
        self.fert_name = fert_name
        self.quantity_input = TextInput(
            label="購買數量",
            placeholder="輸入要購買的肥料數量",
            required=True,
            min_length=1,
            max_length=3
        )
        self.add_item(self.quantity_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            quantity = int(self.quantity_input.value)
            if quantity <= 0:
                await interaction.followup.send("❌ 數量必須大於 0", ephemeral=True)
                return
            
            config = CANNABIS_SHOP["肥料"][self.fert_name]
            total_cost = config['price'] * quantity
            
            user_id = interaction.user.id
            current_kkcoin = await get_user_kkcoin(user_id)
            
            if current_kkcoin < total_cost:
                await interaction.followup.send(
                    f"❌ KKcoin 不足！\n"
                    f"需要：{total_cost} KKcoin\n"
                    f"擁有：{current_kkcoin} KKcoin",
                    ephemeral=True
                )
                return
            
            # 扣除 KKcoin
            await update_user_kkcoin(user_id, current_kkcoin - total_cost)
            
            # 添加到庫存
            await add_inventory(user_id, "肥料", self.fert_name, quantity)
            
            embed = discord.Embed(
                title="✅ 購買成功",
                description=f"你購買了 {quantity} 個 {self.fert_name}",
                color=discord.Color.green()
            )
            embed.add_field(name="花費", value=f"{total_cost} KKcoin", inline=False)
            embed.add_field(name="剩餘 KKcoin", value=f"{current_kkcoin - total_cost} KKcoin", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("❌ 請輸入有效的數字", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class SellCannabisCategoryView(View):
    """出售大麻選擇"""
    
    def __init__(self, cog, cannabis):
        super().__init__(timeout=60)
        self.cog = cog
        self.cannabis = cannabis
        
        for seed_name in cannabis.keys():
            quantity = cannabis[seed_name]
            price = CANNABIS_HARVEST_PRICES[seed_name]
            total = price * quantity
            
            button = discord.ui.Button(
                label=f"出售 {seed_name}",
                style=discord.ButtonStyle.danger,
                emoji=f"💰 {total}",
                custom_id=f"sell_cannabis_{seed_name.replace(' ', '_')}"
            )
            button.callback = self.make_sell_callback(seed_name, quantity, total)
            self.add_item(button)
    
    async def make_sell_callback(self, seed_name, quantity, total):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                user_id = interaction.user.id
                
                # 移除庫存
                await remove_inventory(user_id, "大麻", seed_name, quantity)
                
                # 添加 KKcoin
                current_kkcoin = await get_user_kkcoin(user_id)
                await update_user_kkcoin(user_id, current_kkcoin + total)
                
                embed = discord.Embed(
                    title="✅ 出售成功",
                    description=f"你出售了 {quantity} 個 {seed_name}",
                    color=discord.Color.green()
                )
                embed.add_field(name="獲得", value=f"{total} KKcoin", ephemeral=False)
                embed.add_field(name="現有 KKcoin", value=f"{current_kkcoin + total} KKcoin", inline=False)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback

