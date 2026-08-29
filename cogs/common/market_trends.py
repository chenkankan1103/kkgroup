#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot Cog：台灣 Google Trends 市場趨勢
使用 SerpApi 的 Google Trends API

用法：
    - 放到 cogs/shop/ 資料夾
    - 命令：/trends 或定時推送
"""

import os
import sys

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# 添加根目錄到 sys.path，以便正確導入 market_trends_serpapi
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from shared.market_trends.serpapi import (format_trends_embed,
                                          format_trends_text,
                                          get_trending_topics)

load_dotenv()

TRENDS_CHANNEL_ID = int(os.getenv("TRENDS_CHANNEL_ID", "0"))


class MarketTrends(commands.Cog):
    """台灣 Google Trends 市場趨勢"""

    def __init__(self, bot):
        self.bot = bot
        self.trends_cache = None
        self.last_update = None

        # 禁用定時任務（與 trends_lottery 功能重複）
        # self.send_trends.start()

    def cog_unload(self):
        """卸載 Cog 時停止定時任務"""
        self.send_trends.cancel()

    @commands.hybrid_command(
        name="trends", description="📊 查看台灣 Google Trends 熱門話題"
    )
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def trends(self, ctx):
        """查詢當前台灣 Google Trends 熱門話題"""

        async with ctx.typing():  # 顯示「正在輸入...」
            trends = await get_trending_topics("TW", limit=10)

            if trends:
                embed = format_trends_embed(trends)
                await ctx.send(embed=embed)
                self.trends_cache = trends
            else:
                embed = discord.Embed(
                    title="❌ 獲取趨勢失敗",
                    description="無法連接 Google Trends API，請稍後重試",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)

    @tasks.loop(hours=1)  # 每小時推送一次
    async def send_trends(self):
        """
        定時推送台灣 Google Trends

        時間表：
        - 每小時自動推送一次
        - 推送到 TRENDS_CHANNEL_ID
        """

        if not TRENDS_CHANNEL_ID or TRENDS_CHANNEL_ID == 0:
            return  # 未配置頻道則跳過

        try:
            channel = self.bot.get_channel(TRENDS_CHANNEL_ID)

            if not channel:
                print(f"⚠️ 找不到趨勢頻道 (ID: {TRENDS_CHANNEL_ID})")
                return

            # 獲取趨勢
            trends = await get_trending_topics("TW", limit=10)

            if trends:
                embed = format_trends_embed(trends)

                # 添加時間戳
                from datetime import datetime

                embed.timestamp = datetime.now()

                await channel.send(embed=embed)
                print(f"✅ 已推送台灣趨勢到 {channel.name}")
            else:
                print("⚠️ 無法獲取台灣趨勢")

        except Exception as e:
            print(f"❌ 推送趨勢時出錯：{e}")

    @send_trends.before_loop
    async def before_send_trends(self):
        """在定時任務開始前等待 Bot 準備就緒"""
        await self.bot.wait_until_ready()
        print("✅ 台灣趨勢定時推送已啟用")

    # ============================================================
    # 高級功能
    # ============================================================

    @commands.hybrid_group(name="trends_admin", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def trends_admin(self, ctx):
        """管理員命令：趨勢設定"""
        embed = discord.Embed(
            title="📊 趨勢管理",
            description="可用的管理命令：",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="/trends_admin force",
            value="立即推送一次趨勢（不等待定時）",
            inline=False,
        )
        embed.add_field(
            name="/trends_admin cache", value="查看快取的趨勢數據", inline=False
        )
        await ctx.send(embed=embed)

    @trends_admin.command(name="force")
    @commands.has_permissions(administrator=True)
    async def force_send(self, ctx):
        """立即推送趨勢"""
        async with ctx.typing():
            await self.send_trends()
            await ctx.send("✅ 已立即推送趨勢")

    @trends_admin.command(name="cache")
    @commands.has_permissions(administrator=True)
    async def show_cache(self, ctx):
        """顯示快取的趨勢"""
        if self.trends_cache:
            text = format_trends_text(self.trends_cache)
            await ctx.send(f"```\n{text}\n```")
        else:
            await ctx.send("❌ 沒有快取的趨勢數據，請先執行 /trends")


async def setup(bot):
    """加載 Cog"""
    await bot.add_cog(MarketTrends(bot))
    print("✅ MarketTrends Cog 已加載")
