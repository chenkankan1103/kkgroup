# -*- coding: utf-8 -*-
"""
Threads 趨勢樂透系統 Cog
- /threads_lottery 命令
- 互動式按鈕選擇
- 自訂關鍵字投注
"""

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
import json
import asyncio
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import List, Optional
import logging

from shared.utils.view_registry import PersistentViewBase
from shared.utils.threads_lottery_manager import get_manager as get_lottery_manager
from status_dashboard import add_log

log = logging.getLogger("threads_lottery_cog")

# 台灣時區 (UTC+8)
TW_TZ = ZoneInfo('Asia/Taipei')


class TrendSelectionView(PersistentViewBase):
    """趨勢選擇視圖 - 用戶依序點擊選擇前三名"""
    
    def __init__(self, cog, trends: List[str]):
        super().__init__()
        self.cog = cog
        self.trends = trends
        self.selected = []  # 存儲用戶依序點擊的趨勢索引
        
        # 創建 5 個按鈕
        for i, trend in enumerate(trends):
            button = Button(
                label=f"{i+1}. {trend[:20]}...",
                style=discord.ButtonStyle.primary,
                custom_id=f"trend_select_{i}"
            )
            button.callback = self.make_trend_callback(i)
            self.add_item(button)
    
    def make_trend_callback(self, trend_idx: int):
        """創建趨勢按鈕的回調函數"""
        async def callback(interaction: discord.Interaction):
            if len(self.selected) >= 3:
                await interaction.response.send_message(
                    "❌ 已選擇 3 個趨勢，不能再選",
                    ephemeral=True
                )
                return
            
            if trend_idx in self.selected:
                await interaction.response.send_message(
                    "❌ 此趨勢已選，不能重複選擇",
                    ephemeral=True
                )
                return
            
            self.selected.append(trend_idx)
            order = len(self.selected)
            
            # 更新按鈕顏色
            for item in self.children:
                if hasattr(item, 'custom_id') and item.custom_id == f"trend_select_{trend_idx}":
                    if order == 1:
                        item.style = discord.ButtonStyle.success
                        item.label = f"🥇 {self.trends[trend_idx][:15]}..."
                    elif order == 2:
                        item.style = discord.ButtonStyle.success
                        item.label = f"🥈 {self.trends[trend_idx][:15]}..."
                    elif order == 3:
                        item.style = discord.ButtonStyle.success
                        item.label = f"🥉 {self.trends[trend_idx][:15]}..."
                    item.disabled = False
            
            # 顯示當前選擇進度
            progress = f"✅ 已選 {order}/3: {self.trends[trend_idx]}"
            await interaction.response.send_message(progress, ephemeral=True)
            
            # 3 個都選完後，顯示自訂關鍵字輸入提示
            if len(self.selected) == 3:
                await asyncio.sleep(1)
                # 準備自訂關鍵字 Modal
                modal = CustomKeywordModal(self.cog, self.trends, self.selected)
                await interaction.followup.send(
                    "✅ 已選擇全部 3 個趨勢！\n現在可以點擊下方的「新增自訂關鍵字」按鈕，或直接完成投注。",
                    view=FinalizeView(self.cog, self.trends, self.selected),
                    ephemeral=True
                )
        
        return callback


class CustomKeywordModal(Modal, title="新增自訂關鍵字"):
    """用戶輸入自訂關鍵字"""
    
    keyword = TextInput(
        label="輸入關鍵字",
        placeholder="例: 洪醬、楓星、傳說對決...",
        required=False,
        max_length=50
    )
    
    def __init__(self, cog, trends: List[str], selected: List[int]):
        super().__init__()
        self.cog = cog
        self.trends = trends
        self.selected = selected
    
    async def on_submit(self, interaction: discord.Interaction):
        keyword = self.keyword.value.strip()
        await interaction.response.defer()
        
        # 調用 finalize_bet
        await finalize_bet(
            self.cog, interaction, self.trends, self.selected, keyword
        )


