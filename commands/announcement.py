import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, TextInput, Modal
import json
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv, set_key

load_dotenv()

class AnnouncementCarouselView(View):
    """帶按鈕的公告輪播視圖"""
    
    def __init__(self, carousel_id: str, current_page: int = 0):
        super().__init__(timeout=None)  # 永久監聽按鈕
        self.carousel_id = carousel_id
        self.current_page = current_page
        self.carousel_data = self._load_carousel()
        
        if self.carousel_data:
            self.pages = self.carousel_data.get('pages', [])
            self.update_buttons()
    
    def _load_carousel(self) -> Optional[dict]:
        """載入轉木馬數據"""
        docs_path = Path("docs/announcement_carousel.json")
        try:
            if docs_path.exists():
                with open(docs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    carousels = data.get('announcement_carousels', {})
                    return carousels.get(self.carousel_id, {})
            return None
        except Exception as e:
            print(f"❌ 載入轉木馬失敗: {e}")
            return None
    
    def update_buttons(self):
        """更新按鈕狀態"""
        # 移除舊按鈕
        for item in self.children[:]:
            if isinstance(item, Button):
                self.remove_item(item)
        
        num_pages = len(self.pages)
        
        # 上一頁按鈕
        prev_btn = Button(
            label="⬅️ 上一頁",
            style=discord.ButtonStyle.blurple,
            disabled=self.current_page == 0,
            custom_id=f"carousel_prev_{self.carousel_id}"
        )
        prev_btn.callback = self.prev_page
        self.add_item(prev_btn)
        
        # 頁碼按鈕
        page_btn = Button(
            label=f"{self.current_page + 1}/{num_pages}",
            style=discord.ButtonStyle.gray,
            disabled=True,
            custom_id=f"carousel_page_{self.carousel_id}"
        )
        self.add_item(page_btn)
        
        # 下一頁按鈕
        next_btn = Button(
            label="下一頁 ➡️",
            style=discord.ButtonStyle.blurple,
            disabled=self.current_page == num_pages - 1,
            custom_id=f"carousel_next_{self.carousel_id}"
        )
        next_btn.callback = self.next_page
        self.add_item(next_btn)
    
    async def prev_page(self, interaction: discord.Interaction):
        """上一頁"""
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_embed(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        """下一頁"""
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_embed(interaction)
    
    async def update_embed(self, interaction: discord.Interaction):
        """更新 Embed 顯示"""
        self.update_buttons()
        page_data = self.pages[self.current_page]
        embed = self._create_embed(page_data)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def _create_embed(self, page_data: dict) -> discord.Embed:
        """建立 Embed"""
        embed = discord.Embed(
            title=page_data.get('title', ''),
            description=page_data.get('description', ''),
            color=page_data.get('color', 0x2f3136)
        )
        
        # 添加欄位
        for field in page_data.get('fields', []):
            embed.add_field(
                name=field.get('name', ''),
                value=field.get('value', ''),
                inline=field.get('inline', False)
            )
        
        # 添加內容
        if page_data.get('content'):
            embed.add_field(name="", value=page_data.get('content'), inline=False)
        
        embed.set_footer(text=page_data.get('footer', 'KK 園區'))
        return embed

class Announcement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.announcement_channel_id = int(os.getenv('ANNOUNCEMENT_CHANNEL_ID', 0))
        self.env_path = Path('.env')
    
    async def cog_load(self):
        """Cog 載入時執行"""
        await self.validate_announcement_message()
    
    async def validate_announcement_message(self):
        """驗證公告消息是否還存在"""
        message_id_str = os.getenv('ANNOUNCEMENT_MESSAGE_ID', '').strip()
        if not message_id_str or not message_id_str.isdigit():
            return
        
        try:
            message_id = int(message_id_str)
            channel = self.bot.get_channel(self.announcement_channel_id)
            if channel:
                message = await channel.fetch_message(message_id)
                return  # 消息存在
        except discord.NotFound:
            # 消息已刪除，清除 MESSAGE_ID
            set_key(self.env_path, 'ANNOUNCEMENT_MESSAGE_ID', '')
            print("❌ 公告消息已被刪除，已清除 MESSAGE_ID")
        except Exception as e:
            print(f"❌ 驗證公告消息失敗: {e}")
    
    def _update_env_message_id(self, message_id: int):
        """更新 .env 中的消息 ID"""
        try:
            set_key(self.env_path, 'ANNOUNCEMENT_MESSAGE_ID', str(message_id))
            os.environ['ANNOUNCEMENT_MESSAGE_ID'] = str(message_id)
            print(f"✅ 消息 ID 已保存: {message_id}")
        except Exception as e:
            print(f"❌ 保存消息 ID 失敗: {e}")
    
    def _load_carousel_data(self, carousel_id: str) -> Optional[dict]:
        """載入轉木馬數據"""
        docs_path = Path("docs/announcement_carousel.json")
        try:
            if docs_path.exists():
                with open(docs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    carousels = data.get('announcement_carousels', {})
                    return carousels.get(carousel_id, {})
            return None
        except Exception as e:
            print(f"❌ 載入失敗: {e}")
            return None
    
    @app_commands.command(name="發送公告輪播", description="發送帶按鈕的公告輪播")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        carousel_id="輪播ID (例如：main_guide)"
    )
    async def send_carousel(self, interaction: discord.Interaction, carousel_id: str = "main_guide"):
        """發送或更新公告輪播"""
        
        # 載入數據驗證
        carousel_data = self._load_carousel_data(carousel_id)
        if not carousel_data:
            await interaction.response.send_message(
                f"❌ 找不到轉木馬：{carousel_id}",
                ephemeral=True
            )
            return
        
        pages = carousel_data.get('pages', [])
        if not pages:
            await interaction.response.send_message(
                "❌ 轉木馬沒有頁面",
                ephemeral=True
            )
            return
        
        # 建立視圖
        view = AnnouncementCarouselView(carousel_id, current_page=0)
        
        # 建立第一頁 Embed
        first_page = pages[0]
        embed = view._create_embed(first_page)
        
        # 檢查是否有已存在的消息
        message_id_str = os.getenv('ANNOUNCEMENT_MESSAGE_ID', '').strip()
        channel = self.bot.get_channel(self.announcement_channel_id)
        
        if not channel:
            await interaction.response.send_message(
                "❌ 公告頻道未找到",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        try:
            if message_id_str and message_id_str.isdigit():
                # 嘗試編輯已存在的消息
                try:
                    message_id = int(message_id_str)
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed, view=view)
                    await interaction.followup.send(
                        f"✅ 公告已更新！共 {len(pages)} 頁",
                        ephemeral=True
                    )
                except discord.NotFound:
                    # 消息已刪除，發送新消息
                    message = await channel.send(embed=embed, view=view)
                    self._update_env_message_id(message.id)
                    await interaction.followup.send(
                        f"✅ 公告已發送（新消息）！共 {len(pages)} 頁",
                        ephemeral=True
                    )
            else:
                # 首次發送public消息
                message = await channel.send(embed=embed, view=view)
                self._update_env_message_id(message.id)
                await interaction.followup.send(
                    f"✅ 公告已發送！共 {len(pages)} 頁",
                    ephemeral=True
                )
        
        except Exception as e:
            await interaction.followup.send(
                f"❌ 發送公告失敗: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="查看公告列表", description="查看所有可用的公告轉木馬")
    async def list_carousels(self, interaction: discord.Interaction):
        """查看可用的轉木馬"""
        try:
            docs_path = Path("docs/announcement_carousel.json")
            if not docs_path.exists():
                await interaction.response.send_message("📋 沒有公告文檔", ephemeral=True)
                return
            
            with open(docs_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                carousels = data.get('announcement_carousels', {})
            
            if not carousels:
                await interaction.response.send_message("📋 沒有可用的公告", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📋 可用公告列表",
                color=0x7289da
            )
            
            for carousel_id, carousel_data in carousels.items():
                title = carousel_data.get('title', carousel_id)
                pages = carousel_data.get('pages', [])
                embed.add_field(
                    name=f"📌 {title}",
                    value=f"**ID:** `{carousel_id}`\n**頁數:** {len(pages)} 頁",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            await interaction.response.send_message(f"❌ 錯誤: {e}", ephemeral=True)

async def setup(bot):
    cog = Announcement(bot)
    await bot.add_cog(cog)
    await cog.cog_load()