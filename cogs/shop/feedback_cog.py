"""
玩家意見回饋系統 (Feedback System)
- 玩家點击按鈕 → 彈出 Modal 表單 → 輸入反饋 → 發送到管理員頻道
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import os
from datetime import datetime
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
STAFF_CHANNEL_ID = int(os.getenv("STAFF_ID_CHANNEL_ID", 0))
GUILD_ID = int(os.getenv("GUILD_ID", 0))


class FeedbackModal(Modal):
    """玩家意見回饋表單"""
    
    def __init__(self, bot):
        super().__init__(title="玩家意見回饋", timeout=300)
        self.bot = bot
        
        # 表單欄位
        self.feedback_title = TextInput(
            label="回饋主題",
            placeholder="例如：建議、問題、讚美等...",
            required=True,
            max_length=100,
            min_length=5
        )
        self.add_item(self.feedback_title)
        
        self.feedback_content = TextInput(
            label="詳細內容",
            placeholder="請詳細描述你的意見或問題...",
            style=discord.TextStyle.long,
            required=True,
            max_length=2000,
            min_length=10
        )
        self.add_item(self.feedback_content)
        
        self.feedback_category = TextInput(
            label="分類 (遊戲/功能/社群等)",
            placeholder="例如：遊戲平衡、功能建議、社群問題等",
            required=True,
            max_length=50,
            min_length=3
        )
        self.add_item(self.feedback_category)
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交表單時處理"""
        try:
            # 確認收到反饋
            await interaction.response.defer()
            
            # 構建嵌入消息
            embed = discord.Embed(
                title=f"📝 新玩家回饋 - {self.feedback_category.value}",
                description=self.feedback_content.value,
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # 添加用戶信息
            embed.set_author(
                name=f"{interaction.user.name} ({interaction.user.id})",
                icon_url=interaction.user.avatar.url if interaction.user.avatar else None
            )
            
            # 添加回饋主題
            embed.add_field(
                name="主題",
                value=self.feedback_title.value,
                inline=False
            )
            
            # 添加分類
            embed.add_field(
                name="分類",
                value=self.feedback_category.value,
                inline=True
            )
            
            # 添加時間
            embed.add_field(
                name="提交時間",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=True
            )
            
            # 添加頁腳
            embed.set_footer(text="玩家回饋系統 | 如需回覆，請聯絡管理員")
            
            # 發送到管理員頻道
            if STAFF_CHANNEL_ID:
                try:
                    staff_channel = self.bot.get_channel(STAFF_CHANNEL_ID)
                    if staff_channel:
                        await staff_channel.send(embed=embed)
                        # 回覆用戶
                        await interaction.followup.send(
                            f"✅ 感謝你的回饋！\n\n**主題:** {self.feedback_title.value}\n**分類:** {self.feedback_category.value}\n\n你的意見已發送給管理員，謝謝！",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            "❌ 無法找到管理員頻道。請稍後重試。",
                            ephemeral=True
                        )
                except Exception as e:
                    print(f"[FEEDBACK] 發送到管理員頻道失敗: {e}")
                    await interaction.followup.send(
                        f"❌ 發送失敗: {str(e)}",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "❌ 管理員頻道未設定。請聯絡伺服器管理員。",
                    ephemeral=True
                )
        
        except Exception as e:
            print(f"[FEEDBACK] Modal 提交失敗: {e}")
            try:
                await interaction.followup.send(
                    f"❌ 發生錯誤: {str(e)}",
                    ephemeral=True
                )
            except:
                pass


class FeedbackView(View):
    """包含回饋按鈕的視圖"""
    
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(label="📝 提交意見回饋", style=discord.ButtonStyle.primary, custom_id="feedback_button")
    async def feedback_button(self, interaction: discord.Interaction, button: Button):
        """反饋按鈕回調"""
        modal = FeedbackModal(self.bot)
        await interaction.response.show_modal(modal)


class FeedbackCog(commands.Cog):
    """玩家意見回饋系統"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="feedback", description="提交玩家意見回饋")
    async def feedback_command(self, interaction: discord.Interaction):
        """
        /feedback 命令 - 主要用來觸發回饋系統
        """
        try:
            embed = discord.Embed(
                title="📝 玩家意見回饋系統",
                description="我們很重視你的意見！點擊下方按鈕提交你的建議、問題或讚美。",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="ℹ️ 我們欣然接受",
                value="✅ 功能建議\n✅ 遊戲平衡問題\n✅ Bug 回報\n✅ 社群建議\n✅ 任何反饋！",
                inline=False
            )
            
            embed.add_field(
                name="💡 提示",
                value="• 請盡可能詳細描述\n• 我們會根據情況回覆\n• 你的反饋幫助我們改進遊戲",
                inline=False
            )
            
            view = FeedbackView(self.bot)
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=False
            )
        
        except Exception as e:
            print(f"[FEEDBACK] 命令執行失敗: {e}")
            await interaction.response.send_message(
                f"❌ 發生錯誤: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    """將 cog 加入 bot"""
    await bot.add_cog(FeedbackCog(bot))
    print("[FEEDBACK COG] 已成功載入 Feedback Cog")
