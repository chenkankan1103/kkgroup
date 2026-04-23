# -*- coding: utf-8 -*-
"""
趨勢收集器 - Twitter/X 趨勢（Twikit）+ 備用系統
================================================

主要功能：從 Twitter/X 獲取實時趨勢（使用 Twikit 爬蟲）

使用狀態：
✅ Twikit 實現 - 活躍使用中，需要 Twitter 帳戶認證
🔄 備用方案 - 時間輪轉數據集（當 Twikit 失敗時）

環境變數配置（必需）：
  TWITTER_USERNAME = "your_twitter_username"
  TWITTER_EMAIL = "your_email@example.com"
  TWITTER_PASSWORD = "your_twitter_password"

注意事項：
- Twikit 使用 Twitter 官方 API（不需要 API Key）
- 需要真實 Twitter 帳戶和正確的認證信息
- Cookie 會自動保存以避免頻繁重新登入
- Twitter 可能因頻繁登入而限制帳戶
"""

import asyncio
import logging
import random
import time
import os
from typing import List, Dict, Optional

# 確保 .env 被加載（必須在所有 os.getenv() 之前）
from dotenv import load_dotenv
load_dotenv()

# 嘗試導入 Twikit（Twitter 趨勢爬蟲）
try:
    from twikit import Client
    TWIKIT_AVAILABLE = True
except ImportError:
    TWIKIT_AVAILABLE = False

logger = logging.getLogger(__name__)

# ========================
# Twikit 配置（Twitter 趨勢）
# ========================

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "")
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL", "")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "")
TWITTER_COOKIES_FILE = "/tmp/twitter_cookies.json"


# ========================
# 數據集備用方案（輪轉）
# ========================

FALLBACK_TREND_DATASETS = [
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
    """
    趨勢收集器 - 優先使用 Twitter/X 趨勢（Twikit）
    
    優先級：
    1. 🎯 Twitter/X 實時趨勢（Twikit 爬蟲，主方案）
    2. 🔄 時間輪轉數據集（備用方案）
    """
    
    def __init__(self):
        if not TWIKIT_AVAILABLE:
            logger.warning("⚠️ [Twikit] 未安裝，只能使用備用方案")
        elif TWITTER_USERNAME and TWITTER_EMAIL and TWITTER_PASSWORD:
            logger.info("✅ [Twikit] 帳戶已配置，使用 Twitter 實時趨勢")
        else:
            logger.warning("⚠️ [Twikit] 帳戶信息不完整，將使用備用方案")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def get_combined_trends(self, limit: int = 10) -> List[Dict]:
        """
        主入口：獲取實時趨勢
        
        優先級：
        1. Twitter/X 趨勢（Twikit）
        2. 時間輪轉備用數據集
        """
        # 1. 嘗試 Twikit 獲取 Twitter 趨勢
        if TWIKIT_AVAILABLE and TWITTER_USERNAME:
            trends = await self._fetch_from_twikit()
            if trends:
                logger.info(f"✅ [成功] 從 Twitter 獲取 {len(trends)} 項趨勢")
                return trends[:limit]
        
        # 2. 備用：時間輪轉數據集
        logger.debug("🔄 [備用方案] 使用時間輪轉數據集")
        trends = self._get_fallback_rotated_trends()
        
        return trends[:limit]
    
    async def _fetch_from_twikit(self, retry_count: int = 0, max_retries: int = 3) -> List[Dict]:
        """
        使用 Twikit 從 Twitter/X 獲取實時趨勢（含重試機制）
        
        工作流程：
        1. 使用 Twitter 帳戶登入
        2. 調用 client.get_trends('trending')
        3. 解析並返回格式化的趨勢數據
        
        重試策略：
        - 首次失敗後等待 5 秒再試
        - 最多重試 3 次
        - 首次登入可能需要 10-20 秒
        """
        if not TWIKIT_AVAILABLE:
            return []
        
        try:
            if retry_count == 0:
                logger.info("🔄 [Twikit] 開始從 Twitter 獲取趨勢...")
            else:
                logger.info(f"🔄 [Twikit] 重試 #{retry_count}/{max_retries}...")
            
            # 初始化 Twikit 客戶端
            client = Client('en-US')
            
            # 登入 Twitter（在線程中執行，避免阻塞）
            await asyncio.to_thread(
                client.login,
                auth_info_1=TWITTER_USERNAME,
                auth_info_2=TWITTER_EMAIL,
                password=TWITTER_PASSWORD,
                cookies_file=TWITTER_COOKIES_FILE
            )
            
            # 獲取實時趨勢
            trends_data = await asyncio.to_thread(
                client.get_trends,
                'trending'
            )
            
            # 解析趨勢數據
            trends = []
            if trends_data:
                for trend in trends_data:
                    trend_text = str(trend).strip()
                    if trend_text:
                        trends.append({
                            "trend": trend_text,
                            "platform": "twitter_twikit"
                        })
            
            if trends:
                logger.info(f"✅ [Twikit 成功] 獲取 {len(trends)} 項 Twitter 趨勢")
                return trends
            else:
                logger.warning("⚠️ [Twikit] 獲取到空結果")
                # 空結果也視為失敗，進行重試
                if retry_count < max_retries:
                    logger.info(f"⏳ [Twikit] 等待 5 秒後重試...")
                    await asyncio.sleep(5)
                    return await self._fetch_from_twikit(retry_count + 1, max_retries)
                return []
                
        except Exception as e:
            logger.error(f"❌ [Twikit 失敗] {type(e).__name__}: {str(e)[:100]}")
            
            # 重試機制：失敗後等待 5 秒再試
            if retry_count < max_retries:
                logger.info(f"⏳ [Twikit] 等待 5 秒後重試...")
                await asyncio.sleep(5)
                return await self._fetch_from_twikit(retry_count + 1, max_retries)
            
            logger.error(f"❌ [Twikit] 已達最大重試次數，改用備用方案")
            return []
    
    def _get_fallback_rotated_trends(self) -> List[Dict]:
        """
        備用方案：時間輪轉數據集系統
        
        每小時自動切換到不同的數據集，確保趨勢多樣化
        """
        current_hour = int(time.time()) // 3600
        dataset_index = current_hour % len(FALLBACK_TREND_DATASETS)
        dataset = FALLBACK_TREND_DATASETS[dataset_index]
        
        logger.debug(f"🔄 [輪轉備用] 數據集 #{dataset_index + 1}/{len(FALLBACK_TREND_DATASETS)}")
        
        # 基於時間種子打亂，確保同小時內順序一致
        random.seed(current_hour)
        shuffled = dataset.copy()
        random.shuffle(shuffled)
        
        return [{"trend": t, "platform": "fallback_rotated"} for t in shuffled]


# ========================
# 便利函數
# ========================

async def get_latest_trends(limit: int = 10) -> List[Dict]:
    """
    獲取最新趨勢
    
    使用示例：
        trends = await get_latest_trends(limit=5)
        for trend in trends:
            print(f"• {trend['trend']} ({trend['platform']})")
    """
    async with TrendsCollector() as collector:
        return await collector.get_combined_trends(limit)
