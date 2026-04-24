#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Threads Cookie 失效 Discord 通知系統
當 Cookies 過期或失效時，自動通知管理員頻道
"""

import discord
from discord.ext import commands
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class CookieExpireNotifier:
    """Cookies 過期通知機制"""
    
    def __init__(self, bot_token=None, admin_channel_id=None):
        """
        初始化通知器
        
        Args:
            bot_token: Discord Bot Token
            admin_channel_id: 管理員頻道 ID (整數)
        """
        self.bot_token = bot_token or os.environ.get('DISCORD_BOT_TOKEN')
        self.admin_channel_id = admin_channel_id or os.environ.get('ADMIN_CHANNEL_ID')
        
        if not self.admin_channel_id:
            self.admin_channel_id = int(os.environ.get('ADMIN_CHANNEL_ID', '0'))
    
    async def send_cookie_expired_alert(self, status="EXPIRED", details=None):
        """
        發送 Cookie 失效警告到 Discord
        
        Args:
            status: 失效狀態 ("EXPIRED", "MISSING", "LOAD_FAILED")
            details: 額外詳情
        """
        
        # 如果無法聯繫 Discord，至少在日誌中記錄
        if not self.admin_channel_id or self.admin_channel_id == 0:
            logger.warning("⚠️  ADMIN_CHANNEL_ID 未設置，無法發送 Discord 通知")
            return
        
        # 準備嵌入式消息
        status_map = {
            "EXPIRED": ("⏰ 過期", discord.Color.orange()),
            "MISSING": ("❌ 缺失", discord.Color.red()),
            "LOAD_FAILED": ("🔥 加載失敗", discord.Color.red()),
        }
        
        status_text, color = status_map.get(status, ("未知", discord.Color.greyple()))
        
        embed = discord.Embed(
            title=f"🚨 Threads Cookie {status_text}",
            description=f"爬蟲無法正常運行，需要手動介入",
            color=color,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📋 失效狀態",
            value=f"```{status}```",
            inline=False
        )
        
        embed.add_field(
            name="🕐 偵測時間",
            value=f"`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
            inline=False
        )
        
        if details:
            embed.add_field(
                name="📝 詳情",
                value=f"```{details}```",
                inline=False
            )
        
        embed.add_field(
            name="🔧 需要的操作",
            value="""1. ✅ 在本機環境運行 `threads_scraper_v2.py`
2. 🌐 按提示在瀏覽器中登入 Threads
3. 📁 將 `threads_cookies.json` 上傳到 GCP VM
4. 🔄 運行 `sudo systemctl restart bot.service`

**期間爬蟲已暫停，但 Bot 仍在線**""",
            inline=False
        )
        
        # 這裡可以集成實際的 Discord API 調用
        # 目前只在日誌中記錄
        logger.error(f"Discord 警告已準備 (頻道 ID: {self.admin_channel_id})")
        
        # 如果需要真正發送，可以調用 Bot 的發送方法
        # 例如: await bot.get_channel(self.admin_channel_id).send(embed=embed)

# ============================================================================
# 集成到 Cog 中
# ============================================================================

class ThreadsCookieMonitor(commands.Cog):
    """監控 Threads Cookie 狀態的 Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.notifier = CookieExpireNotifier()
    
    @commands.command(name="cookie_status")
    @commands.has_permissions(administrator=True)
    async def check_cookie_status(self, ctx):
        """
        檢查 Threads Cookie 狀態（管理員命令）
        
        Usage: /cookie_status
        """
        
        from datetime import datetime
        import os
        
        cookies_file = "threads_cookies.json"
        
        if not os.path.exists(cookies_file):
            embed = discord.Embed(
                title="❌ Cookie 狀態: 缺失",
                description="`threads_cookies.json` 文件不存在",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # 檢查文件年齡
        file_mtime = os.path.getmtime(cookies_file)
        age_days = (datetime.now().timestamp() - file_mtime) / 86400
        
        # 判斷健康狀態
        if age_days > 7:
            status = "⚠️ 可能過期"
            color = discord.Color.orange()
        else:
            status = "✅ 有效"
            color = discord.Color.green()
        
        embed = discord.Embed(
            title=f"📋 Cookie 狀態: {status}",
            color=color,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📅 年齡",
            value=f"`{age_days:.1f} 天`",
            inline=True
        )
        
        embed.add_field(
            name="⏰ 最後更新",
            value=f"`{datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')}`",
            inline=True
        )
        
        # 讀取文件中的 Cookie 數量
        try:
            with open(cookies_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            
            embed.add_field(
                name="🔐 Cookie 數量",
                value=f"`{len(cookies)} 個`",
                inline=True
            )
        except:
            embed.add_field(
                name="🔐 Cookie 數量",
                value="`無法讀取`",
                inline=True
            )
        
        if age_days > 7:
            embed.add_field(
                name="🔧 建議操作",
                value="⚠️ 請在本機運行 `threads_scraper_v2.py` 更新 Cookies",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="update_cookies")
    @commands.has_permissions(administrator=True)
    async def update_cookies_manual(self, ctx):
        """
        手動觸發 Cookie 更新流程（管理員命令）
        
        Usage: /update_cookies
        """
        
        embed = discord.Embed(
            title="🔄 Cookie 手動更新流程",
            description="請按照以下步驟完成",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="步驟 1",
            value="在本機環境打開終端機",
            inline=False
        )
        
        embed.add_field(
            name="步驟 2",
            value="執行命令：`python threads_scraper_v2.py`",
            inline=False
        )
        
        embed.add_field(
            name="步驟 3",
            value="在瀏覽器中登入 Threads (30 秒內)",
            inline=False
        )
        
        embed.add_field(
            name="步驟 4",
            value="成功後，文件 `threads_cookies.json` 會自動生成",
            inline=False
        )
        
        embed.add_field(
            name="步驟 5",
            value="使用以下命令上傳到 GCP VM:\n```bash\ngcloud compute scp threads_cookies.json e193752468@instance-20250501-142333:~/kkgroup/ --zone=us-central1-c --tunnel-through-iap\n```",
            inline=False
        )
        
        embed.add_field(
            name="步驟 6",
            value="在 GCP VM 上重啟 Bot:\n```bash\nsudo systemctl restart bot.service\n```",
            inline=False
        )
        
        await ctx.send(embed=embed)

# ============================================================================
# 設置函數
# ============================================================================

async def setup(bot):
    """將 Cog 添加到 Bot"""
    await bot.add_cog(ThreadsCookieMonitor(bot))
    logger.info("✅ ThreadsCookieMonitor Cog 已加載")
