# -*- coding: utf-8 -*-
"""
趨勢樂透 Discord Cog

功能：
- /predict：玩家投注並預測趨勢
- 每4小時自動抓取並顯示趨勢
- 自動開獎並發放獎金
- 排除台灣深夜 00:00-08:00 的推播
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import os
from datetime import datetime
from typing import List, Optional
from dotenv import load_dotenv
import logging

# 時區管理（可能需要 pip install pytz）
try:
    import pytz
    TZ_TW = pytz.timezone("Asia/Taipei")
except ImportError:
    # 備用：使用 UTC+8 的簡單時區（如果 pytz 不可用）
    from datetime import timezone, timedelta
    TZ_TW = timezone(timedelta(hours=8))

# 導入自定義模組
from shared.utils.trends_collector import TrendsCollector, get_latest_trends
from shared.utils.trends_lottery_system import TrendsLotterySystem

load_dotenv()
logger = logging.getLogger(__name__)

# 臨時日誌文件（調試用）
TEMP_DEBUG_LOG = "/tmp/trends_lottery_debug.log"

def temp_debug_log(msg):
    """寫入臨時調試日誌"""
    try:
        with open(TEMP_DEBUG_LOG, "a", encoding="utf-8") as f:
            ts = datetime.now(TZ_TW).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except Exception as e:
        logger.error(f"臨時日誌寫入失敗: {e}")

# 配置
TRENDS_UPDATE_INTERVAL = 240  # 4 小時（秒）
TRENDS_UPDATE_HOURS = [8, 12, 16, 20]  # 08:00, 12:00, 16:00, 20:00 台灣時間

# TRENDS_CHANNEL_ID 将在 setup 时读取
TRENDS_CHANNEL_ID = None


class TrendsPredictionView(discord.ui.View):
    """趨勢預測交互按鈕"""
    
    def __init__(self, cog, trends: List[str], round_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.trends = trends[:10]  # 最多 10 個選項
        self.round_id = round_id
        
        # 創建選項按鈕（每行 5 個）
        for i, trend in enumerate(self.trends):
            button = discord.ui.Button(
                label=f"{i+1}. {trend[:20]}",
                custom_id=f"trend_select_{round_id}_{i}",
                style=discord.ButtonStyle.primary
            )
            button.callback = self.trend_select_callback
            self.add_item(button)
    
    async def trend_select_callback(self, interaction: discord.Interaction):
        """處理趨勢選擇"""
        # 解析 custom_id 獲取選擇的索引
        parts = interaction.custom_id.split("_")
        selected_index = int(parts[-1])
        
        # 取得用戶已選擇的趨勢
        user_id = interaction.user.id
        
        # 檢查用戶是否已經在選擇中
        if not hasattr(self, 'user_selections'):
            self.user_selections = {}
        
        if user_id not in self.user_selections:
            self.user_selections[user_id] = []
        
        selected_trend = self.trends[selected_index]
        
        # 檢查是否重複選擇
        if selected_trend in self.user_selections[user_id]:
            await interaction.response.send_message(
                f"❌ 不能重複選擇 `{selected_trend}`",
                ephemeral=True
            )
            return
        
        # 檢查是否已經選了 3 個
        if len(self.user_selections[user_id]) >= 3:
            await interaction.response.send_message(
                f"❌ 已經選了 3 個趨勢了！\n當前選擇：{', '.join(self.user_selections[user_id])}",
                ephemeral=True
            )
            return
        
        # 添加選擇
        self.user_selections[user_id].append(selected_trend)
        
        # 確認消息
        await interaction.response.send_message(
            f"✅ 已選擇 `{selected_trend}`\n進度：{len(self.user_selections[user_id])}/3",
            ephemeral=True
        )
    
    async def on_timeout(self):
        """按鈕超時（但由於 timeout=None，不會超時）"""
        pass


class TrendsLotteryCog(commands.Cog):
    """趨勢樂透遊戲 Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 延遲初始化 DB adapter（需要在 on_ready 時初始化）
        self.lottery_system: Optional[TrendsLotterySystem] = None
        self.current_trends: List[str] = []
        self.current_round_id: str = ""
        self._db_initialized = False
        self.trends_channel_id = None  # 將在 on_ready 時初始化
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Cog 準備就緒時初始化"""
        # 首先讀取 TRENDS_CHANNEL_ID
        if not self.trends_channel_id:
            self.trends_channel_id = int(os.getenv("TRENDS_CHANNEL_ID", "0"))
            logger.info(f"✅ 初始化 trends_channel_id: {self.trends_channel_id}")
            temp_debug_log(f"[on_ready] trends_channel_id set to {self.trends_channel_id}")
        
        if not self._db_initialized:
            try:
                # 導入 db_adapter
                from db_adapter import get_user_field, set_user_field, get_all_users
                
                # 創建簡單的 DB 適配器對象
                class DBAdapter:
                    @staticmethod
                    def get_user_field(user_id, field, default=None):
                        return get_user_field(user_id, field, default)
                    
                    @staticmethod
                    def set_user_field(user_id, field, value):
                        return set_user_field(user_id, field, value)
                    
                    @staticmethod
                    def add_user_field(user_id, field, value):
                        from db_adapter import add_user_field
                        return add_user_field(user_id, field, value)
                    
                    @staticmethod
                    def get_all_users():
                        return get_all_users()
                
                # 初始化樂透系統
                self.lottery_system = TrendsLotterySystem(db_adapter=DBAdapter())
                self._db_initialized = True
                
                # 啟動定時任務
                if not self.update_trends_task.is_running():
                    self.update_trends_task.start()
                
                logger.info("✅ 趨勢樂透 Cog 已初始化")
            except Exception as e:
                logger.error(f"❌ 趨勢樂透 Cog 初始化失敗: {e}")
    
    async def cog_unload(self):
        """Cog 卸載時清理"""
        self.update_trends_task.cancel()
        logger.info("🛑 趨勢樂透 Cog 已卸載")
    
    @tasks.loop(minutes=1)
    async def update_trends_task(self):
        """定時更新趨勢任務（每分鐘檢查一次是否應該更新）"""
        now = datetime.now(TZ_TW)
        
        # 除錯日誌（每小時僅在 :00 分時輸出）
        if now.minute == 0:
            logger.info(f"⏰ 趨勢任務檢查: 台灣時間 {now.strftime('%H:%M')}")
        
        # 檢查是否在深夜時段（00:00 - 08:00）
        if 0 <= now.hour < 8:
            # 深夜時段：靜默抓取但不推播
            if now.minute == 0:
                await self._fetch_trends_silent()
            return
        
        # 檢查是否是更新時間（08:00, 12:00, 16:00, 20:00）
        # 使用 0-2 分鐘窗口以容納任務延遲
        if now.hour in TRENDS_UPDATE_HOURS and now.minute <= 2:
            logger.info(f"🚀 正在推播趨勢 ({now.hour}:00 時段)")
            await self._update_and_broadcast_trends()
    
    @update_trends_task.before_loop
    async def before_update_trends_task(self):
        """任務啟動前等待 bot 準備"""
        await self.bot.wait_until_ready()
    
    async def _fetch_trends_silent(self):
        """靜默抓取趨勢（深夜時段）"""
        try:
            trends = await get_latest_trends(limit=10)
            
            if trends:
                self.current_trends = [t["trend"] for t in trends]
                logger.info(f"✅ 深夜趨勢已抓取（靜默）：{len(self.current_trends)} 項")
        except Exception as e:
            logger.error(f"❌ 深夜趨勢抓取失敗: {e}")
    
    async def _update_and_broadcast_trends(self):
        """更新趨勢並廣播到 Discord"""
        temp_debug_log("========== START _update_and_broadcast_trends ==========")
        logger.info(f"📝 [_UPDATE_AND_BROADCAST] 開始執行...")
        temp_debug_log(f"1️⃣  _update_and_broadcast_trends called")
        try:
            # 抓取最新趨勢
            logger.info(f"📡 [_UPDATE_AND_BROADCAST] 調用 get_latest_trends()...")
            temp_debug_log(f"2️⃣  Calling get_latest_trends()...")
            trends = await get_latest_trends(limit=10)
            
            temp_debug_log(f"3️⃣  get_latest_trends returned {len(trends) if trends else 0} items")
            logger.info(f"📊 [_UPDATE_AND_BROADCAST] 收到 {len(trends) if trends else 0} 項趨勢")
            
            if not trends:
                temp_debug_log(f"⚠️  No trends returned, returning early")
                logger.warning("⚠️  無法獲取趨勢")
                return
            
            # 更新當前趨勢
            self.current_trends = [t["trend"] for t in trends]
            
            # 生成本輪 ID（格式：2024-04-22-08）
            now = datetime.now(TZ_TW)
            round_id = now.strftime("%Y-%m-%d-%H")
            self.current_round_id = round_id
            
            logger.info(f"🎯 [_UPDATE_AND_BROADCAST] 輪次 ID: {round_id}")
            temp_debug_log(f"4️⃣  Round ID: {round_id}")
            
            # 發送趨勢到 Discord 頻道
            logger.info(f"📤 [_UPDATE_AND_BROADCAST] 調用 _broadcast_trends_to_discord()...")
            temp_debug_log(f"5️⃣  Calling _broadcast_trends_to_discord()...")
            await self._broadcast_trends_to_discord(trends)
            temp_debug_log(f"6️⃣  _broadcast_trends_to_discord() completed")
            
            # 開獎上一輪（如果存在）
            await self._draw_previous_round()
            
            logger.info(f"✅ 趨勢已更新：{round_id}，{len(self.current_trends)} 項")
            temp_debug_log(f"7️⃣  Update completed successfully")
        
        except Exception as e:
            logger.error(f"❌ 趨勢更新失敗: {e}")
            temp_debug_log(f"❌ Exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            temp_debug_log(f"Traceback: {traceback.format_exc()}")
        finally:
            temp_debug_log("========== END _update_and_broadcast_trends ==========\n")
    
    async def _broadcast_trends_to_discord(self, trends: List[dict]):
        """將趨勢廣播到 Discord"""
        temp_debug_log("========== START _broadcast_trends_to_discord ==========")
        logger.info(f"🚀 開始廣播趨勢...（{len(trends)} 項）")
        temp_debug_log(f"A. _broadcast_trends_to_discord called with {len(trends)} trends")
        
        # 備用初始化：如果 on_ready() 沒有執行，這裡初始化
        if not self.trends_channel_id:
            temp_debug_log(f"Z1. trends_channel_id is None, attempting backup initialization...")
            self.trends_channel_id = int(os.getenv("TRENDS_CHANNEL_ID", "0"))
            temp_debug_log(f"Z2. Backup init set trends_channel_id to {self.trends_channel_id}")
            logger.info(f"🔧 備用初始化 trends_channel_id: {self.trends_channel_id}")
        
        if not self.trends_channel_id:
            logger.warning("⚠️  TRENDS_CHANNEL_ID 未設置")
            temp_debug_log(f"B. trends_channel_id is still not set! ({self.trends_channel_id})")
            return
        
        temp_debug_log(f"C. trends_channel_id = {self.trends_channel_id}")
        
        try:
            logger.info(f"📍 目標頻道 ID: {self.trends_channel_id}")
            temp_debug_log(f"D. Getting channel object for ID {self.trends_channel_id}...")
            channel = self.bot.get_channel(self.trends_channel_id)
            temp_debug_log(f"E. channel object = {channel}")
            
            if not channel:
                logger.error(f"❌ 找不到頻道：{self.trends_channel_id}")
                temp_debug_log(f"F. Channel not found!")
                logger.error(f"   可用頻道數: {len(self.bot.get_all_channels())}")
                return
            
            logger.info(f"✅ 找到頻道: {channel.name}")
            temp_debug_log(f"G. Found channel: {channel.name}")
            
            # 創建 Embed
            embed = discord.Embed(
                title="🔥 最新熱門趨勢",
                description="預測下一個時段的前三名趨勢！",
                color=discord.Color.gold(),
                timestamp=datetime.now(TZ_TW)
            )
            
            # 添加趨勢列表
            trends_text = "\n".join([
                f"{i+1}. `{t['trend']}` ({', '.join(t.get('sources', ['twitter']))})"
                for i, t in enumerate(trends[:10])
            ])
            embed.add_field(name="當前趨勢", value=trends_text or "無趨勢數據", inline=False)
            
            logger.info(f"📊 趨勢文本長度: {len(trends_text)} 字符")
            temp_debug_log(f"H. Embed created, trends_text length = {len(trends_text)}")
            
            # 獎池信息
            try:
                jackpot_info = await self.lottery_system.get_jackpot_info(self.current_round_id)
                embed.add_field(
                    name="🎁 中央獎池",
                    value=f"**${jackpot_info['jackpot']:.2f}**\n參與投注：{jackpot_info['total_bets']} 人",
                    inline=False
                )
                temp_debug_log(f"I. Jackpot info added")
            except Exception as e:
                logger.warning(f"⚠️  獎池信息獲取失敗: {e}")
                temp_debug_log(f"I. Jackpot info failed: {e}")
                embed.add_field(name="🎁 中央獎池", value="初始化中...", inline=False)
            
            embed.set_footer(text=f"開獎輪次：{self.current_round_id}")
            
            # 發送消息並添加按鈕
            view = TrendsPredictionView(
                self,
                [t["trend"] for t in trends],
                self.current_round_id
            )
            
            logger.info(f"📤 正在發送 embed 到頻道 {channel.name}...")
            temp_debug_log(f"J. About to send message to channel...")
            message = await channel.send(embed=embed, view=view)
            logger.info(f"✅ 趨勢已廣播！消息 ID: {message.id}")
            temp_debug_log(f"K. Message sent! ID = {message.id}")
        
        except Exception as e:
            logger.error(f"❌ 廣播趨勢失敗: {e}")
            temp_debug_log(f"L. Exception in broadcast: {e}")
            import traceback
            logger.error(traceback.format_exc())
            temp_debug_log(f"Traceback: {traceback.format_exc()}")
        finally:
            temp_debug_log("========== END _broadcast_trends_to_discord ==========\n")
    
    async def _draw_previous_round(self):
        """開獎上一輪"""
        # 計算上一個時段的 round_id
        # 由於我們的 round_id 是按小時生成的，上一個就是 4 小時前
        try:
            if not self.current_trends:
                return
            
            # 開獎邏輯（實際上應該基於前一個時段）
            draw_result = await self.lottery_system.draw_lottery(
                self.current_round_id,
                self.current_trends[:3]
            )
            
            if draw_result:
                await self._announce_draw_result(draw_result)
        
        except Exception as e:
            logger.error(f"❌ 開獎失敗: {e}")
    
    async def _announce_draw_result(self, result: dict):
        """宣布開獎結果"""
        if not TRENDS_CHANNEL_ID:
            return
        
        try:
            channel = self.bot.get_channel(TRENDS_CHANNEL_ID)
            if not channel:
                return
            
            embed = discord.Embed(
                title="🎊 開獎結果",
                description=f"輪次：{result['round_id']}",
                color=discord.Color.green()
            )
            
            # 中獎號碼
            top3_text = "\n".join([
                f"{i+1}. `{trend}`"
                for i, trend in enumerate(result['top3'])
            ])
            embed.add_field(name="🏆 中獎號碼", value=top3_text, inline=False)
            
            # 統計
            embed.add_field(
                name="📊 統計",
                value=f"總投注人數：{result['results'].__len__()}\n獎池總額：${result['jackpot']:.2f}\n全中玩家：{result['jackpot_winners']} 人",
                inline=False
            )
            
            await channel.send(embed=embed)
        
        except Exception as e:
            logger.error(f"❌ 宣布開獎結果失敗: {e}")
    
    @app_commands.command(name="trends_predict", description="預測趨勢並投注 🎰")
    @app_commands.describe(
        trend1="第一個預測的趨勢",
        trend2="第二個預測的趨勢",
        trend3="第三個預測的趨勢"
    )
    async def predict_trends(
        self,
        interaction: discord.Interaction,
        trend1: str,
        trend2: str,
        trend3: str
    ):
        """
        預測趨勢並投注
        
        需要：10 數位美金
        獲獎：
        - 中1個：退回本金 (10 USD)
        - 中2個：100 KK幣
        - 中3個：平分獎池
        """
        try:
            user_id = interaction.user.id
            prediction = [trend1.lower(), trend2.lower(), trend3.lower()]
            
            # 投注
            success, message = await self.lottery_system.place_bet(
                user_id,
                prediction,
                self.current_round_id
            )
            
            # 創建 Embed 回應
            embed = discord.Embed(
                title="🎰 趨勢樂透投注",
                color=discord.Color.green() if success else discord.Color.red()
            )
            
            embed.add_field(name="結果", value=message, inline=False)
            embed.add_field(name="預測", value=f"1. {trend1}\n2. {trend2}\n3. {trend3}", inline=True)
            embed.add_field(name="投注金額", value="10 USD", inline=True)
            embed.add_field(name="開獎輪次", value=self.current_round_id, inline=True)
            
            if success:
                embed.color = discord.Color.green()
            else:
                embed.color = discord.Color.red()
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            logger.error(f"❌ 預測投注失敗: {e}")
            await interaction.response.send_message(
                f"❌ 發生錯誤：{str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="trends_history", description="查看你的投注歷史 📜")
    async def view_history(self, interaction: discord.Interaction):
        """查看玩家的投注歷史"""
        try:
            user_id = interaction.user.id
            bets = await self.lottery_system.get_user_bets(user_id)
            
            if not bets:
                await interaction.response.send_message(
                    "❌ 你還沒有投注記錄",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="📜 你的投注歷史",
                color=discord.Color.blue()
            )
            
            # 顯示最近 5 筆
            for bet in bets[-5:]:
                status = bet.get("result", "待開獎")
                payout = bet.get("payout", 0)
                
                bet_info = f"預測：{', '.join(bet['prediction'])}\n"
                bet_info += f"狀態：{status}\n"
                bet_info += f"獎金：{payout}"
                
                embed.add_field(
                    name=f"輪次：{bet['round_id']}",
                    value=bet_info,
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            logger.error(f"❌ 查看歷史失敗: {e}")
            await interaction.response.send_message(
                f"❌ 發生錯誤：{str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="trends_jackpot", description="查看當前獎池 🎁")
    async def check_jackpot(self, interaction: discord.Interaction):
        """查看當前獎池信息"""
        try:
            jackpot_info = await self.lottery_system.get_jackpot_info(self.current_round_id)
            
            embed = discord.Embed(
                title="🎁 中央獎池",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="當前獎池", value=f"**${jackpot_info['jackpot']:.2f} USD**", inline=False)
            embed.add_field(name="投注人數", value=f"{jackpot_info['total_bets']} 人", inline=True)
            embed.add_field(name="總投注額", value=f"${jackpot_info['total_wagered']:.2f}", inline=True)
            embed.add_field(name="輪次", value=jackpot_info['round_id'], inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            logger.error(f"❌ 查看獎池失敗: {e}")
            await interaction.response.send_message(
                f"❌ 發生錯誤：{str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="trends_test", description="🧪 測試推播趨勢（開發者用）")
    async def test_broadcast(self, interaction: discord.Interaction):
        """手動測試趨勢推播"""
        try:
            # 延遲回應，等待推播完成
            await interaction.response.defer()
            
            logger.info(f"🧪 測試推播已觸發 (by {interaction.user})")
            
            # 立即執行推播
            await self._update_and_broadcast_trends()
            
            await interaction.followup.send(
                "✅ 已推播最新趨勢！",
                ephemeral=True
            )
        
        except Exception as e:
            logger.error(f"❌ 測試推播失敗: {e}")
            await interaction.followup.send(
                f"❌ 推播失敗：{str(e)}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """設置 Cog"""
    await bot.add_cog(TrendsLotteryCog(bot))
    logger.info("✅ 趨勢樂透 Cog 已安裝")
