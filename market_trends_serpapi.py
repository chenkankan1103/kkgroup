#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SerpApi Google Trends 集成模塊 (使用官方 serpapi SDK)

根據文檔：https://serpapi.com/google-trends-trending-now
"""

import os
import asyncio
import logging
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import discord
from serpapi import Client

# 設定 logging
logger = logging.getLogger(__name__)

# 加載 .env
load_dotenv()

SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')
CACHE_EXPIRY_MINUTES = 30  # 緩存 30 分鐘後過期

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
        "params": {"geo": "TW"},
        "name": "google_trends_trending_now with geo=TW ✅"
    },
]


def _fetch_trends_sync(limit: int, timeout: int) -> Optional[List[Dict]]:
    """同步版本的趨勢獲取（用於在執行器中運行）"""
    if not SERPAPI_API_KEY:
        return None
    
    try:
        client = Client(api_key=SERPAPI_API_KEY)
        
        for engine_config in SERPAPI_ENGINES:
            try:
                engine = engine_config["engine"]
                engine_params = engine_config["params"].copy()
                
                search_params = {
                    "engine": engine,
                    **engine_params
                }
                
                logger.debug(f"[Trends] 嘗試 {engine_config['name']}...")
                logger.debug(f"[Trends] 參數: {search_params}")
                
                results = client.search(search_params)
                
                # 檢查 API 錯誤
                if 'error' not in results:
                    trends = _parse_trends_response(results, limit)
                    if trends:
                        logger.info(f"[Trends] ✅ 成功（使用 {engine}）獲取 {len(trends)} 項")
                        return trends
                else:
                    logger.debug(f"[Trends] API 錯誤: {results.get('error')}")
            
            except Exception as e:
                logger.debug(f"[Trends] ❌ {engine_config['name']}: {str(e)[:60]}")
    
    except Exception as e:
        logger.error(f"[Trends] Client 初始化失敗: {str(e)[:80]}")
    
    return None


def get_cached_trending_topics(limit: int = 10, allow_stale: bool = True) -> Optional[List[Dict]]:
    """讀取本地快取趨勢；allow_stale=True 時即使過期也可作為降級資料。"""
    if not CACHE_FILE.exists():
        return None

    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cached = json.load(f)

        trends = cached.get('trends', [])
        if not trends:
            return None

        if allow_stale:
            return trends[:limit]

        cache_time_raw = cached.get('timestamp')
        if not cache_time_raw:
            return None

        cache_time = datetime.fromisoformat(cache_time_raw)
        age_minutes = (datetime.now() - cache_time).total_seconds() / 60
        if age_minutes < CACHE_EXPIRY_MINUTES:
            return trends[:limit]
    except Exception as e:
        logger.debug(f"[Trends] 緩存讀取失敗: {e}")

    return None


def get_fallback_trending_topics(limit: int = 10) -> List[Dict]:
    """取得內建備援趨勢。"""
    return FALLBACK_TRENDS[:limit]


async def get_trending_topics(
    region: str = "TW",
    limit: int = 10,
    timeout: int = 10,
    use_cache: bool = True,
    fallback: bool = True
) -> Optional[List[Dict]]:
    """獲取 Google Trends 熱搜（使用官方 SDK）"""
    
    # 無 API 密鑰時直接使用備用數據
    if not SERPAPI_API_KEY:
        logger.warning("[Trends] ⚠️ 無 API 密鑰，使用備用數據")
        return FALLBACK_TRENDS[:limit]
    
    # 嘗試讀取本地緩存（檢查是否過期）
    if use_cache and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
                # 檢查緩存是否過期
                if 'timestamp' in cached:
                    cache_time = datetime.fromisoformat(cached['timestamp'])
                    age_minutes = (datetime.now() - cache_time).total_seconds() / 60
                    if age_minutes < CACHE_EXPIRY_MINUTES:
                        logger.info(f"[Trends] 📦 使用本地緩存 ({age_minutes:.1f} 分鐘前)")
                        return cached.get('trends', [])[:limit]
                    else:
                        logger.info(f"[Trends] ⏰ 緩存已過期 ({age_minutes:.1f} 分鐘)，重新獲取...")
        except Exception as e:
            logger.debug(f"[Trends] 緩存讀取失敗: {e}")
    
    # 在執行器中運行同步 SDK 調用（避免阻塞事件循環）
    loop = asyncio.get_event_loop()
    trends = await loop.run_in_executor(None, _fetch_trends_sync, limit, timeout)
    
    if trends:
        _save_to_cache(trends)
        return trends
    
    # 所有嘗試都失敗，使用備用數據
    logger.warning("[Trends] API 調用失敗，使用備用數據")
    return get_fallback_trending_topics(limit) if fallback else None


def _parse_trends_response(data: dict, limit: int) -> Optional[List[Dict]]:
    """從 SerpApi 回應中解析趨勢數據"""
    trends = []
    
    # 官方文檔中的正確字段名稱
    if 'trending_searches' in data and isinstance(data['trending_searches'], list):
        for item in data['trending_searches'][:limit]:
            if isinstance(item, dict):
                # 根據官方文檔，字段應該是：query, search_volume, increase_percentage, categories
                trend = {
                    'topic': item.get('query') or item.get('title') or item.get('name') or 'N/A',
                    'search_volume': item.get('search_volume', 0),
                    'increase_percentage': item.get('increase_percentage', 0),
                    'category': (item.get('categories', [{}])[0].get('name') if item.get('categories') else '其他')
                }
                trends.append(trend)
    
    return trends if trends else None


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


def format_lottery_embed(
    trends: List[Dict],
    jackpot_amount: float = 0.0,
    total_bets: int = 0,
    current_round_id: str = "",
    timezone_obj = None,
    is_kkcoin_pool: bool = True
) -> discord.Embed:
    """
    統一合併 Embed - 趨勢詳情 + 投注系統
    
    參數：
    - trends: 趨勢列表（來自 get_latest_trends）
      格式: [{"trend": "...", "search_volume": ..., "increase_percentage": ..., ...}, ...]
    - jackpot_amount: 中央彩池金額 (KK幣 或 USD，取決於 is_kkcoin_pool)
    - total_bets: 投注人數（已廢棄，僅保留向後相容）
    - current_round_id: 輪次 ID
    - timezone_obj: 時區對象（可選）
    - is_kkcoin_pool: 是否為 KK幣池（True）還是 USD 池（False）
    
    返回：
        統一的 Discord Embed，包含趨勢詳情和投注資訊
    """
    if not trends:
        return discord.Embed(
            title="❌ 暫無數據",
            color=discord.Color.red()
        )
    
    embed = discord.Embed(
        title="🔥 台灣趨勢樂透",
        description="📊 投注趨勢預測 • 每 3 小時開獎一次",
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone_obj) if timezone_obj else datetime.now()
    )
    
    # ==================== 第一部分：趨勢詳情（前 10 個） ====================
    trends_field_value = ""
    for idx, trend in enumerate(trends[:10], 1):
        # 處理數據格式 - trend 可能來自 get_latest_trends，使用 'trend' 字段
        topic = trend.get('trend') or trend.get('topic', 'N/A')
        volume = trend.get('search_volume', 0)
        increase = trend.get('increase_percentage', 0)
        
        # 增長指示 icon
        if increase >= 1000:
            icon = "🚀"
        elif increase >= 500:
            icon = "📈"
        elif increase >= 100:
            icon = "↗️"
        else:
            icon = "➡️"
        
        # 進度條
        filled = int(15 * min(volume / 20000, 1))
        bar = '█' * filled + '░' * (15 - filled)
        
        trends_field_value += f"{idx}. `{topic}` {icon}\n"
        trends_field_value += f"   [{bar}] {volume:,} | +{increase}%\n"
    
    embed.add_field(
        name="🔥 熱門趨勢排行",
        value=trends_field_value or "無數據",
        inline=False
    )
    
    # ==================== 第二部分：投注規則 ====================
    embed.add_field(
        name="💰 投注說明",
        value=(
            "• 每次投注: **$10.00 USD**\n"
            "• 選擇 3 個趨勢（只要在前 10 名即中獎）\n"
            "• 開獎間隔: **3 小時**\n"
            "• 開獎時間: 08:00 / 11:00 / 14:00 / 17:00 / 20:00 / 23:00 台灣時間"
        ),
        inline=False
    )
    
    # ==================== 第三部分：獲獎規則 ====================
    embed.add_field(
        name="🏆 獲獎規則 (前 10 名判定)",
        value=(
            "• 🥇 3 個都在前 10 名: $50 USD + 10% 獎池的 KK 幣\n"
            "• 🥈 2 個在前 10 名: $30 USD\n"
            "• 🥉 1 個在前 10 名: $10 USD\n"
            "• ❌ 0 個在前 10 名: 投注入獎池"
        ),
        inline=False
    )
    
    # ==================== 第四部分：獎池資訊 ====================
    jackpot_value = f"{jackpot_amount:.0f}"
    
    if is_kkcoin_pool:
        pool_display = f"🎁 **{jackpot_value} KK幣**"
    else:
        pool_display = f"💵 **${jackpot_value}**"
    
    embed.add_field(
        name="🎁 中央彩池",
        value=pool_display,
        inline=False
    )
    
    # ==================== 頁腳 ====================
    footer_text = "💡 數據來自 SerpApi Google Trends"
    if current_round_id:
        footer_text = f"開獎輪次: {current_round_id} • " + footer_text
    
    embed.set_footer(text=footer_text)
    
    return embed
