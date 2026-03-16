import discord
from discord.ext import commands
from discord.ui import View, Button
import json
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class AnnouncementButtonView(View):
    """公告按鈕選擇視圖"""
    
    def __init__(self):
        super().__init__(timeout=None)  # 永久視圖
        self.announcements = self._load_announcements()
        self.current_announcement_id = self.announcements[0]['id'] if self.announcements else None
        self.update_buttons()
    
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
    
    def update_buttons(self):
        """更新按鈕"""
        # 移除舊按鈕
        for item in self.children[:]:
            if isinstance(item, Button):
                self.remove_item(item)
        
        if not self.announcements:
            return
        
        # 為每個公告建立按鈕
        for ann in self.announcements:
            btn = Button(
                label=ann['name'],
                emoji=ann.get('emoji', '📌'),
                style=discord.ButtonStyle.blurple,
                custom_id=f"ann_btn_{ann['id']}"
            )
            btn.callback = self.make_button_callback(ann['id'])
            self.add_item(btn)
    
    def make_button_callback(self, announcement_id: str):
        """建立按鈕回調函數"""
        async def callback(interaction: discord.Interaction):
            self.current_announcement_id = announcement_id
            
            # 找到選中的公告
            announcement = next(
                (ann for ann in self.announcements if ann['id'] == announcement_id),
                None
            )
            
            if not announcement:
                return
            
            # 建立 Embed
            embed = self._create_embed(announcement)
            
            # 更新按鈕狀態
            self.update_button_styles(announcement_id)
            
            await interaction.response.edit_message(embed=embed, view=self)
        
        return callback
    
    def update_button_styles(self, active_id: str):
        """更新按鈕樣式"""
        for item in self.children:
            if isinstance(item, Button) and item.custom_id:
                if active_id in item.custom_id:
                    item.style = discord.ButtonStyle.green
                else:
                    item.style = discord.ButtonStyle.blurple
    
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
            view = AnnouncementButtonView()
            first_announcement = announcements[0]
            embed = view._create_embed(first_announcement)
            
            # 讀取 MESSAGE_ID
            message_id_str = os.getenv('ANNOUNCEMENT_MESSAGE_ID', '').strip()
            print(f"🔍 讀取到的 MESSAGE_ID: '{message_id_str}'")
            
            if message_id_str and message_id_str.isdigit():
                # 嘗試編輯已存在的消息
                message_id = int(message_id_str)
                print(f"📨 嘗試編輯消息 ID: {message_id}")
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed, view=view)
                    print(f"✅ 公告已編輯 (消息 ID: {message_id})")
                    return
                except discord.NotFound:
                    print(f"⚠️ 消息已刪除 (ID: {message_id})，重新發送新消息")
                    self._clear_env_message_id()
                except Exception as e:
                    print(f"⚠️ 編輯消息失敗: {e}，重新發送新消息")
                    self._clear_env_message_id()
            
            # 發送新消息
            print("📤 發送新公告消息...")
            message = await channel.send(embed=embed, view=view)
            print(f"✅ 公告已發送 (新消息，ID: {message.id})")
            
            # 保存 MESSAGE_ID 並驗證
            self._update_env_message_id(message.id)
            
            # 驗證保存是否成功
            verify_id = os.getenv('ANNOUNCEMENT_MESSAGE_ID', '').strip()
            if verify_id == str(message.id):
                print(f"✅ MESSAGE_ID 已成功保存: {verify_id}")
            else:
                print(f"⚠️ MESSAGE_ID 保存可能失敗 (預期: {message.id}, 實際: {verify_id})")
        
        except Exception as e:
            print(f"❌ 同步公告失敗: {e}")
            import traceback
            traceback.print_exc()
    
    def _update_env_message_id(self, message_id: int):
        """更新 .env 中的消息 ID - 直接寫入文件"""
        try:
            print(f"💾 正在保存 MESSAGE_ID: {message_id}")
            
            # 讀取現有 .env 內容
            env_content = ""
            if self.env_path.exists():
                with open(self.env_path, 'r', encoding='utf-8') as f:
                    env_content = f.read()
            
            # 檢查是否已經有 ANNOUNCEMENT_MESSAGE_ID 這一行
            lines = env_content.split('\n')
            found = False
            new_lines = []
            
            for line in lines:
                if line.startswith('ANNOUNCEMENT_MESSAGE_ID='):
                    new_lines.append(f'ANNOUNCEMENT_MESSAGE_ID={message_id}  # 公告消息 ID（由機器人自動更新）')
                    found = True
                else:
                    new_lines.append(line)
            
            # 如果沒找到，就在 ANNOUNCEMENT_CHANNEL_ID 後面加入
            if not found:
                final_lines = []
                for i, line in enumerate(new_lines):
                    final_lines.append(line)
                    if line.startswith('ANNOUNCEMENT_CHANNEL_ID='):
                        final_lines.append(f'ANNOUNCEMENT_MESSAGE_ID={message_id}  # 公告消息 ID（由機器人自動更新）')
                new_lines = final_lines
            
            # 寫入文件
            new_content = '\n'.join(new_lines)
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # 同時更新環境變數
            os.environ['ANNOUNCEMENT_MESSAGE_ID'] = str(message_id)
            
            # 驗證寫入
            with open(self.env_path, 'r', encoding='utf-8') as f:
                verify_content = f.read()
                if f'ANNOUNCEMENT_MESSAGE_ID={message_id}' in verify_content:
                    print(f"✅ MESSAGE_ID 已成功保存到 .env: {message_id}")
                    return
            
            print(f"⚠️ MESSAGE_ID 保存後驗證失敗")
        
        except Exception as e:
            print(f"❌ 保存 MESSAGE_ID 失敗: {e}")
            import traceback
            traceback.print_exc()
    
    def _clear_env_message_id(self):
        """清除 .env 中的消息 ID"""
        try:
            # 讀取現有 .env 內容
            if self.env_path.exists():
                with open(self.env_path, 'r', encoding='utf-8') as f:
                    env_content = f.read()
                
                # 改為空值
                lines = env_content.split('\n')
                new_lines = []
                
                for line in lines:
                    if line.startswith('ANNOUNCEMENT_MESSAGE_ID='):
                        new_lines.append('ANNOUNCEMENT_MESSAGE_ID=  # 公告消息 ID（由機器人自動更新）')
                    else:
                        new_lines.append(line)
                
                # 寫入文件
                new_content = '\n'.join(new_lines)
                with open(self.env_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            
            os.environ['ANNOUNCEMENT_MESSAGE_ID'] = ''
            print(f"🗑️ 已清除 MESSAGE_ID")
        
        except Exception as e:
            print(f"❌ 清除 MESSAGE_ID 失敗: {e}")
    
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
