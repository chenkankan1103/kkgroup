import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from typing import Optional

class AvatarReset(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'

    def get_user_data(self, user_id: int) -> Optional[dict]:
        """獲取使用者資料"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, row))
                conn.close()
                return result
            
            conn.close()
            return None
        except Exception as e:
            print(f"獲取使用者資料錯誤: {e}")
            return None

    def update_user_avatar(self, user_id: int, avatar_data: dict) -> bool:
        """更新單一使用者的紙娃娃資料"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET face = ?, hair = ?, skin = ?, top = ?, bottom = ?, shoes = ?
                WHERE user_id = ?
            ''', (
                avatar_data['face'],
                avatar_data['hair'],
                avatar_data['skin'],
                avatar_data['top'],
                avatar_data['bottom'],
                avatar_data['shoes'],
                user_id
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"更新使用者外觀錯誤: {e}")
            return False

    def reset_all_avatars_by_gender(self) -> dict:
        """重製所有使用者的紙娃娃為預設外觀"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 獲取所有使用者資料
            cursor.execute("SELECT user_id, gender FROM users")
            users = cursor.fetchall()
            
            reset_count = {'male': 0, 'female': 0, 'error': 0}
            
            for user_id, gender in users:
                if gender == 'female':
                    # 女性預設外觀
                    avatar_data = {
                        'face': 21731,
                        'hair': 34410,
                        'skin': 12000,
                        'top': 1041004,
                        'bottom': 1061008,
                        'shoes': 1072005
                    }
                    reset_count['female'] += 1
                else:
                    # 男性預設外觀（包含未設定性別的使用者）
                    avatar_data = {
                        'face': 20005,
                        'hair': 30120,
                        'skin': 12000,
                        'top': 1040014,
                        'bottom': 1060096,
                        'shoes': 1072005
                    }
                    reset_count['male'] += 1
                
                # 更新該使用者的外觀
                cursor.execute('''
                    UPDATE users 
                    SET face = ?, hair = ?, skin = ?, top = ?, bottom = ?, shoes = ?
                    WHERE user_id = ?
                ''', (
                    avatar_data['face'],
                    avatar_data['hair'],
                    avatar_data['skin'],
                    avatar_data['top'],
                    avatar_data['bottom'],
                    avatar_data['shoes'],
                    user_id
                ))
            
            conn.commit()
            conn.close()
            
            return reset_count
            
        except Exception as e:
            print(f"批量重製紙娃娃錯誤: {e}")
            return {'male': 0, 'female': 0, 'error': 1}

    @app_commands.command(name="重製紙娃娃", description="將你的角色外觀重製為預設樣式")
    async def reset_my_avatar(self, interaction: discord.Interaction):
        """重製個人紙娃娃"""
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        user_data = self.get_user_data(user_id)
        
        if not user_data:
            await interaction.followup.send("❌ 找不到你的資料！請先完成入園流程。")
            return
        
        # 根據性別設定預設外觀
        gender = user_data.get('gender', 'male')
        
        if gender == 'female':
            avatar_data = {
                'face': 21731,
                'hair': 34410,
                'skin': 12000,
                'top': 1041004,
                'bottom': 1061008,
                'shoes': 1072005
            }
        else:
            avatar_data = {
                'face': 20005,
                'hair': 30120,
                'skin': 12000,
                'top': 1040014,
                'bottom': 1060096,
                'shoes': 1072005
            }
        
        # 更新資料庫
        success = self.update_user_avatar(user_id, avatar_data)
        
        if success:
            gender_text = "女性" if gender == 'female' else "男性"
            embed = discord.Embed(
                title="✨ 紙娃娃重製完成！",
                description=(
                    f"🎭 你的角色外觀已重製為 **{gender_text}預設樣式**\n\n"
                    f"**更新內容：**\n"
                    f"👤 臉部ID：`{avatar_data['face']}`\n"
                    f"💇 髮型ID：`{avatar_data['hair']}`\n"
                    f"🧴 膚色ID：`{avatar_data['skin']}`\n"
                    f"👕 上衣ID：`{avatar_data['top']}`\n"
                    f"👖 下裝ID：`{avatar_data['bottom']}`\n"
                    f"👟 鞋子ID：`{avatar_data['shoes']}`\n\n"
                    "✅ 資料庫已更新完成！"
                ),
                color=0x00FF7F
            )
            embed.set_footer(text=f"使用者ID: {user_id} | 性別: {gender_text}")
        else:
            embed = discord.Embed(
                title="❌ 重製失敗",
                description="更新資料庫時發生錯誤，請稍後再試或聯繫管理員。",
                color=0xFF0000
            )
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="批量重製紙娃娃", description="將所有使用者的紙娃娃重製為預設樣式")
    @app_commands.describe(confirm="確認執行批量重製（輸入 'CONFIRM' 確認）")
    async def reset_all_avatars(self, interaction: discord.Interaction, confirm: str):
        """批量重製所有使用者的紙娃娃"""
        await interaction.response.defer()
        
        # 檢查權限（可以根據需要調整權限檢查）
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ 你沒有權限執行此指令！", ephemeral=True)
            return
        
        if confirm.upper() != "CONFIRM":
            embed = discord.Embed(
                title="⚠️ 確認批量重製",
                description=(
                    "此操作將會：\n"
                    "🔄 重製**所有使用者**的紙娃娃外觀\n"
                    "👨 男性使用者 → 男性預設外觀\n"
                    "👩 女性使用者 → 女性預設外觀\n"
                    "💾 直接修改資料庫中的外觀ID\n\n"
                    "⚠️ **此操作無法復原！**\n\n"
                    "如要確認執行，請使用：\n"
                    "`/批量重製紙娃娃 confirm:CONFIRM`"
                ),
                color=0xFFFF00
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # 執行批量重製
        result = self.reset_all_avatars_by_gender()
        
        if result['error'] > 0:
            embed = discord.Embed(
                title="❌ 批量重製失敗",
                description="執行過程中發生錯誤，請檢查資料庫連接或聯繫技術人員。",
                color=0xFF0000
            )
        else:
            embed = discord.Embed(
                title="✅ 批量重製完成！",
                description=(
                    f"🎭 已成功重製所有使用者的紙娃娃外觀\n\n"
                    f"**重製統計：**\n"
                    f"👨 男性使用者：`{result['male']}` 人\n"
                    f"👩 女性使用者：`{result['female']}` 人\n"
                    f"📊 總計：`{result['male'] + result['female']}` 人\n\n"
                    f"**預設外觀設定：**\n"
                    f"👨 **男性預設**\n"
                    f"   • 臉部：`20005` | 髮型：`30120`\n"
                    f"   • 上衣：`1040014` | 下裝：`1060096`\n"
                    f"👩 **女性預設**\n"
                    f"   • 臉部：`21731` | 髮型：`34410`\n"
                    f"   • 上衣：`1041004` | 下裝：`1061008`\n"
                    f"🔧 **共同設定**\n"
                    f"   • 膚色：`12000` | 鞋子：`1072005`\n\n"
                    "💾 所有變更已儲存至資料庫"
                ),
                color=0x00FF00
            )
        
        embed.set_footer(text=f"執行者: {interaction.user.display_name} ({interaction.user.id})")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="查看紙娃娃設定", description="查看指定使用者的紙娃娃設定")
    @app_commands.describe(user="要查看的使用者（不填寫則查看自己）")
    async def view_avatar_settings(self, interaction: discord.Interaction, user: discord.Member = None):
        """查看紙娃娃設定"""
        await interaction.response.defer(ephemeral=True)
        
        target_user = user or interaction.user
        user_data = self.get_user_data(target_user.id)
        
        if not user_data:
            await interaction.followup.send(f"❌ 找不到 {target_user.display_name} 的資料！")
            return
        
        gender_text = "女性 ♀️" if user_data.get('gender') == 'female' else "男性 ♂️"
        
        embed = discord.Embed(
            title=f"🎭 {target_user.display_name} 的紙娃娃設定",
            description=f"👤 **性別：** {gender_text}",
            color=0x9932CC
        )
        
        embed.add_field(
            name="👤 臉部外觀",
            value=(
                f"臉部ID：`{user_data.get('face', 'N/A')}`\n"
                f"髮型ID：`{user_data.get('hair', 'N/A')}`\n"
                f"膚色ID：`{user_data.get('skin', 'N/A')}`"
            ),
            inline=True
        )
        
        embed.add_field(
            name="👕 服裝配件",
            value=(
                f"上衣ID：`{user_data.get('top', 'N/A')}`\n"
                f"下裝ID：`{user_data.get('bottom', 'N/A')}`\n"
                f"鞋子ID：`{user_data.get('shoes', 'N/A')}`"
            ),
            inline=True
        )
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"使用者ID: {target_user.id}")
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AvatarReset(bot))