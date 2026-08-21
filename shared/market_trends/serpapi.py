#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stub module for market_trends_serpapi to prevent ModuleNotFoundError.
Replace with proper implementation later.
"""

import discord
from discord.ext import commands
from typing import List, Any

async def get_trending_topics(region: str = 'TW', limit: int = 10) -> List[Any]:
    """Stub: return empty list."""
    return []

def format_trends_embed(trends: List[Any]) -> discord.Embed:
    """Stub: return a simple embed indicating no data."""
    embed = discord.Embed(
        title="📊 市場趨勢",
        description="目前無趨勢資料可顯示",
        colour=discord.Color.light_gray()
    )
    return embed

def format_trends_text(trends: List[Any]) -> str:
    """Stub: return a simple message."""
    return "目前無趨勢資料"

async def get_cached_trending_topics(region: str = 'TW', limit: int = 10) -> List[Any]:
    """Stub: return empty list."""
    return []

async def get_fallback_trending_topics(region: str = 'TW', limit: int = 10) -> List[Any]:
    """Stub: return empty list."""
    return []