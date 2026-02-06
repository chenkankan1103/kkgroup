# shop_commands/merchant/paperdoll_merchant.py
"""
紙娃娃商人系統 - 讓玩家購買楓之谷紙娃娃部位
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
from typing import Optional, Dict
from db_adapter import get_user, set_user_field, get_user_field

class PaperdollMerchantSystem:
    """紙娃娃商人系統 - 管理部位商品和購買"""
    
    # 商品目錄 - 可以從 Sheet 中動態加載
    PAPERDOLL_SHOP = {
        "face": {
            20000: {"emoji": "😐", "name": "新秀臉", "price": 100, "gender": "male"},
            20005: {"emoji": "😊", "name": "自信臉", "price": 100, "gender": "male"},
            21731: {"emoji": "🥰", "name": "可愛臉", "price": 150, "gender": "female"},
            21002: {"emoji": "😌", "name": "溫柔臉", "price": 150, "gender": "female"},
        },
        "hair": {
            30000: {"emoji": "👨", "name": "清爽短髮", "price": 150, "gender": "male"},
            30120: {"emoji": "👨", "name": "蓬鬆短髮", "price": 150, "gender": "male"},
            34410: {"emoji": "👩", "name": "齊肩長髮", "price": 200, "gender": "female"},
            35200: {"emoji": "👩", "name": "蓬鬆長髮", "price": 200, "gender": "female"},
        },
        "top": {
            1040010: {"emoji": "👕", "name": "白色T恤", "price": 80, "gender": None},
            1040014: {"emoji": "👔", "name": "黑色上衣", "price": 100, "gender": None},
            1041004: {"emoji": "💼", "name": "正式西裝", "price": 300, "gender": "female"},
            1040002: {"emoji": "👕", "name": "紅色T恤", "price": 80, "gender": None},
        },
        "bottom": {
            1060096: {"emoji": "👖", "name": "標準褲子", "price": 100, "gender": None},
            1061008: {"emoji": "👗", "name": "短裙", "price": 150, "gender": "female"},
            1060000: {"emoji": "👖", "name": "牛仔褲", "price": 120, "gender": None},
        },
        "shoes": {
            1072005: {"emoji": "👟", "name": "黑色運動鞋", "price": 80, "gender": None},
            1072288: {"emoji": "👞", "name": "棕色皮鞋", "price": 100, "gender": None},
            1072009: {"emoji": "👟", "name": "白色運動鞋", "price": 80, "gender": None},
        },
    }
    
    @staticmethod
    def get_user_inventory(user_id: int) -> Dict:
        """獲取用戶的紙娃娃庫存"""
        try:
            inventory_data = get_user_field(user_id, 'paperdoll_inventory', default='{}')
            if isinstance(inventory_data, str):
                return json.loads(inventory_data)
            return inventory_data
        except:
            return {
                "face": [],
                "hair": [],
                "top": [],
                "bottom": [],
                "shoes": []
            }
    
    @staticmethod
    def save_user_inventory(user_id: int, inventory: Dict) -> bool:
        """保存用戶的紙娃娃庫存"""
        try:
            set_user_field(user_id, 'paperdoll_inventory', json.dumps(inventory))
            return True
        except Exception as e:
            print(f"❌ 保存庫存失敗: {e}")
            return False
    
    @staticmethod
    def get_equipped_paperdoll(user_id: int) -> Dict:
        """獲取用戶目前穿著的紙娃娃配置"""
        try:
            user = get_user(user_id)
            if not user:
                return {}
            
            return {
                "face": user.get('face', 20005),
                "hair": user.get('hair', 30120),
                "skin": user.get('skin', 12000),
                "top": user.get('top', 1040014),
                "bottom": user.get('bottom', 1060096),
                "shoes": user.get('shoes', 1072005)
            }
        except:
            return {}
    
    @staticmethod
    async def purchase_paperdoll_item(user_id: int, category: str, item_id: int, price: int) -> tuple[bool, str]:
        """
        購買紙娃娃部位
        
        返回: (成功, 訊息)
        """
        try:
            # 檢查金錢
            user = get_user(user_id)
            if not user:
                return False, "❌ 找不到你的資料！"
            
            current_kkcoin = user.get('kkcoin', 0)
            if current_kkcoin < price:
                return False, f"❌ 金錢不足！需要 {price} KKCoin，目前只有 {current_kkcoin}"
            
            # 檢查是否已擁有
            inventory = PaperdollMerchantSystem.get_user_inventory(user_id)
            if item_id in inventory.get(category, []):
                return False, f"❌ 你已經擁有這件道具了！"
            
            # 扣款
            new_kkcoin = current_kkcoin - price
            set_user_field(user_id, 'kkcoin', new_kkcoin)
            
            # 添加到庫存
            if category not in inventory:
                inventory[category] = []
            
            if item_id not in inventory[category]:
                inventory[category].append(item_id)
            
            PaperdollMerchantSystem.save_user_inventory(user_id, inventory)
            
            return True, f"✅ 購買成功！\n💰 剩餘金錢: {new_kkcoin} KKCoin"
            
        except Exception as e:
            return False, f"❌ 購買失敗: {str(e)}"
    
    @staticmethod
    async def equip_paperdoll_item(user_id: int, category: str, item_id: int) -> tuple[bool, str]:
        """
        穿著紙娃娃部位
        
        返回: (成功, 訊息)
        """
        try:
            inventory = PaperdollMerchantSystem.get_user_inventory(user_id)
            
            # 檢查是否擁有此部位
            if item_id not in inventory.get(category, []):
                return False, f"❌ 你不擁有 {category} 分類中 ID {item_id} 的部位！"
            
            # 更新數據庫
            set_user_field(user_id, category, item_id)
            
            return True, f"✅ 已穿著！"
            
        except Exception as e:
            return False, f"❌ 穿著失敗: {str(e)}"
    
    @staticmethod
    def save_paperdoll_set(user_id: int, set_name: str, items: Dict) -> tuple[bool, str]:
        """
        保存紙娃娃搭配方案
        
        items: 包含 face, hair, skin, top, bottom, shoes 的字典
        """
        try:
            # 獲取已保存的方案
            custom_sets_data = get_user_field(user_id, 'paperdoll_custom_sets', default='{}')
            if isinstance(custom_sets_data, str):
                custom_sets = json.loads(custom_sets_data)
            else:
                custom_sets = custom_sets_data
            
            # 限制最多 5 個方案
            if len(custom_sets) >= 5 and set_name not in custom_sets:
                return False, "❌ 搭配方案已滿（最多 5 個），請刪除舊的方案"
            
            # 保存方案
            custom_sets[set_name] = {
                "items": items,
                "timestamp": int(__import__('time').time())
            }
            
            set_user_field(user_id, 'paperdoll_custom_sets', json.dumps(custom_sets))
            return True, f"✅ 已保存搭配方案：{set_name}"
            
        except Exception as e:
            return False, f"❌ 保存失敗: {str(e)}"


class PaperdollMerchantCog(commands.Cog):
    """紙娃娃商人指令"""
    
    def __init__(self, bot):
        self.bot = bot
        self.merchant = PaperdollMerchantSystem()
    
    @app_commands.command(name="購買紙娃娃", description="瀏覽和購買楓之谷紙娃娃部位")
    async def browse_paperdoll(self, interaction: discord.Interaction):
        """瀏覽紙娃娃商品"""
        try:
            await interaction.response.defer()
            
            # 創建分類選擇器
            from .views import PaperdollShopView
            
            embed = discord.Embed(
                title="🎨 紙娃娃商城",
                description="選擇要瀏覽的裝備分類",
                color=discord.Color.purple()
            )
            
            for category in self.merchant.PAPERDOLL_SHOP.keys():
                category_translations = {
                    "face": "臉型",
                    "hair": "髮型",
                    "top": "上衣",
                    "bottom": "下裝",
                    "shoes": "鞋子"
                }
                embed.add_field(
                    name=f"📦 {category_translations.get(category, category)}",
                    value=f"{len(self.merchant.PAPERDOLL_SHOP[category])} 項商品",
                    inline=True
                )
            
            # 使用現有的 PaperdollShopView（需在 views.py 中實現）
            view = PaperdollShopView(self.bot, interaction.user.id, self.merchant)
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 錯誤: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="我的紙娃娃", description="查看和管理你的紙娃娃部位")
    async def my_paperdoll(self, interaction: discord.Interaction):
        """查看用戶的紙娃娃庫存"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            inventory = self.merchant.get_user_inventory(interaction.user.id)
            equipped = self.merchant.get_equipped_paperdoll(interaction.user.id)
            
            embed = discord.Embed(
                title="👗 我的紙娃娃",
                color=discord.Color.purple()
            )
            
            # 顯示已穿著
            embed.add_field(
                name="👕 目前穿著",
                value=(
                    f"臉型: `{equipped.get('face', '?')}`\n"
                    f"髮型: `{equipped.get('hair', '?')}`\n"
                    f"上衣: `{equipped.get('top', '?')}`\n"
                    f"下裝: `{equipped.get('bottom', '?')}`\n"
                    f"鞋子: `{equipped.get('shoes', '?')}`"
                ),
                inline=False
            )
            
            # 顯示庫存
            total_owned = sum(len(v) for v in inventory.values())
            embed.add_field(
                name="🎒 擁有部位",
                value=f"總計 {total_owned} 件\n"
                      f"臉型: {len(inventory.get('face', []))} 件\n"
                      f"髮型: {len(inventory.get('hair', []))} 件\n"
                      f"上衣: {len(inventory.get('top', []))} 件\n"
                      f"下裝: {len(inventory.get('bottom', []))} 件\n"
                      f"鞋子: {len(inventory.get('shoes', []))} 件",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 錯誤: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PaperdollMerchantCog(bot))
