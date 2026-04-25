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
from pathlib import Path

# 確保 .env 被加載（必須在所有 os.getenv() 之前）
from dotenv import load_dotenv
load_dotenv()

# 嘗試導入 Twikit（Twitter 趨勢爬蟲）
try:
    from twikit import Client
    TWIKIT_AVAILABLE = True
except ImportError:
    TWIKIT_AVAILABLE = False

# 嘗試導入官方 SerpApi SDK（Google Trends）
try:
    from serpapi import Client as SerpApiClient
    SERPAPI_AVAILABLE = True
except ImportError:
    SERPAPI_AVAILABLE = False

logger = logging.getLogger(__name__)

# ========================
# SerpApi 配置（Google Trends）
# ========================
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
SERPAPI_ENABLED = bool(SERPAPI_API_KEY)

# ========================
# Twikit 配置（Twitter 趨勢）
# ========================

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "")
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL", "")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "")
TWITTER_COOKIES_FILE = "/tmp/twitter_cookies.json"

# ========================
# Meta Threads 配置
# ========================
# 說明：Meta Threads 沒有官方公開 API
# 可選方案：
# 1. 使用非官方爬蟲（threads-api, threads-py等）
# 2. 在此實現簡單的 HTTP 爬蟲
# 3. 整合已有的 Threads 社群 API（如果有）
# 
# 目前預設使用硬編碼的台灣 Threads 熱門話題作為備用方案

THREADS_ENABLED = os.getenv("THREADS_ENABLED", "false").lower() == "true"
THREADS_USERNAME = os.getenv("THREADS_USERNAME", "")  # 可選：用於爬蟲認證


# ========================
# 數據集備用方案（輪轉）
# ========================

FALLBACK_TREND_DATASETS = [
    # 台灣科技新聞
    ["台積電", "聯發科", "鴻海", "聯電", "日月光"],
    # AI & 科技趨勢
    ["AI晶片", "ChatGPT", "機器學習", "大型語言模型", "深度學習"],
    # 台灣製造業
    ["緯創", "友達", "群創", "技嘉", "廣達"],
    # 區塊鏈 & Web3
    ["元宇宙", "NFT", "區塊鏈", "加密貨幣", "Web3"],
    # 綠能 & 能源
    ["自動駕駛", "電動車", "新能源", "綠能", "永續發展"],
    # 5G & 通訊
    ["雲計算", "邊緣計算", "量子計算", "5G", "6G"],
    # 生物科技 & 醫療
    ["生物科技", "基因編輯", "疫苗", "醫療", "藥物"],
    # 半導體產業
    ["元器件", "晶圓代工", "半導體", "IC設計", "電子產業"],
    # Threads 台灣時事（Meta Threads 熱門話題）
    ["政治新聞", "體育賽事", "娛樂八卦", "社會新聞", "財經焦點"],
    # Threads 生活趨勢
    ["旅遊分享", "美食推薦", "居家佈置", "時尚穿搭", "健身運動"],
]


