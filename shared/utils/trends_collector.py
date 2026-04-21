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
        
        # Reddit API
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = os.getenv("REDDIT_USER_AGENT", "TrendsBot/1.0")
        
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
            logger.warning("⚠️  TWITTER_BEARER_TOKEN 未設定，跳過 Twitter 趨勢")
            return []
        
        try:
            # Twitter API v2 需要用 Trends Endpoint（如果有權限）
            # 否則用替代方案：搜尋熱門詞彙
            headers = {
                "Authorization": f"Bearer {self.twitter_bearer_token}",
                "User-Agent": "TrendsBot/1.0"
            }
            
            # 使用 search/recent 找熱門話題（近7天）
            url = "https://api.twitter.com/2/tweets/search/recent"
            params = {
                "query": "-is:retweet",  # 排除轉推
                "max_results": 100,
                "tweet.fields": "public_metrics",
            }
            
            async with self.session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # 提取話題標籤
                    trends = self._extract_twitter_trends(data)
                    logger.info(f"✅ Twitter 趨勢已獲取：{len(trends)} 項")
                    return trends
                else:
                    logger.error(f"❌ Twitter API 錯誤: {resp.status}")
                    return []
        
        except Exception as e:
            logger.error(f"❌ Twitter 趨勢獲取失敗: {e}")
            return []
    
    async def get_reddit_trends(self, subreddit: str = "all") -> List[Dict]:
        """
        獲取 Reddit 趨勢
        
        Args:
            subreddit: Subreddit 名稱 (default: all)
        
        Returns:
            趨勢列表 [{"trend": "...", "upvotes": 5000}, ...]
        """
        if not self.reddit_client_id or not self.reddit_client_secret:
            logger.warning("⚠️  REDDIT 憑證未設定，跳過 Reddit 趨勢")
            return []
        
        try:
            # 獲取 Reddit OAuth Token
            auth = aiohttp.BasicAuth(self.reddit_client_id, self.reddit_client_secret)
            token_url = "https://www.reddit.com/api/v1/access_token"
            data = {"grant_type": "client_credentials"}
            
            async with self.session.post(token_url, auth=auth, data=data) as resp:
                token_data = await resp.json()
                access_token = token_data.get("access_token")
                
                if not access_token:
                    logger.error("❌ Reddit Token 獲取失敗")
                    return []
            
            # 獲取熱門帖子
            headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": self.reddit_user_agent
            }
            
            url = f"https://oauth.reddit.com/r/{subreddit}/hot"
            params = {"limit": 100}
            
            async with self.session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    trends = self._extract_reddit_trends(data)
                    logger.info(f"✅ Reddit 趨勢已獲取：{len(trends)} 項")
                    return trends
                else:
                    logger.error(f"❌ Reddit API 錯誤: {resp.status}")
                    return []
        
        except Exception as e:
            logger.error(f"❌ Reddit 趨勢獲取失敗: {e}")
            return []
    
    def _extract_twitter_trends(self, data: Dict) -> List[Dict]:
        """從 Twitter 回應中提取趨勢"""
        trends = []
        
        if "data" not in data:
            return trends
        
        hashtags_count = {}
        
        for tweet in data["data"]:
            # 從推文中提取 hashtag
            if "text" in tweet:
                text = tweet["text"]
                words = text.split()
                for word in words:
                    if word.startswith("#") and len(word) > 1:
                        tag = word.lower()
                        hashtags_count[tag] = hashtags_count.get(tag, 0) + 1
        
        # 排序並返回前10名
        sorted_tags = sorted(hashtags_count.items(), key=lambda x: x[1], reverse=True)[:10]
        
        for tag, count in sorted_tags:
            trends.append({
                "trend": tag,
                "count": count,
                "platform": "twitter"
            })
        
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
        獲取合併的趨勢（Twitter + Reddit）
        
        Args:
            limit: 返回的最大趨勢數
        
        Returns:
            合併後的趨勢列表，按熱度排序
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            # 並行獲取兩個平台的趨勢
            twitter_trends, reddit_trends = await asyncio.gather(
                self.get_twitter_trends(),
                self.get_reddit_trends(),
                return_exceptions=True
            )
            
            # 處理異常
            if isinstance(twitter_trends, Exception):
                logger.error(f"Twitter 趨勢獲取異常: {twitter_trends}")
                twitter_trends = []
            
            if isinstance(reddit_trends, Exception):
                logger.error(f"Reddit 趨勢獲取異常: {reddit_trends}")
                reddit_trends = []
            
            # 合併並去重
            combined = {}
            
            for trend in twitter_trends:
                key = trend["trend"].lower()
                combined[key] = {
                    "trend": trend["trend"],
                    "sources": ["twitter"],
                    "score": trend.get("count", 0)
                }
            
            for trend in reddit_trends:
                key = trend["trend"].lower()
                if key in combined:
                    combined[key]["sources"].append("reddit")
                    combined[key]["score"] += trend.get("upvotes", 0)
                else:
                    combined[key] = {
                        "trend": trend["trend"],
                        "sources": ["reddit"],
                        "score": trend.get("upvotes", 0)
                    }
            
            # 排序並返回前 limit 項
            sorted_trends = sorted(
                combined.values(),
                key=lambda x: x["score"],
                reverse=True
            )[:limit]
            
            logger.info(f"✅ 合併趨勢：{len(sorted_trends)} 項")
            return sorted_trends
        
        except Exception as e:
            logger.error(f"❌ 合併趨勢失敗: {e}")
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
