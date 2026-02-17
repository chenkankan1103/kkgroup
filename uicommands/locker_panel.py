"""
置物櫃實時面板系統 - 自動更新的置物櫃概況

功能：
1. 維護一個實時更新的「置物櫃概況」訊息
2. 每30分鐘自動更新一次統計
3. 記錄最近5次的隨機事件
4. 使用 Edit Message 而不是發送新訊息（避免訊息堆積）
"""

import discord
from discord.ext import commands, tasks
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
import traceback

# 數據持久化文件
PANEL_DATA_FILE = './shop_commands/locker_panel_data.json'
DB_PATH = './shop_commands/merchant/cannabis.db'

# 事件類型
EVENTS = {
    'plant': '🌱 種植',
    'fertilize': '💧 施肥',
    'harvest': '🎉 收割',
    'trade': '📦 交易'
}

class LockerPanelCog(commands.Cog):
    """置物櫃實時面板 - UIBot 集成"""
    
    def __init__(self, bot):
        self.bot = bot
        self.panel_message_id = None
        self.panel_channel_id = None
        self.recent_events = []  # 最近5次事件
        
        # 載入保存的數據
        self.load_panel_data()
        
        # ⏹️ 背景定期更新已禁用
        # 原因：cannabis_locker.py 的 CannabisCog 已實現相同的 update_panel_task()
        # 為避免重複更新，此 Cog 只提供靜態面板生成功能
        # self.update_locker_panel.start()
    
    def cog_unload(self):
        self.update_locker_panel.cancel()
    
    def load_panel_data(self):
        """載入持久化數據"""
        try:
            if Path(PANEL_DATA_FILE).exists():
                with open(PANEL_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.panel_message_id = data.get('message_id')
                    self.panel_channel_id = data.get('channel_id')
                    self.recent_events = data.get('events', [])[-5:]  # 只保留最近5條
        except Exception as e:
            print(f"⚠️ 載入面板數據失敗: {e}")
    
    def save_panel_data(self):
        """保存持久化數據"""
        try:
            Path(PANEL_DATA_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(PANEL_DATA_FILE, 'w', encoding='utf-8') as f:
                data = {
                    'message_id': self.panel_message_id,
                    'channel_id': self.panel_channel_id,
                    'events': self.recent_events[-5:]  # 只保留最近5條
                }
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存面板數據失敗: {e}")
    
    async def record_event(self, event_type: str, user_id: int, user_name: str, details: str = ""):
        """記錄事件"""
        try:
            event = {
                'type': event_type,
                'user_id': user_id,
                'user_name': user_name,
                'details': details,
                'timestamp': datetime.now().isoformat()
            }
            
            self.recent_events.append(event)
            # 只保留最近5條
            if len(self.recent_events) > 5:
                self.recent_events = self.recent_events[-5:]
            
            self.save_panel_data()
        except Exception as e:
            print(f"❌ 記錄事件失敗: {e}")
    
    @tasks.loop(minutes=30)  # 每30分鐘更新一次
    async def update_locker_panel(self):
        """更新置物櫃概況面板"""
        try:
            if not Path(DB_PATH).exists():
                return
            
            # 計算統計數據
            stats = await self.get_locker_statistics()
            
            # 生成embed
            embed = await self.create_panel_embed(stats)
            
            # 如果消息存在，編輯它；否則發送新的
            if self.panel_message_id and self.panel_channel_id:
                try:
                    channel = self.bot.get_channel(self.panel_channel_id)
                    if channel:
                        message = await channel.fetch_message(self.panel_message_id)
                        await message.edit(embed=embed)
                        print(f"✅ 置物櫃面板已更新 (每30分鐘)")
                except discord.NotFound:
                    print("⚠️ 原面板訊息已被刪除，稍後會重新建立")
                    self.panel_message_id = None
                except Exception as e:
                    print(f"❌ 更新面板失敗: {e}")
        
        except Exception as e:
            print(f"❌ 面板更新任務失敗: {e}")
            traceback.print_exc()
    
    @update_locker_panel.before_loop
    async def before_update(self):
        """等待機器人準備好"""
        await self.bot.wait_until_ready()
    
    async def get_locker_statistics(self) -> dict:
        """獲取置物櫃統計數據"""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            stats = {
                'total_plants': 0,
                'growing_plants': 0,
                'ready_plants': 0,
                'unique_users': 0,
                'total_inventory_items': 0
            }
            
            # 植物統計
            try:
                c.execute("SELECT COUNT(*), COUNT(CASE WHEN status='harvested' THEN 1 END) FROM cannabis_plants")
                result = c.fetchone()
                if result:
                    stats['total_plants'] = result[0]
                    stats['ready_plants'] = result[1]
                    stats['growing_plants'] = stats['total_plants'] - stats['ready_plants']
            except:
                pass
            
            # 用戶統計
            try:
                c.execute("SELECT COUNT(DISTINCT user_id) FROM cannabis_plants")
                result = c.fetchone()
                if result:
                    stats['unique_users'] = result[0]
            except:
                pass
            
            # 庫存統計
            try:
                c.execute("SELECT COUNT(*) FROM cannabis_inventory")
                result = c.fetchone()
                if result:
                    stats['total_inventory_items'] = result[0]
            except:
                pass
            
            conn.close()
            return stats
        
        except Exception as e:
            print(f"❌ 獲取統計失敗: {e}")
            return {}
    
    async def create_panel_embed(self, stats: dict) -> discord.Embed:
        """生成面板embed"""
        embed = discord.Embed(
            title="📦 置物櫃概況面板",
            description="實時更新的置物櫃統計信息",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        # 統計數據
        embed.add_field(
            name="📊 實時統計",
            value=(
                f"🌱 總植物數: **{stats.get('total_plants', 0)}**\n"
                f"  └─ 生長中: {stats.get('growing_plants', 0)}\n"
                f"  └─ 可收割: {stats.get('ready_plants', 0)}\n"
                f"👥 活躍用戶: **{stats.get('unique_users', 0)}**\n"
                f"📦 庫存項目: **{stats.get('total_inventory_items', 0)}**"
            ),
            inline=False
        )
        
        # 最近5次事件
        if self.recent_events:
            events_text = ""
            for idx, event in enumerate(reversed(self.recent_events), 1):
                event_emoji = EVENTS.get(event['type'], '•')
                event_time = datetime.fromisoformat(event['timestamp'])
                time_ago = self.get_time_ago(event_time)
                
                detail_str = f" - {event['details']}" if event['details'] else ""
                events_text += f"{idx}. {event_emoji} **{event['user_name']}** {time_ago}{detail_str}\n"
            
            embed.add_field(
                name="🎯 最近事件",
                value=events_text.strip(),
                inline=False
            )
        else:
            embed.add_field(
                name="🎯 最近事件",
                value="暫無事件記錄",
                inline=False
            )
        
        embed.set_footer(text="每30分鐘自動更新一次")
        
        return embed
    
    def get_time_ago(self, dt: datetime) -> str:
        """計算時間差"""
        now = datetime.now()
        delta = now - dt
        
        if delta.total_seconds() < 60:
            return "剛剛"
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() / 60)
            return f"{mins}分鐘前"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours}小時前"
        else:
            days = int(delta.total_seconds() / 86400)
            return f"{days}天前"
    



async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(LockerPanelCog(bot))
    print("✅ [UIBot] 置物櫃實時面板已載入")
