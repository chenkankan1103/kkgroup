import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import aiosqlite
import aiohttp
import json
import io
import os
import random
import traceback
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional

from shop_commands.merchant.views import (
    PersistentView, ExploreView, RoleShopView, EquipmentShopView, 
    SlotMachineView, PaperDollPreviewView, EquipmentPreviewView, 
    TryOnResultView, ItemDetailView
)
from shop_commands.merchant.database import (
    get_user_kkcoin, update_user_kkcoin, update_user_equipment, get_user_equipment
)
from shop_commands.merchant.config import MUTE_ROLE_ID, MEMBER_ROLE_ID, VIP_ROLE_ID, RAINBOW_ROLE_ID

class ButtonInteraction(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # GCP資料庫路徑（本地測試用本地檔案，上傳後替換為GCP路徑）
        self.db_path = './user_data.db'  # 本地測試路徑；GCP時替換為遠程路徑，如 'gs://bucket/database.db'
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.categories = self.get_categories()
            print(f"ButtonInteraction initialized with {len(self.categories)} categories")
            # 寫入日誌檔案
            with open('button_interaction_init.log', 'w') as f:
                f.write(f"ButtonInteraction initialized with {len(self.categories)} categories\n")
                f.write(f"Categories: {self.categories[:5]}\n")
        except Exception as e:
            print(f"Error initializing ButtonInteraction: {e}")
            self.conn = None
            self.categories = []  # 設置為空列表，這樣按鈕會顯示錯誤消息
            with open('button_interaction_init.log', 'w') as f:
                f.write(f"Error initializing ButtonInteraction: {e}\n")
        self.price = 100000

    def get_categories(self) -> list:
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT DISTINCT category FROM items")
            categories = [row[0] for row in cursor.fetchall()]
            print(f"Found {len(categories)} categories: {categories[:5]}...")
            return categories
        except Exception as e:
            print(f"Error getting categories: {e}")
            return []

    def get_items_by_category(self, category: str) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, category, region, version, image_url FROM items WHERE category = ?", (category,))
        return [dict(zip(['id', 'name', 'category', 'region', 'version', 'image_url'], row)) for row in cursor.fetchall()]

    async def generate_character_image_url(self, user_data: dict, preview_item: Optional[Dict] = None) -> Optional[str]:
        try:
            items = [
                {"itemId": 2000, "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('skin', 12000), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('face', 20005), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('hair', 30120), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('top', 1040014), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('bottom', 1060096), "region": "TWMS", "version": "256"},
                {"itemId": user_data.get('shoes', 1072005), "region": "TWMS", "version": "256"}
            ]

            if preview_item:
                category_map = {
                    "Hair": "hair", "Face": "face", "Hat": "hat", "Top": "top", "Bottom": "bottom", "Shoes": "shoes"
                }
                part = category_map.get(preview_item['category'])
                if part:
                    for item in items:
                        if item.get('itemId') == user_data.get(part):
                            item['itemId'] = preview_item['id']
                            break

            item_path = ",".join(json.dumps(item, separators=(',', ':')) for item in items)
            api_url = f"https://maplestory.io/api/character/{item_path}/stand1/0?showears=false&resize=2"
            return api_url
        except Exception as e:
            print(f"❌ 生成圖片URL錯誤: {e}")
            return None

    async def get_user_data(self, user_id):
        # 從現有資料庫獲取用戶裝備
        return await get_user_equipment(user_id)

    async def cog_load(self):
        try:
            self.bot.add_view(PersistentView(self))
            self.bot.add_view(ExploreView(self))
            self.bot.add_view(RoleShopView(self))
            self.bot.add_view(EquipmentShopView(self))
        except Exception as e:
            pass

    @app_commands.command(name="shopping", description="開始神秘的黑市探索")
    async def start_interaction(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("只有管理員可以開啟黑市商人。", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="你走進了這個神秘的角落", 
                description="是否要一探究竟？進入後，將會面對更多隱藏的選擇和可能。"
            )
            
            view = PersistentView(self)
            await interaction.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()
            if interaction.response.is_done():
                await interaction.followup.send("❌ 發生錯誤，請稍後再試。", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 發生錯誤，請稍後再試。", ephemeral=True)

    @app_commands.command(name="paperdoll", description="開啟紙娃娃試衣間")
    async def start_paperdoll(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            
            user_data = await self.get_user_data(interaction.user.id)
            if not user_data:
                await interaction.followup.send("❌ 找不到你的角色數據！請先註冊。", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="👗 紙娃娃試衣間",
                description=f"歡迎來到試衣間，{interaction.user.mention}！\n在這裡你可以預覽不同裝備的搭配效果。",
                color=discord.Color.purple()
            )
            
            character_image = await self.fetch_character_image(user_data)
            files = []
            if character_image:
                files.append(character_image)
                embed.set_image(url="attachment://character.png")
            
            view = PaperDollPreviewView(self, user_data)
            await interaction.followup.send(embed=embed, view=view, files=files)
            
        except Exception as e:
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 紙娃娃功能暫時無法使用，請稍後再試。", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 紙娃娃功能暫時無法使用，請稍後再試。", ephemeral=True)
            except:
                pass
    
    async def handle_bet(self, interaction: discord.Interaction, user_id: int, bet_amount: int,
                         history=None, original_message=None):
        """處理拉霸機下注 - 統一更新同一個 Embed（作為 ButtonInteraction 的方法）"""
        try:
            # 初始化歷史記錄
            if history is None or not isinstance(history, list):
                history = []

            # 確保 response 只 defer 一次
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            # 如果沒有 original_message，嘗試從 interaction 取得
            if original_message is None:
                if hasattr(interaction, 'message') and interaction.message:
                    original_message = interaction.message

            # 檢查用戶 KKcoin
            try:
                kkcoin = await get_user_kkcoin(user_id)
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send("❌ 無法獲取你的 KKcoin 餘額，請稍後再試。", ephemeral=True)
                return original_message

            if kkcoin < bet_amount:
                embed = discord.Embed(
                    title="🎰 拉霸機遊戲",
                    description=f"❌ **餘額不足！**\n\n💰 當前擁有：{kkcoin} KKcoin\n💸 需要：{bet_amount} KKcoin",
                    color=discord.Color.red()
                )

                if len(history) > 0:
                    history_text = []
                    for h in reversed(history):
                        history_text.append(
                            f"{h['emoji']} `[ {h['result']} ]` - 下注 {h['bet']} → {h['change_text']}"
                        )
                    embed.add_field(
                        name=f"📜 歷史記錄（最近 {len(history)} 場）",
                        value="\n".join(history_text),
                        inline=False
                    )

                view = SlotMachineView(self, history=history.copy(), original_message=original_message)

                if original_message:
                    await original_message.edit(embed=embed, view=view)
                    return original_message
                else:
                    new_msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                    return new_msg

            # 處理賭博邏輯
            try:
                from shop_commands.merchant.gambling import process_slot_machine_bet
                result, net_change, msg = await process_slot_machine_bet(bet_amount)
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 拉霸機運算失敗：{str(e)[:100]}", ephemeral=True)
                return original_message

            # 更新用戶 KKcoin
            try:
                await update_user_kkcoin(user_id, net_change)
                new_kkcoin = await get_user_kkcoin(user_id)
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send("❌ 無法更新你的 KKcoin，請聯絡管理員。", ephemeral=True)
                return original_message

            # 記錄本次結果到歷史
            result_display = " ".join(result) if isinstance(result, list) else str(result)

            if net_change > 0:
                result_emoji = "✅"
                change_text = f"+{net_change}"
            elif net_change < 0:
                result_emoji = "❌"
                change_text = f"{net_change}"
            else:
                result_emoji = "⚪"
                change_text = "±0"

            history.append({
                'result': result_display,
                'bet': bet_amount,
                'change': net_change,
                'change_text': change_text,
                'emoji': result_emoji,
                'msg': msg
            })

            if len(history) > 5:
                history = history[-5:]

            total_bet = sum(h['bet'] for h in history)
            total_change = sum(h['change'] for h in history)
            win_count = sum(1 for h in history if h['change'] > 0)
            lose_count = sum(1 for h in history if h['change'] < 0)
            draw_count = sum(1 for h in history if h['change'] == 0)

            if net_change > 0:
                color = discord.Color.green()
            elif net_change < 0:
                color = discord.Color.red()
            else:
                color = discord.Color.gold()

            embed = discord.Embed(
                title="🎰 拉霸機遊戲",
                description=f"**最新結果：[ {result_display} ]**\n{msg}",
                color=color
            )

            if len(history) > 0:
                history_text = []
                for i, h in enumerate(reversed(history), 1):
                    history_text.append(
                        f"{h['emoji']} `[ {h['result']} ]` - 下注 {h['bet']} → {h['change_text']}"
                    )
                embed.add_field(
                    name=f"📜 歷史記錄（最近 {len(history)} 場）",
                    value="\n".join(history_text),
                    inline=False
                )

            embed.add_field(
                name="📊 本輪統計",
                value=(
                    f"🎮 總場數：{len(history)} 場\n"
                    f"✅ 勝場：{win_count} | ❌ 敗場：{lose_count} | ⚪ 平手：{draw_count}\n"
                    f"💸 總下注：{total_bet} KKcoin\n"
                    f"💰 淨損益：{'+' if total_change >= 0 else ''}{total_change} KKcoin"
                ),
                inline=False
            )

            embed.add_field(
                name="💼 當前狀態",
                value=f"💰 餘額：{new_kkcoin} KKcoin",
                inline=False
            )

            embed.set_footer(text="選擇下注金額繼續遊戲，或點擊「結束遊戲」查看最終結果")

            try:
                if original_message:
                    try:
                        view = SlotMachineView(self, history=history.copy(), original_message=original_message)
                        await original_message.edit(embed=embed, view=view)
                        return original_message
                    except discord.NotFound:
                        view = SlotMachineView(self, history=history.copy(), original_message=None)
                        new_msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                        view.original_message = new_msg
                        return new_msg
                    except discord.HTTPException:
                        traceback.print_exc()
                        view = SlotMachineView(self, history=history.copy(), original_message=None)
                        new_msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                        view.original_message = new_msg
                        return new_msg
                else:
                    view = SlotMachineView(self, history=history.copy(), original_message=None)
                    new_msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                    view.original_message = new_msg
                    return new_msg
            except Exception:
                traceback.print_exc()
                if original_message:
                    try:
                        await original_message.edit(embed=embed)
                        return original_message
                    except:
                        new_msg = await interaction.followup.send(embed=embed, ephemeral=True)
                        return new_msg
                else:
                    new_msg = await interaction.followup.send(embed=embed, ephemeral=True)
                    return new_msg

        except Exception as e:
            traceback.print_exc()
            error_msg = f"❌ 拉霸機處理失敗：{str(e)[:100]}"
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
            except:
                pass
            return original_message

    async def get_user_data(self, user_id: int) -> dict:
        """獲取用戶完整資料"""
        try:
            # 匯入 db_adapter 的功能
            import sys
            import os
            sys.path.insert(0, os.path.dirname(__file__) + '/..')
            from db_adapter import get_user
            
            user = get_user(user_id)
            
            if not user:
                return None
            
            # 返回用戶資料（已自動適應任何欄位）
            return user
        except Exception as e:
            traceback.print_exc()
            return None

    async def fetch_character_image(self, user_data: dict) -> discord.File:
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

            if user_data.get('is_stunned', 0) == 1:
                items.append({"itemId": 1005411, "region": "GMS", "version": "217"})

            item_path = ",".join([json.dumps(item, separators=(',', ':')) for item in items])
            
            pose = "prone" if user_data.get('is_stunned', 0) == 1 else "stand1"
            url = f"https://maplestory.io/api/character/{item_path}/{pose}/0?showears=false&resize=2&flipX=true"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        if len(image_data) > 100:
                            return discord.File(io.BytesIO(image_data), filename='character.png')

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            traceback.print_exc()
        return None

    def get_category_name(self, category):
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
        try:
            if interaction.response.is_done():
                return
                
            await interaction.response.defer(ephemeral=True)
            kkcoin = await get_user_kkcoin(user.id)
            
            if action == "購買身份":
                embed = discord.Embed(
                    title="黑市商人的身份商品", 
                    description=f"你目前擁有: {kkcoin} KKcoin\n請選擇以下身份商品", 
                    color=discord.Color.gold()
                )
                view = RoleShopView(self)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                
        except Exception as e:
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 處理請求時發生錯誤。", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 處理請求時發生錯誤。", ephemeral=True)
            except:
                pass

    async def handle_role_purchase(self, interaction, role_name, price, role_id, duration=None):
        try:
            if interaction.response.is_done():
                return
                
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
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 購買處理失敗。", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 購買處理失敗。", ephemeral=True)
            except:
                pass

    async def handle_equipment_purchase(self, interaction, item_name: str, item_data: dict, category: str):
        try:
            if interaction.response.is_done():
                return
                
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

            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 購買處理失敗。", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 購買處理失敗。", ephemeral=True)
            except:
                pass

    async def handle_equipment_preview(self, interaction, item_name: str, item_data: dict, category: str):
        try:
            if interaction.response.is_done():
                return
                
            await interaction.response.defer(ephemeral=True)
            
            user_data = await self.get_user_data(interaction.user.id)
            if not user_data:
                await interaction.followup.send("❌ 找不到你的角色數據！", ephemeral=True)
                return
            
            loading_embed = discord.Embed(
                title="👗 正在生成試穿效果...",
                description=f"請稍等，正在為 {interaction.user.mention} 生成 **{item_name}** 的試穿效果！\n\n⏳ 這將需要幾秒鐘時間...",
                color=discord.Color.orange()
            )
            loading_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            await interaction.followup.send(embed=loading_embed, ephemeral=True)
            
            preview_data = user_data.copy()
            preview_data[category] = item_data.get("id", item_data.get("item_id", 0))
            
            await asyncio.sleep(2)
            
            character_image = await self.fetch_character_image(preview_data)
            
            embed = discord.Embed(
                title=f"👗 商品預覽：{item_name}",
                description=f"看看 {interaction.user.mention} 試穿 **{item_name}** 的效果！\n\n{item_data.get('description', '精美的裝備，值得擁有！')}",
                color=discord.Color.purple()
            )
            
            embed.add_field(name="💰 價格", value=f"{item_data['price']} KKcoin", inline=True)
            embed.add_field(name="🏷️ 類別", value=self.get_category_name(category), inline=True)
            embed.add_field(name="🆔 商品編號", value=item_data.get("id", "未知"), inline=True)
            
            if "effects" in item_data:
                effects_text = []
                for effect in item_data["effects"]:
                    if effect["type"] == "kkcoin_bonus":
                        effects_text.append(f"💰 購買獲得額外 {effect['value']} KKcoin")
                    elif effect["type"] == "daily_bonus":
                        effects_text.append(f"📅 每日額外獲得 {effect['value']} KKcoin")
                
                if effects_text:
                    embed.add_field(name="✨ 特殊效果", value="\n".join(effects_text), inline=False)
            
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
                embed.set_image(url=interaction.user.display_avatar.url)
                embed.add_field(
                    name="💡 提示", 
                    value="暫時無法生成試穿圖片，但你仍可以購買此商品！", 
                    inline=False
                )
            
            can_afford = user_kkcoin >= item_data['price']
            view = EquipmentPreviewView(self, item_name, item_data, category, can_afford)
            
            await interaction.edit_original_response(
                embed=embed,
                view=view,
                attachments=files if files else []
            )
                            
        except Exception as e:
            traceback.print_exc()
            
            error_embed = discord.Embed(
                title="❌ 預覽功能暫時無法使用",
                description="抱歉，預覽功能目前遇到技術問題。\n你仍然可以直接購買此商品。",
                color=discord.Color.red()
            )
            
            try:
                kkcoin = await get_user_kkcoin(interaction.user.id)
                can_afford = kkcoin >= item_data['price']
                
                view = ItemDetailView(self, item_name, item_data, category, can_afford)
                
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=error_embed, view=view, ephemeral=True)
                else:
                    await interaction.edit_original_response(embed=error_embed, view=view)
            except:
                pass

    async def apply_equipment_effect(self, user_id: int, effect: dict) -> str:
        try:
            effect_type = effect.get("type")
            value = effect.get("value", 0)
            
            if effect_type == "kkcoin_bonus":
                await update_user_kkcoin(user_id, value)
                return f"💰 獲得額外 {value} KKcoin！"
            elif effect_type == "daily_bonus":
                return f"📅 每日將額外獲得 {value} KKcoin！"
            
        except Exception as e:
            pass
        
        return None

    async def remove_role_after_delay(self, member, role, duration):
        try:
            await asyncio.sleep(duration)
            if role in member.roles:
                await member.remove_roles(role)
        except Exception as e:
            pass

    async def handle_rob_action(self, interaction):
        try:
            if interaction.response.is_done():
                return
                
            await interaction.response.defer(ephemeral=True)
            member = interaction.user
            mute_role = interaction.guild.get_role(MUTE_ROLE_ID)
            member_role = interaction.guild.get_role(MEMBER_ROLE_ID)

            if not mute_role:
                await interaction.followup.send("❌ 找不到禁閉角色，請聯絡管理員設定。", ephemeral=True)
                return
                
            if not member_role:
                await interaction.followup.send("❌ 找不到會員角色，請聯絡管理員設定。", ephemeral=True)
                return

            if mute_role in member.roles:
                embed = discord.Embed(
                    title="🚫 搶劫失敗", 
                    description="你已經被禁閉，無法再次搶劫。",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            success_rate = 30
            is_success = random.randint(1, 100) <= success_rate
            
            if is_success:
                stolen_amount = random.randint(100, 200)
                await update_user_kkcoin(member.id, stolen_amount)
                new_kkcoin = await get_user_kkcoin(member.id)
                
                embed = discord.Embed(
                    title="💰 搶劫成功！",
                    description=f"你成功從黑市商人那裡搶到了 **{stolen_amount} KKcoin**！\n\n"
                               f"黑市商人驚慌失措地看著你逃跑...\n"
                               f"💰 目前擁有：{new_kkcoin} KKcoin",
                    color=discord.Color.green()
                )
            else:
                try:
                    if member_role in member.roles:
                        await member.remove_roles(member_role, reason="搶劫失敗被禁閉")
                    await member.add_roles(mute_role, reason="搶劫失敗被禁閉")
                    
                    embed = discord.Embed(
                        title="🚫 搶劫失敗！",
                        description="你被黑市商人反制，被丟進禁閉室！\n\n"
                                   "黑市商人冷笑道：「想搶劫我？太嫩了！」\n"
                                   "⏰ 將在5分鐘後釋放你。",
                        color=discord.Color.red()
                    )
                    
                    self.bot.loop.create_task(self.release_from_mute(member, mute_role, member_role))
                    
                except discord.Forbidden:
                    embed = discord.Embed(
                        title="❌ 權限不足",
                        description="機器人沒有足夠權限來管理角色，請聯絡管理員檢查權限設定。",
                        color=discord.Color.red()
                    )
                except Exception as e:
                    embed = discord.Embed(
                        title="❌ 系統錯誤",
                        description="處理搶劫時發生錯誤，請稍後再試。",
                        color=discord.Color.red()
                    )

            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 搶劫處理失敗。", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 搶劫處理失敗。", ephemeral=True)
            except:
                pass

    async def release_from_mute(self, member, mute_role, member_role):
        try:
            await asyncio.sleep(300)
            
            guild = member.guild
            member = guild.get_member(member.id)
            
            if not member:
                return
                
            mute_role = guild.get_role(MUTE_ROLE_ID)
            member_role = guild.get_role(MEMBER_ROLE_ID)
            
            if not mute_role or not member_role:
                return
            
            if mute_role in member.roles:
                await member.remove_roles(mute_role, reason="禁閉期滿自動釋放")
                
                if member_role not in member.roles:
                    await member.add_roles(member_role, reason="禁閉期滿恢復會員身份")
                    
        except discord.Forbidden:
            pass
        except Exception as e:
            pass


