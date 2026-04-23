# -*- coding: utf-8 -*-
"""
趨勢收集模組 - 從 Google Trends 獲取實時台灣趨勢

使用 pytrends 庫爬取 Google Trends 數據
"""

import asyncio
import logging
from typing import List, Dict

# Google Trends 爬蟲
try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False
    TrendReq = None

logger = logging.getLogger(__name__)


class TrendsCollector:
    """趨勢收集器 - 從 Google Trends 獲取台灣趨勢"""
    
    def __init__(self):
        if not PYTRENDS_AVAILABLE:
            logger.warning("⚠️  pytrends 未安裝，將使用測試數據")
        
        # Google Trends 設定
        self.hl = 'zh-TW'  # 台灣繁體中文
        self.tz = 480      # 台灣時區 (GMT+8)
        
        logger.info("✅ [TrendsCollector.__init__] 已初始化 Google Trends 收集器")
    
    async def __aenter__(self):
        """上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        pass
    
    async def get_twitter_trends(self, location_woeid: str = "23424971") -> List[Dict]:
        """
        從 Google Trends 獲取台灣實時搜尋趨勢
        
        Args:
            location_woeid: 位置代碼 (已棄用，改用 geo='TW')
        
        Returns:
            趨勢列表 [{"trend": "...", "count": 100, "platform": "google_trends"}, ...]
        """
        if not PYTRENDS_AVAILABLE:
            logger.warning("⚠️  pytrends 未安裝")
            return self._get_test_trends()
        
        try:
            logger.info("=" * 60)
            logger.info("🚀 [Google Trends] 開始拉取台灣實時趨勢")
            logger.info("=" * 60)
            
            # 創建 TrendReq 實例
            pytrends = TrendReq(hl=self.hl, tz=self.tz)
            
            # 獲取台灣的即時搜尋趨勢（Real-time search trends）
            # 這會爬取 Google Trends 首頁的「熱搜榜」
            trending_searches = await asyncio.to_thread(
                self._get_trending_searches, pytrends
            )
            
            if not trending_searches:
                logger.warning("⚠️  未能獲取趨勢")
                return self._get_test_trends()
            
            # 轉換格式
            trends = [
                {
                    "trend": trend,
                    "count": 100,  # Google Trends 不提供具體互動數，使用固定值
                    "platform": "google_trends"
                }
                for trend in trending_searches[:10]
            ]
            
            logger.info(f"✅ [成功] 從 Google Trends 獲取 {len(trends)} 項台灣趨勢:")
            for i, t in enumerate(trends, 1):
                logger.info(f"   {i}. {t['trend']}")
            
            return trends
        
        except Exception as e:
            logger.error(f"❌ [異常] Google Trends 獲取失敗: {type(e).__name__}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return self._get_test_trends()
    
    def _get_trending_searches(self, pytrends) -> List[str]:
        """
        同步方法：獲取台灣趨勢（在線程中執行）
        
        Args:
            pytrends: TrendReq 實例
        
        Returns:
            趨勢列表
        """
        try:
            # 方法 1：trending_searches (最新推薦)
            df = pytrends.trending_searches(pn='taiwan')
            if df is not None and len(df) > 0:
                trends = df[0].tolist()
                logger.info(f"📊 [取得方式] trending_searches (台灣)")
                return trends
        except Exception as e:
            logger.debug(f"⚠️  trending_searches 失敗，嘗試備選方法: {e}")
        
        try:
            # 方法 2：interest_over_time (備選，需要指定搜尋詞)
            # 先搜一般性詞彙，看看什麼是熱門
            pytrends.build_payload(kw_list=[''], geo='TW', timeframe='now 7-d')
            df = pytrends.interest_over_time()
            
            if df is not None and len(df.columns) > 0:
                trends = df.columns.tolist()[:10]
                logger.info(f"📊 [取得方式] interest_over_time (台灣)")
                return trends
        except Exception as e:
            logger.debug(f"⚠️  interest_over_time 失敗: {e}")
        
        # 備選方案：返回測試數據
        logger.warning("⚠️  所有 Google Trends 方法都失敗了")
        return []
    
    async def get_reddit_trends(self, subreddit: str = "all") -> List[Dict]:
        """
        Reddit 已禁用（聚焦 Google Trends）
        
        Returns:
            空列表
        """
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