class FinalizeView(PersistentViewBase):
    """完成投注視圖"""
    
    def __init__(self, cog, trends: List[str], selected: List[int]):
        super().__init__()
        self.cog = cog
        self.trends = trends
        self.selected = selected
    
    @discord.ui.button(label="新增自訂關鍵字", style=discord.ButtonStyle.primary)
    async def add_keyword(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CustomKeywordModal(self.cog, self.trends, self.selected)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="完成投注（無自訂關鍵字）", style=discord.ButtonStyle.success)
    async def finalize(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await finalize_bet(self.cog, interaction, self.trends, self.selected, "")


async def finalize_bet(cog, interaction: discord.Interaction, trends: List[str], 
                       selected: List[int], custom_keyword: str = ""):
    """完成投注流程"""
    try:
        manager = get_lottery_manager()
        user_id = interaction.user.id
        
        # 創建投注
        bet_id = manager.create_bet(user_id, trends, selected, custom_keyword)
        
        # 格式化顯示投注內容
        embed = discord.Embed(
            title="🎰 Threads 趨勢樂透投注確認",
            description="投注已成功記錄！",
            color=0x00FF00
        )
        
        embed.add_field(
            name="📊 選擇的趨勢",
            value="\n".join([f"{i+1}. {trends[selected[i]]}" for i in range(len(selected))]),
            inline=False
        )
        
        if custom_keyword:
            embed.add_field(name="🔑 自訂關鍵字", value=f"`{custom_keyword}`", inline=False)
        
        drawing_time = datetime.now(TW_TZ) + timedelta(hours=4)
        embed.add_field(
            name="⏰ 兌獎時間",
            value=f"<t:{int(drawing_time.timestamp())}:f>",
            inline=False
        )
        
        embed.add_field(
            name="📋 投注 ID",
            value=f"`{bet_id}`",
            inline=False
        )
        
        embed.set_footer(text="4 小時後自動對獎")
        
        await interaction.followup.send(embed=embed)
        
        add_log("lottery", f"[Lottery] 用戶 {user_id} 完成投注: {bet_id}")
        
    except Exception as e:
        log.error(f"完成投注時出錯: {e}")
        await interaction.followup.send(f"❌ 投注失敗: {e}", ephemeral=True)


class ThreadsLotteryCog(commands.Cog):
    """Threads 趨勢樂透系統"""
    
    def __init__(self, bot):
        self.bot = bot
        self.check_settlement.start()
        self.update_trends_scheduled.start()  # 啟動 4 小時排程任務
    
    @commands.command(name="threads_lottery", aliases=["趨勢樂透", "tl"])
    async def threads_lottery_cmd(self, ctx: commands.Context):
        """
        啟動 Threads 趨勢樂透
        
        使用方式: /threads_lottery
        1. 系統顯示 5 個當前 Threads 熱門趨勢
        2. 依序點擊選擇預測的前三名（按 1,2,3 順序點擊）
        3. 可選填自訂關鍵字（若關鍵字出現在該時段任何趨勢中即視為中獎）
        4. 4 小時後自動對獎並通知結果
        """
        await ctx.defer()
        
        try:
            # 取得 Threads 趨勢
            trends = await self.fetch_threads_trends()
            
            if not trends or len(trends) < 5:
                await ctx.send("❌ 無法取得 Threads 趨勢，請稍後重試")
                return
            
            # 建立趨勢選擇視圖
            view = TrendSelectionView(self, trends)
            
            # 顯示趨勢
            embed = discord.Embed(
                title="🎰 Threads 趨勢樂透",
                description="請依序選擇你認為下 4 小時內會排名前三的趨勢",
                color=0xFF6B00
            )
            
            for i, trend in enumerate(trends):
                emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"][i]
                embed.add_field(
                    name=f"{emoji} {trend[:40]}",
                    value="點擊按鈕選擇",
                    inline=False
                )
            
            embed.set_footer(text="選擇 3 個趨勢後，可選填自訂關鍵字")
            
            await ctx.send(embed=embed, view=view)
            add_log("lottery", f"[Lottery] 樂透抽籤開始 by {ctx.author.id}")
            
        except Exception as e:
            log.error(f"樂透命令執行出錯: {e}")
            await ctx.send(f"❌ 出錯: {e}")
    
    async def fetch_threads_trends(self) -> Optional[List[str]]:
        """從 threads_trends.json 獲取趨勢"""
        try:
            if os.path.exists("threads_trends.json"):
                with open("threads_trends.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    trends = [item["trend"] for item in data[:5]]
                    return trends
            
            # 如果沒有預存的趨勢，嘗試即時爬取
            log.warning("threads_trends.json 不存在，嘗試即時爬取...")
            await self.update_threads_trends_async()
            
            if os.path.exists("threads_trends.json"):
                with open("threads_trends.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    trends = [item["trend"] for item in data[:5]]
                    return trends
            
            return None
            
        except Exception as e:
            log.error(f"獲取趨勢出錯: {e}")
            return None
    
    async def update_threads_trends_async(self):
        """異步執行爬蟲更新趨勢"""
        # 這將在背景線程執行爬蟲
        def run_scraper():
            try:
                import subprocess
                result = subprocess.run(
                    ["python", "threads_scraper_v2.py"],
                    capture_output=True,
                    timeout=120
                )
                return result.returncode == 0
            except Exception as e:
                log.error(f"爬蟲執行失敗: {e}")
                return False
        
        # 在背景執行
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_scraper)
    
    @tasks.loop(hours=4)
    async def update_trends_scheduled(self):
        """
        每 4 小時自動執行爬蟲更新趨勢 (台灣時間)
        執行時間: 00:00, 08:00, 12:00, 16:00, 20:00 (台灣時間)
        """
        try:
            # 使用台灣時區獲取當前時間
            now = datetime.now(TW_TZ)
            current_hour = now.hour
            
            # ✅ 只在指定時間執行 (0=00:00, 8, 12, 16, 20) 台灣時間
            allowed_hours = [0, 8, 12, 16, 20]
            
            if current_hour not in allowed_hours:
                # 不在允許的時間，跳過本次執行
                return
            
            # 只執行一次（確保同一小時不會重複執行）
            current_minute = now.minute
            if current_minute > 5:  # 如果已經超過 5 分鐘，說明已經執行過了，跳過
                return
            
            log.info(f"⏰ 開始定時爬蟲任務 ({now.strftime('%Y-%m-%d %H:%M:%S %Z')})")
            
            # 執行爬蟲
            success = await self.update_threads_trends_async()
            
            if success:
                log.info("✅ 爬蟲執行成功，趨勢已更新")
                
                # 發送更新通知到日誌頻道
                log_channel = self.bot.get_channel(int(os.getenv("LOG_CHANNEL_ID", "0")) or 0)
                if log_channel:
                    embed = discord.Embed(
                        title="🎰 Threads 趨勢已更新",
                        description=f"定時爬蟲已執行，新趨勢已保存",
                        color=0x00FF00,
                        timestamp=now
                    )
                    embed.add_field(name="執行時間", value=now.strftime('%Y-%m-%d %H:%M:%S %Z'))
                    await log_channel.send(embed=embed)
                
                add_log("scheduler", f"[Scheduler] 爬蟲執行成功 at {now.strftime('%H:%M:%S')}")
            else:
                log.warning("⚠️ 爬蟲執行失敗")
                add_log("scheduler", f"[Scheduler] 爬蟲執行失敗 at {now.strftime('%H:%M:%S')}")
        
        except Exception as e:
            log.error(f"排程爬蟲執行出錯: {e}")
            add_log("scheduler", f"[Scheduler] 排程爬蟲出錯: {e}")
    
    @tasks.loop(hours=1)
    async def check_settlement(self):
        """定期檢查並結算已到期的投注 (台灣時間)"""
        try:
            manager = get_lottery_manager()
            now = datetime.now(TW_TZ)  # 使用台灣時間
            
            # 找出所有待結算的投注
            for bet_id, bet in list(manager.bets.items()):
                if bet["status"] != "pending":
                    continue
                
                drawing_time = datetime.fromisoformat(bet["drawing_time"])
                if now >= drawing_time:
                    # 更新趨勢並結算
                    trends = await self.fetch_threads_trends()
                    if trends:
                        result = manager.check_and_settle_bet(bet_id, trends)
                        
                        # 通知用戶
                        if result["success"]:
                            user = self.bot.get_user(bet["user_id"])
                            if user:
                                await self.send_settlement_dm(user, bet, result)
            
        except Exception as e:
            log.error(f"結算檢查出錯: {e}")
    
    async def send_settlement_dm(self, user: discord.User, bet: dict, result: dict):
        """發送結算通知給用戶"""
        try:
            embed = discord.Embed(
                title="🎰 樂透對獎結果",
                color=0x00FF00 if result["result"] != "未中" else 0xFF0000
            )
            
            details = result["details"]
            embed.add_field(
                name="🎯 結果",
                value=f"**{details['award']}**",
                inline=False
            )
            
            embed.add_field(
                name="前三名",
                value="\n".join([f"{i+1}. {t}" for i, t in enumerate(details['current_trends'][:3])]),
                inline=False
            )
            
            embed.add_field(
                name="你的選擇",
                value="\n".join([f"- {t}" for t in details['selected_trends']]),
                inline=False
            )
            
            if details['custom_keyword']:
                embed.add_field(
                    name="自訂關鍵字",
                    value=f"`{details['custom_keyword']}` - {'✅ 有中' if details['custom_hit'] else '❌ 未中'}",
                    inline=False
                )
            
            await user.send(embed=embed)
            
        except Exception as e:
            log.error(f"發送結算 DM 出錯: {e}")
    
    @check_settlement.before_loop
    async def before_check_settlement(self):
        """等待 bot 準備完成"""
        await self.bot.wait_until_ready()


async def setup(bot):
    """加載 Cog"""
    await bot.add_cog(ThreadsLotteryCog(bot))
