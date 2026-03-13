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
from datetime import datetime
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


def load_market_message_data() -> Dict:
    """載入市場 message ID 數據"""
    if MARKET_MESSAGE_DATA_FILE.exists():
        try:
            with open(MARKET_MESSAGE_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ 載入 message 數據失敗: {e}")
    return {"message_id": None}


def save_market_message_data(data: Dict):
    """保存市場 message ID 數據"""
    try:
        with open(MARKET_MESSAGE_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ 保存 message 數據失敗: {e}")


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
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 檢查使用者 KK 幣餘額
            balance = get_user_kkcoin(interaction.user.id)
            
            # 建立個人操盤室 Embed
            embed = discord.Embed(
                title="📈 個人操盤室",
                description=f"歡迎 {interaction.user.mention}！\n選擇標的進行虛擬交易。",
                color=discord.Color.blue()
            )
            embed.add_field(name="💰 KK 幣餘額", value=f"{balance:,}", inline=False)
            embed.add_field(name="操作", value="使用下方下拉選單選擇標的，然後點擊買入或賣出。", inline=False)
            embed.set_footer(text="虛擬交易，不涉及真實金錢")
            
            # 建立個人操盤室視圖
            view = StockRoomView(self.cog, interaction.user.id)
            
            # 發送個人專用的 ephemeral Embed
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            logger.error(f"❌ 進入操盤室失敗: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ 進入操盤室失敗，請稍後再試。", ephemeral=True)


# ============================================================
# 個人操盤室視圖
# ============================================================

class StockRoomView(discord.ui.View):
    """個人操盤室主視圖"""
    
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.selected_symbol: Optional[str] = None
        self.current_price: float = 0.0
        self.current_message: Optional[discord.Message] = None
        
        # 填充股票下拉選單
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
        
        select = StockSelectMenu(self, options)
        self.add_item(select)
    
    async def update_embed(self, interaction: discord.Interaction):
        """更新操盤室 Embed，顯示選定標的的資訊"""
        
        if not self.selected_symbol:
            await interaction.response.defer()
            return
        
        try:
            await interaction.response.defer()
            
            # 取得當前價格
            price = await fetch_price(self.selected_symbol)
            if price is None:
                await interaction.followup.send("❌ 無法取得該股票價格", ephemeral=True)
                return
            
            self.current_price = price
            
            # 取得使用者持倉
            user_stocks = get_user_stocks(self.user_id)
            position = next((s for s in user_stocks if s['symbol'] == self.selected_symbol), None)
            
            # 取得 KK 幣餘額
            balance = get_user_kkcoin(self.user_id)
            
            # 建立 Embed
            embed = discord.Embed(
                title=f"📈 {self.selected_symbol}",
                color=discord.Color.green() if price > 0 else discord.Color.red()
            )
            embed.add_field(name="當前價格", value=f"${price:,.2f}", inline=True)
            embed.add_field(name="💰 可用餘額", value=f"{balance:,} KK", inline=True)
            
            if position:
                pnl = (price - position['avg_cost']) * position['shares']
                pnl_pct = (pnl / (position['avg_cost'] * position['shares'])) * 100 if position['avg_cost'] > 0 else 0
                
                embed.add_field(
                    name="📊 持倉",
                    value=f"數量: {position['shares']}\n平均成本: ${position['avg_cost']:.2f}\n未實現損益: ${pnl:,.2f} ({pnl_pct:+.1f}%)",
                    inline=False
                )
            else:
                embed.add_field(name="📊 持倉", value="無持倉", inline=False)
            
            # 取得圖表
            chart_url = await fetch_chart(self.selected_symbol, period="1mo")
            if chart_url:
                embed.set_image(url=chart_url)
            
            embed.set_footer(text="用下方按鈕進行交易")
            
            # 根據是否有舊訊息決定編輯或發送
            if self.current_message:
                await self.current_message.edit(embed=embed, view=self)
            else:
                self.current_message = await interaction.followup.send(embed=embed, view=self)
        
        except Exception as e:
            logger.error(f"❌ 更新操盤室失敗: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ 更新失敗", ephemeral=True)
    
    @discord.ui.button(label="買入", style=discord.ButtonStyle.green, emoji="📈")
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """買入按鈕"""
        if not self.selected_symbol or self.current_price <= 0:
            await interaction.response.send_message("❌ 請先選擇標的", ephemeral=True)
            return
        
        # 進出數量 Modal
        await interaction.response.send_modal(TradeModal(self, "buy", self.selected_symbol, self.current_price))
    
    @discord.ui.button(label="賣出", style=discord.ButtonStyle.red, emoji="📉")
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """賣出按鈕"""
        if not self.selected_symbol or self.current_price <= 0:
            await interaction.response.send_message("❌ 請先選擇標的", ephemeral=True)
            return
        
        # 進出數量 Modal
        await interaction.response.send_modal(TradeModal(self, "sell", self.selected_symbol, self.current_price))


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
        self.parent_view.selected_symbol = self.values[0]
        await self.parent_view.update_embed(interaction)


# ============================================================
# 交易 Modal
# ============================================================

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
            
            # 異步更新操盤室視圖 (0.5秒後)
            async def refresh_view():
                await asyncio.sleep(0.5)
                try:
                    # 直接更新視圖內容
                    await self.parent_view.update_embed(interaction)
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
            
            # 建立摘要 Embed
            embed = discord.Embed(
                title="🏦 台灣虛擬股市 - 操盤中心",
                description="使用 KK 幣進行台股模擬交易\n\n點擊下方按鈕進入個人操盤室",
                color=discord.Color.gold(),
                timestamp=datetime.now()
            )
            
            # 市場統計
            embed.add_field(
                name="📊 市場統計",
                value=f"活躍交易者: {len(active_traders)}\n總持股數: {sum(t['shares'] for t in active_traders)}",
                inline=False
            )
            
            # 損益排行（匿名）
            if active_traders:
                sorted_traders = sorted(active_traders, key=lambda x: x['realized_pnl'], reverse=True)
                leaderboard_lines = []
                for idx, trader in enumerate(sorted_traders[:5]):
                    pnl = trader['realized_pnl']
                    pnl_text = f"+{int(pnl)}" if pnl > 0 else f"{int(pnl)}"
                    leaderboard_lines.append(f"{idx+1}. 交易者 #{trader['user_id']} - {pnl_text} KK")
                
                leaderboard = "\n".join(leaderboard_lines) if leaderboard_lines else "暫無排行"
                embed.add_field(name="🏆 損益排行 (前5名)", value=leaderboard, inline=False)
            
            embed.set_footer(text="熱門代號: 2330(台積電), 0050(台灣50), 2454(聯發科) 等")
            
            print(f"✏️ [STOCK_MARKET] Embed 已生成，checking message 狀態...", flush=True)
            print(f"   - market_message 存在: {self.market_message is not None}", flush=True)
            
            # 編輯現有訊息或發送新訊息
            if self.market_message:
                try:
                    print(f"🔄 [STOCK_MARKET] 編輯現存訊息 ID: {self.market_message.id}", flush=True)
                    await self.market_message.edit(embed=embed, view=StockEntryView(self))
                    print("✅ [STOCK_MARKET] 市場 Embed 已更新（編輯）", flush=True)
                    logger.info("✅ 市場 Embed 已更新（編輯）")
                except discord.NotFound:
                    print("❌ [STOCK_MARKET] 訊息已被刪除，發送新訊息", flush=True)
                    logger.warning("⚠️ 訊息已被刪除，發送新訊息")
                    self.market_message = await channel.send(embed=embed, view=StockEntryView(self))
                    self.market_data["message_id"] = self.market_message.id
                    save_market_message_data(self.market_data)
                    print(f"✅ [STOCK_MARKET] 新訊息已發送，ID: {self.market_message.id}", flush=True)
            else:
                # 發送新訊息
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
