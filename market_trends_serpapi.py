#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SerpApi Google Trends 集成模塊
用於 Discord Bot 的台灣趨勢獲取
支持本地緩存和離線模式（當無法連接 SerpApi 時自動使用備用數據）
"""

import os
import aiohttp
import asyncio
import logging
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional
from datetime import datetime
import discord

# 設定 logging
logger = logging.getLogger(__name__)

# 加載 .env
load_dotenv()

SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')

if not SERPAPI_API_KEY:
    logger.warning("⚠️ 未找到 SERPAPI_API_KEY，將使用離線模式")

# 本地緩存文件
CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = CACHE_DIR / "trends_cache.json"
CACHE_DIR.mkdir(exist_ok=True)

# 備用趨勢數據（當 API 不可用時使用）
FALLBACK_TRENDS = [
    {"topic": "2026年", "search_volume": 15000, "increase_percentage": 1200, "category": "搜尋"},
    {"topic": "春節", "search_volume": 12500, "increase_percentage": 850, "category": "季節"},
    {"topic": "台灣", "search_volume": 11200, "increase_percentage": 650, "category": "地區"},
    {"topic": "天氣", "search_volume": 10800, "increase_percentage": 520, "category": "氣象"},
    {"topic": "新聞", "search_volume": 10200, "increase_percentage": 450, "category": "新聞"},
    {"topic": "Google", "search_volume": 9800, "increase_percentage": 380, "category": "網路"},
    {"topic": "Discord", "search_volume": 8900, "increase_percentage": 320, "category": "遊戲"},
    {"topic": "Python", "search_volume": 8200, "increase_percentage": 290, "category": "程式"},
    {"topic": "AI", "search_volume": 7600, "increase_percentage": 260, "category": "科技"},
    {"topic": "遊戲", "search_volume": 7100, "increase_percentage": 240, "category": "娛樂"},
]


async def get_trending_topics(
    region: str = "TW",
    limit: int = 10,
    timeout: int = 10,
    use_cache: bool = True,
    fallback: bool = True
) -> Optional[List[Dict]]:
    """獲取 Google Trends 熱搜（支持本地緩存和備用數據）"""
    
    # 無 API 密鑰時直接使用備用數據
    if not SERPAPI_API_KEY:
        logger.warning("[Trends] ⚠️ 無 API 密鑰，使用備用數據")
        return FALLBACK_TRENDS[:limit]
    
    # 嘗試讀取本地緩存
    if use_cache and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
                logger.info(f"[Trends] 📦 使用本地緩存")
                return cached.get('trends', [])[:limit]
        except:
            pass
    
    url = "https://api.serpapi.com/search"
    params = {
        "engine": "google_trends",
        "q": "trending-now",
        "geo": region,
        "api_key": SERPAPI_API_KEY
    }
    
    try:
        logger.debug("[Trends] 正在連接 SerpApi...")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status != 200:
                    logger.error(f"[Trends] ❌ HTTP {response.status}")
                    return FALLBACK_TRENDS[:limit] if fallback else None
                
                data = await response.json()
                
                if 'error' in data:
                    logger.error(f"[Trends] ❌ API 錯誤: {data['error']}")
                    return FALLBACK_TRENDS[:limit] if fallback else None
                
                trends = []
                if 'trending_searches' in data:
                    for item in data['trending_searches'][:limit]:
                        trend = {
                            'topic': item.get('query', 'N/A'),
                            'search_volume': item.get('search_volume', 0),
                            'increase_percentage': item.get('increase_percentage', 0),
                            'category': item.get('categories', [{}])[0].get('name', '其他') if item.get('categories') else '其他'
                        }
                        trends.append(trend)
                
                if trends:
                    _save_to_cache(trends)
                    logger.info(f"[Trends] ✅ 成功獲取 {len(trends)} 項趨勢")
                    return trends
                
                return FALLBACK_TRENDS[:limit] if fallback else None
    
    except Exception as e:
        logger.error(f"[Trends] ❌ 錯誤: {type(e).__name__}: {str(e)[:60]}")
        return FALLBACK_TRENDS[:limit] if fallback else None


def _save_to_cache(trends):
    """保存趨勢到緩存"""
    try:
        cache_data = {"timestamp": datetime.now().isoformat(), "trends": trends}
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"[Trends] 緩存保存失敗: {e}")


def format_trends_embed(trends: List[Dict]) -> discord.Embed:
    """轉換為 Discord Embed"""
    if not trends:
        return discord.Embed(title="❌ 無數據", color=discord.Color.red())
    
    embed = discord.Embed(
        title="🔥 台灣 Google Trends 熱搜",
        description=f"更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        color=discord.Color.gold()
    )
    
    for idx, trend in enumerate(trends[:10], 1):
        topic = trend.get('topic', 'N/A')
        volume = trend.get('search_volume', 0)
        increase = trend.get('increase_percentage', 0)
        category = trend.get('category', '其他')
        
        # 進度條
        filled = int(20 * min(volume / 20000, 1))
        bar = '█' * filled + '░' * (20 - filled)
        
        # 增長指示
        if increase >= 1000:
            icon = "🚀"
        elif increase >= 500:
            icon = "📈"
        elif increase >= 100:
            icon = "↗️"
        else:
            icon = "➡️"
        
        value = f"{icon} [{bar}]\n搜索量: {volume:,} | 增長: +{increase}% | {category}"
        embed.add_field(name=f"#{idx}. {topic}", value=value, inline=False)
    
    embed.set_footer(text="💡 資料可能來自緩存或備用數據")
    return embed


def format_trends_text(trends: List[Dict]) -> str:
    """格式化為文本"""
    if not trends:
        return "❌ 暫無數據"
    
    lines = [f"🔥 台灣 Google Trends ({len(trends)} 項)\n"]
    for idx, t in enumerate(trends[:10], 1):
        lines.append(f"{idx}. {t['topic']} | 搜索: {t['search_volume']:,} | 增長: +{t['increase_percentage']}%")
    
    return "\n".join(lines)
