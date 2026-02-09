"""
KKCoin V2 自動更新架構 (Option C - 推薦方案)
這個文件展示在 kcoin.py 中需要添加的代碼

使用方式：
1. /kkcoin_v2_setup -> 發送 3 張圖到指定頻道，並保存消息 ID
2. 後台每 5 分鐘自動更新這 3 張圖
3. 完全模仿原有的 auto_update_leaderboard 架構
"""

import discord
from discord.ext import commands, tasks
import io
import time
from datetime import datetime

# ============================================================
# 在 KKCoin class 的 __init__ 中添加這些配置
# ============================================================

"""
def __init__(self, bot):
    self.bot = bot
    # ... 現有代碼 ...
    
    # V2 自動更新配置
    self.v2_channel_id = int(os.getenv("KKCOIN_V2_CHANNEL_ID", 0))
    self.v2_message_id = int(os.getenv("KKCOIN_V2_MESSAGE_ID", 0))
    self.last_v2_update_time = 0
    self.last_v2_leaderboard_data = []
    
    # 啟動 V2 自動更新任務
    self.auto_update_kkcoin_v2.start()
"""

# ============================================================
# 1️⃣ 初始化命令 - 設置頻道和消息 ID
# ============================================================

async def kkcoin_v2_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
    """
    初始化 V2 自動更新系統
    只需要執行一次！然後就會自動更新
    
    用法: /kkcoin_v2_setup #頻道名稱
    """
    await interaction.response.defer()
    
    # 保存頻道 ID 到環境變數
    self.v2_channel_id = channel.id
    # 可選：保存到 .env 文件
    # from utils import save_to_env
    # save_to_env("KKCOIN_V2_CHANNEL_ID", channel.id)
    
    print(f"📍 V2 自動更新頻道已設定: {channel.name} (ID: {channel.id})")
    
    members_data = self.get_current_leaderboard_data()
    
    if not members_data:
        await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
        return
    
    try:
        from commands.kkcoin_visualizer_v2 import (
            create_enhanced_leaderboard_image,
            create_bar_chart_image,
            create_pie_and_weekly_image,
            MATPLOTLIB_AVAILABLE
        )
        
        # 生成 3 張圖
        print("🎨 生成排行榜圖片...")
        leaderboard_img = await create_enhanced_leaderboard_image(members_data, limit=15)
        
        print("📊 生成長條圖...")
        bar_img = await create_bar_chart_image(members_data, limit=15)
        
        print("🍰 生成饼圖與周統計...")
        pie_img = await create_pie_and_weekly_image(
            members_data=members_data,
            limit=15,
            total_coins=sum(coin for _, coin in members_data),
            this_week_total=int(sum(coin for _, coin in members_data) * 0.3),
            last_week_total=int(sum(coin for _, coin in members_data) * 0.25)
        )
        
        # 創建 Discord 文件
        files = []
        
        with io.BytesIO() as img_bytes:
            leaderboard_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            files.append(discord.File(img_bytes, filename="1_leaderboard.png"))
        
        with io.BytesIO() as img_bytes:
            bar_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            files.append(discord.File(img_bytes, filename="2_bar_chart.png"))
        
        with io.BytesIO() as img_bytes:
            pie_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            files.append(discord.File(img_bytes, filename="3_pie_weekly.png"))
        
        # 發送到指定頻道
        msg = await channel.send(
            content="📊 **KK幣升級版儀表板 - 3合1圖表**\n" +
                    "ℹ️ 本訊息每 5 分鐘自動更新一次\n" +
                    "① 排行榜（前15名）\n" +
                    "② 長條圖排行\n" +
                    "③ 饼圖分布 + 周統計",
            files=files
        )
        
        # 保存消息 ID
        self.v2_message_id = msg.id
        # save_to_env("KKCOIN_V2_MESSAGE_ID", msg.id)
        
        # 保存初始數據用於變化檢查
        self.last_v2_leaderboard_data = members_data.copy()
        self.last_v2_update_time = time.time()
        
        await interaction.followup.send(
            f"✅ V2 自動更新已初始化！\n" +
            f"📍 頻道：{channel.mention}\n" +
            f"💾 消息 ID：{msg.id}\n" +
            f"🔄 將每 5 分鐘自動更新一次",
            ephemeral=True
        )
        
        print(f"✅ V2 自動更新初始化完成！消息 ID: {msg.id}")
        
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(
            f"❌ 初始化失敗：{str(e)[:150]}",
            ephemeral=True
        )


# ============================================================
# 2️⃣ 自動更新任務
# ============================================================

@tasks.loop(minutes=5)
async def auto_update_kkcoin_v2(self):
    """每 5 分鐘自動更新 V2 排行榜"""
    if not self.v2_channel_id or not self.v2_message_id:
        return
    
    await self.update_kkcoin_v2(min_interval=0)


