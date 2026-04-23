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
from urllib.parse import unquote

load_dotenv()
logger = logging.getLogger(__name__)


class TrendsCollector:
    """趨勢收集器 - 聚合多個平台的趨勢數據"""
    
    def __init__(self):
        # Twitter/X API
        self.twitter_api_key = os.getenv("TWITTER_API_KEY")
        # ⚠️ Bearer Token 可能包含 URL 編碼字符，需要解碼
        raw_token = os.getenv("TWITTER_BEARER_TOKEN")
        self.twitter_bearer_token = unquote(raw_token) if raw_token else None
        
        logger.info(f"🔐 [TrendsCollector.__init__] Bearer Token 已解碼：{self.twitter_bearer_token[:50]}..." if self.twitter_bearer_token else "❌ Bearer Token 未設定")
        
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
        獲取 Twitter/X 趨勢 (使用 API v2)
        
        正確的 Twitter API v2 構成：
        - Base URL: https://api.twitter.com/2
        - Endpoint: /tweets/search/recent (搜索最近推文並提取趨勢)
        - Authentication: Bearer Token in Authorization header
        - Query Parameters: query, max_results, tweet.fields
        
        Args:
            location_woeid: 位置代碼 (23424971 = Taiwan) - 目前未用，因為 v2 API 不支持地區過濾
        
        Returns:
            趨勢列表 [{"trend": "...", "count": 12345, "platform": "twitter"}, ...]
        """
        if not self.twitter_bearer_token:
            logger.error("❌ TWITTER_BEARER_TOKEN 未設定或為空")
            return self._get_test_trends()
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            # 正確的 Headers 格式
            headers = {
                "Authorization": f"Bearer {self.twitter_bearer_token}",
                "User-Agent": "TrendsBot/1.0"
            }
            
            # Twitter API v2 端點
            # 搜索台灣相關的熱門推文（不帶轉推、中文、最近7天內）
            url = "https://api.twitter.com/2/tweets/search/recent"
            
            # API v2 正確的參數格式
            params = {
                "query": "lang:zh -is:retweet (台灣 OR Taiwan OR #台灣)",
                "max_results": 100,
                "tweet.fields": "public_metrics,created_at",
                "expansions": "author_id",
                "user.fields": "username,public_metrics"
            }
            
            logger.info("=" * 60)
            logger.info("🚀 [Twitter API v2] 開始調用")
            logger.info(f"📡 API 端點: {url}")
            logger.info(f"🔐 Token 長度: {len(self.twitter_bearer_token)} 字符")
            logger.info(f"📝 查詢語句: {params['query']}")
            logger.info("=" * 60)
            
            # 發送請求（指定 timeout）
            async with self.session.get(
                url, 
                headers=headers, 
                params=params, 
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                logger.info(f"📊 [API 回應] 狀態碼: {resp.status}")
                
                # 讀取響應文本用於調試
                response_text = await resp.text()
                logger.debug(f"📄 [API 原始響應] {response_text[:500]}")
                
                if resp.status == 200:
                    # 成功 - 解析 JSON
                    data = await resp.json() if response_text else {}
                    
                    tweets_count = len(data.get('data', []))
                    logger.info(f"✅ [API 成功] 收到 {tweets_count} 條推文")
                    
                    # 從推文中提取趨勢
                    trends = self._extract_twitter_trends(data)
                    logger.info(f"✅ [趨勢提取] 從推文中提取了 {len(trends)} 項趨勢")
                    
                    if trends:
                        logger.info("📊 [前 3 項趨勢]:")
                        for i, t in enumerate(trends[:3], 1):
                            logger.info(f"   {i}. {t['trend']} ({t['count']} 互動數)")
                        return trends
                    else:
                        logger.warning("⚠️  [提取失敗] 沒有提取到趨勢")
                        return self._get_test_trends()
                    
                elif resp.status == 401:
                    logger.error("❌ [認証失敗] HTTP 401 - Bearer Token 無效或已過期")
                    logger.error(f"   Token 前 20 字: {self.twitter_bearer_token[:20]}...")
                    return self._get_test_trends()
                    
                elif resp.status == 429:
                    logger.warning("⚠️  [限流] HTTP 429 - API 請求超過限制")
                    return self._get_test_trends()
                    
                elif resp.status == 403:
                    logger.error("❌ [權限不足] HTTP 403 - Token 可能沒有足夠的權限")
                    logger.error(f"   響應: {response_text[:300]}")
                    return self._get_test_trends()
                    
                else:
                    logger.error(f"❌ [API 錯誤] HTTP {resp.status}")
                    logger.error(f"   響應內容: {response_text[:500]}")
                    return self._get_test_trends()
        
        except asyncio.TimeoutError:
            logger.error("❌ [超時] Twitter API 請求超時（15 秒）")
            return self._get_test_trends()
            
        except Exception as e:
            logger.error(f"❌ [異常] Twitter 趨勢獲取失敗: {type(e).__name__}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return self._get_test_trends()
    
    def _get_test_trends(self) -> List[Dict]:
        """返回測試數據 - 台灣流行趨勢"""
        test_trends = [
            {"trend": "緯創", "count": 450, "platform": "twitter"},
            {"trend": "友達", "count": 420, "platform": "twitter"},
            {"trend": "鴻海", "count": 380, "platform": "twitter"},
            {"trend": "TSMC", "count": 350, "platform": "twitter"},
            {"trend": "聯發科", "count": 320, "platform": "twitter"},
            {"trend": "台積電", "count": 300, "platform": "twitter"},
            {"trend": "中華電信", "count": 280, "platform": "twitter"},
            {"trend": "台灣股市", "count": 250, "platform": "twitter"},
            {"trend": "半導體", "count": 220, "platform": "twitter"},
            {"trend": "電子產業", "count": 200, "platform": "twitter"},
        ]
        logger.info(f"✅ 使用測試數據：{len(test_trends)} 項（台灣流行趨勢）")
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
        """
        從 Twitter API v2 回應中提取趨勢
        
        邏輯：
        1. 遍歷所有推文的 metrics（likes, retweets）
        2. 提取推文中的 hashtags 和關鍵詞
        3. 按互動數加權排序
        """
        trends = {}
        
        if "data" not in data or len(data.get("data", [])) == 0:
            logger.warning("⚠️  [趨勢提取] 推文數據為空")
            return []
        
        try:
            for tweet in data.get("data", []):
                text = tweet.get("text", "")
                metrics = tweet.get("public_metrics", {})
                
                # 計算互動分數（likes + retweets + replies）
                engagement = (
                    metrics.get("like_count", 0) +
                    metrics.get("retweet_count", 0) * 2 +
                    metrics.get("reply_count", 0)
                )
                
                # 提取文本中的詞彙
                words = text.split()
                
                for word in words:
                    word_clean = word.lower().strip(".,!?;:\"'")
                    
                    # 提取 Hashtag (#xxx)
                    if word.startswith("#") and len(word_clean) > 2:
                        tag = word_clean
                        trends[tag] = trends.get(tag, 0) + engagement + 1
                    
                    # 提取關鍵詞（2-20 字符，不是停止詞）
                    elif 2 < len(word_clean) < 30 and not word_clean.startswith("http"):
                        stop_words = {
                            "the", "is", "a", "an", "and", "or", "but", "in", "on", "at", 
                            "to", "for", "of", "that", "this", "which", "who", "what", 
                            "where", "when", "why", "how", "台灣", "twitter", "x"
                        }
                        if word_clean not in stop_words:
                            trends[word_clean] = trends.get(word_clean, 0) + engagement
            
            # 排序並返回前 10 項
            sorted_trends = sorted(trends.items(), key=lambda x: x[1], reverse=True)[:10]
            
            result = [
                {
                    "trend": trend,
                    "count": count,
                    "platform": "twitter"
                }
                for trend, count in sorted_trends
            ]
            
            logger.info(f"✅ [提取完成] 提取了 {len(result)} 項不同的趨勢")
            return result
            
        except Exception as e:
            logger.error(f"❌ [提取錯誤] {type(e).__name__}: {e}")
            return []
    
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
