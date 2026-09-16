#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Trends API via trendspyg (free, unofficial, uses RSS).
Provides the same interface as the previous SerpApi stub.
"""

import logging
import os
import asyncio
from typing import List, Any

log = logging.getLogger(__name__)

# Use trendspyg's RSS method for trending searches
try:
    from trendspyg import download_google_trends_rss
    TRENDSPYG_AVAILABLE = True
except ImportError:
    log.warning("trendspyg not installed, trending topics will not be available")
    TRENDSPYG_AVAILABLE = False

# Fallback region mapping for trendspyg (uses geo codes like 'TW', 'US', etc.)
# trendspyg uses standard Google Trends geo codes directly
def _region_to_geo(region: str) -> str:
    """Convert region code to trendspyg geo parameter."""
    # trendspyg uses standard Google Trends geo codes
    # 'TW' for Taiwan, 'US' for United States, etc.
    return region.upper()

def _fetch_trending_topics(region: str = 'TW', limit: int = 10) -> List[dict]:
    """Blocking call to fetch trending searches via trendspyg RSS."""
    if not TRENDSPYG_AVAILABLE:
        log.error("trendspyg not available, cannot fetch trending topics")
        return []
    
    try:
        geo = _region_to_geo(region)
        log.debug(f"Fetching trending searches via trendspyg RSS for region={region} -> geo={geo}")
        
        # trendspyg's RSS method - returns list of dicts with title, traffic, url, etc.
        trends = download_google_trends_rss(geo=geo)
        
        if not trends:
            log.warning(f"No trending topics returned for region {region}")
            return []
        
        # Take top `limit` rows
        trends = trends[:limit]
        
        # Build list of dicts similar to the old SerpApi format
        results = []
        for i, item in enumerate(trends):
            keyword = item.get('title', '') or item.get('trend', '')
            if not keyword:
                continue
            # Assign a decreasing score
            score = limit - i
            # Use the provided URL or construct one
            url = item.get('url', f"https://trends.google.com/trends/trendingsearches/daily?geo={region}&date=today 1-m&q={keyword}")
            results.append({
                # trendspyg 原生鍵（format_trends_embed / format_trends_text 使用）
                "title": keyword,
                "value": score,
                "url": url,
                # 舊 SerpApi 相容鍵（fortress_system.trends_to_enemies /
                # _extract_trend_titles 讀 topic / rank / search_volume）
                "topic": keyword,
                "rank": i + 1,
                "search_volume": score,
            })
        return results
    except Exception as e:
        log.error(f"Error fetching trending topics via trendspyg for region {region}: {e}")
        return []

async def get_trending_topics(region: str = 'TW', limit: int = 10) -> List[Any]:
    """Async wrapper for fetching trending topics."""
    loop = asyncio.get_event_loop()
    # Run the blocking call in a thread pool.
    result = await loop.run_in_executor(None, _fetch_trending_topics, region, limit)
    return result

def format_trends_embed(trends: List[Any]) -> Any:
    """Format trends into a Discord embed (same signature as before)."""
    import discord
    if not trends:
        embed = discord.Embed(
            title="📊 市場趨勢",
            description="目前無趨勢資料可顯示",
            colour=discord.Color.light_gray()
        )
        return embed
    # Build description.
    lines = []
    for i, item in enumerate(trends, start=1):
        title = item.get('title', 'Unknown')
        value = item.get('value', 0)
        lines.append(f"{i}. **{title}** (熱度: {value})")
    description = "\n".join(lines)
    embed = discord.Embed(
        title="📊 市場趨勢",
        description=description,
        colour=discord.Color.blue()
    )
    return embed

def format_trends_text(trends: List[Any]) -> str:
    """Format trends into plain text."""
    if not trends:
        return "目前無趨勢資料"
    lines = []
    for i, item in enumerate(trends, start=1):
        title = item.get('title', 'Unknown')
        value = item.get('value', 0)
        lines.append(f"{i}. {title} ({value})")
    return "\n".join(lines)

async def get_cached_trending_topics(region: str = 'TW', limit: int = 10) -> List[Any]:
    """For now, no caching; same as get_trending_topics."""
    return await get_trending_topics(region, limit)

async def get_fallback_trending_topics(region: str = 'TW', limit: int = 10) -> List[Any]:
    """Fallback: try a different region like 'worldwide' or 'US'."""
    # Try worldwide as fallback
    if region.upper() != 'WORLD' and region.upper() != 'GLOBAL':
        return await get_trending_topics('worldwide', limit)
    return []
