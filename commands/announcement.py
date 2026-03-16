import discord
from discord.ext import commands
from discord.ui import View, Select
import json
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv, set_key

load_dotenv()

class AnnouncementSelectView(View):
    """公告選擇視圖"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.announcements = self._load_announcements()
        self.current_announcement_id = self.announcements[0]['id'] if self.announcements else None
        self.update_select()
    
    def _load_announcements(self) -> list:
        """載入公告數據"""
        docs_path = Path("docs/announcement_carousel.json")
        try:
            if docs_path.exists():
                with open(docs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('announcement_carousels', {}).get('announcements', [])
            return []
        except Exception as e:
            print(f"❌ 載入公告失敗: {e}")
            return []
    
    def update_select(self):
        """更新下拉選單"""
        # 移除舊Select
        for item in self.children[:]:
            if isinstance(item, Select):
                self.remove_item(item)
        
        if not self.announcements:
            return
        
        # 建立選項
        options = [
            discord.SelectOption(
                label=ann['name'],
                value=ann['id'],
                emoji=ann.get('emoji', '📌')
            )
            for ann in self.announcements
        ]
        
        select = Select(
            placeholder="選擇公告...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        """選擇公告回調"""
        selected_id = interaction.data['values'][0]
        self.current_announcement_id = selected_id
        
        # 找到選中的公告
        announcement = next(
            (ann for ann in self.announcements if ann['id'] == selected_id),
            None
        )
        
        if not announcement:
            return
        
        # 建立 Embed
        embed = self._create_embed(announcement)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def _create_embed(self, announcement: dict) -> discord.Embed:
        """建立 Embed"""
        embed = discord.Embed(
            title=announcement.get('title', ''),
            description=announcement.get('description', ''),
            color=announcement.get('color', 0x2f3136)
        )
        
        # 添加欄位
        for field in announcement.get('fields', []):
            embed.add_field(
                name=field.get('name', ''),
                value=field.get('value', ''),
                inline=field.get('inline', False)
            )
        
        # 添加內容
        if announcement.get('content'):
            embed.add_field(
                name="",
                value=announcement.get('content'),
                inline=False
            )
        
        embed.set_footer(text=announcement.get('footer', 'KK 園區'))
        return embed

class Announcement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.announcement_channel_id = int(os.getenv('ANNOUNCEMENT_CHANNEL_ID', 0))
        self.env_path = Path('.env')
    
    async def cog_load(self):
        """Cog 載入時自動同步公告"""
        await self.sync_announcement()
    
    async def sync_announcement(self):
        """同步公告：編輯已存在的消息或發送新消息"""
        try:
            # 載入數據
            announcements = self._load_announcements()
            if not announcements:
                print("❌ 沒有公告數據")
                return
            
            # 取得公告頻道
            channel = self.bot.get_channel(self.announcement_channel_id)
            if not channel:
                print(f"❌ 公告頻道未找到 (ID: {self.announcement_channel_id})")
                return
            
            # 建立視圖和第一個公告
            view = AnnouncementSelectView()
            first_announcement = announcements[0]
            embed = view._create_embed(first_announcement)
            
            message_id_str = os.getenv('ANNOUNCEMENT_MESSAGE_ID', '').strip()
            
            if message_id_str and message_id_str.isdigit():
                # 嘗試編輯已存在的消息
                try:
                    message_id = int(message_id_str)
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed, view=view)
                    print(f"✅ 公告已更新 (消息 ID: {message_id})")
                except discord.NotFound:
                    # 消息已刪除，發送新消息
                    message = await channel.send(embed=embed, view=view)
                    self._update_env_message_id(message.id)
                    print(f"✅ 公告已發送 (新消息，ID: {message.id})")
                except Exception as e:
                    print(f"❌ 編輯公告失敗: {e}")
            else:
                # 首次發送消息
                message = await channel.send(embed=embed, view=view)
                self._update_env_message_id(message.id)
                print(f"✅ 公告已發送 (新消息，ID: {message.id})")
        
        except Exception as e:
            print(f"❌ 同步公告失敗: {e}")
    
    def _update_env_message_id(self, message_id: int):
        """更新 .env 中的消息 ID"""
        try:
            set_key(self.env_path, 'ANNOUNCEMENT_MESSAGE_ID', str(message_id))
            os.environ['ANNOUNCEMENT_MESSAGE_ID'] = str(message_id)
        except Exception as e:
            print(f"❌ 保存消息 ID 失敗: {e}")
    
    def _load_announcements(self) -> list:
        """載入公告數據"""
        docs_path = Path("docs/announcement_carousel.json")
        try:
            if docs_path.exists():
                with open(docs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('announcement_carousels', {}).get('announcements', [])
            return []
        except Exception as e:
            print(f"❌ 載入公告失敗: {e}")
            return []

async def setup(bot):
    cog = Announcement(bot)
    await bot.add_cog(cog)
    await cog.cog_load()
