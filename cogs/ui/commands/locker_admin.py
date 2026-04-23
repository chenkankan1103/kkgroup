"""
置物櫃管理員命令 - 檢查和初始化會員置物櫃

功能：
1. /locker_check <user> - 檢查特定會員是否有置物櫃
2. /locker_init <user> - 為會員初始化置物櫃
3. /locker_check_all - 檢查所有會員的置物櫃狀況
4. /locker_fix_missing - 批量為沒有置物櫃的會員初始化
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db_adapter import get_all_users, set_user_field, get_user
import json


class LockerAdminCog(commands.Cog):
    """置物櫃管理員命令"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="locker_check", description="檢查特定會員是否有置物櫃")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="要檢查的會員")
    async def locker_check(self, interaction: discord.Interaction, user: discord.User):
        """檢查會員是否有置物櫃（是否有植物記錄）"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_data = get_user(user.id)
            
            if not user_data:
                await interaction.followup.send(
                    f"❌ 找不到會員 {user.mention} 的資料",
                    ephemeral=True
                )
                return
            
            # 檢查置物櫃字段
            plants_json = user_data.get('cannabis_plants', '[]')
            inventory_json = user_data.get('cannabis_inventory', '{}')
            
            # 解析 JSON
            try:
                if isinstance(plants_json, str):
                    plants = json.loads(plants_json) if plants_json else []
                else:
                    plants = plants_json if isinstance(plants_json, list) else []
                
                if isinstance(inventory_json, str):
                    inventory = json.loads(inventory_json) if inventory_json else {}
                else:
                    inventory = inventory_json if isinstance(inventory_json, dict) else {}
            except json.JSONDecodeError:
                plants = []
                inventory = {}
            
            # 檢查結果
            has_plants = len(plants) > 0
            has_inventory = len(inventory) > 0
            has_locker = has_plants or has_inventory
            
            embed = discord.Embed(
                title=f"📦 {user.display_name} 的置物櫃狀況",
                color=discord.Color.green() if has_locker else discord.Color.red()
            )
            
            embed.add_field(
                name="置物櫃狀態",
                value=f"✅ 已初始化" if has_locker else "❌ 未初始化",
                inline=False
            )
            
            embed.add_field(
                name="🌱 植物",
                value=f"{len(plants)} 株" if has_plants else "無植物",
                inline=True
            )
            
            embed.add_field(
                name="📦 庫存",
                value=f"{len(inventory)} 種類別" if has_inventory else "無庫存",
                inline=True
            )
            
            if has_plants:
                plant_info = []
                for plant in plants[:5]:  # 最多顯示5株
                    plant_info.append(
                        f"• {plant.get('seed_type', '未知')} "
                        f"({plant.get('status', '未知')})"
                    )
                if len(plants) > 5:
                    plant_info.append(f"... 還有 {len(plants) - 5} 株")
                embed.add_field(
                    name="植物清單",
                    value="\n".join(plant_info),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ 檢查失敗: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="locker_init", description="為會員初始化置物櫃")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="要初始化的會員")
    async def locker_init(self, interaction: discord.Interaction, user: discord.User):
        """為沒有置物櫃的會員初始化"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_data = get_user(user.id)
            
            if not user_data:
                await interaction.followup.send(
                    f"❌ 找不到會員 {user.mention} 的資料\n"
                    f"提示：會員可能尚未註冊系統",
                    ephemeral=True
                )
                return
            
            # 檢查是否已有置物櫃
            plants_json = user_data.get('cannabis_plants', '[]')
            inventory_json = user_data.get('cannabis_inventory', '{}')
            
            try:
                if isinstance(plants_json, str):
                    plants = json.loads(plants_json) if plants_json else []
                else:
                    plants = plants_json if isinstance(plants_json, list) else []
                
                if isinstance(inventory_json, str):
                    inventory = json.loads(inventory_json) if inventory_json else {}
                else:
                    inventory = inventory_json if isinstance(inventory_json, dict) else {}
            except json.JSONDecodeError:
                plants = []
                inventory = {}
            
            has_locker = len(plants) > 0 or len(inventory) > 0
            
            if has_locker:
                await interaction.followup.send(
                    f"⚠️ {user.mention} 已經有置物櫃了\n"
                    f"• 植物: {len(plants)} 株\n"
                    f"• 庫存: {len(inventory)} 種",
                    ephemeral=True
                )
                return
            
            # 初始化置物櫃
            success = True
            success &= set_user_field(user.id, 'cannabis_plants', '[]')
            success &= set_user_field(user.id, 'cannabis_inventory', '{}')
            
            if success:
                await interaction.followup.send(
                    f"✅ 已為 {user.mention} 初始化置物櫃\n"
                    f"現在可以開始種植和管理物品了！",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ 初始化失敗，請檢查資料庫連接",
                    ephemeral=True
                )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ 初始化失敗: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="locker_check_all", description="檢查所有會員的置物櫃狀況（統計）")
    @app_commands.checks.has_permissions(administrator=True)
    async def locker_check_all(self, interaction: discord.Interaction):
        """統計所有會員的置物櫃初始化狀況"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            all_users = get_all_users()
            
            has_locker_count = 0
            no_locker_count = 0
            no_locker_users = []
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                plants_json = user_data.get('cannabis_plants', '[]')
                inventory_json = user_data.get('cannabis_inventory', '{}')
                
                try:
                    if isinstance(plants_json, str):
                        plants = json.loads(plants_json) if plants_json else []
                    else:
                        plants = plants_json if isinstance(plants_json, list) else []
                    
                    if isinstance(inventory_json, str):
                        inventory = json.loads(inventory_json) if inventory_json else {}
                    else:
                        inventory = inventory_json if isinstance(inventory_json, dict) else {}
                except json.JSONDecodeError:
                    plants = []
                    inventory = {}
                
                has_locker = len(plants) > 0 or len(inventory) > 0
                
                if has_locker:
                    has_locker_count += 1
                else:
                    no_locker_count += 1
                    no_locker_users.append(user_id)
            
            # 生成報告
            embed = discord.Embed(
                title="📦 置物櫃統計報告",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="✅ 已初始化",
                value=f"{has_locker_count} 個會員",
                inline=True
            )
            
            embed.add_field(
                name="❌ 未初始化",
                value=f"{no_locker_count} 個會員",
                inline=True
            )
            
            if no_locker_count > 0:
                embed.add_field(
                    name="⚠️ 缺少置物櫃的會員 ID",
                    value=", ".join(map(str, no_locker_users[:20])) + 
                          (f"\n... 及其他 {no_locker_count - 20} 個" if no_locker_count > 20 else ""),
                    inline=False
                )
            
            embed.set_footer(text=f"總會員數: {len(all_users)}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ 統計失敗: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="locker_fix_missing", description="批量初始化所有缺少置物櫃的會員")
    @app_commands.checks.has_permissions(administrator=True)
    async def locker_fix_missing(self, interaction: discord.Interaction):
        """批量為所有沒有置物櫃的會員初始化"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            all_users = get_all_users()
            
            fixed_count = 0
            already_have_count = 0
            failed_count = 0
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                plants_json = user_data.get('cannabis_plants', '[]')
                inventory_json = user_data.get('cannabis_inventory', '{}')
                
                try:
                    if isinstance(plants_json, str):
                        plants = json.loads(plants_json) if plants_json else []
                    else:
                        plants = plants_json if isinstance(plants_json, list) else []
                    
                    if isinstance(inventory_json, str):
                        inventory = json.loads(inventory_json) if inventory_json else {}
                    else:
                        inventory = inventory_json if isinstance(inventory_json, dict) else {}
                except json.JSONDecodeError:
                    plants = []
                    inventory = {}
                
                has_locker = len(plants) > 0 or len(inventory) > 0
                
                if has_locker:
                    already_have_count += 1
                    continue
                
                # 初始化這個會員
                try:
                    success = True
                    success &= set_user_field(user_id, 'cannabis_plants', '[]')
                    success &= set_user_field(user_id, 'cannabis_inventory', '{}')
                    
                    if success:
                        fixed_count += 1
                    else:
                        failed_count += 1
                except Exception:
                    failed_count += 1
            
            # 生成報告
            embed = discord.Embed(
                title="✅ 置物櫃批量初始化完成",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="🔧 已修復",
                value=f"{fixed_count} 個會員",
                inline=True
            )
            
            embed.add_field(
                name="➡️ 已有置物櫃",
                value=f"{already_have_count} 個會員",
                inline=True
            )
            
            if failed_count > 0:
                embed.add_field(
                    name="❌ 修復失敗",
                    value=f"{failed_count} 個會員",
                    inline=True
                )
            
            embed.set_footer(text=f"總處理: {fixed_count + already_have_count + failed_count} 個會員")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ 批量初始化失敗: {e}",
                ephemeral=True
            )


async def setup(bot):
    """加載 Cog"""
    await bot.add_cog(LockerAdminCog(bot))
