"""
虛擬股票市場 - 使用 KK 幣進行股票模擬交易

功能：
- 公開的主 Embed 顯示市場摘要與排行
- 個人專用的操盤室進行買賣
- 使用 yfinance 取得台股報價
- QuickChart 生成圖表
- 自動發送 embed 至指定頻道，並持久化 MESSAGE ID
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import json
import logging
import math
import os
import time
from datetime import datetime
from dotenv import load_dotenv, set_key
from typing import Optional, Dict, List, Tuple
import traceback
from pathlib import Path

from db_adapter import (
    get_user_kkcoin, update_user_kkcoin, 
    get_user_stocks, set_user_stocks, add_stock_position, close_stock_position,
    get_user_total_stock_value, get_user_field, set_user_field, get_all_users
)
from utils.stock_api import (
    fetch_price, fetch_chart, get_popular_stocks, fetch_historical_data
)

logger = logging.getLogger(__name__)

# 配置
MARKET_CHANNEL_ID = 1481373417897988347
REALIZED_PNL_FIELD = "stock_realized_pnl"  # 已實現損益欄位
MARKET_MESSAGE_DATA_FILE = Path("./market_message_data.json")  # 存儲 message ID
ENV_MARKET_MESSAGE_ID = "MARKET_EMBED_MESSAGE_ID"  # 若設置，優先使用環境變數（.env）

# 如果專案有 .env，先加載（讓 os.environ 可用）
load_dotenv()


def load_market_message_data() -> Dict:
    """載入市場 message ID 數據

    優先使用環境變數（例如 .env 中的 MARKET_EMBED_MESSAGE_ID），若不存在則退回到本地檔案。
    """
    # 優先使用環境變數，方便在 Docker/系統 service 環境中設定
    env_id = os.environ.get(ENV_MARKET_MESSAGE_ID)
    if env_id:
        try:
            return {"message_id": int(env_id)}
        except ValueError:
            logger.warning(f"⚠️ 環境變數 {ENV_MARKET_MESSAGE_ID} 不是有效的 message_id: {env_id}")

    if MARKET_MESSAGE_DATA_FILE.exists():
        try:
            with open(MARKET_MESSAGE_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ 載入 message 數據失敗: {e}")
    return {"message_id": None}


def save_market_message_data(data: Dict):
    """保存市場 message ID 數據

    同時嘗試同步更新環境變數（.env 文件），讓部署環境可以直接讀取。
    """
    try:
        with open(MARKET_MESSAGE_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ 保存 message 數據失敗: {e}")

    # 儲存到 .env
    try:
        set_key('.env', ENV_MARKET_MESSAGE_ID, str(data.get('message_id') or ''))
    except Exception as e:
        logger.warning(f"⚠️ 無法更新 .env 中的 {ENV_MARKET_MESSAGE_ID}: {e}")


# 快取（減少 API 呼叫）
_symbol_cache: Dict[str, str] = {}
for code, name, symbol in get_popular_stocks():
    _symbol_cache[code] = symbol


# ============================================================
# 主 Embed 和入口視圖
# ============================================================

class StockEntryView(discord.ui.View):
    """主 Embed 上的入場按鈕"""
    
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.button(label="進入操盤室", style=discord.ButtonStyle.primary, emoji="📈", custom_id="stock_entry_button")
    async def enter_trading_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        """進入個人專用的操盤室"""
        try:
            # 先 defer 交互，避免 token 過期
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            logger.info(f"👤 [ENTER_ROOM] 使用者 {interaction.user.id} 進入操盤室")
            
            # 建立個人操盤室視圖
            view = StockRoomView(self.cog, interaction.user.id)
            
            # 發送新的私人 Embed（使用 followup，因為已 defer）
            await view.show_selection_view_followup(interaction)
        
        except Exception as e:
            logger.error(f"❌ 進入操盤室失敗: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 進入操盤室失敗，請稍後再試。", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 進入操盤室失敗，請稍後再試。", ephemeral=True)
            except:
                logger.error("❌ 無法發送錯誤訊息")


# ============================================================
# 股票選擇視圖（第一層）
# ============================================================

class StockSelectionView(discord.ui.View):
    """股票選擇視圖 - 只有下拉選單"""
    
    def __init__(self, room_view):
        super().__init__(timeout=None)
        self.room_view = room_view
        self._update_stock_select()
    
    def _update_stock_select(self):
        """更新下拉選單內容"""
        # 移除舊的 select
        for item in list(self.children):
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)
        
        # 建立新的 select
        options = []
        for code, name, symbol in get_popular_stocks():
            option = discord.SelectOption(
                label=f"{code} - {name}",
                value=symbol,
                emoji="📊"
            )
            options.append(option)
        
        # 添加自訂代號選項
        options.append(discord.SelectOption(
            label="📝 自訂代號",
            value="CUSTOM",
            emoji="✏️",
            description="輸入其他股票代號"
        ))
        
        select = StockSelectMenu(self.room_view, options)
        self.add_item(select)


class TimeframeButton(discord.ui.Button):
    """時間框架選擇按鈕"""
    
    def __init__(self, label: str, timeframe: str, room_view, symbol: str, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.timeframe = timeframe
        self.room_view = room_view
        self.symbol = symbol
    
    async def callback(self, interaction: discord.Interaction):
        self.room_view.current_timeframe = self.timeframe
        logger.info(f"📊 [TIMEFRAME] 使用者切換時間框架: {self.timeframe}")
        await self.room_view.update_detail_view(self.symbol, interaction, force_refresh=True)


class UpdateChartButton(discord.ui.Button):
    """更新圖表按鈕（30 秒 CD）"""
    
    COOLDOWN_SECONDS = 30
    
    def __init__(self, room_view, symbol: str, row: int):
        super().__init__(label="🔄 更新圖表", style=discord.ButtonStyle.primary, row=row)
        self.room_view = room_view
        self.symbol = symbol
    
    async def callback(self, interaction: discord.Interaction):
        now = time.time()
        remaining = self.COOLDOWN_SECONDS - (now - self.room_view.last_chart_update)
        if remaining > 0:
            await interaction.response.send_message(
                f"⏳ 請等待 **{math.ceil(remaining)}** 秒後再更新圖表",
                ephemeral=True
            )
            return
        self.room_view.last_chart_update = now
        await self.room_view.update_detail_view(self.symbol, interaction, force_refresh=True)


class StockDetailView(discord.ui.View):
    """股票詳細視圖 - 有買入、賣出、返回按鈕及時間框架選擇"""
    
    def __init__(self, room_view, symbol: str, price: float):
        super().__init__(timeout=None)
        self.room_view = room_view
        self.symbol = symbol
        self.price = price
        
        # 時間框架按鈕（Row 1: 5分/15分/60分/日/月，Row 2: 季/更新圖表）
        timeframes_row1 = [("5分", "5m"), ("15分", "15m"), ("60分", "60m"), ("日", "日"), ("月", "月")]
        for label, tf in timeframes_row1:
            self.add_item(TimeframeButton(label, tf, room_view, symbol, row=1))
        
        self.add_item(TimeframeButton("季", "季", room_view, symbol, row=2))
        self.add_item(UpdateChartButton(room_view, symbol, row=2))
    
    @discord.ui.button(label="買入", style=discord.ButtonStyle.green, emoji="📈", row=0)
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """買入按鈕"""
        if not self.symbol or self.price <= 0:
            await interaction.response.send_message("❌ 請先選擇標的", ephemeral=True)
            return
        await interaction.response.send_modal(TradeModal(self.room_view, "buy", self.symbol, self.price))
    
    @discord.ui.button(label="賣出", style=discord.ButtonStyle.red, emoji="📉", row=0)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """賣出按鈕"""
        if not self.symbol or self.price <= 0:
            await interaction.response.send_message("❌ 請先選擇標的", ephemeral=True)
            return
        await interaction.response.send_modal(TradeModal(self.room_view, "sell", self.symbol, self.price))
    
    @discord.ui.button(label="返回", style=discord.ButtonStyle.secondary, emoji="⬅️", row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回按鈕"""
        await self.room_view.update_selection_view(interaction)


