import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import aiosqlite
import aiohttp
import json
import io
import os
from dotenv import load_dotenv

# 導入按鈕視圖
from shop_commands.merchant.views import (
    PersistentView, ExploreView, RoleShopView, EquipmentShopView, 
    SlotMachineView, PaperDollPreviewView, EquipmentPreviewView, 
    TryOnResultView, ItemDetailView
)
from shop_commands.merchant.database import (
    get_user_kkcoin, update_user_kkcoin, update_user_equipment, get_user_equipment
)
from shop_commands.merchant.config import MUTE_ROLE_ID, MEMBER_ROLE_ID

load_dotenv()

class ButtonInteraction(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        """在 cog 加載時添加持久化視圖"""
        self.bot.add_view(PersistentView(self))
        self.bot.add_view(ExploreView(self))
        self.bot.add_view(RoleShopView(self))
        self.bot.add_view(EquipmentShopView(self))

    @app_commands.command(name="shopping", description="開始神秘的黑市探索")
    async def start_interaction(self, interaction: discord.Interaction):
        """開啟黑市商人界面 - 僅管理員可用"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("只有管理員可以開啟黑市商人。", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="你走進了這個神秘的角落", 
            description="是否要一探究竟？進入後，將會面對更多隱藏的選擇和可能。"
        )
        await interaction.response.send_message(embed=embed, view=PersistentView(self))

    @app_commands.command(name="paperdoll", description="開啟紙娃娃試衣間")
    async def start_paperdoll(self, interaction: discord.Interaction):
        """開啟紙娃娃試衣間"""
        await interaction.response.defer()
        
        # 獲取用戶數據
        user_data = await self.get_user_data(interaction.user.id)
        if not user_data:
            await interaction.followup.send("❌ 找不到你的角色數據！請先註冊。", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="👗 紙娃娃試衣間",
            description=f"歡迎來到試衣間，{interaction.user.mention}！\n在這裡你可以預覽不同裝備的搭配效果。",
            color=discord.Color.purple()
        )
        
        # 生成當前角色預覽
        character_image = await self.fetch_character_image(user_data)
        files = []
        if character_image:
            files.append(character_image)
            embed.set_image(url="attachment://character.png")
        
        view = PaperDollPreviewView(self, user_data)
        await interaction.followup.send(embed=embed, view=view, files=files)

    async def get_user_data(self, user_id: int) -> dict:
        """獲取用戶數據 - 與 UserPanel 中的方法一致"""
        try:
            import sqlite3
            db_path = './user_data.db'
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            query = """
                SELECT user_id, level, xp, kkcoin, title, hp, stamina, 
                inventory, character_config, face, hair, skin, 
                top, bottom, shoes, is_stunned, gender
                FROM users 
                WHERE user_id = ?
            """
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'user_id': row[0],
                    'level': row[1],
                    'xp': row[2],
                    'kkcoin': row[3],
                    'title': row[4],
                    'hp': row[5],
                    'stamina': row[6],
                    'inventory': row[7],
                    'character_config': row[8],
                    'face': row[9] or 20000,
                    'hair': row[10] or 30000,
                    'skin': row[11] or 12000,
                    'top': row[12] or 1040010,
                    'bottom': row[13] or 1060096,
                    'shoes': row[14] or 1072288,
                    'is_stunned': row[15] or 0,
                    'gender': row[16] or 'male'
                }
            return None
        except Exception as e:
            print(f"獲取用戶數據錯誤: {e}")
            return None

    async def fetch_character_image(self, user_data: dict) -> discord.File:
        """使用 MapleStory.io API 獲取角色圖片"""
        try:
            items = [
                {"itemId": 2000, "region": "GMS", "version": "217"},
                {"itemId": user_data.get('skin', 12000), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('face', 20005), "animationName": "default", "region": "GMS", "version": "217"},
                {"itemId": user_data.get('hair', 30120), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('top', 1040014), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('bottom', 1060096), "region": "GMS", "version": "217"},
                {"itemId": user_data.get('shoes', 1072005), "region": "GMS", "version": "217"}
            ]

            # 檢查是否被擊暈，添加眩暈效果道具
            if user_data.get('is_stunned', 0) == 1:
                items.append({"itemId": 1005411, "region": "GMS", "version": "217"})

            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            
            # 如果被擊暈，使用prone姿勢，否則使用stand1
            pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
            url = f"https://maplestory.io/api/character/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            return discord.File(io.BytesIO(image_data), filename='character.png')

        except Exception as e:
            print(f"獲取角色圖片錯誤: {e}")
        return None

    def get_category_name(self, category):
        """獲取分類中文名稱"""
        names = {
            "hair": "髮型", 
            "face": "臉型", 
            "skin": "膚色", 
            "top": "上衣", 
            "bottom": "下裝", 
            "shoes": "鞋子"
        }
        return names.get(category, category)

    async def get_merchant_response(self, user, action: str, interaction: discord.Interaction):
        """處理商人回應"""
        await interaction.response.defer(ephemeral=True)
        kkcoin = await get_user_kkcoin(user.id)
        
        if action == "購買身份":
            embed = discord.Embed(
                title="黑市商人的身份商品", 
                description=f"你目前擁有: {kkcoin} KKcoin\n請選擇以下身份商品", 
                color=discord.Color.gold()
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id, 
                embed=embed, 
                view=RoleShopView(self)
            )
        elif action == "購買裝備":
            embed = discord.Embed(
                title="🛍️ 裝備商店 - 髮型", 
                description=f"你目前擁有: {kkcoin} KKcoin\n選擇類別來瀏覽裝備！", 
                color=discord.Color.blue()
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id, 
                embed=embed, 
                view=EquipmentShopView(self)
            )

    async def handle_role_purchase(self, interaction, role_name, price, role_id, duration=None):
        """處理身份購買"""
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        kkcoin = await get_user_kkcoin(member.id)

        if kkcoin < price:
            await interaction.followup.send(f"你沒有足夠的 KKcoin 購買 {role_name}！", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.followup.send("找不到對應角色，請聯絡管理員。", ephemeral=True)
            return

        await update_user_kkcoin(member.id, -price)
        await member.add_roles(role)
        
        if duration:
            self.bot.loop.create_task(self.remove_role_after_delay(member, role, duration))

        kkcoin_new = await get_user_kkcoin(member.id)
        embed = discord.Embed(
            title="購買成功", 
            description=f"你成功購買了 {role_name}，花費了 {price} KKcoin！\n剩餘：{kkcoin_new} KKcoin"
        )
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)

    async def handle_equipment_purchase(self, interaction, item_name: str, item_data: dict, category: str):
        """處理裝備購買"""
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        kkcoin = await get_user_kkcoin(member.id)
        price = item_data["price"]
        item_id = item_data["id"]

        if kkcoin < price:
            await interaction.followup.send(f"你沒有足夠的 KKcoin 購買 {item_name}！需要 {price} KKcoin", ephemeral=True)
            return

        await update_user_kkcoin(member.id, -price)
        await update_user_equipment(member.id, category, item_id)

        kkcoin_new = await get_user_kkcoin(member.id)
        embed = discord.Embed(
            title="✅ 購買成功",
            description=f"你成功購買了 **{item_name}**！\n💰 花費：{price} KKcoin\n💰 剩餘：{kkcoin_new} KKcoin\n🎭 裝備已自動穿戴！",
            color=discord.Color.green()
        )
        
        if "effects" in item_data:
            effect_messages = []
            for effect in item_data["effects"]:
                effect_msg = await self.apply_equipment_effect(member.id, effect)
                if effect_msg:
                    effect_messages.append(effect_msg)
            
            if effect_messages:
                embed.add_field(name="✨ 特殊效果", value="\n".join(effect_messages), inline=False)

        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)

    async def handle_equipment_preview(self, interaction, item_name: str, item_data: dict, category: str):
        """處理裝備預覽試穿 - 合併預覽和試穿功能"""
        await interaction.response.defer(ephemeral=True)
        
        # 獲取用戶當前裝備數據
        user_data = await self.get_user_data(interaction.user.id)
        if not user_data:
            await interaction.followup.send("❌ 找不到你的角色數據！", ephemeral=True)
            return
        
        # 顯示加載中的訊息
        loading_embed = discord.Embed(
            title="👗 正在生成試穿效果...",
            description=f"請稍等，正在為 {interaction.user.mention} 生成 **{item_name}** 的試穿效果！\n\n⏳ 這將需要幾秒鐘時間...",
            color=discord.Color.orange()
        )
        loading_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.edit_original_response(embed=loading_embed)
        
        try:
            # 創建試穿數據 - 替換指定類別的裝備
            preview_data = user_data.copy()
            preview_data[category] = item_data.get("id", item_data.get("item_id", 0))
            
            # 模擬處理時間
            await asyncio.sleep(2)
            
            # 生成預覽圖片
            character_image = await self.fetch_character_image(preview_data)
            
            # 構建預覽embed
            embed = discord.Embed(
                title=f"👗 商品預覽：{item_name}",
                description=f"看看 {interaction.user.mention} 試穿 **{item_name}** 的效果！\n\n{item_data.get('description', '精美的裝備，值得擁有！')}",
                color=discord.Color.purple()
            )
            
            # 添加商品資訊
            embed.add_field(name="💰 價格", value=f"{item_data['price']} KKcoin", inline=True)
            embed.add_field(name="🏷️ 類別", value=self.get_category_name(category), inline=True)
            embed.add_field(name="🆔 商品編號", value=item_data.get("id", "未知"), inline=True)
            
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
            
            # 檢查購買能力
            user_kkcoin = await get_user_kkcoin(interaction.user.id)
            if user_kkcoin >= item_data['price']:
                embed.add_field(name="💸 購買狀態", value="✅ 你有足夠的 KKcoin 購買此商品", inline=False)
            else:
                needed = item_data['price'] - user_kkcoin
                embed.add_field(name="💸 購買狀態", value=f"❌ 還需要 {needed} KKcoin 才能購買", inline=False)
            
            files = []
            if character_image:
                files.append(character_image)
                embed.set_image(url="attachment://character.png")
                embed.add_field(
                    name="✨ 試穿效果", 
                    value="上圖顯示了試穿此裝備後的效果！", 
                    inline=False
                )
            else:
                # 如果無法生成圖片，顯示用戶頭像
                embed.set_image(url=interaction.user.display_avatar.url)
                embed.add_field(
                    name="💡 提示", 
                    value="暫時無法生成試穿圖片，但你仍可以購買此商品！", 
                    inline=False
                )
            
            # 創建預覽視圖（包含購買和返回按鈕）
            can_afford = user_kkcoin >= item_data['price']
            view = EquipmentPreviewView(self, item_name, item_data, category, can_afford)
            
            # 發送結果
            if files:
                await interaction.followup.send(
                    embed=embed,
                    view=view,
                    files=files,
                    ephemeral=True
                )
            else:
                await interaction.edit_original_response(
                    embed=embed,
                    view=view
                )
                            
        except Exception as e:
            print(f"預覽功能錯誤: {e}")
            
            # 錯誤處理
            error_embed = discord.Embed(
                title="❌ 預覽功能暫時無法使用",
                description="抱歉，預覽功能目前遇到技術問題。\n你仍然可以直接購買此商品。",
                color=discord.Color.red()
            )
            
            # 返回到商品詳情頁面
            kkcoin = await get_user_kkcoin(interaction.user.id)
            can_afford = kkcoin >= item_data['price']
            
            view = ItemDetailView(self, item_name, item_data, category, can_afford)
            
            await interaction.edit_original_response(
                embed=error_embed,
                view=view
            )

    async def apply_equipment_effect(self, user_id: int, effect: dict) -> str:
        """應用裝備特殊效果"""
        effect_type = effect.get("type")
        value = effect.get("value", 0)
        
        if effect_type == "kkcoin_bonus":
            await update_user_kkcoin(user_id, value)
            return f"💰 獲得額外 {value} KKcoin！"
        elif effect_type == "daily_bonus":
            return f"📅 每日將額外獲得 {value} KKcoin！"
        
        return None

    async def remove_role_after_delay(self, member, role, duration):
        """延遲移除角色"""
        await asyncio.sleep(duration)
        try:
            if role in member.roles:
                await member.remove_roles(role)
        except Exception as e:
            print(f"移除角色失敗: {e}")

    async def handle_rob_action(self, interaction):
        """處理搶劫行為"""
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        mute_role = interaction.guild.get_role(MUTE_ROLE_ID)
        member_role = interaction.guild.get_role(MEMBER_ROLE_ID)

        if mute_role in member.roles:
            embed = discord.Embed(title="搶劫失敗", description="你已經被禁閉，無法再次搶劫。")
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)
            return

        await member.remove_roles(member_role)
        await member.add_roles(mute_role)
        
        embed = discord.Embed(title="搶劫失敗", description="你被黑市商人反制，被丟進禁閉室！將在5分鐘後釋放。")
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)

        await asyncio.sleep(300)
        try:
            await member.remove_roles(mute_role)
            await member.add_roles(member_role)
        except Exception as e:
            print(f"解除禁閉失敗：{e}")

    async def handle_bet(self, interaction: discord.Interaction, user_id: int, bet_amount: int):
        """處理賭博邏輯"""
        from shop_commands.merchant.gambling import process_slot_machine_bet
        
        kkcoin = await get_user_kkcoin(user_id)
        if kkcoin < bet_amount:
            await interaction.followup.send(f"你的 KKcoin 不足，無法下注 {bet_amount}！", ephemeral=True)
            return

        result, net_change, msg = await process_slot_machine_bet(bet_amount)
        await update_user_kkcoin(user_id, net_change)
        new_kkcoin = await get_user_kkcoin(user_id)

        result_display = "".join(result)
        embed = discord.Embed(
            title="🎰 拉霸結果", 
            description=f"**{result_display}**\n\n{msg}\n剩餘 KKcoin: {new_kkcoin}", 
            color=discord.Color.green() if net_change > 0 else discord.Color.red()
        )
        
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed)

# 重要：添加 setup 函數
async def setup(bot):
    await bot.add_cog(ButtonInteraction(bot))