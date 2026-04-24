#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SerpApi Google Trends 集成模塊
用於 Discord Bot 的台灣趨勢獲取

使用方式：
    from market_trends_serpapi import get_trending_topics, format_trends_embed
    
    trends = await get_trending_topics()
    embed = format_trends_embed(trends)
    await channel.send(embed=embed)
"""

import os
import aiohttp
import asyncio
import logging
from dotenv import load_dotenv
from typing import List, Dict, Optional
from datetime import datetime

# 設定 logging
logger = logging.getLogger(__name__)

# 加載 .env
load_dotenv()

SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')

if not SERPAPI_API_KEY:
    raise ValueError("❌ 未找到 SERPAPI_API_KEY，請檢查 .env 文件")


async def get_trending_topics(
    region: str = "TW",
    limit: int = 10,
    timeout: int = 10
) -> Optional[List[Dict[str, str]]]:
    """
    異步獲取指定地區的 Google Trends
    
    Args:
        region: 地區代碼（預設台灣 TW）
        limit: 返回的趨勢數量
        timeout: 請求超時時間
    
    Returns:
        趨勢列表或 None
    
    Example:
        trends = await get_trending_topics("TW", limit=10)
    """
    url = "https://api.serpapi.com/search"
    
    params = {
        "engine": "google_trends",
        "q": "trending-now",
        "geo": region,
        "api_key": SERPAPI_API_KEY
    }
    
    try:
        logger.debug(f"[Trends] 正在連接 SerpApi... URL: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                logger.debug(f"[Trends] 收到回應: HTTP {response.status}")
                
                if response.status != 200:
                    logger.error(f"[Trends] ❌ API 錯誤 - HTTP {response.status}")
                    return None
                
                data = await response.json()
                logger.debug(f"[Trends] 📊 回應 keys: {list(data.keys())}")
                
                # 檢查 API 錯誤
                if 'error' in data:
                    logger.error(f"[Trends] ❌ SerpApi 錯誤: {data['error']}")
                    return None
                
                # 提取趨勢
                trends = []
                if 'trending_searches' in data:
                    logger.info(f"[Trends] 📊 找到 {len(data['trending_searches'])} 項趨勢")
                    for item in data['trending_searches'][:limit]:
                        # 從 SerpApi 實際回傳的字段提取數據
                        trend = {
                            'topic': item.get('query', 'N/A'),
                            'search_volume': item.get('search_volume', 0),
                            'increase_percentage': item.get('increase_percentage', 0),
                            'category': item.get('categories', [{}])[0].get('name', '其他') if item.get('categories') else '其他'
                        }
                        trends.append(trend)
                
                logger.info(f"[Trends] ✅ 成功獲取 {len(trends)} 項趨勢")
                return trends if trends else None
    
    except asyncio.TimeoutError:
        logger.error(f"[Trends] ❌ 請求超時 (>{timeout}秒)")
        return None
    except aiohttp.ClientConnectorError as e:
        logger.error(f"[Trends] ❌ DNS/連接錯誤: {type(e).__name__}: {e}")
        return None
    except aiohttp.ClientError as e:
        logger.error(f"[Trends] ❌ aiohttp 客戶端錯誤: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.exception(f"[Trends] ❌ 未知錯誤: {type(e).__name__}: {e}")


def format_trends_embed(trends: List[Dict[str, str]]) -> Optional[object]:
    """
    將趨勢數據轉換為 Discord Embed
    
    Args:
        trends: 趨勢列表
    
    Returns:
        Discord Embed 物件
    
    需要 discord.py：
        pip install discord.py
    """
    try:
        import discord
    except ImportError:
        print("⚠️ discord.py 未安裝，返回文字格式")
        return format_trends_text(trends)
    
    if not trends:
        embed = discord.Embed(
            title="❌ 無趨勢數據",
            description="暫無台灣 Google Trends 數據",
            color=discord.Color.red()
        )
        return embed
    
    embed = discord.Embed(
        title="📊 台灣 Google Trends",
        description=f"取得時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        color=discord.Color.blue()
    )
    
    for idx, trend in enumerate(trends[:10], 1):
        # 計算排行圖表
        bar_length = min(int(idx * 2), 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        
        # 構建欄位內容
        increase = trend.get('increase_percentage', 0)
        volume = trend.get('search_volume', 0)
        category = trend.get('category', '其他')
        
        field_value = f"`{bar}`\n"
        field_value += f"🔥 **{trend['topic']}**\n"
        field_value += f"搜尋量：{volume:,} | 上升：↑ {increase}% | 分類：{category}"
        
        embed.add_field(
            name=f"#{idx}",
            value=field_value,
            inline=False
        )
    
    embed.set_footer(text="數據來源：Google Trends (via SerpApi)")
    return embed


def format_trends_text(trends: List[Dict[str, str]]) -> str:
    """
    將趨勢數據轉換為文字格式（用於測試或日誌）
    
    Args:
        trends: 趨勢列表
    
    Returns:
        格式化的文字
    """
    if not trends:
        return "❌ 無趨勢數據"
    
    text = f"📊 台灣 Google Trends (更新：{datetime.now().strftime('%H:%M:%S')})\n"
    text += "=" * 70 + "\n"
    
    for idx, trend in enumerate(trends, 1):
        topic = trend['topic']
        increase = trend.get('increase_percentage', 0)
        volume = trend.get('search_volume', 0)
        category = trend.get('category', '其他')
        
        text += f"#{idx}. {topic}\n"
        text += f"   搜尋量：{volume:,} | 上升：↑ {increase}% | 分類：{category}\n"
    
    return text


# ============================================================
# 快速測試
# ============================================================
if __name__ == "__main__":
    import sys
    
    # 同步版本測試
    async def test():
        print("🚀 開始測試 SerpApi...\n")
        trends = await get_trending_topics("TW", limit=10)
        
        if trends:
            print("✅ 成功獲取趨勢！\n")
            print(format_trends_text(trends))
        else:
            print("❌ 無法獲取趨勢")
    
    # 執行測試
    asyncio.run(test())