class TrendsCollector:
    """
    趨勢收集器 - 多平台支持
    
    優先級（嚴格模式）：
    1. � Google Trends（SerpApi 官方 SDK，主方案）
    2. 🐦 Twitter/X 實時趨勢（Twikit 爬蟲）
    3. 🧵 Meta Threads 台灣時事（未來實現）
    4. 🔄 時間輪轉數據集（備用方案）
    
    說明：
    - SerpApi 使用官方 SDK（需要 API Key）
    - Twikit 使用 Twitter 官方 API（不需要 API Key）
    - Threads 目前無官方 API，備用使用時間輪轉台灣時事數據
    - 關鍵詞：Google Trends, Twikit, Threads, 趨勢爬蟲, 實時數據
    """
    
    def __init__(self):
        if SERPAPI_ENABLED:
            logger.info("✅ [Google Trends] SerpApi 已配置，使用官方 SDK")
        else:
            logger.warning("⚠️ [Google Trends] SERPAPI_API_KEY 未設置")
        
        if not TWIKIT_AVAILABLE:
            logger.warning("⚠️ [Twikit] 未安裝，只能使用其他方案")
        elif TWITTER_USERNAME and TWITTER_EMAIL and TWITTER_PASSWORD:
            logger.info("✅ [Twikit] 帳戶已配置，使用 Twitter 實時趨勢")
        else:
            logger.warning("⚠️ [Twikit] 帳戶信息不完整，將跳過 Twitter 方案")
        
        if THREADS_ENABLED and THREADS_USERNAME:
            logger.info("✅ [Threads] 帳戶已配置，將嘗試蒐集 Threads 趨勢")
        else:
            logger.info("ℹ️ [Threads] 未配置，將使用台灣時事備用數據")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def get_combined_trends(self, limit: int = 10, strict: bool = False) -> List[Dict]:
        """
        主入口：獲取實時趨勢（多平台）
        
        參數：
        - limit: 返回趨勢數量
        - strict: 嚴格模式
          - True: 只返回真實平台數據，失敗返回空列表
          - False: 失敗時使用備用方案（預設）
        
        優先級：
        1. Google Trends（SerpApi）- 台灣地區
        2. Twitter/X 趨勢（Twikit）- 需要帳戶認證
        3. Meta Threads 趨勢（未來支持）
        4. 時間輪轉備用數據集（非嚴格模式）
        """
        # 1. 嘗試 SerpApi 獲取 Google Trends
        if SERPAPI_ENABLED:
            trends = await self._fetch_from_google_trends()
            if trends:
                logger.info(f"✅ [成功] 從 Google Trends 獲取 {len(trends)} 項台灣趨勢")
                return trends[:limit]
        
        # 2. 嘗試 Twikit 獲取 Twitter 趨勢
        if TWIKIT_AVAILABLE and TWITTER_USERNAME:
            trends = await self._fetch_from_twikit()
            if trends:
                logger.info(f"✅ [成功] 從 Twitter 獲取 {len(trends)} 項趨勢")
                return trends[:limit]
        
        # 3. 嘗試 Threads 獲取台灣時事趨勢（未來實現）
        if THREADS_ENABLED and THREADS_USERNAME:
            trends = await self._fetch_from_threads()
            if trends:
                logger.info(f"✅ [成功] 從 Threads 獲取 {len(trends)} 項台灣時事趨勢")
                return trends[:limit]
        
        # 嚴格模式：如果所有真實平台都失敗，不使用備用方案
        if strict:
            logger.warning("⚠️ [嚴格模式] 所有真實平台失敗，返回空列表（跳過本次發布）")
            return []
        
        # 4. 備用：時間輪轉數據集
        logger.debug("🔄 [備用方案] 使用時間輪轉數據集")
        trends = self._get_fallback_rotated_trends()
        
        return trends[:limit]
    
    async def _fetch_from_google_trends(self) -> List[Dict]:
        """
        使用 SerpApi 官方 SDK 從 Google Trends 獲取台灣地區熱搜
        
        特點：
        - 使用官方 SerpApi 包（已克服 DNS 阻止問題）
        - 地區限制：台灣 (geo=TW)
        - 語言：繁體中文 (hl=zh-TW，可選)
        - 穩定性：官方 SDK 比 requests 更可靠
        
        返回：
            List[Dict] - [{"trend": "...", "platform": "google_trends", ...}, ...]
        """
        if not SERPAPI_ENABLED:
            return []
        
        try:
            logger.info("🔍 [Google Trends] 開始從 SerpApi 獲取台灣趨勢...")
            
            # 在執行器中運行同步 SDK 調用（避免阻塞事件循環）
            loop = asyncio.get_event_loop()
            trends = await loop.run_in_executor(
                None,
                self._fetch_google_trends_sync
            )
            
            if trends:
                logger.info(f"✅ [Google Trends] 成功獲取 {len(trends)} 項")
                return trends
            else:
                logger.warning("⚠️ [Google Trends] 未能解析趨勢數據")
                return []
                
        except Exception as e:
            logger.error(f"❌ [Google Trends 失敗] {type(e).__name__}: {str(e)[:100]}")
            return []
    
    def _fetch_google_trends_sync(self) -> List[Dict]:
        """
        同步版本的 Google Trends 獲取（在執行器中運行）
        """
        try:
            client = SerpApiClient(api_key=SERPAPI_API_KEY)
            results = client.search({
                'engine': 'google_trends_trending_now',
                'geo': 'TW'
            })
            
            trends_list = []
            for item in results.get('trending_searches', []):
                trend_text = item.get('query') or item.get('title') or 'Unknown'
                trends_list.append({
                    "trend": trend_text,
                    "platform": "google_trends",
                    "search_volume": item.get('search_volume', 0),
                    "increase_percentage": item.get('increase_percentage', 0)
                })
            
            # 輸出前 5 項趨勢用於調試
            if trends_list:
                top_5 = [t['trend'] for t in trends_list[:5]]
                logger.info(f"📊 [Google Trends 前5項] {', '.join(top_5)}")
            
            return trends_list
            
        except Exception as e:
            logger.error(f"❌ [Google Trends SDK] {type(e).__name__}: {str(e)[:100]}")
            return []
    
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
    
    async def _fetch_from_threads(self) -> List[Dict]:
        """
        使用 Meta Threads API 獲取台灣時事趨勢（未來實現）
        
        實現方案（可選）：
        1. GitHub: https://github.com/iSarabjitDhiman/MetaThreads
           - 安裝：pip install threads-api
           - 使用：from threads_api import Client
           - 獲取趨勢：client.get_trends('Taiwan') 或類似 API
        
        2. 自定義爬蟲
           - 爬取 threads.net 的探索頁面
           - 解析熱門話題標籤
        
        3. Threads 官方 API（如果未來開放）
        
        目前狀態：
        - 框架已準備
        - 返回空列表（未實現真實爬蟲）
        - 系統會自動回退到備用方案
        """
        if not THREADS_ENABLED:
            return []
        
        try:
            logger.info("🔄 [Threads] 開始從 Meta Threads 獲取台灣時事趨勢...")
            
            # TODO: 在此實現真實的 Threads 爬蟲
            # 例如：
            # from threads_api import Client
            # client = Client(username=THREADS_USERNAME)
            # trends = client.get_trends('Taiwan')
            
            logger.debug("ℹ️ [Threads] 尚未實現真實爬蟲，返回空列表")
            return []
            
        except Exception as e:
            logger.error(f"❌ [Threads 失敗] {type(e).__name__}: {str(e)[:100]}")
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

async def get_latest_trends(limit: int = 10, strict: bool = False) -> List[Dict]:
    """
    獲取最新趨勢
    
    參數：
    - limit: 返回趨勢數量（預設 10）
    - strict: 嚴格模式（預設 False）
      - True: 只發布真實 Twitter 趨勢，失敗返回空列表
      - False: 失敗時使用時間輪轉備用數據集
    
    使用示例：
        # 標準模式（失敗用備用數據）
        trends = await get_latest_trends(limit=5)
        
        # 嚴格模式（只要真實 Twitter 數據）
        trends = await get_latest_trends(limit=5, strict=True)
        if not trends:
            logger.warning("未能獲得 Twitter 趨勢，跳過本次發布")
    
    返回：
        List[Dict] - [{"trend": "...", "platform": "twitter_twikit"或"fallback_rotated"}, ...]
    """
    async with TrendsCollector() as collector:
        return await collector.get_combined_trends(limit, strict=strict)