# ============ 紙娃娃系統View類 ============
class DressingRoomView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id
        
        # 類別中英對照表
        self.category_names = {
            "Face": "臉型",
            "Hair": "髮型", 
            "Hat": "帽子",
            "Face Accessory": "臉部飾品",
            "Eye Decoration": "眼睛飾品",
            "Top": "上衣",
            "Bottom": "下衣",
            "Shoes": "鞋子",
            "Gloves": "手套",
            "Cape": "披風",
            "Shield": "盾牌",
            "Weapon": "武器",
            "Earrings": "耳環",
            "Necklace": "項鍊",
            "Ring": "戒指",
            "Overall": "套裝",
            "Pet": "寵物",
            "Mount": "坐騎",
            "Android": "機器人",
            "Mechanical Heart": "機械之心",
            "Badge": "徽章",
            "Medal": "勳章",
            "Shoulder": "肩膀裝飾",
            "Pocket Item": "口袋物品",
            "Bits": "晶片"
        }
        
        # 創建下拉選單
        self.create_select_menu()

    def create_select_menu(self):
        options = []
        for category in self.cog.categories:
            chinese_name = self.category_names.get(category, category)
            options.append(discord.SelectOption(
                label=f"{chinese_name}",
                value=category,
                description=f"選擇 {chinese_name} 進行更換"
            ))
        
        select = discord.ui.Select(
            placeholder="👗 選擇要更換的部位...",
            options=options,
            custom_id="category_select"
        )
        select.callback = self.category_selected
        self.add_item(select)
        
        # 返回按鈕
        back_button = discord.ui.Button(label="返回商店", style=discord.ButtonStyle.secondary, emoji="⬅️")
        back_button.callback = self.back_to_shop
        self.add_item(back_button)

    async def category_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的衣帽間！", ephemeral=True)
            return

        selected_category = interaction.data['values'][0]
        chinese_name = self.category_names.get(selected_category, selected_category)
        
        items = self.cog.get_items_by_category(selected_category)
        if not items:
            await interaction.response.send_message(f"❌ {chinese_name} 分類目前沒有物品。", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"✂️ 編輯 {chinese_name}",
            description=f"選擇 {chinese_name} 物品進行預覽或購買。",
            color=0x87CEEB
        )

        view = EditView(self.cog, self.user_id, selected_category, items, page=0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def back_to_shop(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的頁面！", ephemeral=True)
            return
        await interaction.response.defer()
        # 返回商人主頁（由商人代碼處理）


class EditView(discord.ui.View):
    def __init__(self, cog, user_id, category, items, page=0):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id
        self.category = category
        self.items = items
        self.page = page
        self.items_per_page = 5
        
        # 類別中英對照表（與DressingRoomView保持一致）
        self.category_names = {
            "Face": "臉型",
            "Hair": "髮型", 
            "Hat": "帽子",
            "Face Accessory": "臉部飾品",
            "Eye Decoration": "眼睛飾品",
            "Top": "上衣",
            "Bottom": "下衣",
            "Shoes": "鞋子",
            "Gloves": "手套",
            "Cape": "披風",
            "Shield": "盾牌",
            "Weapon": "武器",
            "Earrings": "耳環",
            "Necklace": "項鍊",
            "Ring": "戒指",
            "Overall": "套裝",
            "Pet": "寵物",
            "Mount": "坐騎",
            "Android": "機器人",
            "Mechanical Heart": "機械之心",
            "Badge": "徽章",
            "Medal": "勳章",
            "Shoulder": "肩膀裝飾",
            "Pocket Item": "口袋物品",
            "Bits": "晶片"
        }
        
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        page_items = self.items[start:end]

        for item in page_items:
            button = discord.ui.Button(label=f"{item['name'][:20]}", style=discord.ButtonStyle.secondary)
            button.callback = self.create_item_callback(item)
            self.add_item(button)

        if self.page > 0:
            prev_button = discord.ui.Button(label="上一頁", style=discord.ButtonStyle.secondary, emoji="⬅️")
            prev_button.callback = self.prev_page
            self.add_item(prev_button)

        if end < len(self.items):
            next_button = discord.ui.Button(label="下一頁", style=discord.ButtonStyle.secondary, emoji="➡️")
            next_button.callback = self.next_page
            self.add_item(next_button)

        back_button = discord.ui.Button(label="返回", style=discord.ButtonStyle.secondary, emoji="⬅️")
        back_button.callback = self.back_to_dressing_room
        self.add_item(back_button)

    def create_item_callback(self, item):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ 這不是你的編輯頁！", ephemeral=True)
                return

            user_data = await self.cog.get_user_data(self.user_id)
            image_url = await self.cog.generate_character_image_url(user_data, item)

            embed = discord.Embed(
                title=f"👀 預覽 {item['name']}",
                description=f"價格：{self.cog.price} KK幣",
                color=0x32CD32
            )
            if image_url:
                embed.set_image(url=image_url)

            view = PreviewView(self.cog, self.user_id, item)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return callback

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    async def back_to_dressing_room(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的頁面！", ephemeral=True)
            return
        embed = discord.Embed(title="👗 衣帽間", description="選擇要更改的部位。", color=0xFF69B4)
        view = DressingRoomView(self.cog, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)


class PreviewView(discord.ui.View):
    def __init__(self, cog, user_id, selected_item):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id
        self.selected_item = selected_item

    @discord.ui.button(label="購買", style=discord.ButtonStyle.danger, emoji="💰")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的預覽！", ephemeral=True)
            return

        user_data = await self.cog.get_user_data(self.user_id)
        if not user_data or user_data.get('kkcoin', 0) < self.cog.price:
            await interaction.response.send_message("❌ KK幣不足！", ephemeral=True)
            return

        image_url = await self.cog.generate_character_image_url(user_data, self.selected_item)

        embed = discord.Embed(
            title="⚠️ 確認購買",
            description=f"確定購買 **{self.selected_item['name']}**？\n價格：{self.cog.price} KK幣\n本園區不提供退貨機制。",
            color=0xFF4500
        )
        if image_url:
            embed.set_image(url=image_url)
        view = ConfirmView(self.cog, self.user_id, self.selected_item)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="返回", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的頁面！", ephemeral=True)
            return
        
        # 獲取中文類別名稱
        category_names = {
            "Face": "臉型", "Hair": "髮型", "Hat": "帽子", "Face Accessory": "臉部飾品",
            "Eye Decoration": "眼睛飾品", "Top": "上衣", "Bottom": "下衣", "Shoes": "鞋子",
            "Gloves": "手套", "Cape": "披風", "Shield": "盾牌", "Weapon": "武器",
            "Earrings": "耳環", "Necklace": "項鍊", "Ring": "戒指", "Overall": "套裝",
            "Pet": "寵物", "Mount": "坐騎", "Android": "機器人", "Mechanical Heart": "機械之心",
            "Badge": "徽章", "Medal": "勳章", "Shoulder": "肩膀裝飾", "Pocket Item": "口袋物品", "Bits": "晶片"
        }
        chinese_name = category_names.get(self.selected_item['category'], self.selected_item['category'])
        
        embed = discord.Embed(title=f"✂️ 編輯 {chinese_name}", description=f"選擇 {chinese_name} 物品進行預覽或購買。", color=0x87CEEB)
        items = self.cog.get_items_by_category(self.selected_item['category'])
        view = EditView(self.cog, self.user_id, self.selected_item['category'], items)
        await interaction.response.edit_message(embed=embed, view=view)


class ConfirmView(discord.ui.View):
    def __init__(self, cog, user_id, selected_item):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.selected_item = selected_item

    @discord.ui.button(label="是", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的確認頁！", ephemeral=True)
            return

        try:
            current_kkcoin = await get_user_kkcoin(self.user_id)
            await update_user_kkcoin(self.user_id, current_kkcoin - self.cog.price)
            category_map = {"Hair": "hair", "Face": "face", "Hat": "hat", "Top": "top", "Bottom": "bottom", "Shoes": "shoes"}
            part = category_map.get(self.selected_item['category'])
            if part:
                await update_user_equipment(self.user_id, part, self.selected_item['id'])

            await interaction.response.send_message(f"✅ 購買成功！已裝備 {self.selected_item['name']}。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 購買失敗: {str(e)[:100]}", ephemeral=True)

    @discord.ui.button(label="否", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的頁面！", ephemeral=True)
            return
        await interaction.response.send_message("❌ 取消購買。", ephemeral=True)


async def setup(bot):
    try:
        await bot.add_cog(ButtonInteraction(bot))
    except Exception as e:
        traceback.print_exc()
