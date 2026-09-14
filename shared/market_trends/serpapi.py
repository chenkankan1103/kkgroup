#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Trends API via pytrends (free, unofficial).
Provides the same interface as the previous SerpApi stub.
"""

import logging
import os
import asyncio
from typing import List, Any

import pandas as pd
from pytrends.request import TrendReq

log = logging.getLogger(__name__)

# Global pytrends session (reuse to avoid too many requests)
_pytrends = TrendReq(hl='en-US', tz=360)  # Taiwan time? tz=0 for UTC, but we can adjust.

def _region_to_pn(region: str) -> str:
    """Convert region code to pytrends pn parameter."""
    # Mapping of common region codes to pytrends country names.
    # https://github.com/GeneralMills/pytrends/blob/master/pytrends/trend_req.py#L30
    # The pn is the "location" as per Google Trends.
    # We'll keep simple: if region is two-letter uppercase, try to map.
    mapping = {
        'TW': 'taiwan',
        'US': 'united_states',
        'JP': 'japan',
        'KR': 'south_korea',
        'CN': 'china',
        'HK': 'hong_kong',
        'SG': 'singapore',
        'MY': 'malaysia',
        'TH': 'thailand',
        'VN': 'vietnam',
        'PH': 'philippines',
        'ID': 'indonesia',
        'AU': 'australia',
        'CA': 'canada',
        'GB': 'united_kingdom',
        'DE': 'germany',
        'FR': 'france',
        'IT': 'italy',
        'ES': 'spain',
    }
    # If region in mapping, return mapped; else return region lowercased (may still work)
    return mapping.get(region.upper(), region.lower())

def _fetch_trending_topics(region: str = 'TW', limit: int = 10) -> List[dict]:
    """Blocking call to fetch trending searches via pytrends."""
    try:
        pn = _region_to_pn(region)
        log.debug(f"Fetching trending searches for region={region} -> pn={pn}")
        # pytrends expects region like 'TW' for Taiwan.
        # For trending searches, we use trending_searches.
        df = _pytrends.trending_searches(pn=pn)
        # df has columns: [0] (the query), maybe 'title'? Actually returns DataFrame with one column named 0.
        # Rename for clarity.
        if df.empty:
            return []
        # Take top `limit` rows.
        df = df.head(limit)
        # Build list of dicts similar to the old SerpApi format: each item has 'title' (query) and maybe 'value' and 'url'.
        # Since pytrends doesn't provide numeric value, we can set a placeholder or use index.
        # We'll set value as (limit - idx) to give descending scores.
        results = []
        for i, row in df.iterrows():
            keyword = str(row.iloc[0]) if len(row) > 0 else ""
            if not keyword:
                continue
            # Assign a decreasing score.
            score = limit - i
            results.append({
                "title": keyword,
                "value": score,
                "url": f"https://trends.google.com/trends/trendingsearches/daily?geo={region}&date=today 1-m&q={keyword}"
            })
        return results
    except Exception as e:
        log.error(f"Error fetching trending topics via pytrends for region {region}: {e}")
        # Optionally, try fallback to worldwide or empty.
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
    """Fallback: also pytrends but maybe with different region or parameters."""
    # We'll just call the same function; could also try a different region like 'GLOBAL' or 'worldwide'.
    # For simplicity, we reuse the same.
    return await get_trending_topics(region, limit)
