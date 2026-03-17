import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import json
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

class FeedbackModal(Modal):
    """玩家意見回饋表單"""
    
    def __init__(self, bot):
        super().__init__(title="💝 玩家意見回饋")
        self.bot = bot
        
        # 只添加內容欄位
        self.feedback_content = TextInput(
            label="您的意見或建議（詳細描述）",
            placeholder="請詳細說明您的想法或遇到的問題...",
            required=True,
            style=discord.TextStyle.long,
            max_length=2000,
            min_length=5
        )
        self.add_item(self.feedback_content)
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        """處理表單提交"""
        try:
            # 獲取管理員頻道
            staff_channel_id_str = os.getenv('STAFF_ID_CHANNEL_ID')
            if not staff_channel_id_str or not staff_channel_id_str.isdigit():
                staff_channel_id = 0
            else:
                staff_channel_id = int(staff_channel_id_str)
            
            if staff_channel_id == 0:
                await interaction.response.send_message(
                    "❌ 無法提交意見：管理員頻道未配置",
                    ephemeral=True
                )
                return
            
            channel = await self.bot.fetch_channel(staff_channel_id)
            
            if not channel:
                await interaction.response.send_message(
                    "❌ 無法提交意見：管理員頻道未找到",
                    ephemeral=True
                )
                return
            
            # 取得用戶昵稱（優先使用 nick，其次使用 name）
            user_display_name = interaction.user.nick or interaction.user.name
            
            # 建立回饋 Embed
            embed = discord.Embed(
                title="💝 新的玩家意見回饋",
                description=f"**用戶：** {interaction.user.mention}",
                color=discord.Color.gold(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="👤 昵稱",
                value=user_display_name,
                inline=True
            )
            
            embed.add_field(
                name="ID",
                value=interaction.user.id,
                inline=True
            )
            
            embed.add_field(
                name="📝 意見內容",
                value=self.feedback_content.value,
                inline=False
            )
            
            embed.set_footer(text=f"伺服器ID: {interaction.guild.id}")
            
            # 發送到管理員頻道
            await channel.send(embed=embed)
            
            # 給玩家確認訊息
            confirm_embed = discord.Embed(
                title="✅ 意見已提交",
                description="感謝您的寶貴意見！我們已收到您的回饋，管理團隊將認真審視。",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(
                embed=confirm_embed,
                ephemeral=True
            )
            
            print(f"✅ [意見回饋] {user_display_name} (ID: {interaction.user.id}) 提交了意見")
            
        except ValueError as e:
            print(f"❌ [意見回饋] 配置錯誤: {e}")
            await interaction.response.send_message(
                "❌ 提交意見時發生配置錯誤",
                ephemeral=True
            )
        except discord.DiscordException as e:
            print(f"❌ [意見回饋] Discord 錯誤: {e}")
            await interaction.response.send_message(
                "❌ 提交意見時發生網路錯誤，請稍後重試",
                ephemeral=True
            )

class AnnouncementButtonView(View):
    """公告按鈕選擇視圖"""
    
    def __init__(self, bot=None):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
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
        except (IOError, json.JSONDecodeError) as e:
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
        
        # 添加意見回饋按鈕
        feedback_btn = Button(
            label="意見回饋",
            emoji="💝",
            style=discord.ButtonStyle.green,
            custom_id="feedback_btn"
        )
        feedback_btn.callback = self.feedback_button_callback
        self.add_item(feedback_btn)
    
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
            embed = self.create_embed_for_announcement(announcement)
            
            # 更新按鈕狀態
            self.update_button_styles(announcement_id)
            
            await interaction.response.edit_message(embed=embed, view=self)
        
        return callback
    
    async def feedback_button_callback(self, interaction: discord.Interaction):
        """意見回饋按鈕回調"""
        if not self.bot:
            await interaction.response.send_message(
                "❌ 機器人配置錯誤，無法提交意見",
                ephemeral=True
            )
            return
        
        modal = FeedbackModal(self.bot)
        await interaction.response.send_modal(modal)
    
    def update_button_styles(self, active_id: str):
        """更新按鈕樣式"""
        for item in self.children:
            if isinstance(item, Button) and item.custom_id:
                if active_id in item.custom_id:
                    item.style = discord.ButtonStyle.green
                else:
                    item.style = discord.ButtonStyle.blurple
    
    def create_embed_for_announcement(self, announcement: dict) -> discord.Embed:
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
        # 直接從 .env 讀取，避免 os.getenv() 的緩存問題
        self.env_path = Path('.env')
        self.announcement_channel_id = self._read_channel_id_from_env()
        self._synced = False  # 追蹤是否已同步過
        print(f"✅ [Announcement COG INITIALIZED] Channel ID: {self.announcement_channel_id}")
        
        # 啟動背景任務監控 bot 連接
        self.sync_task = asyncio.create_task(self._wait_and_sync())
    
    async def _wait_and_sync(self):
        """等待 bot 連接然後同步"""
        try:
            await self.bot.wait_until_ready()
            await asyncio.sleep(2)  # 額外延遲確保完全初始化
            if not self._synced:
                self._synced = True
                print("[Announcement] Bot 已就緒，開始同步公告...")
                print(f"[Announcement] 當前 Channel ID: {self.announcement_channel_id}")
                await self.sync_announcement()
        except asyncio.CancelledError:
            pass
        except (discord.DiscordException, OSError, asyncio.TimeoutError) as e:
            print(f"❌ [Announcement] 任務執行失敗: {e}")
            import traceback
            traceback.print_exc()
    
    def _read_channel_id_from_env(self) -> int:
        """從 .env 讀取 ANNOUNCEMENT_CHANNEL_ID，避免 os.getenv() 的緩存問題"""
        try:
            if not self.env_path.exists():
                print(f"⚠️ .env 文件不存在: {self.env_path}，使用默認值 0")
                return 0
            
            with open(self.env_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if 'ANNOUNCEMENT_CHANNEL_ID' in line and '=' in line:
                    value = line.split('=', 1)[1].strip()
                    value = value.strip('\'"')
                    value = value.split('#')[0].strip()
                    
                    if value and value.isdigit():
                        return int(value)
            
            print("⚠️ 未在 .env 中找到有效的 ANNOUNCEMENT_CHANNEL_ID")
            return 0
        except (IOError, OSError):
            return 0
    
    async def sync_announcement(self):
        """同步公告：編輯已存在的消息或發送新消息"""
        try:
            # 載入數據
            announcements = self._load_announcements()
            if not announcements:
                print("❌ 沒有公告數據")
                return
            
            # 取得公告頻道
            try:
                channel = await self.bot.fetch_channel(self.announcement_channel_id)
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"❌ 無法獲取公告頻道 (ID: {self.announcement_channel_id}): {e}")
                return
            
            if not channel:
                print(f"❌ 公告頻道未找到 (ID: {self.announcement_channel_id})")
                return
            
            print(f"✓ 已連接到頻道: {channel.name} (ID: {self.announcement_channel_id})")
            
            # 建立視圖和第一個公告
            view = AnnouncementButtonView(self.bot)
            first_announcement = announcements[0]
            embed = view.create_embed_for_announcement(first_announcement)
            
            # ======== 關鍵邏輯：讀取 .env 中已保存的 MESSAGE_ID ========
            message_id = self._read_message_id_from_env()
            print(f"🔍 [重要] 讀取到的 MESSAGE_ID: {message_id}")
            
            # 如果有有效的 MESSAGE_ID，嘗試編輯
            if message_id and message_id > 0:
                print(f"📨 [嘗試編輯] 尋找現有消息 ID: {message_id}")
                try:
                    message = await channel.fetch_message(message_id)
                    print(f"✓ [找到消息] 成功獲取消息，準備編輯...")
                    await message.edit(embed=embed, view=view)
                    print(f"✅ [編輯成功] 公告已編輯 (消息 ID: {message_id})")
                    return
                except discord.NotFound:
                    print(f"⚠️ [消息已刪除] 原消息 ID {message_id} 已被刪除或不存在，將發送新消息")
                    print(f"   詳細信息: 頻道 ID={channel.id}, 消息 ID={message_id}")
                    self._clear_env_message_id()
                except discord.Forbidden as e:
                    print(f"⚠️ [權限不足] 無法編輯消息: {e}，將發送新消息")
                    self._clear_env_message_id()
                except asyncio.TimeoutError as e:
                    print(f"⚠️ [超時] 編輯消息超時: {e}，將發送新消息")
                    self._clear_env_message_id()
                except discord.DiscordException as e:
                    print(f"⚠️ [Discord 錯誤] 消息編輯失敗 ({type(e).__name__}): {e}")
                    print(f"   詳細信息: 嘗試發送新消息...")
                    self._clear_env_message_id()
            else:
                print(f"⚠️ [無效 MESSAGE_ID] 無有效的已保存 MESSAGE_ID (值為: {message_id})，將發送新消息")
            
            # 發送新消息
            print("📤 [發送新消息] 開始發送新公告...")
            message = await channel.send(embed=embed, view=view)
            print(f"✓ [消息已發送] 新消息 ID: {message.id}")
            
            # 保存 MESSAGE_ID 到 .env
            self._update_env_message_id(message.id)
            
            # 驗證保存是否成功
            verify_id = self._read_message_id_from_env()
            if verify_id == message.id:
                print(f"✅ [驗證成功] MESSAGE_ID 已正確保存: {verify_id}")
            else:
                print(f"⚠️ [驗證失敗] MESSAGE_ID 保存失敗 (預期: {message.id}, 實際: {verify_id})")
        
        except asyncio.CancelledError:
            pass
        except (discord.DiscordException, OSError, asyncio.TimeoutError) as e:
            print(f"❌ [同步失敗] 同步公告失敗: {e}")
            import traceback
            traceback.print_exc()
    
    def _read_message_id_from_env(self) -> int:
        """從 .env 讀取 MESSAGE_ID，返回有效的整數或 0 - 每次都直接讀取文件"""
        try:
            if not self.env_path.exists():
                print(f"⚠️ .env 文件不存在: {self.env_path}")
                return 0
            
            # 直接讀取文件，避免緩存問題
            with open(self.env_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 逐行查找
            for line in content.split('\n'):
                line = line.strip()
                # 跳過空行和註釋
                if not line or line.startswith('#'):
                    continue
                    
                if 'ANNOUNCEMENT_MESSAGE_ID' in line:
                    # 提取 = 後的值
                    if '=' not in line:
                        continue
                    
                    value = line.split('=', 1)[1].strip()  # 獲取 = 後的內容
                    
                    # 移除引號（可能被dotenv包裹）
                    value = value.strip('\'"')
                    
                    # 分割並去掉註釋
                    value = value.split('#')[0].strip()
                    
                    # 確保是純數字
                    if value and value.isdigit():
                        msg_id = int(value)
                        print(f"  ✅ 成功讀取 MESSAGE_ID: {msg_id}")
                        return msg_id
                    else:
                        print(f"  ⚠️ MESSAGE_ID 不是有效的數字: {value}")
                        return 0
            
            print("  ⚠️ .env 中未找到 ANNOUNCEMENT_MESSAGE_ID")
            return 0
        except (IOError, OSError) as e:
            print(f"❌ 讀取 MESSAGE_ID 失敗: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def _update_env_message_id(self, message_id: int):
        """更新 .env 中的消息 ID - 確保持久化"""
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
                    # 只保存純數字，避免額外的引號或註解
                    new_lines.append(f'ANNOUNCEMENT_MESSAGE_ID={message_id}')
                    found = True
                else:
                    new_lines.append(line)
            
            # 如果沒找到，就在 ANNOUNCEMENT_CHANNEL_ID 後面加入
            if not found:
                final_lines = []
                for line in new_lines:
                    final_lines.append(line)
                    if line.startswith('ANNOUNCEMENT_CHANNEL_ID='):
                        final_lines.append(f'ANNOUNCEMENT_MESSAGE_ID={message_id}')
                new_lines = final_lines
            
            # 寫入文件并確保 flush
            new_content = '\n'.join(new_lines)
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                f.flush()  # 強制刷寫到磁盤
                os.fsync(f.fileno())  # 確保操作系統已寫入
            
            print(f"  [DEBUG] 已寫入 .env 文件並 flush，MESSAGE_ID={message_id}")
            
            # 同時更新環境變數
            os.environ['ANNOUNCEMENT_MESSAGE_ID'] = str(message_id)
            
            # 小延遲確保文件系統已寫入
            import time
            time.sleep(0.5)
            
            # 驗證寫入（直接讀取文件）
            verify_id = self._read_message_id_from_env()
            if verify_id == message_id:
                print(f"✅ MESSAGE_ID 已成功保存到 .env: {message_id}")
                return
            
            print(f"⚠️ MESSAGE_ID 保存後驗證失敗 (預期: {message_id}, 實際: {verify_id})")
        
        except (IOError, OSError) as e:
            print(f"❌ 保存 MESSAGE_ID 失敗: {e}")
            import traceback
            traceback.print_exc()
    
    def _clear_env_message_id(self):
        """清除 .env 中的消息 ID，確保持久化"""
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
                        new_lines.append('ANNOUNCEMENT_MESSAGE_ID=')
                    else:
                        new_lines.append(line)
                
                # 寫入文件並確保 flush
                new_content = '\n'.join(new_lines)
                with open(self.env_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                    f.flush()  # 強制刷寫到磁盤
                    os.fsync(f.fileno())  # 確保操作系統已寫入
            
            os.environ['ANNOUNCEMENT_MESSAGE_ID'] = ''
            print("🗑️ 已清除 MESSAGE_ID")
        
        except (IOError, OSError) as e:
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
        except (IOError, json.JSONDecodeError) as e:
            print(f"❌ 載入公告失敗: {e}")
            return []

async def setup(bot):
    await bot.add_cog(Announcement(bot))
