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
            print(f"❌ 記錄事件失敗: {e}")
    
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
            if not hasattr(PersonalLockerView, 'plant_seed_button'):
                print(f"❌ [Button Health Check] PersonalLockerView.plant_seed_button not found!")
                self.button_check_failures += 1
                return
            
            # 檢查按鈕裝飾器是否存在
            button_method = getattr(PersonalLockerView, 'plant_seed_button', None)
            if not button_method or not hasattr(button_method, '__discord_ui_model_type__'):
                print(f"⚠️  [Button Health Check] plant_seed_button missing discord.ui.button decorator")
                self.button_check_failures += 1
                return
            
            # 檢查成功
            print(f"✅ [Button Health Check] Plant Seed button is properly configured")
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
    
    @commands.command(name="置物櫃", description="📦 打開個人置物櫃查看種植狀態")
    async def personal_locker(self, ctx):
        """查看個人置物櫃"""
        try:
            user_id = ctx.author.id
            plants = await get_user_plants(user_id)
            inventory = await get_inventory(user_id)
            
            embed = discord.Embed(
                title=f"📦 {ctx.author.name} 的個人置物櫃",
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
            
            # 添加按鈕
            try:
                view = PersonalLockerView(self.bot, self, user_id, ctx.guild.id if ctx.guild else 0, ctx.channel.id, plants)
                # 驗證按鈕是否正確加載
                if not hasattr(view, 'plant_seed_button'):
                    print(f"⚠️  [Locker] PersonalLockerView created without plant_seed_button!")
                    await ctx.send(embed=embed)  # Send without buttons as fallback
                    await ctx.send("⚠️  置物櫃已開啟，但部分按鈕可能無法使用。請聯繫管理員。", delete_after=10)
                    return
                
                await ctx.send(embed=embed, view=view)
                print(f"✅ [Locker] Personal locker opened for user {user_id} with all buttons")
            except Exception as view_error:
                print(f"❌ [Locker] Failed to create view for user {user_id}: {view_error}")
                traceback.print_exc()
                # Fallback: send embed without view
                await ctx.send(embed=embed)
                await ctx.send("⚠️  置物櫃按鈕載入失敗！請稍後再試或聯繫管理員。", delete_after=15)
            
        except Exception as e:
            print(f"❌ [Locker] Error in personal_locker command: {e}")
            traceback.print_exc()
            await ctx.send(f"❌ 發生錯誤：{str(e)[:100]}")
    
    @commands.command(name="建置物櫃面板", description="🔧 在此頻道建立置物櫃概況面板")
    async def create_panel(self, ctx):
        """建立置物櫃概況面板"""
        try:
            if not ctx.author.guild_permissions.administrator:
                await ctx.send("❌ 需要管理員權限", ephemeral=True)
                return
            
            # 計算統計
            stats = await self.get_locker_stats()
            embed = await self.create_panel_embed(stats)
            
            # 發送訊息
            panel_message = await ctx.send(embed=embed)
            
            # 保存訊息信息
            self.panel_message_id = panel_message.id
            self.panel_channel_id = ctx.channel.id
            self.save_panel_data()
            
            await ctx.send(
                f"✅ 置物櫃面板已建立！\n"
                f"📍 訊息ID: {panel_message.id}\n"
                f"🔄 每30分鐘自動更新一次"
            )
        
        except Exception as e:
            await ctx.send(f"❌ 建立面板失敗: {str(e)[:100]}")
            traceback.print_exc()


class PersonalLockerView(discord.ui.View):
    """個人置物櫃交互菜單"""
    
    def __init__(self, bot, cog, user_id, guild_id, channel_id, plants):
        super().__init__(timeout=None)  # No timeout to prevent button expiration
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.plants = plants
    
    @discord.ui.button(label="施肥", style=discord.ButtonStyle.success, emoji="💧")
    async def fertilize_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """選擇植物施肥"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            growing_plants = [p for p in self.plants if p["status"] != "harvested"]
            if not growing_plants:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return
            
            inventory = await get_inventory(self.user_id)
            if not inventory.get("肥料"):
                await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                return
            
            view = SelectPlantForFertilizerView(self.bot, self.user_id, growing_plants)
            await interaction.followup.send("選擇要施肥的植物：", view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="收割", style=discord.ButtonStyle.success, emoji="✂️")
    async def harvest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """選擇植物收割"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            harvestable = [p for p in self.plants if p["status"] == "harvested"]
            if not harvestable:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return
            
            view = SelectPlantForHarvestView(self.bot, self.user_id, harvestable)
            await interaction.followup.send("選擇要收割的植物：", view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="查看肥料", style=discord.ButtonStyle.primary, emoji="🧂")
    async def view_fertilizer(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查看可用肥料"""
        try:
            await interaction.response.defer(ephemeral=True)
            
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
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="種植種子", style=discord.ButtonStyle.success, emoji="🌱")
    async def plant_seed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """選擇種子進行種植"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 獲取用戶種子庫存
            try:
                inventory = await get_inventory(self.user_id)
                if not inventory:
                    print(f"⚠️  [Plant Seed Button] Failed to get inventory for user {self.user_id}")
                    await interaction.followup.send("❌ 無法獲取庫存資料！請稍後再試。", ephemeral=True)
                    return
            except Exception as inv_error:
                print(f"❌ [Plant Seed Button] Inventory error for user {self.user_id}: {inv_error}")
                traceback.print_exc()
                await interaction.followup.send("❌ 獲取庫存時發生錯誤！請聯繫管理員。", ephemeral=True)
                return
            
            seeds = inventory.get("種子", {})
            
            # 檢查是否有種子
            if not seeds or not any(qty > 0 for qty in seeds.values()):
                await interaction.followup.send("❌ 你沒有種子！請先到商店購買種子。", ephemeral=True)
                return
            
            # 顯示種子選擇界面
            embed = discord.Embed(
                title="🌱 選擇要種植的種子",
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
                        print(f"⚠️  [Plant Seed Button] Seed type '{seed_name}' not found in CANNABIS_SHOP")
                        continue
            
            view = SelectSeedView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, seeds)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            print(f"✅ [Plant Seed Button] Seed selection view sent to user {self.user_id}")
            
        except Exception as e:
            print(f"❌ [Plant Seed Button] Unexpected error for user {self.user_id}: {e}")
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤：{str(e)[:100]}", ephemeral=True)



class SelectPlantForFertilizerView(discord.ui.View):
    """選擇要施肥的植物"""
    
    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        
        for idx, plant in enumerate(plants[:5], 1):  # 限制 5 個
            seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            button = Button(
                label=f"植物 #{plant['id']} - {plant['seed_type']}",
                style=discord.ButtonStyle.secondary,
                emoji=seed_config["emoji"],
                custom_id=f"fert_plant_{plant['id']}"
            )
            button.callback = self.make_fert_callback(plant)
            self.add_item(button)
    
    async def make_fert_callback(self, plant):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                inventory = await get_inventory(self.user_id)
                fertilizers = inventory.get("肥料", {})
                
                if not fertilizers:
                    await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="💧 選擇肥料",
                    color=discord.Color.blue()
                )
                
                for fert_name, qty in fertilizers.items():
                    config = CANNABIS_SHOP["肥料"][fert_name]
                    embed.add_field(
                        name=f"{config['emoji']} {fert_name} (x{qty})",
                        value=f"加速：{config['growth_boost']*100:.0f}%",
                        inline=False
                    )
                
                view = SelectFertilizerView(self.bot, self.user_id, plant, fertilizers)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                
            except Exception as e:
                traceback.print_exc()
                await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
        
        return callback


class SelectFertilizerView(discord.ui.View):
    """選擇肥料視圖"""
    
    def __init__(self, bot, user_id, plant, fertilizers):
        super().__init__(timeout=60)
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


class SelectPlantForHarvestView(discord.ui.View):
    """選擇要收割的植物"""
    
    def __init__(self, bot, user_id, plants):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        
        for idx, plant in enumerate(plants[:5], 1):  # 限制 5 個
            seed_config = CANNABIS_SHOP["種子"][plant["seed_type"]]
            button = Button(
                label=f"收割植物 #{plant['id']}",
                style=discord.ButtonStyle.danger,
                emoji="✂️",
                custom_id=f"harvest_plant_{plant['id']}"
            )
            button.callback = self.make_harvest_callback(plant)
            self.add_item(button)
    
    async def make_harvest_callback(self, plant):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                # 收割
                result = await harvest_plant(plant["id"])
                
                if result and result.get("success"):
                    yield_amount = result.get("yield_amount", 0)
                    
                    embed = discord.Embed(
                        title="✅ 收割成功",
                        description=f"你收割了 {plant['seed_type']}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="產量", value=f"{yield_amount}個", inline=False)
                    
                    # 記錄事件
                    if hasattr(self, 'cog'):
                        user = await self.bot.fetch_user(self.user_id)
                        await self.cog.record_event(
                            'harvest',
                            user,
                            f"收割{plant['seed_type']} - {yield_amount}個"
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 收割失敗", ephemeral=True)
                
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


class CropOperationView(discord.ui.View):
    """作物操作視圖 - 整合種植、施肥、收割按鈕"""
    
    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds, plants, growing, harvested):
        super().__init__(timeout=60)
        self.bot = bot
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.seeds = seeds
        self.plants = plants
        self.growing = growing
        self.harvested = harvested
        
        # 種植按鈕（只要有種子）
        if seeds:
            plant_button = Button(
                label="🌱 種植",
                style=discord.ButtonStyle.success,
                custom_id="crop_op_plant"
            )
            plant_button.callback = self.plant_callback
            self.add_item(plant_button)
        
        # 施肥按鈕（只要有成長中的植物和肥料）
        if growing:
            fertilize_button = Button(
                label="💧 施肥",
                style=discord.ButtonStyle.primary,
                custom_id="crop_op_fertilize"
            )
            fertilize_button.callback = self.fertilize_callback
            self.add_item(fertilize_button)
        
        # 收割按鈕（只要有已成熟的植物）
        if harvested:
            harvest_button = Button(
                label="✂️ 收割",
                style=discord.ButtonStyle.danger,
                custom_id="crop_op_harvest"
            )
            harvest_button.callback = self.harvest_callback
            self.add_item(harvest_button)
    
    async def plant_callback(self, interaction: discord.Interaction):
        """種植 - 顯示種子選擇"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not self.seeds:
                await interaction.followup.send("❌ 你沒有種子！", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🌱 選擇要種植的種子",
                color=discord.Color.green()
            )
            
            for idx, (seed_name, qty) in enumerate(self.seeds.items(), 1):
                if qty > 0:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    embed.add_field(
                        name=f"#{idx} {config['emoji']} {seed_name}",
                        value=f"擁有：{qty} 粒\n成長時間：{config['growth_time']//3600}h",
                        inline=False
                    )
            
            view = SelectSeedView(self.bot, self.cog, self.user_id, self.guild_id, self.channel_id, self.seeds)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    async def fertilize_callback(self, interaction: discord.Interaction):
        """施肥 - 顯示植物選擇"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not self.growing:
                await interaction.followup.send("❌ 沒有成長中的植物！", ephemeral=True)
                return
            
            inventory = await get_inventory(self.user_id)
            if not inventory.get("肥料"):
                await interaction.followup.send("❌ 你沒有肥料！", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="💧 選擇要施肥的植物",
                color=discord.Color.blue()
            )
            
            for idx, plant in enumerate(self.growing[:5], 1):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                embed.add_field(
                    name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                    value=f"已施肥：{plant['fertilizer_applied']}次",
                    inline=False
                )
            
            view = SelectPlantForFertilizerView(self.bot, self.user_id, self.growing)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    async def harvest_callback(self, interaction: discord.Interaction):
        """收割 - 顯示可收割植物選擇"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            if not self.harvested:
                await interaction.followup.send("❌ 沒有已成熟的植物！", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🔪 選擇要收割的植物",
                color=discord.Color.gold()
            )
            
            for idx, plant in enumerate(self.harvested[:5], 1):
                config = CANNABIS_SHOP["種子"][plant["seed_type"]]
                yield_amount = plant.get("harvested_amount", 0)
                embed.add_field(
                    name=f"#{idx} {config['emoji']} {plant['seed_type']}",
                    value=f"產量：{yield_amount}",
                    inline=False
                )
            
            view = SelectPlantForHarvestView(self.bot, self.user_id, self.harvested)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)


class SelectSeedView(discord.ui.View):
    """選擇要種植的種子"""
    
    def __init__(self, bot, cog, user_id, guild_id, channel_id, seeds):
        super().__init__(timeout=60)
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


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(PersonalLockerCog(bot))