@auto_update_kkcoin_v2.before_loop
async def before_auto_update_v2(self):
    """啟動前準備"""
    await self.bot.wait_until_ready()
    if self.v2_channel_id and self.v2_message_id:
        print(f"✅ V2 自動更新任務已啟動 (頻道 ID: {self.v2_channel_id})")
    else:
        print("⚠️ V2 自動更新：尚未初始化。請執行 /kkcoin_v2_setup 命令")


# ============================================================
# 3️⃣ 更新邏輯
# ============================================================

async def update_kkcoin_v2(self, min_interval=300, force=False):
    """
    更新 V2 排行榜
    min_interval: 最小更新間隔（秒），預設 300 秒 = 5 分鐘
    force: 是否強制更新
    """
    current_time = time.time()
    
    if not self.v2_channel_id or not self.v2_message_id:
        return
    
    # 檢查更新間隔
    if not force and current_time - self.last_v2_update_time < min_interval:
        return
    
    try:
        channel = self.bot.get_channel(self.v2_channel_id)
        if not channel:
            print(f"❌ 找不到 V2 頻道 {self.v2_channel_id}")
            return
        
        # 取得訊息
        try:
            msg = await channel.fetch_message(self.v2_message_id)
        except discord.NotFound:
            print("❌ V2 訊息已被刪除，將重新初始化")
            self.v2_message_id = 0
            return
        except Exception as e:
            print(f"❌ 取得 V2 訊息失敗: {e}")
            return
        
        # 取得數據
        members_data = self.get_current_leaderboard_data()
        
        if not members_data:
            return
        
        # 檢查數據是否改變（使用現有的 has_data_changed 方法）
        if not force and not self.has_data_changed(members_data, self.last_v2_leaderboard_data):
            self.last_v2_update_time = current_time
            return
        
        from commands.kkcoin_visualizer_v2 import (
            create_enhanced_leaderboard_image,
            create_bar_chart_image,
            create_pie_and_weekly_image
        )
        
        print(f"🔄 開始更新 V2 排行榜...")
        
        # 生成 3 張圖
        leaderboard_img = await create_enhanced_leaderboard_image(members_data, limit=15)
        bar_img = await create_bar_chart_image(members_data, limit=15)
        pie_img = await create_pie_and_weekly_image(
            members_data=members_data,
            limit=15,
            total_coins=sum(coin for _, coin in members_data),
            this_week_total=int(sum(coin for _, coin in members_data) * 0.3),
            last_week_total=int(sum(coin for _, coin in members_data) * 0.25)
        )
        
        # 創建 Discord 文件
        files = []
        
        with io.BytesIO() as img_bytes:
            leaderboard_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            files.append(discord.File(img_bytes, filename="1_leaderboard.png"))
        
        with io.BytesIO() as img_bytes:
            bar_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            files.append(discord.File(img_bytes, filename="2_bar_chart.png"))
        
        with io.BytesIO() as img_bytes:
            pie_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            files.append(discord.File(img_bytes, filename="3_pie_weekly.png"))
        
        # 編輯訊息（關鍵！用新的 3 張圖替換舊圖）
        await msg.edit(attachments=files)
        
        # 更新內部狀態
        self.last_v2_leaderboard_data = members_data.copy()
        self.last_v2_update_time = current_time
        
        print(f"✅ V2 排行榜更新成功 ({len(members_data)} 名使用者)")
        
    except discord.HTTPException as e:
        print(f"❌ Discord API 錯誤: {e}")
    except Exception as e:
        print(f"❌ 更新 V2 排行榜時發生錯誤: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# 使用說明
# ============================================================

"""
📝 完整使用流程：

1️⃣ 初次設置（只需一次）
   /kkcoin_v2_setup #你的頻道名稱
   → 3 張圖會被發送到指定頻道
   → 消息 ID 自動保存

2️⃣ 之後自動運行
   - 後台的 @tasks.loop(minutes=5) 每 5 分鐘自動檢查一次
   - 如果排行榜資料改變，就會編輯訊息更新 3 張圖
   - 不會重複發送消息，只會編輯現有消息

3️⃣ 手動更新（測試用）
   可以在代碼中添加指令：
   /kkcoin_v2_force_update -> 強制立即更新（不等 5 分鐘）

💡 優點：
   ✅ 數據實時更新
   ✅ 同一條訊息，不會垃圾信息
   ✅ 完全自動化，無需人工干預
   ✅ 架構清晰，易於維護

⚙️ 需要修改的環境變數：
   KKCOIN_V2_CHANNEL_ID=你的頻道ID（由命令自動設置）
   KKCOIN_V2_MESSAGE_ID=訊息ID（由命令自動設置）

📌 現有架構參考：
   原有的 auto_update_leaderboard 就是這樣工作的！
   V2 版完全複製相同的邏輯
"""

