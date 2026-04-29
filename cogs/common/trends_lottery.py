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
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import logging

# ⚠️ 在導入其他模塊之前，必須先加載 .env！
# 使用絕對路徑加載 .env
__file_abs = os.path.abspath(__file__)
ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file_abs))),
    ".env"
)

from dotenv import load_dotenv
load_dotenv(ENV_PATH)

# 時區管理（可能需要 pip install pytz）
try:
    import pytz
    TZ_TW = pytz.timezone("Asia/Taipei")
except ImportError:
    # 備用：使用 UTC+8 的簡單時區（如果 pytz 不可用）
    from datetime import timezone, timedelta
    TZ_TW = timezone(timedelta(hours=8))

# 導入自定義模組
import json
from pathlib import Path
from shared.utils.trends_lottery_system import TrendsLotterySystem
from shared.utils.view_registry import PersistentViewBase
from market_trends_serpapi import get_trending_topics, format_lottery_embed

logger = logging.getLogger(__name__)

# 全局狀態存儲（JSON 文件）
LOTTERY_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "lottery_state.json"
LOTTERY_STATE_FILE.parent.mkdir(exist_ok=True)


def load_lottery_state() -> Dict:
    """加載全局狀態"""
    try:
        if LOTTERY_STATE_FILE.exists():
            with open(LOTTERY_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ 加載狀態失敗: {e}")
    return {"pushed_rounds": {}}


def save_lottery_state(state: Dict):
    """保存全局狀態"""
    try:
        LOTTERY_STATE_FILE.parent.mkdir(exist_ok=True)
        with open(LOTTERY_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ 保存狀態失敗: {e}")


def is_round_pushed(round_id: str) -> bool:
    """檢查某輪是否已推送"""
    state = load_lottery_state()
    return state.get("pushed_rounds", {}).get(round_id, False)


def mark_round_pushed(round_id: str):
    """標記某輪為已推送"""
    state = load_lottery_state()
    if "pushed_rounds" not in state:
        state["pushed_rounds"] = {}
    state["pushed_rounds"][round_id] = True
    save_lottery_state(state)

# 配置
TRENDS_UPDATE_INTERVAL = 240  # 4 小時（秒）
TRENDS_UPDATE_HOURS = [8, 11, 14, 17, 20, 23]  # 08:00, 11:00, 14:00, 17:00, 20:00, 23:00 台灣時間


class TrendsPredictionView(PersistentViewBase):
    """趨勢預測交互按鈕"""
    
    def __init__(self, cog, trends: List[str], round_id: str):
        super().__init__()
        self.cog = cog
        self.trends = trends[:10]  # 最多 10 個選項
        self.round_id = round_id
        self.user_selections = {}  # 初始化用戶選擇紀錄
        
        # 使用 discord.ui.Button 動態創建按鈕（每行 5 個）
        for i, trend in enumerate(self.trends):
            button = discord.ui.Button(
                label=f"{i+1}. {trend[:20]}",
                style=discord.ButtonStyle.primary,
                custom_id=f"trend_select_{round_id}_{i}",
                row=i // 5  # 每行 5 個按鈕
            )
            # 綁定回調函數
            button.callback = self._make_callback(i)
            self.add_item(button)
    
    def _make_callback(self, index: int):
        """製造回調函數（解決 lambda 閉包問題）"""
        async def callback(interaction: discord.Interaction):
            await self._handle_trend_select(interaction, index)
        return callback
    
    async def _handle_trend_select(self, interaction: discord.Interaction, selected_index: int):
        """處理趨勢選擇"""
        user_id = interaction.user.id
        
        # 初始化用戶選擇記錄
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
        # 延遲初始化 DB adapter（需要在 before_loop 時初始化）
        self.lottery_system: Optional[TrendsLotterySystem] = None
        self.current_trends: List[str] = []
        self.current_round_id: str = ""
        self._db_initialized = False
        self.trends_channel_id = None  # 將在 before_loop 時初始化
        self.round_message_ids: Dict[str, int] = {}  # 儲存 round_id -> message_id 的映射
        
        # 直接啟動排程任務
        logger.info(f"🔧 [TrendsLotteryCog.__init__] 初始化開始，即將啟動任務...")
        self.update_trends_task.start()
        logger.info(f"✅ [TrendsLotteryCog.__init__] 任務已啟動")
    
    async def cog_load(self):
        """Cog 加載時執行 - 全域註冊視圖"""
        logger.info("🔧 [TrendsLotteryCog.cog_load] 開始全域註冊趨勢視圖...")
        # 注意：由於趨勢是動態生成的，我們無法預先註冊
        # 每次推播時會創建新的 TrendsPredictionView
        # 由於已使用 PersistentViewBase，所有視圖都有 timeout=None
        logger.info("✅ [TrendsLotteryCog.cog_load] 準備完成，將使用 PersistentViewBase")
    
    async def cog_unload(self):
        """Cog 卸載時清理"""
        self.update_trends_task.cancel()
        logger.info("🛑 趨勢樂透 Cog 已卸載")
    
    @tasks.loop(minutes=15)
    async def update_trends_task(self):
        """定時更新趨勢任務（每 15 分鐘檢查一次是否應該更新）"""
        try:
            now = datetime.now(TZ_TW)
            
            # 定期檢查日誌
            logger.info(f"⏰ 趨勢排程檢查: 台灣時間 {now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 檢查是否在深夜時段（00:00 - 08:00）
            if 0 <= now.hour < 8:
                # 深夜時段：靜默抓取但不推播
                if now.minute == 0:
                    logger.info(f"🌙 深夜時段 ({now.hour}:00)，靜默抓取趨勢...")
                    await self._fetch_trends_silent()
                return
            
            # 檢查是否是更新時間（08:00, 12:00, 16:00, 20:00）
            # 使用 0-5 分鐘窗口以容納任務延遲和 Bot 重連
            if now.hour in TRENDS_UPDATE_HOURS and now.minute <= 5:
                logger.info(f"🚀 觸發推播時間 ({now.hour}:{now.minute:02d})，正在推播趨勢...")
                await self._update_and_broadcast_trends()
                # 標記為已推送
                current_round_id = now.strftime("%Y-%m-%d-%H")
                mark_round_pushed(current_round_id)
            # 檢查是否錯過了最近的推送時間（補發機制）
            elif now.hour in TRENDS_UPDATE_HOURS and now.minute > 5:
                # 如果在 5-59 分鐘之間，檢查本小時是否已經推送過
                current_round_id = now.strftime("%Y-%m-%d-%H")
                already_pushed = is_round_pushed(current_round_id)
                
                if not already_pushed:
                    logger.warning(f"⚠️ 檢測到可能錯過推送時間 ({now.hour}:00)，正在補發...")
                    await self._update_and_broadcast_trends()
                    # 標記為已推送
                    mark_round_pushed(current_round_id)
            else:
                # 顯示何時下一次推播（每個整點時刻）
                if now.minute == 0 and now.hour >= 8:
                    next_update = None
                    for hour in TRENDS_UPDATE_HOURS:
                        if hour > now.hour:
                            next_update = hour
                            break
                    if next_update is None:
                        next_update = TRENDS_UPDATE_HOURS[0]  # 明天的第一個時段
                    logger.info(f"⏳ 下次推播: {next_update:02d}:00 台灣時間")
        except Exception as e:
            logger.error(f"❌ 趨勢排程任務出錯: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    @update_trends_task.before_loop
    async def before_update_trends_task(self):
        """任務啟動前初始化數據庫和等待 bot 準備"""
        logger.info(f"🔧 [before_loop] 開始執行...")
        await self.bot.wait_until_ready()
        logger.info(f"✅ [before_loop] Bot 已就緒")
        
        # 初始化 TRENDS_CHANNEL_ID
        if not self.trends_channel_id:
            self.trends_channel_id = int(os.getenv("TRENDS_CHANNEL_ID", "0"))
            logger.info(f"✅ [before_loop] trends_channel_id: {self.trends_channel_id}")
        
        # 初始化 DB 和樂透系統
        if not self._db_initialized:
            logger.info(f"🔄 [before_loop] 開始初始化 DB...")
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
                logger.info(f"✅ [before_loop] 樂透系統初始化完成")
                
            except Exception as e:
                logger.error(f"❌ [before_loop] DB 初始化失敗: {e}")
                import traceback
                logger.error(traceback.format_exc())
    
    async def _fetch_trends_silent(self):
        """靜默抓取趨勢（深夜時段）"""
        try:
            trends = await get_trending_topics(region="TW", limit=10, use_cache=False)
            
            if trends:
                self.current_trends = [t.get("topic", t.get("trend", "")) for t in trends]
                logger.info(f"✅ 深夜趨勢已抓取（靜默）：{len(self.current_trends)} 項")
        except Exception as e:
            logger.error(f"❌ 深夜趨勢抓取失敗: {e}")
    
    async def _update_and_broadcast_trends(self):
        """更新趨勢並廣播到 Discord"""
        logger.info(f"📝 [_UPDATE_AND_BROADCAST] 開始執行...")
        try:
            # 抓取最新趨勢（使用 SerpApi Google Trends，強制不用緩存確保最新數據）
            logger.info(f"📡 [_UPDATE_AND_BROADCAST] 調用 get_trending_topics (use_cache=False)...")
            trends = await get_trending_topics(region="TW", limit=10, use_cache=False)
            logger.info(f"📊 [_UPDATE_AND_BROADCAST] 收到 {len(trends) if trends else 0} 項趨勢")
            
            if not trends:
                logger.warning("⚠️ 無法獲取任何趨勢數據，跳過本次發布")
                return
            
            logger.info(f"✅ [品質檢查] 成功獲取 Google Trends 數據")
            
            # 更新當前趨勢
            self.current_trends = [t.get("topic", t.get("trend", "")) for t in trends]
            
            # 生成本輪 ID（格式：2026-04-24-08）
            now = datetime.now(TZ_TW)
            round_id = now.strftime("%Y-%m-%d-%H")
            self.current_round_id = round_id
            
            logger.info(f"🎯 [_UPDATE_AND_BROADCAST] 輪次 ID: {round_id}")
            
            # 發送趨勢到 Discord 頻道
            logger.info(f"📤 [_UPDATE_AND_BROADCAST] 調用 _broadcast_trends_to_discord()...")
            await self._broadcast_trends_to_discord(trends)
            
            # 開獎上一輪（如果存在）
            await self._draw_previous_round()
            
            logger.info(f"✅ 趨勢已更新：{round_id}，{len(self.current_trends)} 項 (Twitter 真實數據)")
        
        except Exception as e:
            logger.error(f"❌ 趨勢更新失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _broadcast_trends_to_discord(self, trends: List[dict]):
        """將趨勢廣播到 Discord"""
        logger.info(f"🚀 開始廣播趨勢...（{len(trends)} 項）")
        
        # 備用初始化：如果 on_ready() 沒有執行，這裡初始化
        if not self.trends_channel_id:
            self.trends_channel_id = int(os.getenv("TRENDS_CHANNEL_ID", "0"))
            logger.info(f"🔧 備用初始化 trends_channel_id: {self.trends_channel_id}")
        
        if not self.trends_channel_id:
            logger.warning("⚠️  TRENDS_CHANNEL_ID 未設置")
            return
        
        try:
            logger.info(f"📍 目標頻道 ID: {self.trends_channel_id}")
            channel = self.bot.get_channel(self.trends_channel_id)
            
            if not channel:
                logger.warning(f"⚠️ 緩存中找不到頻道，嘗試從所有 guild 中查找...")
                # 遍歷所有 guild 查找頻道
                for guild in self.bot.guilds:
                    channel = guild.get_channel(self.trends_channel_id)
                    if channel:
                        logger.info(f"✅ 在 guild '{guild.name}' 中找到頻道")
                        break
                
            if not channel:
                logger.error(f"❌ 找不到頻道：{self.trends_channel_id}")
                all_channels = list(self.bot.get_all_channels())
                logger.error(f"   可用頻道數: {len(all_channels)}")
                logger.error(f"   可用 guilds: {[g.name for g in self.bot.guilds]}")
                return
            
            logger.info(f"✅ 找到頻道: {channel.name}")
            
            # 計算前一輪 round_id（查詢已結束的輪次的獎池）
            now = datetime.now(TZ_TW)
            current_hour = now.hour
            prev_hour = None
            
            for hour in reversed(TRENDS_UPDATE_HOURS):
                if hour < current_hour:
                    prev_hour = hour
                    break
            
            if prev_hour is None:
                prev_hour = TRENDS_UPDATE_HOURS[-1]
                prev_round_id = (now - timedelta(days=1)).replace(hour=prev_hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d-%H")
            else:
                prev_round_id = now.replace(hour=prev_hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d-%H")
            
            # 獲取前一輪的獎池信息
            jackpot_amount = 0.0
            total_bets = 0
            try:
                jackpot_info = await self.lottery_system.get_jackpot_info(prev_round_id)
                jackpot_amount = jackpot_info.get('jackpot', 0.0)
                total_bets = jackpot_info.get('total_bets', 0)
                logger.info(f"📊 前一輪 {prev_round_id} 的獎池: ${jackpot_amount}")
            except Exception as e:
                logger.warning(f"⚠️ 獎池信息獲取失敗: {e}")
            
            # ==================== 使用統一的 format_lottery_embed 生成 Embed ====================
            embed = format_lottery_embed(
                trends=trends,
                jackpot_amount=jackpot_amount,
                total_bets=total_bets,
                current_round_id=self.current_round_id,
                timezone_obj=TZ_TW
            )
            
            # 發送消息並添加按鈕
            view = TrendsPredictionView(
                self,
                [t["topic"] for t in trends],
                self.current_round_id
            )
            
            logger.info(f"📤 正在發送統一 embed 到頻道 {channel.name}...")
            message = await channel.send(embed=embed, view=view)
            
            # 儲存消息 ID 用於後續編輯
            self.round_message_ids[self.current_round_id] = message.id
            logger.info(f"✅ 趨勢已廣播！消息 ID: {message.id}，輪次: {self.current_round_id}")
        
        except Exception as e:
            logger.error(f"❌ 廣播趨勢失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _draw_previous_round(self):
        """開獎上一輪"""
        try:
            if not self.current_trends:
                return
            
            # 計算上一輪 round_id（從當前時間往回 3 小時到上一個推播時段）
            now = datetime.now(TZ_TW)
            current_hour = now.hour
            prev_hour = None
            
            # 從推播時段中找出前一個時段
            for hour in reversed(TRENDS_UPDATE_HOURS):
                if hour < current_hour:
                    prev_hour = hour
                    break
            
            # 如果沒找到（現在是 08:00 之前），取前一天的最後一個時段
            if prev_hour is None:
                prev_hour = TRENDS_UPDATE_HOURS[-1]
                prev_round_id = (now - timedelta(days=1)).replace(hour=prev_hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d-%H")
            else:
                prev_round_id = now.replace(hour=prev_hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d-%H")
            
            logger.info(f"🎰 開始開獎上一輪：{prev_round_id}，使用前 10 名趨勢")
            
            # 開獎邏輯（傳遞前 10 名趨勢）
            draw_result = await self.lottery_system.draw_lottery(
                prev_round_id,
                self.current_trends[:10]
            )
            
            if draw_result and draw_result.get('jackpot_winners', 0) >= 0:
                # 有開獎就記錄結果
                logger.info(f"✅ 開獎完成，{draw_result.get('jackpot_winners', 0)} 人全中，獎池分配：{draw_result.get('jackpot_distributed', 0)} USD")
                
                # 編輯之前的 embed 消息添加結果
                await self._update_embed_with_result(prev_round_id, draw_result)
                
                # 另外發送開獎結果公告
                await self._announce_draw_result(draw_result)
            else:
                logger.info(f"⏭️  上一輪 {prev_round_id} 無投注，跳過開獎")
        
        except Exception as e:
            logger.error(f"❌ 開獎失敗: {e}")
    
    async def _update_embed_with_result(self, round_id: str, result: dict):
        """編輯 embed 消息添加開獎結果"""
        try:
            if not self.trends_channel_id:
                logger.warning("⚠️  無法更新 embed，trends_channel_id 未設置")
                return
            
            # 檢查是否有該輪的消息 ID
            if round_id not in self.round_message_ids:
                logger.warning(f"⚠️  沒有找到 {round_id} 的消息 ID")
                return
            
            message_id = self.round_message_ids[round_id]
            channel = self.bot.get_channel(self.trends_channel_id)
            
            if not channel:
                logger.error(f"❌ 無法獲取頻道")
                return
            
            try:
                message = await channel.fetch_message(message_id)
                
                # 獲取原始 embed
                if message.embeds:
                    embed = message.embeds[0]
                    
                    # 添加開獎結果字段
                    top3_text = "\n".join([
                        f"{i+1}. `{trend}`"
                        for i, trend in enumerate(result['top3'])
                    ])
                    embed.add_field(
                        name="🏆 開獎結果",
                        value=top3_text,
                        inline=False
                    )
                    
                    # 添加獲獎信息（只有全中才顯示）
                    if result.get('jackpot_winners', 0) > 0:
                        embed.add_field(
                            name="🎊 全中獲獎",
                            value=f"恭喜 {result['jackpot_winners']} 位玩家全中！\n每人獲得：${result['jackpot'] / result['jackpot_winners']:.2f}",
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="📊 開獎統計",
                            value=f"投注人數：{result['total_bets']} 人\n獎池總額：${result['jackpot']:.2f}",
                            inline=False
                        )
                    
                    # 編輯消息
                    await message.edit(embed=embed)
                    logger.info(f"✅ 已編輯 embed 添加開獎結果 ({round_id})")
                    
                    # 清理已過期的消息 ID
                    if round_id in self.round_message_ids:
                        del self.round_message_ids[round_id]
                        
            except discord.NotFound:
                logger.warning(f"⚠️  消息已被刪除 (ID: {message_id})")
                if round_id in self.round_message_ids:
                    del self.round_message_ids[round_id]
        
        except Exception as e:
            logger.error(f"❌ 編輯 embed 失敗: {e}")
    
    async def _announce_draw_result(self, result: dict):
        """宣布開獎結果"""
        if not self.trends_channel_id:
            logger.warning("⚠️  無法宣布結果，trends_channel_id 未設置")
            return
        
        try:
            channel = self.bot.get_channel(self.trends_channel_id)
            if not channel:
                logger.warning(f"⚠️  找不到頻道 {self.trends_channel_id}")
                return
            
            embed = discord.Embed(
                title="🎊 開獎結果公告",
                description=f"輪次：{result.get('round_id', '未知')}",
                color=discord.Color.green(),
                timestamp=datetime.now(TZ_TW)
            )
            
            # 中獎號碼
            top3_text = "\n".join([
                f"{i+1}. `{trend}`"
                for i, trend in enumerate(result['top3'])
            ])
            embed.add_field(name="🏆 中獎號碼", value=top3_text, inline=False)
            
            # 統計
            total_bets = result.get('total_bets', 0)
            jackpot_winners = result.get('jackpot_winners', 0)
            
            if jackpot_winners > 0:
                winner_earnings = result['jackpot'] / jackpot_winners
                embed.add_field(
                    name="🎁 獲獎信息",
                    value=f"投注人數：{total_bets} 人\n全中玩家：{jackpot_winners} 人\n每人獲得：${winner_earnings:.2f}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="📊 統計",
                    value=f"投注人數：{total_bets} 人\n獎池總額：${result['jackpot']:.2f}\n本輪無全中者",
                    inline=False
                )
            
            await channel.send(embed=embed)
            logger.info(f"✅ 開獎結果已發布")
        
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
            # 檢查 lottery_system 是否已初始化
            if self.lottery_system is None:
                logger.error("❌ lottery_system 尚未初始化，無法執行投注")
                embed = discord.Embed(
                    title="❌ 系統尚未就緒",
                    description="樂透系統正在初始化中，請稍後再試。\n如果問題持續，請聯繫管理員。",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
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
            
            # 投注成功後編輯原始 embed 更新投注人數
            if success and self.current_round_id in self.round_message_ids:
                try:
                    message_id = self.round_message_ids[self.current_round_id]
                    channel = self.bot.get_channel(self.trends_channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)
                        
                        # 獲取最新的獎池信息
                        jackpot_info = await self.lottery_system.get_jackpot_info(self.current_round_id)
                        jackpot_amount = jackpot_info.get('jackpot', 0.0)
                        total_bets = jackpot_info.get('total_bets', 0)
                        
                        # 重新生成 embed
                        new_embed = format_lottery_embed(
                            trends=[{"trend": t} for t in self.current_trends[:10]],
                            jackpot_amount=jackpot_amount,
                            total_bets=total_bets,
                            current_round_id=self.current_round_id,
                            timezone_obj=TZ_TW
                        )
                        
                        await message.edit(embed=new_embed)
                        logger.info(f"✅ 已編輯 embed 更新投注人數：{total_bets} 人")
                except Exception as e:
                    logger.error(f"❌ 編輯 embed 失敗: {e}")
        
        except Exception as e:
            logger.error(f"❌ 預測投注失敗: {e}")
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
            
            # 嘗試獲取趨勢
            logger.info(f"📡 測試推播：嘗試獲取趨勢數據 (use_cache=False)...")
            trends = await get_trending_topics(region="TW", limit=10, use_cache=False)
            
            if not trends:
                logger.warning("⚠️ 測試推播：無法獲得任何趨勢數據")
                await interaction.followup.send(
                    "⚠️ **無法推播**：無法獲取任何趨勢數據\n\n"
                    "可能原因：\n"
                    "• SerpApi API 金鑰無效\n"
                    "• 網路連接問題\n\n"
                    "請檢查 SERPAPI_API_KEY 環境變數。",
                    ephemeral=True
                )
                return
            
            # 立即執行推播
            await self._update_and_broadcast_trends()
            
            # 顯示數據來源
            twitter_count = sum(1 for t in trends if t.get("platform") == "twitter_twikit")
            data_source = f"Twitter ({twitter_count}項)" if twitter_count > 0 else "Google Trends"
            
            await interaction.followup.send(
                f"✅ 已推播最新趨勢！({len(trends)} 項 {data_source})",
                ephemeral=True
            )
        
        except Exception as e:
            logger.error(f"❌ 測試推播失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await interaction.followup.send(
                f"❌ 推播失敗：{str(e)[:100]}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """設置 Cog"""
    await bot.add_cog(TrendsLotteryCog(bot))
    logger.info("✅ 趨勢樂透 Cog 已安裝")
