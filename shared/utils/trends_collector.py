# -*- coding: utf-8 -*-
"""
趨勢收集模組 - 從 Twitter/X、Reddit 等平台獲取實時趨勢

支持的平台：
- Twitter/X：使用官方 API v2
- Reddit：使用 PRAW 庫
- PTT：後期擴展（使用爬蟲）
"""

import aiohttp
import asyncio
import os
from typing import List, Dict, Optional
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class TrendsCollector:
    """趨勢收集器 - 聚合多個平台的趨勢數據"""
    
    def __init__(self):
        # Twitter/X API
        self.twitter_api_key = os.getenv("TWITTER_API_KEY")
        self.twitter_bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        
        # Reddit API (已禁用)
        self.reddit_client_id = None
        self.reddit_client_secret = None
        self.reddit_user_agent = "TrendsBot/1.0"
        
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def get_twitter_trends(self, location_woeid: str = "23424971") -> List[Dict]:
        """
        獲取 Twitter/X 趨勢
        
        Args:
            location_woeid: 位置代碼 (23424971 = Taiwan)
        
        Returns:
            趨勢列表 [{"trend": "...", "tweets": 12345}, ...]
        """
        if not self.twitter_bearer_token:
            logger.warning("⚠️  TWITTER_BEARER_TOKEN 未設定，使用測試數據")
            return self._get_test_trends()
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            headers = {
                "Authorization": f"Bearer {self.twitter_bearer_token}",
                "User-Agent": "TrendsBot/1.0"
            }
            
            logger.info(f"🔍 開始搜尋 Twitter 趨勢...")
            
            url = "https://api.twitter.com/2/tweets/search/recent"
            params = {
                "query": "lang:zh -is:retweet",
                "max_results": 100,
                "tweet.fields": "public_metrics",
            }
            
            logger.info(f"📡 API 端點: {url}")
            
            async with self.session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                logger.info(f"📊 API 回應狀態: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ 收到 API 響應，包含 {len(data.get('data', []))} 條推文")
                    
                    trends = self._extract_twitter_trends(data)
                    logger.info(f"✅ Twitter 趨勢已獲取：{len(trends)} 項")
                    
                    if trends:
                        for t in trends[:3]:
                            logger.info(f"   - {t['trend']}: {t['count']} 次")
                    else:
                        logger.warning("⚠️  沒有提取到趨勢，使用測試數據")
                        return self._get_test_trends()
                    
                    return trends
                    
                elif resp.status == 429:
                    logger.warning("⚠️  Twitter API 限流（429）- 使用測試數據")
                    return self._get_test_trends()
                elif resp.status == 401:
                    logger.error(f"❌ Twitter API 認証失敗（401）- Token 可能無效")
                    return self._get_test_trends()
                else:
                    text = await resp.text()
                    logger.error(f"❌ Twitter API 錯誤: {resp.status} - {text[:200]}")
                    return self._get_test_trends()
        
        except asyncio.TimeoutError:
            logger.error(f"❌ Twitter API 超時 - 使用測試數據")
            return self._get_test_trends()
        except Exception as e:
            logger.error(f"❌ Twitter 趨勢獲取失敗: {e}")
            return self._get_test_trends()
    
    def _get_test_trends(self) -> List[Dict]:
        """返回測試數據"""
        test_trends = [
            {"trend": "#臺灣", "count": 450, "platform": "twitter"},
            {"trend": "#台灣", "count": 420, "platform": "twitter"},
            {"trend": "鴻海", "count": 380, "platform": "twitter"},
            {"trend": "TSMC", "count": 350, "platform": "twitter"},
            {"trend": "聯發科", "count": 320, "platform": "twitter"},
            {"trend": "新聞", "count": 300, "platform": "twitter"},
            {"trend": "天氣", "count": 280, "platform": "twitter"},
            {"trend": "體育", "count": 250, "platform": "twitter"},
            {"trend": "股市", "count": 220, "platform": "twitter"},
            {"trend": "政治", "count": 200, "platform": "twitter"},
        ]
        logger.info(f"✅ 使用測試數據：{len(test_trends)} 項")
        return test_trends
    
    async def get_reddit_trends(self, subreddit: str = "all") -> List[Dict]:
        """
        Reddit 趨勢已禁用（聚焦 Twitter 台灣趨勢）
        
        Args:
            subreddit: Subreddit 名稱 (已禁用)
        
        Returns:
            空列表
        """
        logger.info("⏭️  Reddit 已禁用，返回空列表")
        return []
    
    def _extract_twitter_trends(self, data: Dict) -> List[Dict]:
        """從 Twitter 回應中提取趨勢"""
        trends = []
        
        if "data" not in data or len(data["data"]) == 0:
            logger.debug(f"  無推文數據: {data}")
            return trends
        
        hashtags_count = {}
        word_count = {}
        
        for tweet in data["data"]:
            # 從推文中提取 hashtag 和常見詞彙
            if "text" in tweet:
                text = tweet["text"]
                # 獲取推文的互動數
                metrics = tweet.get("public_metrics", {})
                engagement = metrics.get("like_count", 0) + metrics.get("retweet_count", 0)
                
                words = text.split()
                for word in words:
                    word_clean = word.lower().strip(".,!?;:")
                    
                    # 提取 hashtag
                    if word.startswith("#") and len(word) > 1:
                        tag = word_clean
                        hashtags_count[tag] = hashtags_count.get(tag, 0) + engagement + 1
                    
                    # 提取高排名詞彙（長度合理的詞）
                    elif 2 < len(word_clean) < 50 and not word_clean.startswith("http"):
                        if word_clean not in ["the", "is", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of"]:
                            word_count[word_clean] = word_count.get(word_clean, 0) + engagement + 1
        
        # 合併 hashtag 和詞彙
        combined = {**hashtags_count, **word_count}
        
        # 排序並返回前10名
        sorted_tags = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:10]
        
        for tag, count in sorted_tags:
            trends.append({
                "trend": tag,
                "count": count,
                "platform": "twitter"
            })
        
        logger.debug(f"  提取了 {len(trends)} 個趨勢")
        return trends
    
    def _extract_reddit_trends(self, data: Dict) -> List[Dict]:
        """從 Reddit 回應中提取趨勢"""
        trends = []
        
        if "data" not in data or "children" not in data["data"]:
            return trends
        
        posts = data["data"]["children"][:10]  # 前10個熱門帖子
        
        for post in posts:
            post_data = post.get("data", {})
            trends.append({
                "trend": post_data.get("title", "").split()[0][:50],  # 使用標題前50個字
                "upvotes": post_data.get("ups", 0),
                "platform": "reddit"
            })
        
        return trends
    
    async def get_combined_trends(self, limit: int = 10) -> List[Dict]:
        """
        獲取 Twitter 台灣趨勢（Reddit 已禁用）
        
        Args:
            limit: 返回的最大趨勢數
        
        Returns:
            台灣 Twitter 趨勢列表，按熱度排序
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            # 只獲取 Twitter 台灣趨勢
            twitter_trends = await self.get_twitter_trends()
            
            if isinstance(twitter_trends, Exception):
                logger.error(f"Twitter 趨勢獲取異常: {twitter_trends}")
                twitter_trends = []
            
            # 過濾並格式化趨勢
            trends_list = []
            for trend in twitter_trends:
                trends_list.append({
                    "trend": trend["trend"],
                    "sources": ["twitter"],
                    "score": trend.get("count", 0),
                    "region": "Taiwan"
                })
            
            # 排序並返回前 limit 項
            sorted_trends = sorted(
                trends_list,
                key=lambda x: x["score"],
                reverse=True
            )[:limit]
            
            logger.info(f"✅ 取得台灣 Twitter 趨勢：{len(sorted_trends)} 項")
            return sorted_trends
        
        except Exception as e:
            logger.error(f"❌ 趨勢獲取失敗: {e}")
            return []


async def get_latest_trends(limit: int = 10) -> List[Dict]:
    """
    便利函數 - 獲取最新趨勢
    
    使用示例：
        trends = await get_latest_trends(limit=10)
        for trend in trends:
            print(f"{trend['trend']} - {trend['sources']}")
    """
    async with TrendsCollector() as collector:
        return await collector.get_combined_trends(limit=limit)
