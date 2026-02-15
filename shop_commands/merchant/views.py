import discord
from discord.ui import Button, View, Modal, TextInput, Select
import asyncio
import os
import random
import traceback
from .config import RAINBOW_ROLE_ID, VIP_ROLE_ID, EQUIPMENT_SHOP, ROLE_SHOP

class CustomAmountModal(Modal):
    def __init__(self, slot_machine_view):
        super().__init__(title="自訂賭注金額")
        self.slot_machine_view = slot_machine_view
        self.amount_input = TextInput(label="賭注金額 (KKcoin)", placeholder="輸入你要下注的 KKcoin 數量", required=True)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount_input.value)
            if bet_amount <= 0:
                await interaction.response.send_message("賭注金額必須大於 0！", ephemeral=True)
                return
            
            for child in self.slot_machine_view.children:
                if isinstance(child, discord.ui.Select):
                    child.placeholder = f"目前賭注: {bet_amount} KKcoin"
                    self.slot_machine_view.bet_amount = bet_amount
                elif isinstance(child, discord.ui.Button) and child.custom_id == "gamble":
                    child.label = f"拉霸 ({bet_amount} KKcoin)"
            
            await interaction.response.edit_message(view=self.slot_machine_view)
        except ValueError:
            await interaction.response.send_message("請輸入有效的數字！", ephemeral=True)


