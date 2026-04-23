# -*- coding: utf-8 -*-
import asyncio
import logging
import re
import random
from typing import List, Dict

# --- 核心導入與防錯機制 ---
try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# 基礎變數定義
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
logger = logging.getLogger(__name__)

class TrendsCollector:
    """趨勢收集器 - 整合 Google Trends RSS"""
    
    def __init__(self):
        if not FEEDPARSER_AVAILABLE or not REQUESTS_AVAILABLE:
            logger.warning("⚠️  關鍵組件 (feedparser/requests) 未安裝，將依賴備援數據")
        logger.info("✅ [TrendsCollector] 初始化成功，準備截獲情報")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def get_combined_trends(self, limit: int = 10) -> List[Dict]:
        """主入口：獲取台灣實時趨勢"""
        # 1. 嘗試 Google RSS
        trends = await self._fetch_from_rss()
        
        # 2. 最終保險：測試數據
        if not trends:
            trends = self._get_test_trends()
            
        return trends[:limit]

    async def _fetch_from_rss(self) -> List[Dict]:
        """解析 Google Trends RSS"""
        if not (REQUESTS_AVAILABLE and FEEDPARSER_AVAILABLE):
            return []
            
        rss_url = "https://trends.google.com.tw/trends/trendingsearches/daily/rss?geo=TW"
        try:
            # 在 thread 中執行同步的 requests 請求，避免卡住 asyncio
            response = await asyncio.to_thread(
                lambda: requests.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=8)
            )
            
            if response.status_code != 200:
                logger.warning(f"📡 RSS 連線失敗: HTTP {response.status_code}")
                return []
            
            feed = feedparser.parse(response.content)
            results = []
            for entry in feed.entries:
                title = re.sub(r'<[^>]+>', '', entry.get("title", ""))
                title = re.sub(r'\s+', ' ', title).strip()
                if title:
                    results.append({"trend": title, "platform": "google_rss"})
            return results
        except Exception as e:
            logger.error(f"❌ RSS 解析異常: {e}")
            return []

    def _get_test_trends(self) -> List[Dict]:
        """硬編碼保險數據"""
        defaults = ["緯創", "友達", "群創", "技嘉", "廣達"]
        return [{"trend": t, "platform": "hardcoded_fallback"} for t in defaults]

# 便利函數
async def get_latest_trends(limit: int = 10) -> List[Dict]:
    async with TrendsCollector() as collector:
        return await collector.get_combined_trends(limit)
