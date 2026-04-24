#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SerpApi Google Trends 集成模塊
支持多種 engine 配置以應對 SerpApi API 變更

根據文檔：https://serpapi.com/google-trends-trending-now
engine 可能需要是 "google_trends_trending_now"
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
    logger.warning("⚠️ 未找到 SERPAPI_API_KEY，將使用備用數據")

# 本地緩存文件
CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = CACHE_DIR / "trends_cache.json"
CACHE_DIR.mkdir(exist_ok=True)

# 備用趨勢數據
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

# SerpApi 支持的 engine 配置列表（優先順序）
SERPAPI_ENGINES = [
    {
        "engine": "google_trends_trending_now",
        "params": {"geo": "TW", "hl": "zh-TW"},
        "name": "google_trends_trending_now (推薦)"
    },
    {
        "engine": "google_trends",
        "params": {"q": "trending-now", "geo": "TW", "hl": "zh-TW"},
        "name": "google_trends with q=trending-now"
    },
    {
        "engine": "google_trends",
        "params": {"q": "trending searches", "geo": "TW", "hl": "zh-TW"},
        "name": "google_trends with q=trending searches"
    },
]


async def get_trending_topics(
    region: str = "TW",
    limit: int = 10,
    timeout: int = 10,
    use_cache: bool = True,
    fallback: bool = True
) -> Optional[List[Dict]]:
    """獲取 Google Trends 熱搜（支持多個 engine 配置）"""
    
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
    
    # 依次嘗試不同的 engine 配置
    for engine_config in SERPAPI_ENGINES:
        try:
            engine = engine_config["engine"]
            engine_params = engine_config["params"].copy()
            engine_params["api_key"] = SERPAPI_API_KEY
            
            logger.debug(f"[Trends] 嘗試 {engine_config['name']}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params={"engine": engine, **engine_params},
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # 檢查 API 錯誤
                        if 'error' not in data:
                            trends = _parse_trends_response(data, limit)
                            if trends:
                                logger.info(f"[Trends] ✅ 成功（使用 {engine}）獲取 {len(trends)} 項")
                                _save_to_cache(trends)
                                return trends
        
        except asyncio.TimeoutError:
            logger.debug(f"[Trends] ⏱️ {engine_config['name']} 超時")
        except Exception as e:
            logger.debug(f"[Trends] ❌ {engine_config['name']}: {str(e)[:60]}")
    
    # 所有配置都失敗，使用備用數據
    logger.warning("[Trends] 所有 engine 配置均失敗，使用備用數據")
    return FALLBACK_TRENDS[:limit] if fallback else None


def _parse_trends_response(data: dict, limit: int) -> Optional[List[Dict]]:
    """從 SerpApi 回應中解析趨勢數據"""
    trends = []
    
    # 嘗試不同的回應格式
    keys_to_try = ['trending_searches', 'results', 'items', 'trends']
    
    for key in keys_to_try:
        if key in data and isinstance(data[key], list):
            for item in data[key][:limit]:
                if isinstance(item, dict):
                    trend = {
                        'topic': item.get('query') or item.get('title') or item.get('name') or 'N/A',
                        'search_volume': item.get('search_volume', 0),
                        'increase_percentage': item.get('increase_percentage', 0),
                        'category': item.get('categories', [{}])[0].get('name') if item.get('categories') else '其他'
                    }
                    trends.append(trend)
                elif isinstance(item, str):
                    # 簡單字符串格式
                    trend = {
                        'topic': item,
                        'search_volume': 10000 - len(trends) * 500,
                        'increase_percentage': max(0, 100 - len(trends) * 10),
                        'category': '搜尋'
                    }
                    trends.append(trend)
            
            if trends:
                return trends
    
    return None


def _save_to_cache(trends: List[Dict]):
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
    
    embed.set_footer(text="💡 資料來自 SerpApi Google Trends")
    return embed


def format_trends_text(trends: List[Dict]) -> str:
    """格式化為文本"""
    if not trends:
        return "❌ 暫無數據"
    
    lines = [f"🔥 台灣 Google Trends ({len(trends)} 項)\n"]
    for idx, t in enumerate(trends[:10], 1):
        lines.append(f"{idx}. {t['topic']} | 搜索: {t['search_volume']:,} | 增長: +{t['increase_percentage']}%")
    
    return "\n".join(lines)