class SlotMachineView(discord.ui.View):
    def __init__(self, cog, history=None, original_message=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.history = history if isinstance(history, list) else []
        self.original_message = original_message  # 接收並保留原始訊息
    
    @discord.ui.button(label="下注 50 KKcoin", style=discord.ButtonStyle.primary, emoji="💰")
    async def bet_50(self, interaction: discord.Interaction, button: discord.ui.Button):
        """下注 50 KKcoin"""
        try:
            if self.original_message is None:
                self.original_message = interaction.message
            
            # 關鍵修正：將返回的訊息重新賦值
            result_message = await self.cog.handle_bet(
                interaction, 
                interaction.user.id, 
                50, 
                history=self.history,
                original_message=self.original_message
            )
            
            # 更新 original_message 為最新的訊息
            if result_message:
                self.original_message = result_message
                
        except Exception as e:
            traceback.print_exc()
            try:
                err_text = str(e)[:200]
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 下注處理失敗: {err_text}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 下注處理失敗: {err_text}", ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="下注 100 KKcoin", style=discord.ButtonStyle.primary, emoji="💎")
    async def bet_100(self, interaction: discord.Interaction, button: discord.ui.Button):
        """下注 100 KKcoin"""
        try:
            if self.original_message is None:
                self.original_message = interaction.message
            
            result_message = await self.cog.handle_bet(
                interaction, 
                interaction.user.id, 
                100, 
                history=self.history,
                original_message=self.original_message
            )
            
            if result_message:
                self.original_message = result_message
                
        except Exception as e:
            traceback.print_exc()
            try:
                err_text = str(e)[:200]
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 下注處理失敗: {err_text}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 下注處理失敗: {err_text}", ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="下注 200 KKcoin", style=discord.ButtonStyle.primary, emoji="💸")
    async def bet_200(self, interaction: discord.Interaction, button: discord.ui.Button):
        """下注 200 KKcoin"""
        try:
            if self.original_message is None:
                self.original_message = interaction.message
            
            result_message = await self.cog.handle_bet(
                interaction, 
                interaction.user.id, 
                200, 
                history=self.history,
                original_message=self.original_message
            )
            
            if result_message:
                self.original_message = result_message
                
        except Exception as e:
            traceback.print_exc()
            try:
                err_text = str(e)[:200]
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 下注處理失敗: {err_text}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 下注處理失敗: {err_text}", ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="結束遊戲", style=discord.ButtonStyle.danger, emoji="🚪", row=1)
    async def end_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        """結束遊戲並顯示最終統計"""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            # 計算統計
            if len(self.history) == 0:
                embed = discord.Embed(
                    title="🎰 遊戲結束",
                    description="你還沒有進行任何遊戲！",
                    color=discord.Color.blue()
                )
            else:
                total_bet = sum(h['bet'] for h in self.history)
                total_change = sum(h['change'] for h in self.history)
                win_count = sum(1 for h in self.history if h['change'] > 0)
                lose_count = sum(1 for h in self.history if h['change'] < 0)
                draw_count = sum(1 for h in self.history if h['change'] == 0)
                
                # 根據最終結果決定顏色
                if total_change > 0:
                    color = discord.Color.green()
                    result_emoji = "🎉"
                    result_text = "恭喜獲利！"
                elif total_change < 0:
                    color = discord.Color.red()
                    result_emoji = "😢"
                    result_text = "很遺憾虧損了"
                else:
                    color = discord.Color.gold()
                    result_emoji = "😐"
                    result_text = "打平收場"
                
                embed = discord.Embed(
                    title=f"🎰 遊戲結束 - {result_text}",
                    description=f"{result_emoji} 感謝遊玩拉霸機！",
                    color=color
                )
                
                # 最終統計
                embed.add_field(
                    name="📊 最終統計",
                    value=(
                        f"🎮 總場數：{len(self.history)} 場\n"
                        f"✅ 勝場：{win_count} | ❌ 敗場：{lose_count} | ⚪ 平手：{draw_count}\n"
                        f"💸 總下注：{total_bet} KKcoin\n"
                        f"💰 淨損益：{'+' if total_change >= 0 else ''}{total_change} KKcoin"
                    ),
                    inline=False
                )
                
                # 顯示歷史記錄
                history_text = []
                for i, h in enumerate(reversed(self.history), 1):
                    history_text.append(
                        f"{h['emoji']} `[ {h['result']} ]` - 下注 {h['bet']} → {h['change_text']}"
                    )
                
                embed.add_field(
                    name=f"📜 遊戲記錄（共 {len(self.history)} 場）",
                    value="\n".join(history_text),
                    inline=False
                )
                
                # 勝率統計
                if len(self.history) > 0:
                    win_rate = (win_count / len(self.history)) * 100
                    embed.add_field(
                        name="📈 勝率分析",
                        value=f"勝率：{win_rate:.1f}%",
                        inline=False
                    )
            
            embed.set_footer(text="期待下次再來挑戰！")
            
            # 停用所有按鈕
            for item in self.children:
                item.disabled = True
            
            # 更新原始訊息
            try:
                if self.original_message:
                    await self.original_message.edit(embed=embed, view=self)
                else:
                    await interaction.message.edit(embed=embed, view=self)
            except discord.NotFound:
                # 如果訊息被刪除，發送新訊息
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 結束遊戲時發生錯誤", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 結束遊戲時發生錯誤", ephemeral=True)
            except:
                pass
    
    async def on_gamble(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("這不是你的賭博視窗！", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.cog.handle_bet(interaction, self.user_id, self.bet_amount)
    
    async def on_leave(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("這不是你的賭博視窗！", ephemeral=True)
            return

        await interaction.response.send_message("你離開了賭博機。", ephemeral=True)

        try:
            await interaction.message.delete()
        except Exception as e:
            print(f"Failed to delete message: {e}")
            try:
                await interaction.followup.send("刪除訊息時發生錯誤。", ephemeral=True)
            except:
                pass  # 如果 followup 也失敗就靜默處理

class PersistentView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)  # 持久化視圖必須 timeout=None
        self.cog = cog

    @discord.ui.button(label="探索", style=discord.ButtonStyle.grey, custom_id="persistent_explore")
    async def explore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="黑市商人出現了", description="竟然被你發現了，想要買些什麼，還是...")
        await interaction.response.send_message(embed=embed, view=ExploreView(self.cog), ephemeral=True)

    @discord.ui.button(label="離開", style=discord.ButtonStyle.grey, custom_id="persistent_exit")
    async def exit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("你決定離開這片神秘的黑暗角落。", ephemeral=True)


class ExploreView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="購買身份", style=discord.ButtonStyle.green, custom_id="persistent_buy_roles")
    async def buy_roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.get_merchant_response(interaction.user, "購買身份", interaction)

    @discord.ui.button(label="購買裝備", style=discord.ButtonStyle.blurple, custom_id="persistent_buy_equipment")
    async def buy_equipment_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.get_merchant_response(interaction.user, "購買裝備", interaction)

    @discord.ui.button(label="🔫 搶劫商人 (30%機率)", style=discord.ButtonStyle.red, custom_id="persistent_rob")
    async def rob_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_rob_action(interaction)

    @discord.ui.button(label="🎰 拉霸機", style=discord.ButtonStyle.secondary, custom_id="persistent_gamble")
    async def gamble_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            
            rules_embed = discord.Embed(
                title="🎰 拉霸機規則",
                description=(
                    "下注 KKcoin，挑戰你的運氣！\n\n"
                    "🎯 三個相同圖案可獲得以下獎勵：\n"
                    "💎💎💎：x15\n"
                    "⭐⭐⭐：x8\n"
                    "🔔🔔🔔：x5\n"
                    "🍋🍋🍋：x3\n"
                    "🍒🍒🍒：x2.5\n"
                    "🍊🍊🍊 / 🍉🍉🍉 / 🍇🍇🍇：x1.5\n\n"
                    "🌀 兩個圖案相同：獲得 110% 賭金 (賺10%)\n"
                    "⭐ 僅出現一顆星星：保本回收 100% 賭金\n"
                    "💸 沒有任何中獎條件：損失 5% 賭金\n\n"
                    "選擇下注金額開始遊戲！"
                ),
                color=discord.Color.gold()
            )
            
            view = SlotMachineView(self.cog, history=[])
            message = await interaction.followup.send(embed=rules_embed, view=view, ephemeral=True)
            
            # 設定初始訊息
            view.original_message = message
            
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send("❌ 拉霸機啟動失敗", ephemeral=True)
            except:
                pass

    @discord.ui.button(label="🌱 種植大麻", style=discord.ButtonStyle.success, custom_id="persistent_cannabis")
    async def cannabis_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from shop_commands.merchant.cannabis_merchant_view_v2 import CannabisMerchantViewV2
        embed = discord.Embed(
            title="🌱 大麻商店",
            description="歡迎來到大麻商店！選擇您想要的功能。",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, view=CannabisMerchantViewV2(self.cog), ephemeral=True)

    @discord.ui.button(label="👗 進入衣帽間", style=discord.ButtonStyle.primary, custom_id="persistent_paperdoll", emoji="👗")
    async def paperdoll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        with open('paperdoll_button_click.log', 'a') as f:
            f.write(f"Paperdoll button clicked. Categories count: {len(self.cog.categories)}\n")
            f.write(f"Categories: {self.cog.categories[:5] if self.cog.categories else 'None'}\n")
        
        if not self.cog.categories:
            await interaction.response.send_message("❌ 衣帽間暫時無法使用。", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="👗 衣帽間",
            description="選擇要更改的部位。",
            color=0xFF69B4
        )
        
        # 動態導入View
        from shop_commands.shop import DressingRoomView
        view = DressingRoomView(self.cog, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class RoleShopView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="七彩披風 (50 KKcoin/1天)", style=discord.ButtonStyle.blurple, custom_id="persistent_buy_rainbow")
    async def rainbow_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = ROLE_SHOP["七彩披風"]
        await self.cog.handle_role_purchase(interaction, "七彩披風", item["price"], item["role_id"], item["duration"])

    @discord.ui.button(label="進階組員 (75 KKcoin/1週)", style=discord.ButtonStyle.blurple, custom_id="persistent_buy_vip")
    async def vip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = ROLE_SHOP["進階組員"]
        await self.cog.handle_role_purchase(interaction, "進階組員", item["price"], item["role_id"], item["duration"])

    @discord.ui.button(label="返回", style=discord.ButtonStyle.grey, custom_id="persistent_role_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="黑市商人出現了", description="竟然被你發現了，想要買些什麼，還是...")
        await interaction.response.edit_message(embed=embed, view=ExploreView(self.cog))


class EquipmentShopView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)  # 持久化視圖
        self.cog = cog
        self.current_category = "hair"
        self.update_items()
    
    def update_items(self):
        self.clear_items()
        
        category_select = Select(
            placeholder=f"目前類別: {self.get_category_name(self.current_category)}",
            custom_id="persistent_category_select",
            options=[
                discord.SelectOption(label="髮型", value="hair", emoji="💇"),
                discord.SelectOption(label="臉型", value="face", emoji="😊"),
                discord.SelectOption(label="膚色", value="skin", emoji="🎨"),
                discord.SelectOption(label="上衣", value="top", emoji="👔"),
                discord.SelectOption(label="下裝", value="bottom", emoji="👖"),
                discord.SelectOption(label="鞋子", value="shoes", emoji="👟")
            ]
        )
        category_select.callback = self.category_callback
        self.add_item(category_select)
        
        items = EQUIPMENT_SHOP.get(self.current_category, {})
        button_count = 0
        
        # 修改：每個商品使用下拉選單而不是直接購買按鈕
        for item_name, item_data in items.items():
            if button_count >= 15:  # 減少按鈕數量，為新功能留空間
                break
            
            # 創建商品選項按鈕，點擊後顯示詳細選項
            button = Button(
                label=f"👀 {item_name}",
                style=discord.ButtonStyle.primary,
                custom_id=f"persistent_view_{self.current_category}_{button_count}",
                emoji="🔍"
            )
            button.callback = lambda i, name=item_name, data=item_data: self.show_item_options(i, name, data)
            self.add_item(button)
            button_count += 1
        
        # 返回按鈕
        back_button = Button(label="返回", style=discord.ButtonStyle.grey, custom_id="persistent_equipment_back")
        back_button.callback = self.back_callback
        self.add_item(back_button)
    
    def get_category_name(self, category):
        names = {"hair": "髮型", "face": "臉型", "skin": "膚色", "top": "上衣", "bottom": "下裝", "shoes": "鞋子"}
        return names.get(category, category)
    
    async def category_callback(self, interaction: discord.Interaction):
        self.current_category = interaction.data["values"][0]
        self.update_items()
        
        from shop_commands.merchant.database import get_user_kkcoin
        kkcoin = await get_user_kkcoin(interaction.user.id)
        
        embed = discord.Embed(
            title=f"🛍️ 裝備商店 - {self.get_category_name(self.current_category)}",
            description=f"你目前擁有: {kkcoin} KKcoin\n點擊商品名稱查看詳細選項！",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def show_item_options(self, interaction: discord.Interaction, item_name: str, item_data: dict):
        """顯示商品的詳細選項（預覽、試穿、購買）"""
        await interaction.response.defer(ephemeral=True)
        
        from shop_commands.merchant.database import get_user_kkcoin
        kkcoin = await get_user_kkcoin(interaction.user.id)
        
        embed = discord.Embed(
            title=f"🛍️ {item_name}",
            description=item_data.get("description", "精美的裝備，值得擁有！"),
            color=discord.Color.gold()
        )
        
        embed.add_field(name="💰 價格", value=f"{item_data['price']} KKcoin", inline=True)
        embed.add_field(name="🏷️ 類別", value=self.get_category_name(self.current_category), inline=True)
        embed.add_field(name="💳 你的餘額", value=f"{kkcoin} KKcoin", inline=True)
        
        # 如果有特殊效果，顯示出來
        if "effects" in item_data:
            effects_text = []
            for effect in item_data["effects"]:
                if effect["type"] == "kkcoin_bonus":
                    effects_text.append(f"💰 購買獲得額外 {effect['value']} KKcoin")
                elif effect["type"] == "daily_bonus":
                    effects_text.append(f"📅 每日額外獲得 {effect['value']} KKcoin")
            
            if effects_text:
                embed.add_field(name="✨ 特殊效果", value="\n".join(effects_text), inline=False)
        
        # 如果有預覽圖片，添加縮圖
        if "image_url" in item_data:
            embed.set_thumbnail(url=item_data["image_url"])
        
        # 顯示是否有足夠金錢購買
        can_afford = kkcoin >= item_data['price']
        embed.add_field(
            name="💸 購買狀態", 
            value="✅ 可以購買" if can_afford else "❌ 金錢不足", 
            inline=False
        )
        
        view = ItemDetailView(self.cog, item_name, item_data, self.current_category, can_afford)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
    
    async def back_callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="黑市商人出現了", description="竟然被你發現了，想要買些什麼，還是...")
        await interaction.response.edit_message(embed=embed, view=ExploreView(self.cog))