# ============================================================
# 個人操盤室視圖
# ============================================================

class StockRoomView(discord.ui.View):
    """個人操盤室主視圖 - 管理狀態"""
    
    # 時間框架 → (period, interval) 映射
    TIMEFRAME_PARAMS: Dict[str, Tuple[str, str]] = {
        "5m":  ("5d",  "5m"),    # 5 天的 5 分鐘 K 線
        "15m": ("5d",  "15m"),   # 5 天的 15 分鐘 K 線
        "60m": ("1mo", "60m"),   # 1 個月的 60 分鐘 K 線
        "日":  ("3mo", "1d"),    # 3 個月的日線
        "月":  ("2y",  "1mo"),   # 2 年的月線
        "季":  ("5y",  "3mo"),   # 5 年的季線
    }
    
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.selected_symbol: Optional[str] = None
        self.current_price: float = 0.0
        self.current_message: Optional[discord.Message] = None
        self.current_timeframe: str = "日"      # 預設日線
        self.last_chart_update: float = 0.0     # 更新圖表 CD 計時
    
    def _build_detail_embed(self, symbol: str, price: float, chart_url: Optional[str], 
                            avg_cost: Optional[float] = None, balance: int = 0) -> discord.Embed:
        """構建股票詳細 Embed（共用邏輯）"""
        embed = discord.Embed(
            title=f"{symbol}",
            color=discord.Color.gold()
        )
        
        price_str = f"💹 {price:,.2f}"
        embed.add_field(name="現價", value=price_str, inline=True)
        embed.add_field(name="餘額", value=f"💰 {balance:,}", inline=True)
        embed.add_field(name="時間框架", value=f"📅 {self.current_timeframe}", inline=True)
        
        if avg_cost is not None and avg_cost > 0:
            # 如果有成本信息，計算損益
            # 從 get_user_stocks 獲取完整的持倉信息
            user_stocks = get_user_stocks(self.user_id)
            position = next((s for s in user_stocks if s['symbol'] == symbol), None)
            
            if position:
                shares_str = f"📊 {position['shares']} 股"
                cost_str = f"${position['avg_cost']:.2f}"
                pnl = (price - position['avg_cost']) * position['shares']
                pnl_pct = (pnl / (position['avg_cost'] * position['shares'])) * 100 if position['avg_cost'] > 0 else 0
                pnl_color = "📈" if pnl >= 0 else "📉"
                pnl_str = f"{pnl_color} {pnl:,.0f} ({pnl_pct:+.1f}%)"
                
                embed.add_field(name="持倉", value=shares_str, inline=True)
                embed.add_field(name="平均成本", value=cost_str, inline=True)
                embed.add_field(name="未實現損益", value=pnl_str, inline=True)
            else:
                embed.add_field(name="持倉", value="無", inline=True)
                embed.add_field(name="\u200b", value="\u200b", inline=True)
        else:
            embed.add_field(name="持倉", value="無", inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        if chart_url:
            embed.set_image(url=chart_url)
        else:
            embed.add_field(name="⚠️ 圖表", value="目前無法載入圖表", inline=False)
        
        embed.set_footer(text="👇 選擇時間框架或進行交易")
        return embed
    
    async def show_selection_view(self, interaction: discord.Interaction, is_new_message: bool = False):
        """顯示股票選擇視圖（首次發送）"""
        # 在線程池中執行數據庫操作，避免阻塞事件迴圈
        loop = asyncio.get_event_loop()
        balance = await loop.run_in_executor(None, lambda: get_user_kkcoin(self.user_id))
        
        embed = discord.Embed(
            title="📊 私人操盤室",
            description="選擇標的開始交易",
            color=discord.Color.gold()
        )
        embed.add_field(name="可用資金", value=f"💰 {balance:,} KK", inline=False)
        embed.add_field(name="\u200b", value="**👇 選擇標的**", inline=False)
        embed.set_footer(text="✨ 虛擬交易，零風險")
        
        view = StockSelectionView(self)
        
        # 發送新的私人訊息（不編輯原來的回應）
        if is_new_message or not interaction.response.is_done():
            msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            self.current_message = msg
        else:
            # 如果已經有過一次 defer/response，就用 followup 發送
            msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            self.current_message = msg
    
    async def update_selection_view(self, interaction: discord.Interaction):
        """更新股票選擇視圖（編輯現有訊息）"""
        # 在線程池中執行數據庫操作，避免阻塞事件迴圈
        loop = asyncio.get_event_loop()
        balance = await loop.run_in_executor(None, lambda: get_user_kkcoin(self.user_id))
        
        embed = discord.Embed(
            title="📊 私人操盤室",
            description="選擇標的開始交易",
            color=discord.Color.gold()
        )
        embed.add_field(name="可用資金", value=f"💰 {balance:,} KK", inline=False)
        embed.add_field(name="\u200b", value="**👇 選擇標的**", inline=False)
        embed.set_footer(text="✨ 虛擬交易，零風險")
        
        view = StockSelectionView(self)
        
        await interaction.response.defer(ephemeral=True)
        # 編輯現有訊息
        if self.current_message:
            try:
                await self.current_message.edit(embed=embed, view=view)
            except:
                pass
    
    async def show_selection_view_followup(self, interaction: discord.Interaction):
        """使用 followup 發送股票選擇視圖（用於已 defer 的情況）"""
        try:
            loop = asyncio.get_event_loop()
            balance = await loop.run_in_executor(None, lambda: get_user_kkcoin(self.user_id))
            
            embed = discord.Embed(
                title="📊 私人操盤室",
                description="選擇標的開始交易",
                color=discord.Color.gold()
            )
            embed.add_field(name="可用資金", value=f"💰 {balance:,} KK", inline=False)
            embed.add_field(name="\u200b", value="**👇 選擇標的**", inline=False)
            embed.set_footer(text="✨ 虛擬交易，零風險")
            
            view = StockSelectionView(self)
            
            logger.info(f"📨 [ENTRY] 使用 followup 發送股票選擇視圖")
            msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            self.current_message = msg
            logger.info(f"✅ [ENTRY] 訊息已發送 ID: {msg.id}")
        except Exception as e:
            logger.error(f"❌ show_selection_view_followup 失敗: {e}")
            traceback.print_exc()
    
    async def show_detail_view(self, symbol: str, interaction: discord.Interaction,
                               force_refresh: bool = False, is_new_message: bool = False):
        """顯示股票詳細視圖（首次發送新訊息）"""
        try:
            price = await fetch_price(symbol)
            if price is None:
                await interaction.response.send_message("❌ 無法取得該股票價格", ephemeral=True)
                return
            
            self.selected_symbol = symbol
            self.current_price = price
            
            # 在線程池中執行數據庫操作，避免阻塞事件迴圈
            loop = asyncio.get_event_loop()
            def _get_data():
                user_stocks = get_user_stocks(self.user_id)
                position = next((s for s in user_stocks if s['symbol'] == symbol), None)
                avg_cost = position['avg_cost'] if position else None
                balance = get_user_kkcoin(self.user_id)
                return avg_cost, balance
            
            avg_cost, balance = await loop.run_in_executor(None, _get_data)
            
            period, interval = self.TIMEFRAME_PARAMS.get(self.current_timeframe, ("3mo", "1d"))
            logger.info(f"📊 取得 {symbol} 圖表 period={period} interval={interval} force={force_refresh}")
            
            # 傳遞成本線資訊給 fetch_chart
            chart_url = await fetch_chart(symbol, period=period, interval=interval,
                                          force_refresh=force_refresh, avg_cost=avg_cost)
            if not chart_url:
                logger.warning(f"⚠️ {symbol} 圖表 URL 為 None，跳過圖表顯示")
            
            embed = self._build_detail_embed(symbol, price, chart_url, avg_cost, balance)
            view = StockDetailView(self, symbol, price)
            
            # 發送新的私人訊息
            if is_new_message or not interaction.response.is_done():
                msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                self.current_message = msg
            else:
                msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                self.current_message = msg
        
        except Exception as e:
            logger.error(f"❌ 顯示股票詳細失敗: {e}")
            traceback.print_exc()
            await interaction.response.send_message("❌ 顯示詳細失敗", ephemeral=True)
    
    async def update_detail_view(self, symbol: str, interaction: discord.Interaction,
                                  force_refresh: bool = False):
        """更新股票詳細視圖（編輯現有訊息）"""
        try:
            # 先 defer，避免「interaction token 已過期」的錯誤
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            price = await fetch_price(symbol)
            if price is None:
                logger.warning(f"⚠️ 無法取得 {symbol} 的價格")
                return
            
            self.selected_symbol = symbol
            self.current_price = price
            
            # 在線程池中執行數據庫操作，避免阻塞事件迴圈
            loop = asyncio.get_event_loop()
            def _get_data():
                user_stocks = get_user_stocks(self.user_id)
                position = next((s for s in user_stocks if s['symbol'] == symbol), None)
                avg_cost = position['avg_cost'] if position else None
                balance = get_user_kkcoin(self.user_id)
                return avg_cost, balance
            
            avg_cost, balance = await loop.run_in_executor(None, _get_data)
            
            period, interval = self.TIMEFRAME_PARAMS.get(self.current_timeframe, ("3mo", "1d"))
            logger.info(f"📊 [UPDATE] 取得 {symbol} 圖表 period={period} interval={interval} force_refresh={force_refresh}")
            chart_url = await fetch_chart(symbol, period=period, interval=interval,
                                          force_refresh=force_refresh, avg_cost=avg_cost)
            if chart_url:
                logger.info(f"✅ [UPDATE] 圖表 URL 已取得: {chart_url[:80]}...")
            else:
                logger.warning(f"⚠️ [UPDATE] 圖表 URL 為空")
            
            embed = self._build_detail_embed(symbol, price, chart_url, avg_cost, balance)
            view = StockDetailView(self, symbol, price)
            
            # 編輯現有訊息，而不是發送新的
            if self.current_message:
                try:
                    logger.info(f"📝 [UPDATE] 編輯訊息 ID: {self.current_message.id}")
                    await self.current_message.edit(embed=embed, view=view)
                    logger.info(f"✅ [UPDATE] 訊息編輯成功")
                except Exception as edit_err:
                    logger.error(f"❌ [UPDATE] 編輯訊息失敗: {edit_err}")
            else:
                logger.warning(f"⚠️ [UPDATE] 沒有可編輯的訊息（current_message 為 None）。發送新訊息...")
                try:
                    if not interaction.response.is_done():
                        msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                    else:
                        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                    self.current_message = msg
                    logger.info(f"✅ [UPDATE] 已發送新訊息 ID: {msg.id}")
                except Exception as send_err:
                    logger.error(f"❌ [UPDATE] 發送訊息失敗: {send_err}")
        
        except Exception as e:
            logger.error(f"❌ 更新股票詳細失敗: {e}")
            traceback.print_exc()
    
    async def _update_trading_room_embed(self, symbol: str):
        """無 interaction 情境下直接更新操盤室 embed（例如交易完成後刷新）"""
        if not self.current_message:
            return
        try:
            price = await fetch_price(symbol)
            if price is None:
                return
            
            self.selected_symbol = symbol
            self.current_price = price
            
            # 在線程池中執行數據庫操作，避免阻塞事件迴圈
            loop = asyncio.get_event_loop()
            def _get_data():
                user_stocks = get_user_stocks(self.user_id)
                position = next((s for s in user_stocks if s['symbol'] == symbol), None)
                avg_cost = position['avg_cost'] if position else None
                balance = get_user_kkcoin(self.user_id)
                return avg_cost, balance
            
            avg_cost, balance = await loop.run_in_executor(None, _get_data)
            
            period, interval = self.TIMEFRAME_PARAMS.get(self.current_timeframe, ("3mo", "1d"))
            chart_url = await fetch_chart(symbol, period=period, interval=interval, avg_cost=avg_cost)
            
            embed = self._build_detail_embed(symbol, price, chart_url, avg_cost, balance)
            view = StockDetailView(self, symbol, price)
            
            try:
                await self.current_message.edit(embed=embed, view=view)
            except Exception:
                # 如果無法編輯（可能為 ephemeral 或訊息已過期），忽略即可
                pass
        except Exception as e:
            logger.debug(f"⚠️ 背景刷新操盤室失敗 (token 可能已過期): {e}")
    
    async def update_stock_select(self):
        """更新下拉選單內容"""
        pass
    
    async def update_embed(self, interaction: discord.Interaction, defer_first: bool = True):
        """更新操盤室 Embed（交易後刷新，使用 stored message）"""
        if not self.selected_symbol:
            if defer_first:
                await interaction.response.defer(ephemeral=True)
            return
        await self._update_trading_room_embed(self.selected_symbol)



class StockSelectMenu(discord.ui.Select):
    """股票選擇下拉選單"""
    
    def __init__(self, parent_view: StockRoomView, options: List[discord.SelectOption]):
        super().__init__(
            placeholder="選擇股票代號...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        """選項變更時的回調"""
        selected_value = self.values[0]
        
        # 如果選擇自訂代號，必須先送出 Modal（不能先 defer）
        if selected_value == "CUSTOM":
            await interaction.response.send_modal(CustomStockModal(self.parent_view))
            return

        # 編輯現有訊息（而不是發送新訊息），並強制刷新圖表快取
        logger.info(f"👤 [SELECT] 使用者選擇股票: {selected_value}")
        await self.parent_view.update_detail_view(selected_value, interaction, force_refresh=True)


# ============================================================
# 自訂股票代號 Modal
# ============================================================

class CustomStockModal(discord.ui.Modal, title="輸入股票代號"):
    """自訂股票代號輸入 Modal"""
    
    stock_code = discord.ui.TextInput(
        label="股票代號",
        placeholder="例如: 2330.TW 或 AAPL",
        required=True,
        min_length=2,
        max_length=10
    )
    
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
    
    async def on_submit(self, modal_interaction: discord.Interaction):
        """提交股票代號"""
        try:
            symbol = self.stock_code.value.strip().upper()
            
            # 如果沒有已知市場後綴，自動添加 .TW
            known_suffixes = (".TW", ".TWO", ".HK", ".US", ".SS", ".SZ")
            if not any(symbol.endswith(s) for s in known_suffixes):
                symbol = f"{symbol}.TW"
            
            print(f"🔍 [STOCK_MARKET] 用戶輸入自訂代號: {symbol}", flush=True)
            
            # 測試是否能取得該股票的價格
            price = await fetch_price(symbol)
            if price is None:
                print(f"❌ [STOCK_MARKET] 無法取得 {symbol} 的價格", flush=True)
                await modal_interaction.response.send_message(
                    f"❌ 無法取得 **{symbol}** 的價格。請檢查:\n"
                    f"1. 代號是否正確\n"
                    f"2. 台股請用 .TW 後綴 (如: 2330.TW)\n"
                    f"3. 確認代號存在",
                    ephemeral=True
                )
                return
            
            print(f"✅ [STOCK_MARKET] 成功取得 {symbol} 的價格: ${price:,.2f}", flush=True)
            
            # 發送新的操盤室訊息
            await self.parent_view.show_detail_view(symbol, modal_interaction)
            
            # 額外確認訊息
            await modal_interaction.followup.send(
                f"✅ 已選擇 **{symbol}**",
                ephemeral=True
            )
        
        except Exception as e:
            print(f"❌ [STOCK_MARKET] 自訂代號處理失敗: {e}", flush=True)
            logger.error(f"❌ 自訂代號處理失敗: {e}")
            traceback.print_exc()
            await modal_interaction.response.send_message("❌ 處理失敗，請稍後再試", ephemeral=True)


class TradeModal(discord.ui.Modal, title="進行交易"):
    """交易輸入 Modal"""
    
    quantity = discord.ui.TextInput(
        label="交易數量",
        placeholder="輸入要買入/賣出的股數",
        required=True,
        min_length=1,
        max_length=10
    )
    
    def __init__(self, parent_view: StockRoomView, action: str, symbol: str, price: float):
        super().__init__()
        self.parent_view = parent_view
        self.action = action  # 'buy' or 'sell'
        self.symbol = symbol
        self.price = price
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交交易"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            qty = int(self.quantity.value)
            if qty <= 0:
                raise ValueError("數量必須大於 0")
            
            # 計算成本或獲得
            total_cost = qty * self.price
            user_id = interaction.user.id
            balance = get_user_kkcoin(user_id)
            
            if self.action == "buy":
                # 買入
                if balance < total_cost:
                    await interaction.followup.send(
                        f"❌ KK 幣不足！\n需要: {total_cost:,} KK\n當前: {balance:,} KK",
                        ephemeral=True
                    )
                    return
                
                # 收取 KK 幣
                update_user_kkcoin(user_id, -int(total_cost))
                
                # 加入持倉
                add_stock_position(user_id, self.symbol, qty, self.price)
                
                embed = discord.Embed(
                    title="✅ 買入成功",
                    description=f"買入 {qty} 股 {self.symbol}\n價格: ${self.price:,.2f}/股\n總成本: {int(total_cost):,} KK",
                    color=discord.Color.green()
                )
            
            elif self.action == "sell":
                # 賣出
                success, realized_pnl = close_stock_position(user_id, self.symbol, qty, self.price)
                
                if not success:
                    await interaction.followup.send(
                        f"❌ 持倉不足或不存在該持倉！",
                        ephemeral=True
                    )
                    return
                
                # 增加 KK 幣
                update_user_kkcoin(user_id, int(total_cost))
                
                # 記錄已實現損益
                realized_total = get_user_field(user_id, REALIZED_PNL_FIELD, default=0.0)
                set_user_field(user_id, REALIZED_PNL_FIELD, realized_total + (realized_pnl or 0))
                
                embed = discord.Embed(
                    title="✅ 賣出成功",
                    description=f"賣出 {qty} 股 {self.symbol}\n價格: ${self.price:,.2f}/股\n總收入: {int(total_cost):,} KK",
                    color=discord.Color.green()
                )
                
                if realized_pnl:
                    pnl_text = f"+{int(realized_pnl)}" if realized_pnl > 0 else f"{int(realized_pnl)}"
                    embed.add_field(name="已實現損益", value=pnl_text, inline=True)
            
            # 更新操盤室
            embed.set_footer(text="交易已完成，操盤室已更新")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # 異步更新操盤室視圖（不依賴 interaction token）
            async def refresh_view():
                await asyncio.sleep(0.5)
                try:
                    await self.parent_view._update_trading_room_embed(self.symbol)
                except Exception as e:
                    logger.debug(f"⚠️ 自動刷新操盤室失敗: {e}")
            
            # 在背景運行刷新
            asyncio.create_task(refresh_view())
        
        except ValueError:
            await interaction.followup.send("❌ 請輸入有效的數字", ephemeral=True)
        except Exception as e:
            logger.error(f"❌ 交易失敗: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ 交易失敗，請稍後再試。", ephemeral=True)


# ============================================================
# 主 Cog
# ============================================================

class StockMarket(commands.Cog):
    """虛擬股票市場 Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.market_channel_id = MARKET_CHANNEL_ID
        self.market_message: Optional[discord.Message] = None
        self.market_data = load_market_message_data()
    
    async def _setup_market_message(self):
        """設置市場消息（在 setup() 中由異步任務調用）"""
        try:
            print("⏳ [STOCK_MARKET] 等待 bot 就緒...", flush=True)
            await self.bot.wait_until_ready()
            print("✅ [STOCK_MARKET] Bot 已就緒，開始初始化", flush=True)
            
            # 啟動定期更新
            if not self.periodic_market_update.is_running():
                print("⏰ [STOCK_MARKET] 啟動定期更新任務...", flush=True)
                self.periodic_market_update.start()
            
            # 初始化市場消息
            await self.initialize_market_message()
            
            print("✅ [STOCK_MARKET] 市場設置完成", flush=True)
        except Exception as e:
            print(f"❌ [STOCK_MARKET] 市場設置失敗: {e}", flush=True)
            logger.error(f"❌ [STOCK_MARKET] 市場設置失敗: {e}")
            traceback.print_exc()
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot 啟動時的初始化"""
        print(f"🚀 [STOCK_MARKET] on_ready 被觸發", flush=True)
        logger.info("🚀 [STOCK_MARKET] on_ready 被觸發")
        
        try:
            # 註冊持久視圖
            print(f"📌 [STOCK_MARKET] 註冊 StockEntryView...", flush=True)
            self.bot.add_view(StockEntryView(self))
            
            # 嘗試恢復舊訊息或發送新訊息
            print(f"📡 [STOCK_MARKET] 初始化市場訊息...", flush=True)
            await self.initialize_market_message()
            
            # 啟動定期更新
            if not self.periodic_market_update.is_running():
                print(f"⏰ [STOCK_MARKET] 啟動定期更新任務...", flush=True)
                self.periodic_market_update.start()
            
            print("✅ [STOCK_MARKET] StockMarket Cog 完全初始化！", flush=True)
            logger.info("✅ StockMarket Cog 已載入")
        
        except Exception as e:
            print(f"❌ [STOCK_MARKET] on_ready 失敗: {e}", flush=True)
            logger.error(f"❌ on_ready 失敗: {e}")
            traceback.print_exc()
    
    async def _get_market_channel(self) -> Optional[discord.abc.GuildChannel]:
        """嘗試取得市場頻道：先用緩存，沒有再發 API 請求"""
        channel = self.bot.get_channel(self.market_channel_id)
        if channel:
            return channel

        try:
            return await self.bot.fetch_channel(self.market_channel_id)
        except discord.Forbidden:
            logger.warning("⚠️ 無法存取市場頻道（權限不足）")
        except discord.NotFound:
            logger.warning("⚠️ 找不到市場頻道（ID 可能錯誤）")
        except Exception as e:
            logger.warning(f"⚠️ 取得市場頻道失敗: {e}")
        return None

    async def initialize_market_message(self):
        """初始化市場訊息（開機時檢查是否已有訊息）"""
        try:
            print(f"📍 [STOCK_MARKET] 開始初始化市場訊息，頻道 ID: {self.market_channel_id}", flush=True)
            
            channel = await self._get_market_channel()
            if not channel:
                print(f"❌ [STOCK_MARKET] 無法取得市場頻道！", flush=True)
                return

            print(f"✅ [STOCK_MARKET] 成功取得頻道: {channel.name} (ID: {channel.id})", flush=True)

            # 檢查是否有保存的 message ID
            message_id = self.market_data.get("message_id")
            print(f"💾 [STOCK_MARKET] 保存的 message ID: {message_id}", flush=True)

            if message_id:
                try:
                    self.market_message = await channel.fetch_message(int(message_id))
                    print(f"✅ [STOCK_MARKET] 恢復舊訊息 ID: {message_id}", flush=True)
                    logger.info(f"✅ 恢復舊訊息 ID: {message_id}")
                except discord.NotFound:
                    print(f"⚠️ [STOCK_MARKET] 舊訊息已被刪除，發送新訊息", flush=True)
                    logger.warning(f"⚠️ 舊訊息已被刪除，發送新訊息")
                    self.market_message = None
                except Exception as e:
                    print(f"⚠️ [STOCK_MARKET] 無法恢復訊息: {e}", flush=True)
                    logger.warning(f"⚠️ 無法恢復訊息: {e}")
                    self.market_message = None

            # 如果沒有訊息，發送新訊息
            if not self.market_message:
                print(f"📮 [STOCK_MARKET] 沒有現存訊息，正在發送新訊息...", flush=True)
                await self.update_market_embed()

        except Exception as e:
            print(f"❌ [STOCK_MARKET] 初始化市場訊息失敗: {e}", flush=True)
            logger.error(f"❌ 初始化市場訊息失敗: {e}")
            traceback.print_exc()
    
    async def update_market_embed(self):
        """更新市場主 Embed（編輯現有訊息或發送新訊息）"""
        try:
            print(f"📊 [STOCK_MARKET] 開始更新市場 Embed...", flush=True)
            
            channel = await self._get_market_channel()
            if not channel:
                print(f"❌ [STOCK_MARKET] 無法取得市場頻道！", flush=True)
                return
            
            print(f"📈 [STOCK_MARKET] 計算市場摘要...", flush=True)
            # 計算市場摘要
            all_users = get_all_users()
            print(f"📞 [STOCK_MARKET] 取得用戶數: {len(all_users) if all_users else 0}", flush=True)
            
            active_traders = []
            
            if all_users:
                for user_data in all_users:
                    stocks = user_data.get('stocks')
                    if not stocks or stocks == '[]':
                        continue
                    
                    try:
                        stocks_list = json.loads(stocks) if isinstance(stocks, str) else stocks
                        if not stocks_list:
                            continue
                        
                        # 簡化：只計算持股數
                        total_shares = sum(s.get('shares', 0) for s in stocks_list)
                        realized_pnl = user_data.get(REALIZED_PNL_FIELD, 0)
                        
                        active_traders.append({
                            'user_id': user_data['user_id'],
                            'shares': total_shares,
                            'realized_pnl': realized_pnl
                        })
                    except Exception as e:
                        print(f"⚠️ [STOCK_MARKET] 解析用戶數據失敗: {e}", flush=True)
                        continue
            
            print(f"🎯 [STOCK_MARKET] 活躍交易者數: {len(active_traders)}", flush=True)
            
            # 建立摘要 Embed - 簡潔設計
            embed = discord.Embed(
                title="🏦 台灣虛擬股市",
                description="模擬交易 台股 使用 KK 幣",
                color=discord.Color.gold(),
                timestamp=datetime.now()
            )
            
            # 市場統計 - 簡化格式
            total_shares = sum(t['shares'] for t in active_traders)
            embed.add_field(
                name="📈 市場",
                value=f"交易者: {len(active_traders)} | 總股數: {total_shares}",
                inline=True
            )
            
            # 損益排行（前5名）
            if active_traders:
                sorted_traders = sorted(active_traders, key=lambda x: x['realized_pnl'], reverse=True)
                leaderboard_lines = []
                for idx, trader in enumerate(sorted_traders[:5]):
                    pnl = trader['realized_pnl']
                    emoji = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else f"{idx+1}."
                    pnl_text = f"+{int(pnl)}" if pnl > 0 else f"{int(pnl)}"
                    leaderboard_lines.append(f"{emoji} {pnl_text} KK")
                
                leaderboard = "\n".join(leaderboard_lines)
                embed.add_field(name="🏆 排行", value=leaderboard, inline=True)
            
            embed.add_field(name="\u200b", value="**👇 點擊進入你的操盤室**", inline=False)
            embed.set_footer(text="熱門: 2330 | 0050 | 2454 | 自訂代號 | 無風險交易")
            
            
            print(f"✏️ [STOCK_MARKET] Embed 已生成，checking message 狀態...", flush=True)
            print(f"   - market_message 存在: {self.market_message is not None}", flush=True)
            
            # 編輯現有訊息或發送新訊息
            if self.market_message:
                try:
                    print(f"🔄 [STOCK_MARKET] 編輯現存訊息 ID: {self.market_message.id}", flush=True)
                    await self.market_message.edit(embed=embed, view=StockEntryView(self))
                    print("✅ [STOCK_MARKET] 市場 Embed 已更新（編輯）", flush=True)
                    logger.info("✅ 市場 Embed 已更新（編輯）")
                    return
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                    # 如果訊息不存在或無法編輯，嘗試刪除舊訊息（若仍存在），避免重複
                    print(f"⚠️ [STOCK_MARKET] 無法編輯舊訊息（可能已刪除/無權限），將嘗試刪除並發送新訊息: {e}", flush=True)
                    logger.warning(f"⚠️ 無法編輯舊訊息，將發送新訊息: {e}")
                    try:
                        await self.market_message.delete()
                        print("✅ [STOCK_MARKET] 已刪除舊市場訊息", flush=True)
                        logger.info("✅ 已刪除舊市場訊息")
                    except Exception as delete_exc:
                        print(f"⚠️ [STOCK_MARKET] 刪除舊訊息失敗（可能已不存在）: {delete_exc}", flush=True)
                        logger.debug(f"⚠️ 刪除舊訊息失敗: {delete_exc}")
                    self.market_message = None
                except Exception as e:
                    print(f"❌ [STOCK_MARKET] 更新市場 Embed 失敗: {e}", flush=True)
                    logger.error(f"❌ 更新市場 Embed 失敗: {e}")
                    traceback.print_exc()
                    return

            # 如果沒有可編輯的舊訊息，發送新訊息
            print(f"📤 [STOCK_MARKET] 發送新的市場 Embed 訊息...", flush=True)
            self.market_message = await channel.send(embed=embed, view=StockEntryView(self))
            self.market_data["message_id"] = self.market_message.id
            save_market_message_data(self.market_data)
            print(f"✅ [STOCK_MARKET] 市場 Embed 已發送 (Message ID: {self.market_message.id})", flush=True)
            logger.info(f"✅ 市場 Embed 已發送 (Message ID: {self.market_message.id})")
        
        except Exception as e:
            print(f"❌ [STOCK_MARKET] 更新市場 Embed 失敗: {e}", flush=True)
            logger.error(f"❌ 更新市場 Embed 失敗: {e}")
            traceback.print_exc()
    
    @tasks.loop(minutes=5)
    async def periodic_market_update(self):
        """定期更新市場行情（每 5 分鐘）"""
        await self.update_market_embed()
    
    @periodic_market_update.before_loop
    async def before_periodic_update(self):
        """等待 Bot 就緒"""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    """Cog 載入"""
    try:
        print("🔧 [STOCK_MARKET] 開始載入 StockMarket Cog...", flush=True)
        logger.info("🔧 [STOCK_MARKET] 開始載入 StockMarket Cog...")
        
        cog = StockMarket(bot)
        await bot.add_cog(cog)
        
        print("✅ [STOCK_MARKET] StockMarket Cog 已設置！", flush=True)
        logger.info("✅ [STOCK_MARKET] StockMarket Cog 已設置")
        
        # 立即註冊持久視圖（不等待 on_ready）
        print("📌 [STOCK_MARKET] 在 setup 中註冊 StockEntryView...", flush=True)
        bot.add_view(StockEntryView(cog))
        
        # 異步初始化市場消息（因為 Cog 被添加後 on_ready listener 不會被觸發）
        print("⏳ [STOCK_MARKET] 安排市場消息初始化...", flush=True)
        cog._init_task = asyncio.create_task(cog._setup_market_message())
        
    except Exception as e:
        print(f"❌ [STOCK_MARKET] Cog 載入失敗: {e}", flush=True)
        logger.error(f"❌ [STOCK_MARKET] Cog 載入失敗: {e}")
        traceback.print_exc()
