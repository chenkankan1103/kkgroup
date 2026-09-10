"""
動畫推送 Embed 格式模組
專門負責生成動畫推送的 Embed 格式
"""

import logging
import discord
from typing import Optional, Dict

logger = logging.getLogger(__name__)

async def generate_anime_embed(episode: dict, push_mode: str = "unknown") -> Optional[discord.Embed]:
    """
    生成動畫推送 embed

    Args:
        episode: 動畫資訊字典
        push_mode: 推送模式 ("排程推送" or "輪詢 (備案模式)")

    Returns:
        discord.Embed: 生成的 embed 物件，失敗則返回 None
    """
    try:
        title = episode.get("title", "未知標題")
        cover = episode.get("cover", "")
        description = episode.get("description", "")

        embed = discord.Embed(
            title=title, description=description, color=discord.Color.blue()
        )

        if cover:
            embed.set_image(url=cover)

        # 添加推送方式指示器
        embed.add_field(name="📡 推送方式", value=push_mode, inline=True)

        return embed
    except Exception as e:
        logger.error(f"生成 embed 失敗: {e}")
        return None