class ItemDetailView(View):
    """商品詳細頁面視圖"""
    def __init__(self, cog, item_name: str, item_data: dict, category: str, can_afford: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.item_name = item_name
        self.item_data = item_data
        self.category = category
        self.can_afford = can_afford
    
    @discord.ui.button(label="👀 預覽試穿", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def preview_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_equipment_preview(interaction, self.item_name, self.item_data, self.category)
    
    @discord.ui.button(label="🛒 直接購買", style=discord.ButtonStyle.green, emoji="💰")
    async def buy_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.can_afford:
            await interaction.response.send_message("❌ 你的 KKcoin 不足，無法購買此商品！", ephemeral=True)
            return
        await self.cog.handle_equipment_purchase(interaction, self.item_name, self.item_data, self.category)
    
    @discord.ui.button(label="🔙 返回商店", style=discord.ButtonStyle.grey)
    async def back_to_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        from shop_commands.merchant.database import get_user_kkcoin
        kkcoin = await get_user_kkcoin(interaction.user.id)
        
        embed = discord.Embed(
            title=f"🛍️ 裝備商店 - {self.get_category_name(self.category)}",
            description=f"你目前擁有: {kkcoin} KKcoin\n點擊商品名稱查看詳細選項！",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=embed, view=EquipmentShopView(self.cog))
    
    def get_category_name(self, category):
        names = {"hair": "髮型", "face": "臉型", "skin": "膚色", "top": "上衣", "bottom": "下裝", "shoes": "鞋子"}
        return names.get(category, category)

class EquipmentPreviewView(discord.ui.View):
    """裝備詳情預覽視圖"""
    def __init__(self, cog, item_name: str, item_data: dict, category: str, can_afford: bool = True):
        super().__init__(timeout=300)
        self.cog = cog
        self.item_name = item_name
        self.item_data = item_data
        self.category = category
        self.can_afford = can_afford

    @discord.ui.button(label="👀 再次試穿", style=discord.ButtonStyle.primary, emoji="👗")
    async def try_on_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_equipment_preview(interaction, self.item_name, self.item_data, self.category)

    @discord.ui.button(label="💰 立即購買", style=discord.ButtonStyle.success, emoji="🛒")
    async def purchase_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.can_afford:
            await interaction.response.send_message("❌ 你的 KKcoin 不足，無法購買此商品！", ephemeral=True)
            return
        await self.cog.handle_equipment_purchase(interaction, self.item_name, self.item_data, self.category)

    @discord.ui.button(label="🔙 返回商店", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from shop_commands.merchant.database import get_user_kkcoin
        
        kkcoin = await get_user_kkcoin(interaction.user.id)
        embed = discord.Embed(
            title="🛍️ 裝備商店", 
            description=f"你目前擁有: {kkcoin} KKcoin\n選擇類別來瀏覽裝備！", 
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=EquipmentShopView(self.cog))
        
class TryOnResultView(discord.ui.View):
    """試穿結果操作視圖"""
    def __init__(self, cog, item_name: str, item_data: dict, category: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.item_name = item_name
        self.item_data = item_data
        self.category = category

    @discord.ui.button(label="💰 喜歡！立即購買", style=discord.ButtonStyle.success, emoji="❤️")
    async def purchase_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_equipment_purchase(interaction, self.item_name, self.item_data, self.category)

    @discord.ui.button(label="🔄 試穿其他裝備", style=discord.ButtonStyle.primary)
    async def try_other_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from shop_commands.merchant.views import EquipmentShopView
        from shop_commands.merchant.database import get_user_kkcoin
        
        kkcoin = await get_user_kkcoin(interaction.user.id)
        embed = discord.Embed(
            title="🛍️ 裝備商店", 
            description=f"你目前擁有: {kkcoin} KKcoin\n選擇類別來瀏覽裝備！", 
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=EquipmentShopView(self.cog))

    @discord.ui.button(label="📋 查看詳細資訊", style=discord.ButtonStyle.secondary)
    async def details_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_equipment_preview(interaction, self.item_name, self.item_data, self.category)

class PaperDollPreviewView(discord.ui.View):
    """紙娃娃預覽視圖 - 支援多部位混搭"""
    def __init__(self, cog, user_data: dict):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_data = user_data.copy()
        self.original_data = user_data.copy()
        self.preview_items = {}  # 記錄預覽中的裝備

    async def update_preview(self, interaction: discord.Interaction):
        """更新紙娃娃預覽"""
        # 合併用戶原有裝備和預覽裝備
        current_equipment = self.user_data.copy()
        current_equipment.update(self.preview_items)
        
        embed = discord.Embed(
            title="👗 紙娃娃試衣間",
            description=f"正在為 {interaction.user.mention} 預覽裝備搭配效果",
            color=discord.Color.purple()
        )
        
        # 顯示當前裝備
        equipment_info = []
        for category, item_id in current_equipment.items():
            if category in ['hair', 'face', 'skin', 'top', 'bottom', 'shoes']:
                status = "🆕 試穿中" if category in self.preview_items else "✅ 已擁有"
                category_name = self.cog.get_category_name(category)
                equipment_info.append(f"{category_name}: {item_id} {status}")
        
        embed.add_field(name="🎭 當前搭配", value="\n".join(equipment_info), inline=False)
        
        # 生成預覽圖片
        character_image = await self.cog.fetch_character_image(current_equipment)
        if character_image:
            embed.set_image(url="attachment://character.png")
            files = [character_image]
        else:
            files = []
            embed.add_field(name="⚠️ 注意", value="預覽圖片生成失敗，請稍後再試", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self, attachments=files)

    @discord.ui.select(
        placeholder="選擇要試穿的裝備類別",
        options=[
            discord.SelectOption(label="髮型", value="hair", emoji="💇"),
            discord.SelectOption(label="臉型", value="face", emoji="😊"),
            discord.SelectOption(label="膚色", value="skin", emoji="🎨"),
            discord.SelectOption(label="上衣", value="top", emoji="👔"),
            discord.SelectOption(label="下裝", value="bottom", emoji="👖"),
            discord.SelectOption(label="鞋子", value="shoes", emoji="👟"),
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        category = select.values[0]
        
        # 這裡可以展示該類別的可用裝備選項
        # 為了簡化，我們先顯示一個輸入提示
        embed = discord.Embed(
            title=f"🛍️ 選擇{self.cog.get_category_name(category)}",
            description=f"請使用下方按鈕輸入想要試穿的{self.cog.get_category_name(category)}ID",
            color=discord.Color.blue()
        )
        
        view = CategoryItemSelectView(self.cog, self, category)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="💾 保存搭配", style=discord.ButtonStyle.success)
    async def save_outfit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.preview_items:
            await interaction.response.send_message("❌ 沒有試穿任何新裝備！", ephemeral=True)
            return
        
        # 這裡可以實現保存搭配的邏輯
        embed = discord.Embed(
            title="💾 搭配已保存",
            description="你的搭配已保存為預設外觀！",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="🔄 重置", style=discord.ButtonStyle.secondary)
    async def reset_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.preview_items.clear()
        await self.update_preview(interaction)

    @discord.ui.button(label="🛒 購買全套", style=discord.ButtonStyle.primary)
    async def buy_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.preview_items:
            await interaction.response.send_message("❌ 沒有試穿任何新裝備！", ephemeral=True)
            return
        
        # 計算總價格 (這裡需要根據實際的商品數據來計算)
        total_price = len(self.preview_items) * 100  # 簡化計算
        
        embed = discord.Embed(
            title="🛒 購買確認",
            description=f"即將購買 {len(self.preview_items)} 件裝備\n總價格: {total_price} KKcoin",
            color=discord.Color.orange()
        )
        
        view = PurchaseConfirmView(self.cog, self.preview_items, total_price)
        await interaction.response.edit_message(embed=embed, view=view)

class CategoryItemSelectView(discord.ui.View):
    """類別裝備選擇視圖"""
    def __init__(self, cog, parent_view: PaperDollPreviewView, category: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.parent_view = parent_view
        self.category = category

    @discord.ui.button(label="輸入裝備ID", style=discord.ButtonStyle.primary)
    async def input_item_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ItemIDInputModal(self.cog, self.parent_view, self.category)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔙 返回預覽", style=discord.ButtonStyle.secondary)
    async def back_to_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.parent_view.update_preview(interaction)

class ItemIDInputModal(discord.ui.Modal):
    """裝備ID輸入模態框"""
    def __init__(self, cog, parent_view: PaperDollPreviewView, category: str):
        super().__init__(title=f"輸入{cog.get_category_name(category)}ID")
        self.cog = cog
        self.parent_view = parent_view
        self.category = category
        
        self.item_id_input = discord.ui.TextInput(
            label=f"{cog.get_category_name(category)}ID",
            placeholder="請輸入裝備ID (例如: 30000)",
            required=True,
            max_length=10
        )
        self.add_item(self.item_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            item_id = int(self.item_id_input.value)
            self.parent_view.preview_items[self.category] = item_id
            await self.parent_view.update_preview(interaction)
        except ValueError:
            await interaction.response.send_message("❌ 請輸入有效的數字ID！", ephemeral=True)

class PurchaseConfirmView(discord.ui.View):
    """購買確認視圖"""
    def __init__(self, cog, items: dict, total_price: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.items = items
        self.total_price = total_price

    @discord.ui.button(label="✅ 確認購買", style=discord.ButtonStyle.success)
    async def confirm_purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 實現批量購買邏輯
        from shop_commands.merchant.database import get_user_kkcoin, update_user_kkcoin
        
        kkcoin = await get_user_kkcoin(interaction.user.id)
        if kkcoin < self.total_price:
            await interaction.response.send_message(
                f"❌ KKcoin 不足！需要 {self.total_price}，但你只有 {kkcoin}", 
                ephemeral=True
            )
            return
        
        # 扣除金錢並更新裝備
        await update_user_kkcoin(interaction.user.id, -self.total_price)
        
        embed = discord.Embed(
            title="✅ 購買成功！",
            description=f"成功購買 {len(self.items)} 件裝備\n花費: {self.total_price} KKcoin",
            color=discord.Color.green()
        )
        
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.danger)
    async def cancel_purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ 已取消購買",
            description="購買操作已取消",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)
