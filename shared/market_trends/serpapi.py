#!/usr/bin/env python3
"""
Stub module for market_trends_serpapi to prevent ModuleNotFoundError.
Replace with proper implementation later.
"""

from typing import Any

import discord


async def get_trending_topics(region: str = "TW", limit: int = 10) -> list[Any]:
    """Stub: return empty list."""
    return []


def format_trends_embed(trends: list[Any]) -> discord.Embed:
    """Stub: return a simple embed indicating no data."""
    embed = discord.Embed(
        title="📊 市場趨勢",
        description="目前無趨勢資料可顯示",
        colour=discord.Color.light_gray(),
    )
    return embed


def format_trends_text(trends: list[Any]) -> str:
    """Stub: return a simple message."""
    return "目前無趨勢資料"


async def get_cached_trending_topics(region: str = "TW", limit: int = 10) -> list[Any]:
    """Stub: return empty list."""
    return []


async def get_fallback_trending_topics(
    region: str = "TW", limit: int = 10
) -> list[Any]:
    """Stub: return empty list."""
    return []
