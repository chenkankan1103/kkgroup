"""黑市商人 - 大麻系統整合版（在同一個embed中編輯）"""
import discord
from discord.ui import View, Button, Select, TextInput, Modal
import traceback
from shop_commands.merchant.database import get_user_kkcoin, update_user_kkcoin
from shop_commands.merchant.cannabis_farming import add_inventory, remove_inventory, get_inventory
from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES


class CannabisMerchantViewV2(View):
    """黑市商人 - 大麻購買選單（改進版）"""
    
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.current_menu = "main"  # 追蹤當前菜單狀態
    
    @discord.ui.button(label="購買種子", style=discord.ButtonStyle.success, emoji="🌱", custom_id="cannabis_buy_seeds_v2")
    async def buy_seeds(self, interaction: discord.Interaction, button: discord.ui.Button):
        """購買種子 - 使用 Select Menu"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 構建種子選擇菜單
            options = []
            for seed_name, config in CANNABIS_SHOP["種子"].items():
                options.append(discord.SelectOption(
                    label=f"{config['emoji']} {seed_name} - {config['price']} KKcoin",
                    value=f"buy_seed_{seed_name}",
                    description=f"成長時間：{config['growth_time']/3600:.0f}h | 最大產量：{config['max_yield']}"
                ))
            
            view = SeedSelectView(self.cog, options)
            embed = discord.Embed(
                title="🌱 購買種子",
                description="從下方選擇要購買的種子類型",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="購買肥料", style=discord.ButtonStyle.primary, emoji="💧", custom_id="cannabis_buy_fertilizer_v2")
    async def buy_fertilizer(self, interaction: discord.Interaction, button: discord.ui.Button):
        """購買肥料 - 使用 Select Menu"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 構建肥料選擇菜單
            options = []
            for fert_name, config in CANNABIS_SHOP["肥料"].items():
                options.append(discord.SelectOption(
                    label=f"{config['emoji']} {fert_name} - {config['price']} KKcoin",
                    value=f"buy_fert_{fert_name}",
                    description=f"加速效果：{config['growth_boost']*100:.0f}%"
                ))
            
            view = FertilizerSelectView(self.cog, options)
            embed = discord.Embed(
                title="💧 購買肥料",
                description="從下方選擇要購買的肥料類型",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="出售大麻", style=discord.ButtonStyle.danger, emoji="💰", custom_id="cannabis_sell_v2")
    async def sell_cannabis(self, interaction: discord.Interaction, button: discord.ui.Button):
        """出售大麻 - 使用 Select Menu"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            try:
                inventory = await get_inventory(user_id)
            except Exception as e:
                # 如果表不存在，返回錯誤
                await interaction.followup.send(f"❌ 數據庫錯誤，請稍後重試：{str(e)[:100]}", ephemeral=True)
                return
            
            if "大麻" not in inventory or not inventory["大麻"]:
                await interaction.followup.send("❌ 你沒有大麻可以出售！", ephemeral=True)
                return
            
            # 構建大麻選擇菜單
            options = []
            for seed_name, quantity in inventory["大麻"].items():
                price = CANNABIS_HARVEST_PRICES.get(seed_name, 100)
                total = price * quantity
                options.append(discord.SelectOption(
                    label=f"{seed_name} x{quantity}",
                    value=f"sell_{seed_name}_{quantity}",
                    description=f"單價：{price} KKcoin | 總計：{total} KKcoin"
                ))
            
            view = SellSelectView(self.cog, inventory["大麻"])
            embed = discord.Embed(
                title="💰 出售大麻",
                description="選擇要出售的大麻類型",
                color=discord.Color.gold()
            )
            
            for seed_name, quantity in inventory["大麻"].items():
                price = CANNABIS_HARVEST_PRICES.get(seed_name, 100)
                total = price * quantity
                embed.add_field(
                    name=f"{seed_name}",
                    value=f"數量：{quantity} | 單價：{price} KKcoin | 合計：{total} KKcoin",
                    inline=False
                )
            
            view = SellSelectView(self.cog, inventory["大麻"])
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="返回", style=discord.ButtonStyle.grey, custom_id="cannabis_back_v2")
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


class SeedSelectView(View):
    """種子選擇菜單"""
    
    def __init__(self, cog, options):
        super().__init__(timeout=60)
        self.cog = cog
        
        select = Select(
            placeholder="選擇種子類型",
            options=options,
            custom_id="seed_select",
            min_values=1,
            max_values=1
        )
        select.callback = self.seed_selected
        self.add_item(select)
    
    async def seed_selected(self, interaction: discord.Interaction):
        """種子選擇完成"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            seed_name = interaction.data['values'][0].replace("buy_seed_", "")
            
            from shop_commands.merchant.cannabis_config import CANNABIS_SHOP
            seed_config = CANNABIS_SHOP["種子"][seed_name]
            
            embed = discord.Embed(
                title=f"購買 {seed_name}",
                description=f"{seed_config['emoji']} 種子\n\n請選擇購買數量",
                color=discord.Color.green()
            )
            embed.add_field(name="單價", value=f"{seed_config['price']} KKcoin", inline=False)
            
            # 使用通用數量選擇
            view = QuantitySelectView(
                self.cog,
                "種子",
                seed_name,
                f"buy_seed_{seed_name}",
                seed_config['price']
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
            except:
                pass
            
            quantity = int(self.quantity_input.value)
            if quantity <= 0 or quantity > 99:
                await interaction.followup.send("❌ 數量必須在 1-99 之間", ephemeral=True)
                return
            
            seed_config = CANNABIS_SHOP["種子"][self.seed_name]
            total_cost = seed_config["price"] * quantity
            
            # 檢查 KKcoin
            user_kkcoin = await get_user_kkcoin(interaction.user.id)
            if user_kkcoin < total_cost:
                await interaction.followup.send(
                    f"❌ KKcoin 不足\n需要：{total_cost}\n擁有：{user_kkcoin}",
                    ephemeral=True
                )
                return
            
            # 扣除 KKcoin
            await update_user_kkcoin(interaction.user.id, -total_cost)
            
            # 添加到庫存
            await add_inventory(interaction.user.id, "種子", self.seed_name, quantity)
            
            embed = discord.Embed(
                title="✅ 購買成功",
                description=f"成功購買了 {quantity} 個 {seed_config['emoji']} {self.seed_name}",
                color=discord.Color.green()
            )
            embed.add_field(name="花費", value=f"{total_cost} KKcoin", inline=False)
            embed.add_field(name="剩餘 KKcoin", value=f"{user_kkcoin - total_cost}", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        except ValueError:
            await interaction.followup.send("❌ 請輸入有效的數字", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)


class QuantitySelectView(View):
    """通用數量選擇按鈕"""
    
    def __init__(self, cog, item_type, item_name, buy_type, price_per_unit):
        super().__init__(timeout=30)
        self.cog = cog
        self.item_type = item_type  # "種子" or "肥料"
        self.item_name = item_name
        self.buy_type = buy_type    # "buy_seed_..." or "buy_fert_..."
        self.price_per_unit = price_per_unit
        
        # 數量按鈕
        for qty in [1, 5, 10, 25, 50]:
            button = Button(label=str(qty), style=discord.ButtonStyle.primary)
            button.callback = self._create_qty_callback(qty)
            self.add_item(button)
    
    def _create_qty_callback(self, qty):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                # 計算成本
                total_cost = qty * self.price_per_unit
                user_kkcoin = await get_user_kkcoin(interaction.user.id)
                
                if user_kkcoin < total_cost:
                    await interaction.followup.send(
                        f"❌ KKcoin 不足\n需要：{total_cost}\n擁有：{user_kkcoin}",
                        ephemeral=True
                    )
                    return
                
                # 扣除 KKcoin 並添加庫存
                await update_user_kkcoin(interaction.user.id, -total_cost)
                await add_inventory(interaction.user.id, self.item_type, self.item_name, qty)
                
                # 取得配置（用於 emoji）
                if self.item_type == "種子":
                    config = CANNABIS_SHOP["種子"].get(self.item_name, {})
                else:
                    config = CANNABIS_SHOP["肥料"].get(self.item_name, {})
                
                emoji = config.get('emoji', '')
                
                embed = discord.Embed(
                    title="✅ 購買成功",
                    description=f"成功購買了 {qty} 個 {emoji} {self.item_name}",
                    color=discord.Color.green()
                )
                embed.add_field(name="單位價格", value=f"{self.price_per_unit} KKcoin", inline=True)
                embed.add_field(name="數量", value=f"{qty}", inline=True)
                embed.add_field(name="總花費", value=f"{total_cost} KKcoin", inline=False)
                embed.add_field(name="剩餘 KKcoin", value=f"{user_kkcoin - total_cost}", inline=False)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback


class FertilizerSelectView(View):
    """肥料選擇菜單"""
    
    def __init__(self, cog, options):
        super().__init__(timeout=60)
        self.cog = cog
        
        select = Select(
            placeholder="選擇肥料類型",
            options=options,
            custom_id="fert_select",
            min_values=1,
            max_values=1
        )
        select.callback = self.fertilizer_selected
        self.add_item(select)
    
    async def fertilizer_selected(self, interaction: discord.Interaction):
        """肥料選擇完成"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            fert_name = interaction.data['values'][0].replace("buy_fert_", "")
            fert_config = CANNABIS_SHOP["肥料"].get(fert_name, {})
            price = fert_config.get('price', 0)
            
            # 使用通用數量選擇
            view = QuantitySelectView(
                self.cog,
                "肥料",
                fert_name,
                f"buy_fert_{fert_name}",
                price
            )
            
            await interaction.followup.send("選擇購買數量", view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)



class SellSelectView(View):
    """出售大麻選擇菜單"""
    
    def __init__(self, cog, inventory):
        super().__init__(timeout=60)
        self.cog = cog
        self.inventory = inventory
        
        options = []
        for seed_name, quantity in inventory.items():
            price = CANNABIS_HARVEST_PRICES.get(seed_name, 100)
            total = price * quantity
            options.append(discord.SelectOption(
                label=f"{seed_name} x{quantity}",
                value=f"sell_{seed_name}",
                description=f"單價：{price} | 合計：{total} KKcoin"
            ))
        
        select = Select(
            placeholder="選擇要出售的大麻",
            options=options,
            custom_id="sell_select",
            min_values=1,
            max_values=1
        )
        select.callback = self.sell_selected
        self.add_item(select)
    
    async def sell_selected(self, interaction: discord.Interaction):
        """確認出售"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            seed_name = interaction.data['values'][0].replace("sell_", "")
            quantity = self.inventory[seed_name]
            price = CANNABIS_HARVEST_PRICES.get(seed_name, 100)
            total_reward = price * quantity
            
            # 移除庫存
            await remove_inventory(interaction.user.id, "大麻", seed_name, quantity)
            
            # 增加 KKcoin
            await update_user_kkcoin(interaction.user.id, total_reward)
            
            # 獲取最新的 KKcoin
            new_kkcoin = await get_user_kkcoin(interaction.user.id)
            
            embed = discord.Embed(
                title="✅ 出售成功",
                description=f"成功出售了 {quantity} 個 {seed_name}",
                color=discord.Color.gold()
            )
            embed.add_field(name="單價", value=f"{price} KKcoin", inline=True)
            embed.add_field(name="數量", value=f"{quantity} 個", inline=True)
            embed.add_field(name="合計", value=f"{total_reward} KKcoin", inline=True)
            embed.add_field(name="目前 KKcoin", value=f"{new_kkcoin}", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
