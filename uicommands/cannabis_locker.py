"""個人置物櫃 - 大麻種植管理 UI + 實時面板"""
import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import traceback
from datetime import datetime, timedelta
from pathlib import Path
import json
import aiosqlite
from collections import deque
from status_dashboard import add_log
from shop_commands.merchant.cannabis_farming import (
    get_user_plants, plant_cannabis, apply_fertilizer, harvest_plant, get_inventory, remove_inventory, add_inventory
)
from shop_commands.merchant.cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
from shop_commands.merchant.database import update_user_kkcoin, get_user_kkcoin

# 导入拆分的View类
from .views.personal_locker import PersonalLockerView, WeeklySummaryCannabisPanelView
from .views.crop_operations import CropOperationView, CropPlantingView, SelectSeedView
from .views.selection_views import SelectPlantForFertilizerView, SelectPlantForHarvestView, SelectFertilizerView

# 配置
DB_PATH = './shop_commands/merchant/cannabis.db'
PANEL_DATA_FILE = './shop_commands/locker_panel_data.json'


class PersonalLockerCog(commands.Cog):
    """個人置物櫃 - 大麻種植管理 + 伺服器面板"""

    def __init__(self, bot):
        self.bot = bot
        # 面板相關
        self.panel_message_id = None
        self.panel_channel_id = None
        self.recent_events = deque(maxlen=5)  # 最近5個事件
        # Button check tracking
        self.button_check_failures = 0
        self.last_button_check = None
        self.load_panel_data()
        # 啟動面板更新任務
        self.update_panel_task.start()
        self.button_health_check.start()

    def cog_unload(self):
        """Cog 卸載時停止任務"""
        self.update_panel_task.cancel()
        self.button_health_check.cancel()

    def load_panel_data(self):
        """載入持久化的面板數據"""
        try:
            if Path(PANEL_DATA_FILE).exists():
                with open(PANEL_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.panel_message_id = data.get('message_id')
                    self.panel_channel_id = data.get('channel_id')
                    self.recent_events = deque(data.get('events', []), maxlen=5)
        except Exception as e:
            print(f"⚠️  載入面板數據失敗: {e}")

    def save_panel_data(self):
        """保存面板數據"""
        try:
            Path(PANEL_DATA_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(PANEL_DATA_FILE, 'w', encoding='utf-8') as f:
                data = {
                    'message_id': self.panel_message_id,
                    'channel_id': self.panel_channel_id,
                    'events': list(self.recent_events)
                }
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存面板數據失敗: {e}")

    async def record_event(self, event_type: str, user: discord.User, details: str = ""):
        """記錄事件到面板"""
        try:
            event = {
                'type': event_type,
                'user_id': user.id,
                'user_name': user.display_name,
                'details': details,
                'timestamp': datetime.now().isoformat()
            }
            self.recent_events.append(event)
            self.save_panel_data()
        except Exception as e:
            add_log("ui", f"記錄事件失敗: {e}")

    @tasks.loop(minutes=30)
    async def update_panel_task(self):
        """每30分鐘更新面板"""
        try:
            if not self.panel_message_id or not self.panel_channel_id:
                return

            # 計算統計
            stats = await self.get_locker_stats()
            embed = await self.create_panel_embed(stats)

            # 嘗試編輯訊息
            try:
                channel = self.bot.get_channel(self.panel_channel_id)
                if channel:
                    message = await channel.fetch_message(self.panel_message_id)
                    await message.edit(embed=embed)
                    print(f"✅ 置物櫃面板已更新")
            except discord.NotFound:
                print(f"⚠️  面板訊息已被刪除")
                self.panel_message_id = None
        except Exception as e:
            print(f"❌ 面板更新失敗: {e}")

    @tasks.loop(minutes=15)
    async def button_health_check(self):
        """每15分鐘檢查按鈕健康狀態"""
        try:
            self.last_button_check = datetime.now()

            # 檢查 PersonalLockerView 類是否正確定義
            if not hasattr(PersonalLockerView, 'crop_planting_callback'):
                print(f"❌ [Button Health Check] PersonalLockerView.crop_planting_callback not found!")
                self.button_check_failures += 1
                return

            # 檢查按鈕是否在初始化中正確添加
            try:
                # 創建一個測試實例來檢查按鈕
                test_view = PersonalLockerView(None, None, 123, 456, 789, [], None)
                crop_buttons = [item for item in test_view.children if getattr(item, 'custom_id', None) == 'crop_planting']
                if not crop_buttons:
                    print(f"⚠️  [Button Health Check] Crop planting button not found in view")
                    self.button_check_failures += 1
                    return
            except Exception as e:
                print(f"❌ [Button Health Check] Error creating test view: {e}")
                self.button_check_failures += 1
                return

            # 檢查成功
            print(f"✅ [Button Health Check] Crop planting button is properly configured")
            self.button_check_failures = 0

        except Exception as e:
            print(f"❌ [Button Health Check] Error during check: {e}")
            self.button_check_failures += 1
            traceback.print_exc()

    @button_health_check.before_loop
    async def before_button_health_check(self):
        """等待機器人準備"""
        await self.bot.wait_until_ready()

    @update_panel_task.before_loop
    async def before_update_panel(self):
        """等待機器人準備"""
        await self.bot.wait_until_ready()

    async def get_locker_stats(self) -> dict:
        """獲取置物櫃統計"""
        stats = {
            'total_plants': 0,
            'growing_plants': 0,
            'ready_plants': 0,
            'unique_users': 0,
            'total_inventory_items': 0
        }

        if not Path(DB_PATH).exists():
            return stats

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # 植物統計
                async with db.execute(
                    "SELECT COUNT(*), COUNT(CASE WHEN status='harvested' THEN 1 END) FROM cannabis_plants"
                ) as cursor:
                    result = await cursor.fetchone()
                    if result:
                        stats['total_plants'] = result[0]
                        stats['ready_plants'] = result[1]
                        stats['growing_plants'] = stats['total_plants'] - stats['ready_plants']

                # 用戶統計
                async with db.execute(
                    "SELECT COUNT(DISTINCT user_id) FROM cannabis_plants"
                ) as cursor:
                    result = await cursor.fetchone()
                    if result:
                        stats['unique_users'] = result[0]

                # 庫存統計
                async with db.execute(
                    "SELECT COUNT(*) FROM cannabis_inventory"
                ) as cursor:
                    result = await cursor.fetchone()
                    if result:
                        stats['total_inventory_items'] = result[0]
        except Exception as e:
            print(f"❌ 獲取統計失敗: {e}")

        return stats

    async def create_panel_embed(self, stats: dict) -> discord.Embed:
        """生成面板embed"""
        embed = discord.Embed(
            title="📦 置物櫃概況面板",
            description="實時伺服器統計",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )

        # 統計字段
        embed.add_field(
            name="📊 統計數據",
            value=(
                f"🌱 總植物: **{stats['total_plants']}**\n"
                f"  ├─ 生長中: {stats['growing_plants']}\n"
                f"  └─ 可收割: {stats['ready_plants']}\n"
                f"👥 活躍用戶: **{stats['unique_users']}**\n"
                f"📦 庫存項目: **{stats['total_inventory_items']}**"
            ),
            inline=False
        )

        # 最近事件
        if self.recent_events:
            events_text = ""
            for idx, event in enumerate(reversed(self.recent_events), 1):
                time_ago = self.get_time_ago(
                    datetime.fromisoformat(event['timestamp'])
                )
                detail_str = f" - {event['details']}" if event['details'] else ""
                events_text += f"{idx}. **{event['user_name']}** {time_ago}{detail_str}\n"

            embed.add_field(
                name="🎯 最近事件",
                value=events_text.strip(),
                inline=False
            )
        else:
            embed.add_field(
                name="🎯 最近事件",
                value="暫無事件",
                inline=False
            )

        embed.set_footer(text="每30分鐘自動更新")
        return embed

    def get_time_ago(self, dt: datetime) -> str:
        """計算時間差"""
        delta = datetime.now() - dt

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

    @commands.Cog.listener()
    async def on_ready(self):
        print("[PersonalLocker] 個人置物櫃已載入")
        # 在bot啟動時檢查並更新所有置物櫃視圖
        await self.update_all_locker_views()

    async def update_all_locker_views(self):
        """在bot啟動時檢查並更新所有置物櫃視圖"""
        try:
            print("🔄 [Locker Update] 開始檢查並更新所有置物櫃視圖...")

            updated_count = 0

            # 獲取所有活躍的置物櫃thread
            for guild in self.bot.guilds:
                # 查找置物櫃頻道（假設是論壇頻道）
                locker_channel = None
                for channel in guild.channels:
                    if hasattr(channel, 'type') and channel.type == discord.ChannelType.forum:
                        # 檢查頻道名稱是否包含置物櫃相關關鍵字
                        if '置物櫃' in channel.name or 'locker' in channel.name.lower():
                            locker_channel = channel
                            break

                if not locker_channel:
                    continue

                print(f"📂 [Locker Update] 檢查頻道: {locker_channel.name}")

                # 獲取活躍的置物櫃threads
                try:
                    active_threads = []

                    # 獲取活躍的threads
                    async for thread in locker_channel.active_threads:
                        if '置物櫃' in thread.name or '的置物櫃' in thread.name:
                            active_threads.append(thread)

                    # 也檢查最近的已歸檔threads
                    async for thread in locker_channel.archived_threads(limit=20):
                        if '置物櫃' in thread.name or '的置物櫃' in thread.name:
                            active_threads.append(thread)

                    print(f"🧵 [Locker Update] 找到 {len(active_threads)} 個置物櫃threads")

                    for thread in active_threads:
                        try:
                            updated = await self.update_single_locker_view(thread)
                            if updated:
                                updated_count += 1
                        except Exception as thread_error:
                            print(f"❌ [Locker Update] 處理thread {thread.name} 時出錯: {thread_error}")
                            continue

                except Exception as channel_error:
                    print(f"❌ [Locker Update] 處理頻道 {locker_channel.name} 時出錯: {channel_error}")
                    continue

            print(f"✅ [Locker Update] 置物櫃視圖更新完成，共更新 {updated_count} 個threads")

        except Exception as e:
            print(f"❌ [Locker Update] 置物櫃視圖更新任務出錯: {e}")
            traceback.print_exc()

    async def update_single_locker_view(self, thread):
        """檢查並更新單個置物櫃thread的視圖"""
        try:
            # 從thread名稱提取用戶ID
            user_id = None
            if '的置物櫃' in thread.name:
                try:
                    # 獲取thread的擁有者
                    if hasattr(thread, 'owner_id') and thread.owner_id:
                        user_id = thread.owner_id
                    else:
                        print(f"⚠️ [Locker Update] Thread {thread.name} 沒有owner_id")
                        return False
                except Exception as parse_error:
                    print(f"⚠️ [Locker Update] 解析thread名稱失敗 '{thread.name}': {parse_error}")
                    return False

            if not user_id:
                return False

            # 獲取最新的置物櫃消息
            try:
                # 獲取最近的幾條消息
                messages = []
                async for msg in thread.history(limit=5):
                    messages.append(msg)

                if not messages:
                    print(f"⚠️ [Locker Update] Thread {thread.name} 沒有消息")
                    return False

                # 找到最新的置物櫃embed消息
                locker_message = None
                for msg in messages:
                    if msg.embeds and len(msg.embeds) > 0:
                        embed = msg.embeds[0]
                        if '置物櫃' in embed.title or 'Locker' in embed.title:
                            locker_message = msg
                            break

                if not locker_message:
                    print(f"⚠️ [Locker Update] Thread {thread.name} 沒有找到置物櫃embed")
                    return False

                # 檢查當前按鈕數量是否與最新版本匹配
                current_button_count = 0
                if locker_message.components:
                    for component in locker_message.components:
                        if hasattr(component, 'children'):
                            current_button_count += len(component.children)

                # 創建一個測試視圖來比較按鈕數量
                plants = await get_user_plants(user_id)
                test_view = PersonalLockerView(self.bot, self, user_id, thread.guild.id, thread.id, plants, None)
                expected_button_count = len(test_view.children)

                # 如果按鈕數量不匹配，需要更新
                if current_button_count != expected_button_count:
                    print(f"🔄 [Locker Update] Thread {thread.name} 按鈕數量不匹配 ({current_button_count} vs {expected_button_count})，需要更新")
                    await self.send_updated_locker_embed(thread, user_id)
                    return True
                else:
                    print(f"✅ [Locker Update] Thread {thread.name} 按鈕數量正確 ({current_button_count})")
                    return False

            except Exception as msg_error:
                print(f"❌ [Locker Update] 檢查thread消息失敗 {thread.name}: {msg_error}")
                return False

        except Exception as e:
            print(f"❌ [Locker Update] 檢查thread失敗 {thread.name}: {e}")
            return False

    async def send_updated_locker_embed(self, thread, user_id):
        """發送更新後的置物櫃embed"""
        try:
            # 獲取用戶數據
            plants = await get_user_plants(user_id)
            inventory = await get_inventory(user_id)

            # 創建用戶對象（用於顯示名稱）
            try:
                user = await self.bot.fetch_user(user_id)
                user_name = user.name
            except:
                user_name = f"用戶{user_id}"

            embed = discord.Embed(
                title=f"📦 {user_name} 的個人置物櫃",
                description="你的大麻種植狀態",
                color=discord.Color.green()
            )

            if not plants:
                embed.add_field(
                    name="🌱 沒有種植中的植物",
                    value="還未開始種植！",
                    inline=False
                )
            else:
                for idx, plant in enumerate(plants, 1):
                    seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]

                    # 計算進度和剩餘時間
                    if plant["status"] == "harvested":
                        status_text = "✅ 已成熟，可以收割！"
                        progress_bar = "████████████████████ 100%"
                    else:
                        planted_time = plant["planted_at"] if isinstance(plant["planted_at"], float) else plant["planted_at"]
                        matured_time = plant["matured_at"] if isinstance(plant["matured_at"], float) else plant["matured_at"]

                        if isinstance(planted_time, str):
                            planted_time = datetime.fromisoformat(planted_time).timestamp()
                        if isinstance(matured_time, str):
                            matured_time = datetime.fromisoformat(matured_time).timestamp()

                        now = datetime.now().timestamp()
                        elapsed = now - planted_time
                        total = matured_time - planted_time
                        progress = min(100, (elapsed / total * 100)) if total > 0 else 0

                        filled = int(progress / 5)
                        empty = 20 - filled
                        progress_bar = "█" * filled + "░" * empty + f" {progress:.0f}%"

                        remaining = max(0, matured_time - now)
                        if remaining > 0:
                            hours = int(remaining // 3600)
                            mins = int((remaining % 3600) // 60)
                            status_text = f"🌱 成長中... 剩餘 {hours}h {mins}m"
                        else:
                            status_text = "✅ 已成熟，可以收割！"

                    field_value = (
                        f"種子：{seed_config['emoji']} {plant['seed_type']}\n"
                        f"進度：{progress_bar}\n"
                        f"狀態：{status_text}\n"
                        f"施肥：{plant['fertilizer_applied']} 次"
                    )

                    embed.add_field(
                        name=f"植物 #{plant['id']}",
                        value=field_value,
                        inline=False
                    )

            # 添加庫存信息
            if inventory.get("種子"):
                seeds_info = ""
                for seed_name, qty in inventory["種子"].items():
                    seeds_info += f"  🌱 {seed_name} x{qty}\n"
                embed.add_field(
                    name="🌾 種子庫存",
                    value=seeds_info.strip(),
                    inline=True
                )

            if inventory.get("肥料"):
                fert_info = ""
                for fert_name, qty in inventory["肥料"].items():
                    fert_info += f"  💧 {fert_name} x{qty}\n"
                embed.add_field(
                    name="💧 肥料庫存",
                    value=fert_info.strip(),
                    inline=True
                )

            cannabis_info = ""
            if inventory.get("大麻"):
                for seed_name, qty in inventory["大麻"].items():
                    price = CANNABIS_HARVEST_PRICES[seed_name]
                    cannabis_info += f"  💰 {seed_name} x{qty} ({price}/個)\n"
                embed.add_field(
                    name="📦 大麻庫存",
                    value=cannabis_info.strip(),
                    inline=False
                )

            # 創建按鈕視圖
            view = PersonalLockerView(self.bot, self, user_id, thread.guild.id, thread.id, plants, self)

            # 發送更新後的消息
            await thread.send(embed=embed, view=view)
            print(f"✅ [Locker Update] 已更新用戶 {user_id} 的置物櫃thread")

        except Exception as e:
            print(f"❌ [Locker Update] 更新置物櫃embed失敗: {e}")
            traceback.print_exc()


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(PersonalLockerCog(bot))
