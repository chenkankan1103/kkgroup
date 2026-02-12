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
                test_view = PersonalLockerView(None, None, 123, 456, 789, [])
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
                test_view = PersonalLockerView(self.bot, self, user_id, thread.guild.id, thread.id, plants)
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
            view = PersonalLockerView(self.bot, self, user_id, thread.guild.id, thread.id, plants)
            
            # 發送更新後的消息
            await thread.send(embed=embed, view=view)
            print(f"✅ [Locker Update] 已更新用戶 {user_id} 的置物櫃thread")
            
        except Exception as e:
            print(f"❌ [Locker Update] 更新置物櫃embed失敗: {e}")
            traceback.print_exc()


class PersonalLockerView(discord.ui.View):
    """個人置物櫃交互菜單 - 永久視圖"""
    
    def __init__(self, bot, cog, user_id, guild_id, channel_id, plants, user_panel=None):
        super().__init__(timeout=None)  # 永久視圖，不會過期
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.plants = plants
        self.user_panel = user_panel
        
        # 添加作物資訊按鈕
        crop_info_button = discord.ui.Button(
            label="🌾 作物資訊",
            style=discord.ButtonStyle.success,
            custom_id="crop_info"
        )
        crop_info_button.callback = self.crop_info_callback
        self.add_item(crop_info_button)
        
        # 添加個人物品按鈕
        personal_items_button = discord.ui.Button(
            label="🎒 個人物品",
            style=discord.ButtonStyle.primary,
            custom_id="personal_items"
        )
        personal_items_button.callback = self.personal_items_callback
        self.add_item(personal_items_button)
        
        # 添加返回按鈕
        back_button = discord.ui.Button(
            label="⬅️ 返回",
            style=discord.ButtonStyle.secondary,
            custom_id="back_to_main"
        )
        back_button.callback = self.back_to_main_callback
        self.add_item(back_button)
    
    @discord.ui.button(label="施肥", style=discord.ButtonStyle.success, emoji="💧")
    async def fertilize_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """選擇植物施肥"""
        try:
            await interaction.response.defer()
            
            growing_plants = [p for p in self.plants if p["status"] != "harvested"]
            if not growing_plants:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return
            
            inventory = await get_inventory(self.user_id)
            if not inventory.get("肥料"):
                await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                return
            
            view = SelectPlantForFertilizerView(self.bot, self.user_id, growing_plants)
            embed = discord.Embed(
                title="💧 選擇要施肥的植物",
                description="選擇一棵植物進行施肥",
                color=discord.Color.blue()
            )
            # 更新原來的embed
            await interaction.message.edit(embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="收割", style=discord.ButtonStyle.success, emoji="✂️")
    async def harvest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """選擇植物收割"""
        try:
            await interaction.response.defer()
            
            harvestable = [p for p in self.plants if p["status"] == "harvested"]
            if not harvestable:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return
            
            view = SelectPlantForHarvestView(self.bot, self.user_id, harvestable)
            embed = discord.Embed(
                title="✂️ 選擇要收割的植物",
                description="選擇一棵成熟的植物進行收割",
                color=discord.Color.orange()
            )
            # 更新原來的embed
            await interaction.message.edit(embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="查看肥料", style=discord.ButtonStyle.primary, emoji="🧂")
    async def view_fertilizer(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查看可用肥料"""
        try:
            await interaction.response.defer()
            
            inventory = await get_inventory(self.user_id)
            fertilizers = inventory.get("肥料", {})
            
            embed = discord.Embed(
                title="🧂 可用肥料",
                color=discord.Color.blue()
            )
            
            if not fertilizers:
                embed.description = "你沒有肥料"
            else:
                for fert_name, qty in fertilizers.items():
                    fert_config = CANNABIS_SHOP["肥料"][fert_name]
                    embed.add_field(
                        name=f"{fert_config['emoji']} {fert_name}",
                        value=f"擁有：{qty} 份\n加速：{fert_config['growth_boost']*100:.0f}%",
                        inline=True
                    )
            
            # 添加返回按鈕
            view = PersonalLockerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.plants, self.user_panel)
            embed.set_footer(text="點擊下方按鈕返回主選項")
            
            # 更新原來的embed
            await interaction.message.edit(embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    async def crop_planting_callback(self, interaction: discord.Interaction):
        """作物種植 - 顯示種子選擇介面"""
        try:
            # await interaction.response.defer(ephemeral=True)
            
            # 獲取用戶種子庫存
            try:
                inventory = await get_inventory(self.user_id)
                if not inventory:
                    print(f"⚠️  [Crop Planting] Failed to get inventory for user {self.user_id}")
                    await interaction.response.send_message("❌ 無法獲取庫存資料！請稍後再試。", ephemeral=True)
                    return
            except Exception as inv_error:
                print(f"❌ [Crop Planting] Inventory error for user {self.user_id}: {inv_error}")
                traceback.print_exc()
                await interaction.response.send_message("❌ 獲取庫存時發生錯誤！請聯繫管理員。", ephemeral=True)
                return
            
            seeds = inventory.get("種子", {})
            
            # 檢查是否有種子
            if not seeds or not any(qty > 0 for qty in seeds.values()):
                await interaction.response.send_message("❌ 你沒有種子！請先到商店購買種子。", ephemeral=True)
                return
            
            # 顯示種子選擇界面
            embed = discord.Embed(
                title="🌱 作物種植 - 選擇種子",
                description="選擇一種種子進行種植",
                color=discord.Color.green()
            )
            
            for seed_name, qty in seeds.items():
                if qty > 0:
                    try:
                        config = CANNABIS_SHOP["種子"][seed_name]
                        embed.add_field(
                            name=f"{config['emoji']} {seed_name}",
                            value=f"擁有：{qty} 粒\n成長時間：{config['growth_time']//3600}h\n最大產量：{config['max_yield']}",
                            inline=True
                        )
                    except KeyError:
                        print(f"⚠️  [Crop Planting] Seed type '{seed_name}' not found in CANNABIS_SHOP")
                        continue
            
            view = SelectSeedView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, seeds)
            # 更新原來的embed而不是發送新訊息
            await interaction.response.edit_message(embed=embed, view=view)
            add_log("ui", f"[Crop Planting] Seed selection view updated for user {self.user_id}")
            
        except Exception as e:
            add_log("ui", f"[Crop Planting] Unexpected error for user {self.user_id}: {e}")
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
            except:
                pass
    
    def make_plant_callback(self, seed_name):
        """生成種植回調函數"""
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                # 檢查是否有種子
                has_seed = await remove_inventory(self.user_id, "種子", seed_name, 1)
                if not has_seed:
                    await interaction.followup.send("❌ 你沒有這種種子！", ephemeral=True)
                    return
                
                # 種植
                result = await plant_cannabis(self.user_id, self.guild_id, self.channel_id, seed_name)
                
                if result and not result.get("success") == False:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    embed = discord.Embed(
                        title="🌱 種植成功",
                        description=f"已種植 {seed_name}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="成長時間", value=f"{config['growth_time']//3600} 小時", inline=False)
                    embed.add_field(name="最大產量", value=f"{config['max_yield']} 個", inline=False)
                    
                    # 記錄事件
                    if self.cog:
                        user = await self.bot.fetch_user(self.user_id)
                        await self.cog.record_event(
                            'plant',
                            user,
                            f"種植{seed_name}"
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    # 種植失敗，退還種子
                    await add_inventory(self.user_id, "種子", seed_name, 1)
                    reason = result.get("reason", "未知原因") if result else "未知原因"
                    await interaction.followup.send(f"❌ 種植失敗：{reason}", ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                # 如果發生錯誤，嘗試退還種子
                try:
                    await add_inventory(self.user_id, "種子", seed_name, 1)
                except Exception as refund_error:
                    print(f"⚠️ 退還種子失敗：{refund_error}", file=__import__('sys').stderr)
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback

    async def crop_info_callback(self, interaction: discord.Interaction):
        """作物資訊 - 顯示作物狀態和操作選項"""
        try:
            await interaction.response.defer(ephemeral=True)

            plants = await get_user_plants(self.user_id)
            inventory = await get_inventory(self.user_id)
            seeds = inventory.get("種子", {})
            fertilizers = inventory.get("肥料", {})

            # 分類植物
            growing = [p for p in plants if p["status"] != "harvested"]
            harvested = [p for p in plants if p["status"] == "harvested"]

            embed = discord.Embed(
                title="🌾 作物資訊",
                description=f"已使用 {len(plants)}/5 個位置",
                color=discord.Color.green()
            )

            # 顯示成長中的植物
            if growing:
                embed.add_field(name="🌱 成長中的植物", value="━" * 25, inline=False)
                for idx, plant in enumerate(growing, 1):
                    config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    # 計算進度
                    if plant["status"] == "harvested":
                        progress = 100
                        time_left = "已成熟"
                    else:
                        planted_time = plant["planted_at"]
                        matured_time = plant["matured_at"]
                        now = datetime.now().timestamp()
                        elapsed = now - planted_time
                        total = matured_time - planted_time
                        progress = min(100, (elapsed / total * 100)) if total > 0 else 0
                        remaining = max(0, matured_time - now)
                        hours = int(remaining // 3600)
                        mins = int((remaining % 3600) // 60)
                        time_left = f"{hours}h {mins}m"

                    progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
                    value = f"進度：{progress_bar} {progress:.0f}%\n時間：{time_left}\n施肥：{plant['fertilizer_applied']}次"
                    embed.add_field(name=f"#{idx} {config['emoji']} {plant['seed_type']}", value=value, inline=True)

            # 顯示已成熟的植物
            if harvested:
                embed.add_field(name="✅ 已成熟的植物", value="━" * 25, inline=False)
                for idx, plant in enumerate(harvested, 1):
                    config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                    embed.add_field(
                        name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                        value="準備收割！✂️",
                        inline=True
                    )

            # 創建作物操作視圖，包含選項
            view = CropOperationView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, seeds, plants, growing, harvested)

            embed.set_footer(text="💡 使用下方按鈕進行種植、施肥或收割操作")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def personal_items_callback(self, interaction: discord.Interaction):
        """個人物品 - 顯示物品庫存"""
        try:
            await interaction.response.defer(ephemeral=True)

            inventory = await get_inventory(self.user_id)

            embed = discord.Embed(
                title="🎒 個人物品",
                description="你的物品庫存",
                color=discord.Color.blue()
            )

            # 顯示種子
            if inventory.get("種子"):
                seed_info = ""
                for seed_name, qty in inventory["種子"].items():
                    if qty > 0:
                        config = CANNABIS_SHOP["種子"][seed_name]
                        seed_info += f"{config['emoji']} {seed_name}: {qty} 粒\n"
                if seed_info:
                    embed.add_field(name="🌱 種子", value=seed_info.strip(), inline=True)

            # 顯示肥料
            if inventory.get("肥料"):
                fert_info = ""
                for fert_name, qty in inventory["肥料"].items():
                    if qty > 0:
                        config = CANNABIS_SHOP["肥料"][fert_name]
                        fert_info += f"{config['emoji']} {fert_name}: {qty} 份\n"
                if fert_info:
                    embed.add_field(name="💧 肥料", value=fert_info.strip(), inline=True)

            # 顯示大麻
            if inventory.get("大麻"):
                cannabis_info = ""
                for seed_name, qty in inventory["大麻"].items():
                    if qty > 0:
                        price = CANNABIS_HARVEST_PRICES[seed_name]
                        cannabis_info += f"💰 {seed_name}: {qty} 個 ({price}/個)\n"
                if cannabis_info:
                    embed.add_field(name="📦 大麻", value=cannabis_info.strip(), inline=True)

            if not any(inventory.values()):
                embed.add_field(name="📦 庫存", value="目前沒有任何物品", inline=False)

            # 返回按鈕
            view = PersonalLockerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.plants, self.user_panel)
            embed.set_footer(text="點擊下方按鈕返回主選項")

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def back_to_main_callback(self, interaction: discord.Interaction):
        """返回到主選項"""
        try:
            # 創建主選項embed
            embed = discord.Embed(
                title="📦 個人置物櫃",
                description="使用下方按鈕管理你的作物種植、施肥和收割操作。",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🌱 作物管理",
                value="• 作物種植：開始種植新的作物\n• 施肥：為成長中的植物施肥\n• 收割：收割成熟的作物\n• 查看肥料：檢查你的肥料庫存",
                inline=False
            )
            
            embed.set_footer(text="💡 這個視圖是永久的，按鈕不會過期")
            
            # 重新創建PersonalLockerView
            view = PersonalLockerView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.plants, self.user_panel)
            
            # 更新原來的embed
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.response.send_message(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)
            
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.response.send_message(f"❌ 返回時發生錯誤：{str(e)[:100]}", ephemeral=True)



class SelectFertilizerView(discord.ui.View):
    """選擇肥料視圖"""
    
    def __init__(self, bot, user_id, plant, fertilizers):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.user_id = user_id
        self.plant = plant
        
        for fert_name in fertilizers.keys():
            config = CANNABIS_SHOP["肥料"][fert_name]
            button = Button(
                label=f"用 {fert_name}",
                style=discord.ButtonStyle.primary,
                emoji=config["emoji"],
                custom_id=f"apply_fert_{fert_name.replace(' ', '_')}"
            )
            button.callback = self.make_apply_callback(fert_name)
            self.add_item(button)
    
    async def make_apply_callback(self, fert_name):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                # 施肥
                result = await apply_fertilizer(self.user_id, self.plant["id"], fert_name)
                
                if result:
                    # 移除肥料
                    await remove_inventory(self.user_id, "肥料", fert_name, 1)
                    
                    config = CANNABIS_SHOP["肥料"][fert_name]
                    embed = discord.Embed(
                        title="✅ 施肥成功",
                        description=f"已使用 {fert_name} 施肥 {self.plant['seed_type']}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="加速", value=f"{config['growth_boost']*100:.0f}%", inline=False)
                    
                    # 記錄事件
                    if hasattr(self, 'cog'):
                        user = await self.bot.fetch_user(self.user_id)
                        await self.cog.record_event(
                            'fertilize',
                            user,
                            f"為{self.plant['seed_type']}施肥"
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 施肥失敗", ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback


class WeeklySummaryCannabisPanelView(discord.ui.View):
    """周統計面板的大麻系統快速訪問"""
    
    def __init__(self, bot, user_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
    
    @discord.ui.button(label="施肥加速", style=discord.ButtonStyle.primary, emoji="💧", custom_id="weekly_fertilize")
    async def fertilize_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """施肥加速"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            plants = await get_user_plants(self.user_id)
            growing_plants = [p for p in plants if p["status"] != "harvested"]
            
            if not growing_plants:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return
            
            inventory = await get_inventory(self.user_id)
            if not inventory.get("肥料"):
                await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                return
            
            # 顯示植物列表
            embed = discord.Embed(
                title="💧 選擇要施肥的植物",
                color=discord.Color.blue()
            )
            
            for idx, plant in enumerate(growing_plants[:5], 1):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                embed.add_field(
                    name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                    value=f"已施肥：{plant['fertilizer_applied']}次",
                    inline=False
                )
            
            view = SelectPlantForFertilizerView(self.bot, self.user_id, growing_plants)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="收割成熟", style=discord.ButtonStyle.success, emoji="✂️", custom_id="weekly_harvest")
    async def harvest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """收割成熟植物"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            plants = await get_user_plants(self.user_id)
            harvestable = [p for p in plants if p["status"] == "harvested"]
            
            if not harvestable:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return
            
            # 顯示可收割的植物
            embed = discord.Embed(
                title="🔪 選擇要收割的植物",
                color=discord.Color.gold()
            )
            
            for idx, plant in enumerate(harvestable[:5], 1):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                yield_amount = plant.get("harvested_amount", 0)
                embed.add_field(
                    name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                    value=f"產量：{yield_amount}",
                    inline=False
                )
            
            view = SelectPlantForHarvestView(self.bot, self.user_id, harvestable)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="查看狀態", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="weekly_view_plants")
    async def view_plants_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查看植物狀態"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            plants = await get_user_plants(self.user_id)
            
            if not plants:
                await interaction.followup.send("❌ 你還沒有種植任何植物！", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🌱 我的植物狀態",
                color=discord.Color.green()
            )
            
            for idx, plant in enumerate(plants, 1):
                seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                
                # 計算進度
                if plant["status"] == "harvested":
                    progress_text = "✅ 已成熟 100%"
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
                    progress_text = f"{'█' * filled}{'░' * empty} {progress:.0f}%"
                    
                    remaining = max(0, matured_time - now)
                    if remaining > 0:
                        hours = int(remaining // 3600)
                        mins = int((remaining % 3600) // 60)
                        status_info = f"剩餘 {hours}h {mins}m"
                    else:
                        status_info = "✅ 已成熟"
                    
                    progress_text += f"\n{status_info}"
                
                value = (
                    f"🌾 種類：{plant['seed_type']}\n"
                    f"📊 進度：{progress_text}\n"
                    f"💧 施肥：{plant['fertilizer_applied']}次"
                )
                embed.add_field(name=f"#{idx} {seed_config['emoji']}", value=value, inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


class CropPlantingView(discord.ui.View):
    """種植作物選擇視圖"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, options):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id

        # 添加種子選擇下拉選單
        if options:
            select = discord.ui.Select(
                placeholder="選擇要種植的種子...",
                options=options[:25],  # Discord限制最多25個選項
                custom_id="seed_select"
            )
            select.callback = self.seed_select_callback
            self.add_item(select)

    async def seed_select_callback(self, interaction: discord.Interaction):
        """處理種子選擇"""
        try:
            await interaction.response.defer(ephemeral=True)

            selected_seed = interaction.data["values"][0]

            # 檢查是否有種子
            has_seed = await remove_inventory(self.user_id, "種子", selected_seed, 1)
            if not has_seed:
                await interaction.followup.send("❌ 你沒有這種種子！", ephemeral=True)
                return

            # 種植
            result = await plant_cannabis(self.user_id, self.guild_id, self.channel_id, selected_seed)

            if result and not result.get("success") == False:
                config = CANNABIS_SHOP["種子"][selected_seed]
                embed = discord.Embed(
                    title="🌱 種植成功",
                    description=f"已種植 {selected_seed}",
                    color=discord.Color.green()
                )
                embed.add_field(name="成長時間", value=f"{config['growth_time']//3600} 小時", inline=False)
                embed.add_field(name="最大產量", value=f"{config['max_yield']} 個", inline=False)

                # 記錄事件
                if self.cog:
                    await self.cog.record_event(
                        'plant',
                        interaction.user,
                        f"種植{selected_seed}"
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                # 種植失敗，退還種子
                await add_inventory(self.user_id, "種子", selected_seed, 1)
                reason = result.get("reason", "未知原因") if result else "未知原因"
                await interaction.followup.send(f"❌ 種植失敗：{reason}", ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            # 如果發生錯誤，嘗試退還種子
            if 'selected_seed' in locals():
                try:
                    await add_inventory(self.user_id, "種子", selected_seed, 1)
                except Exception as refund_error:
                    print(f"⚠️ 退還種子失敗：{refund_error}", file=__import__('sys').stderr)
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


class SelectSeedView(discord.ui.View):
    """選擇要種植的種子"""
    
    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        
        for idx, (seed_name, qty) in enumerate(seeds.items(), 1):
            if qty > 0:
                config = CANNABIS_SHOP["種子"][seed_name]
                button = Button(
                    label=f"種植 {seed_name}",
                    style=discord.ButtonStyle.success,
                    emoji=config["emoji"],
                    custom_id=f"plant_seed_{seed_name.replace(' ', '_')}"
                )
                button.callback = self.make_plant_callback(seed_name)
                self.add_item(button)
    
    def make_plant_callback(self, seed_name):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                # 檢查是否有種子
                has_seed = await remove_inventory(self.user_id, "種子", seed_name, 1)
                if not has_seed:
                    await interaction.followup.send("❌ 你沒有這種種子！", ephemeral=True)
                    return
                
                # 種植
                result = await plant_cannabis(self.user_id, self.guild_id, self.channel_id, seed_name)
                
                if result and not result.get("success") == False:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    embed = discord.Embed(
                        title="🌱 種植成功",
                        description=f"已種植 {seed_name}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="成長時間", value=f"{config['growth_time']//3600} 小時", inline=False)
                    embed.add_field(name="最大產量", value=f"{config['max_yield']} 個", inline=False)
                    
                    # 記錄事件
                    if self.cog:
                        user = await self.bot.fetch_user(self.user_id)
                        await self.cog.record_event(
                            'plant',
                            user,
                            f"種植{seed_name}"
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    # 種植失敗，退還種子
                    await add_inventory(self.user_id, "種子", seed_name, 1)
                    reason = result.get("reason", "未知原因") if result else "未知原因"
                    await interaction.followup.send(f"❌ 種植失敗：{reason}", ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                # 如果發生錯誤，嘗試退還種子
                try:
                    await add_inventory(self.user_id, "種子", seed_name, 1)
                except Exception as refund_error:
                    print(f"⚠️ 退還種子失敗：{refund_error}", file=__import__('sys').stderr)
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback


class CropOperationView(discord.ui.View):
    """作物操作視圖 - 提供種植、施肥、收割選項"""

    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds, plants, growing, harvested):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.seeds = seeds
        self.plants = plants
        self.growing = growing
        self.harvested = harvested

        # 添加種植按鈕（如果有種子且有空位）
        if seeds and len(plants) < 5:
            plant_button = discord.ui.Button(
                label="🌱 種植",
                style=discord.ButtonStyle.success,
                custom_id="crop_planting"
            )
            plant_button.callback = self.crop_planting_callback
            self.add_item(plant_button)

        # 添加施肥按鈕（如果有成長中的植物且有肥料）
        if growing:
            fertilizer_button = discord.ui.Button(
                label="💧 施肥",
                style=discord.ButtonStyle.primary,
                custom_id="crop_fertilize"
            )
            fertilizer_button.callback = self.crop_fertilize_callback
            self.add_item(fertilizer_button)

        # 添加收割按鈕（如果有成熟的植物）
        if harvested:
            harvest_button = discord.ui.Button(
                label="✂️ 收割",
                style=discord.ButtonStyle.danger,
                custom_id="crop_harvest"
            )
            harvest_button.callback = self.crop_harvest_callback
            self.add_item(harvest_button)

    async def crop_planting_callback(self, interaction: discord.Interaction):
        """種植作物"""
        try:
            await interaction.response.defer(ephemeral=True)

            # 創建種子選擇下拉選單
            options = []
            for seed_name, qty in self.seeds.items():
                if qty > 0:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    options.append(discord.SelectOption(
                        label=f"{config['emoji']} {seed_name}",
                        description=f"數量: {qty} | 時間: {config['growth_time']//3600}小時",
                        value=seed_name
                    ))

            if not options:
                await interaction.followup.send("❌ 你沒有任何種子！", ephemeral=True)
                return

            view = CropPlantingView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, options)
            embed = discord.Embed(
                title="🌱 選擇要種植的種子",
                description="從下方選單選擇一種子進行種植",
                color=discord.Color.green()
            )

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def crop_fertilize_callback(self, interaction: discord.Interaction):
        """施肥作物"""
        try:
            await interaction.response.defer(ephemeral=True)

            # 檢查是否有肥料
            inventory = await get_inventory(self.user_id)
            fertilizers = inventory.get("肥料", {})

            if not fertilizers:
                await interaction.followup.send("❌ 你沒有任何肥料！", ephemeral=True)
                return

            # 創建植物選擇下拉選單
            options = []
            for plant in self.growing:
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                options.append(discord.SelectOption(
                    label=f"{config['emoji']} {plant['seed_type']}",
                    description=f"施肥次數: {plant['fertilizer_applied']}",
                    value=str(plant['id'])
                ))

            if not options:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return

            view = SelectPlantForFertilizerView(self.bot, self.user_id, self.growing)
            embed = discord.Embed(
                title="💧 選擇要施肥的植物",
                description="選擇一棵植物進行施肥",
                color=discord.Color.blue()
            )

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)

    async def crop_harvest_callback(self, interaction: discord.Interaction):
        """收割作物"""
        try:
            await interaction.response.defer(ephemeral=True)

            # 創建植物選擇下拉選單
            options = []
            for plant in self.harvested:
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                options.append(discord.SelectOption(
                    label=f"{config['emoji']} {plant['seed_type']}",
                    description="已成熟，準備收割",
                    value=str(plant['id'])
                ))

            if not options:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return

            view = SelectPlantForHarvestView(self.bot, self.user_id, self.harvested)
            embed = discord.Embed(
                title="✂️ 選擇要收割的植物",
                description="選擇一棵成熟的植物進行收割",
                color=discord.Color.orange()
            )

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


class SelectPlantForFertilizerView(discord.ui.View):
    """選擇植物進行施肥的視圖"""

    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.user_id = user_id
        self.plants = plants

        # 創建選擇選項
        options = []
        for plant in plants:
            config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            options.append(discord.SelectOption(
                label=f"{config['emoji']} {plant['seed_type']}",
                description=f"施肥次數: {plant['fertilizer_applied']}",
                value=str(plant['id'])
            ))

        if options:
            select = discord.ui.Select(
                placeholder="選擇要施肥的植物...",
                options=options[:25],  # Discord限制最多25個選項
                custom_id="select_plant_fertilize"
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        """處理植物選擇"""
        try:
            await interaction.response.defer(ephemeral=True)

            plant_id = int(interaction.data['values'][0])
            plant = next((p for p in self.plants if p['id'] == plant_id), None)

            if not plant:
                await interaction.followup.send("❌ 找不到選擇的植物！", ephemeral=True)
                return

            # 檢查肥料
            inventory = await get_inventory(self.user_id)
            fertilizers = inventory.get("肥料", {})

            if not fertilizers:
                await interaction.followup.send("❌ 你沒有任何肥料！", ephemeral=True)
                return

            # 應用肥料
            result = await apply_fertilizer(self.user_id, plant_id)

            if result and result.get("success"):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                embed = discord.Embed(
                    title="💧 施肥成功",
                    description=f"已為 {config['emoji']} {plant['seed_type']} 施肥",
                    color=discord.Color.green()
                )
                embed.add_field(name="施肥次數", value=f"{result['fertilizer_applied']} 次", inline=True)
                embed.add_field(name="效果", value="成長速度加快 20%", inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                reason = result.get("reason", "未知原因") if result else "未知原因"
                await interaction.followup.send(f"❌ 施肥失敗：{reason}", ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


class SelectPlantForHarvestView(discord.ui.View):
    """選擇植物進行收割的視圖"""

    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=None)  # 永久視圖
        self.bot = bot
        self.user_id = user_id
        self.plants = plants

        # 創建選擇選項
        options = []
        for plant in plants:
            config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            yield_amount = plant.get("yield", config["max_yield"])
            options.append(discord.SelectOption(
                label=f"{config['emoji']} {plant['seed_type']}",
                description=f"產量: {yield_amount} 個",
                value=str(plant['id'])
            ))

        if options:
            select = discord.ui.Select(
                placeholder="選擇要收割的植物...",
                options=options[:25],  # Discord限制最多25個選項
                custom_id="select_plant_harvest"
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        """處理植物選擇"""
        try:
            await interaction.response.defer(ephemeral=True)

            plant_id = int(interaction.data['values'][0])
            plant = next((p for p in self.plants if p['id'] == plant_id), None)

            if not plant:
                await interaction.followup.send("❌ 找不到選擇的植物！", ephemeral=True)
                return

            # 收割植物
            result = await harvest_plant(self.user_id, plant_id)

            if result and result.get("success"):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                yield_amount = result.get("yield", 0)
                price = CANNABIS_HARVEST_PRICES[plant["seed_type"]]
                total_value = yield_amount * price

                embed = discord.Embed(
                    title="✂️ 收割成功",
                    description=f"已收割 {config['emoji']} {plant['seed_type']}",
                    color=discord.Color.gold()
                )
                embed.add_field(name="收割數量", value=f"{yield_amount} 個", inline=True)
                embed.add_field(name="單價", value=f"{price} KK幣", inline=True)
                embed.add_field(name="總價值", value=f"{total_value} KK幣", inline=True)

                # 更新用戶KK幣
                await update_user_kkcoin(self.user_id, total_value)

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                reason = result.get("reason", "未知原因") if result else "未知原因"
                await interaction.followup.send(f"❌ 收割失敗：{reason}", ephemeral=True)

        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(PersonalLockerCog(bot))
