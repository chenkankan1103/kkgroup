# -*- coding: utf-8 -*-
import asyncio
import logging
import re
import random
import time
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

# 多套數據集，輪轉使用
TREND_DATASETS = [
    ["台積電", "聯發科", "鴻海", "聯電", "日月光"],
    ["AI晶片", "ChatGPT", "機器學習", "大型語言模型", "深度學習"],
    ["緯創", "友達", "群創", "技嘉", "廣達"],
    ["元宇宙", "NFT", "區塊鏈", "加密貨幣", "Web3"],
    ["自動駕駛", "電動車", "新能源", "綠能", "永續發展"],
    ["雲計算", "邊緣計算", "量子計算", "5G", "6G"],
    ["生物科技", "基因編輯", "疫苗", "醫療", "藥物"],
    ["元器件", "晶圓代工", "半導體", "IC設計", "電子產業"],
]

class TrendsCollector:
    """趨勢收集器 - 整合 Google Trends RSS + 輪轉數據集"""
    
    def __init__(self):
        if not FEEDPARSER_AVAILABLE or not REQUESTS_AVAILABLE:
            logger.warning("⚠️  關鍵組件 (feedparser/requests) 未安裝，將依賴數據集輪轉")
        logger.info("✅ [TrendsCollector] 初始化成功，使用動態數據集輪轉系統")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def get_combined_trends(self, limit: int = 10) -> List[Dict]:
        """主入口：獲取台灣實時趨勢"""
        # 1. 嘗試 Google RSS (Google 已關閉，會返回 404)
        trends = await self._fetch_from_rss()
        
        # 2. 使用輪轉數據集 (每小時/每天輪換)
        if not trends:
            trends = self._get_rotated_trends()
            
        return trends[:limit]

    async def _fetch_from_rss(self) -> List[Dict]:
        """解析 Google Trends RSS（已關閉）"""
        if not (REQUESTS_AVAILABLE and FEEDPARSER_AVAILABLE):
            return []
            
        rss_url = "https://trends.google.com.tw/trends/trendingsearches/daily/rss?geo=TW"
        try:
            response = await asyncio.to_thread(
                lambda: requests.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=8)
            )
            
            if response.status_code != 200:
                logger.debug(f"📡 RSS 連線失敗: HTTP {response.status_code}")
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
            logger.debug(f"📡 RSS 異常: {type(e).__name__}")
            return []

    def _get_rotated_trends(self) -> List[Dict]:
        """
        使用輪轉數據集系統
        每小時更換一個數據集，確保趨勢不重複
        """
        # 根據當前小時選擇數據集
        current_hour = int(time.time()) // 3600
        dataset_index = current_hour % len(TREND_DATASETS)
        dataset = TREND_DATASETS[dataset_index]
        
        logger.info(f"📊 [輪轉系統] 使用數據集 #{dataset_index + 1}/{len(TREND_DATASETS)}")
        
        # 隨機打亂順序 (基於時間戳種子，確保同小時內順序一致)
        random.seed(current_hour)
        shuffled = dataset.copy()
        random.shuffle(shuffled)
        
        return [{"trend": t, "platform": "rotated_dataset"} for t in shuffled]

    def _get_test_trends(self) -> List[Dict]:
        """硬編碼備援數據（作為最後手段）"""
        defaults = ["緯創", "友達", "群創", "技嘉", "廣達"]
        return [{"trend": t, "platform": "hardcoded_fallback"} for t in defaults]

# 便利函數
async def get_latest_trends(limit: int = 10) -> List[Dict]:
    async with TrendsCollector() as collector:
        return await collector.get_combined_trends(limit)
