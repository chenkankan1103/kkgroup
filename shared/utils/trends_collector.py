# -*- coding: utf-8 -*-
"""
趨勢收集模組 - 從 Google Trends 官方 RSS feed 獲取台灣實時趨勢

使用 Google Trends 官方 RSS feed - 最可靠的方法，無需認證，無爬蟲限制
RSS URL: https://trends.google.com.tw/trends/trendingsearches/daily/rss?geo=TW
"""

import asyncio
import logging
import re
from typing import List, Dict

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

logger = logging.getLogger(__name__)


class TrendsCollector:
    """趨勢收集器 - 從 Google Trends RSS feed 獲取台灣實時趨勢"""
    
    def __init__(self):
        if not FEEDPARSER_AVAILABLE:
            logger.warning("⚠️  feedparser 未安裝，將使用測試數據")
        logger.info("✅ [TrendsCollector.__init__] 已初始化 Google Trends RSS 收集器")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def get_twitter_trends(self, location_woeid: str = "23424971") -> List[Dict]:
        """
        從 Google Trends RSS feed 獲取台灣實時搜尋趨勢
        
        Returns:
            趨勢列表 [{"trend": "...", "count": 100, "platform": "google_trends"}, ...]
        """
        if not FEEDPARSER_AVAILABLE:
            logger.warning("⚠️  feedparser 未安裝")
            return self._get_test_trends()
        
        try:
            logger.info("=" * 60)
            logger.info("🚀 [Google Trends RSS] 開始拉取台灣實時趨勢")
            logger.info("=" * 60)
            
            # 使用 Google Trends RSS feed
            trends = await self._fetch_from_rss()
            
            if trends:
                logger.info(f"✅ [成功] 從 Google Trends RSS 獲取 {len(trends)} 項台灣趨勢:")
                for i, t in enumerate(trends[:10], 1):
                    logger.info(f"   {i}. {t['trend']}")
                return trends[:10]
            
            logger.warning("⚠️  RSS feed 方法失敗")
            return self._get_test_trends()
            
        except Exception as e:
            logger.error(f"❌ [異常] Google Trends 獲取失敗: {type(e).__name__}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return self._get_test_trends()
    
    async def _fetch_from_rss(self) -> List[Dict]:
        """使用 Google Trends 官方 RSS feed 獲取台灣趨勢"""
        try:
            # Google Trends 台灣區每日搜尋趨勢 RSS
            rss_url = "https://trends.google.com.tw/trends/trendingsearches/daily/rss?geo=TW"
            
            logger.info(f"📡 正在請求 RSS: {rss_url}")
            
            # 在線程中解析 RSS（避免阻塞）
            feed = await asyncio.to_thread(feedparser.parse, rss_url)
            
            trends = []
            if feed.entries:
                for entry in feed.entries[:20]:
                    # 清理標題（移除多餘空格、特殊字符）
                    title = entry.get("title", "")
                    if title:
                        # 移除 HTML 標籤和多餘空格
                        clean_title = re.sub(r'<[^>]+>', '', title)  # 移除 HTML
                        clean_title = re.sub(r'\s+', ' ', clean_title).strip()  # 清理空格
                        
                        if clean_title:
                            trends.append({
                                "trend": clean_title,
                                "count": 100,
                                "platform": "google_trends"
                            })
                
                logger.info(f"📊 [取得方式] RSS feed - 獲取 {len(trends)} 項")
            else:
                logger.warning("⚠️  RSS feed 無條目")
                
            return trends
                
        except Exception as e:
            logger.error(f"❌ RSS 解析失敗: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    async def get_reddit_trends(self, subreddit: str = "all") -> List[Dict]:
        """Reddit 已禁用（聚焦 Google Trends）"""
        return []
    
    def _get_test_trends(self) -> List[Dict]:
        """
        返回測試數據 - 常見台灣搜尋趨勢
        當 Google Trends API 失敗時使用
        """
        test_trends = [
            {"trend": "緯創", "count": 100, "platform": "google_trends_test"},
            {"trend": "友達", "count": 100, "platform": "google_trends_test"},
            {"trend": "鴻海", "count": 100, "platform": "google_trends_test"},
            {"trend": "TSMC", "count": 100, "platform": "google_trends_test"},
            {"trend": "聯發科", "count": 100, "platform": "google_trends_test"},
            {"trend": "台積電", "count": 100, "platform": "google_trends_test"},
            {"trend": "中華電信", "count": 100, "platform": "google_trends_test"},
            {"trend": "台灣股市", "count": 100, "platform": "google_trends_test"},
            {"trend": "半導體", "count": 100, "platform": "google_trends_test"},
            {"trend": "電子產業", "count": 100, "platform": "google_trends_test"},
        ]
        logger.info(f"📋 使用測試數據：{len(test_trends)} 項台灣流行搜尋")
        return test_trends
    
    async def get_combined_trends(self, limit: int = 10) -> List[Dict]:
        """
        獲取台灣 Google Trends 趨勢
        
        Args:
            limit: 返回的最大趨勢數
        
        Returns:
            台灣趨勢列表，按熱度排序
        """
        try:
            # 獲取 Google Trends
            trends = await self.get_twitter_trends()
            
            # 只保留前 limit 項
            return trends[:limit]
        
        except Exception as e:
            logger.error(f"❌ [get_combined_trends] 失敗: {e}")
            return self._get_test_trends()[:limit]


# 全局便利函數
async def get_latest_trends(limit: int = 10) -> List[Dict]:
    """
    取得最新趨勢的便利函數
    
    Args:
        limit: 返回的最大趨勢數
    
    Returns:
        台灣趨勢列表
    """
    async with TrendsCollector() as collector:
        return await collector.get_combined_trends(limit)
