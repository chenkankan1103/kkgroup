"""
JustWatch Popular Titles GraphQL Client
取得台灣區 Netflix 熱門電影/影集（含標題、類型和海報 URL）
使用 GraphQL API 無需 API Key
"""

import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

JUSTWATCH_GRAPHQL_ENDPOINT = "https://apis.justwatch.com/graphql"
DEFAULT_HEADERS = {
    "User-Agent": "KKGroup-Discord-Bot/1.0 (https://github.com/kkgroup)",
    "Content-Type": "application/json",
}

# 簡單記憶體快取（key: f"{country}_{content_type}", value: (data, timestamp)）
_cache: dict = {}
CACHE_TTL = 7200  # 2 小時（熱門榜變動不大）


async def fetch_popular_netflix(
    content_type: str,  # "movie" or "show"
    country: str = "TW",
    provider: str = "nfx",  # 注意：GraphQL 可能不直接使用這個參數
    page_size: int = 20,
) -> list[dict]:
    """
    從 JustWatch GraphQL 取得熱門排行

    Returns:
        list[dict]: 每筆包含 title, object_type (SHOW/MOVIE), id, poster_url
    """
    cache_key = f"{country}_{content_type}"
    now = time.time()

    # 檢查快取
    cached = _cache.get(cache_key)
    if cached and (now - cached[1]) < CACHE_TTL:
        logger.debug(f"JustWatch 快取命中: {cache_key}")
        return cached[0]

    # GraphQL 查詢
    graphql_query = """
    query PopularTitles($country: Country!, $first: Int!) {
      popularTitles(country: $country, first: $first) {
        edges {
          node {
            __typename
            id
            objectType
            content(country: $country, language: "zh-TW") {
              title
              posterUrl
            }
          }
        }
      }
    }
    """

    variables = {"country": country, "first": page_size}

    try:
        async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
            async with session.post(
                JUSTWATCH_GRAPHQL_ENDPOINT,
                json={"query": graphql_query, "variables": variables},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 429:
                    logger.warning("JustWatch 429 速率限制，回傳快取或空列表")
                    return cached[0] if cached else []

                if resp.status != 200:
                    text = await resp.text()
                    logger.error(
                        f"JustWatch GraphQL API 錯誤 HTTP {resp.status}: {text[:300]}"
                    )
                    return cached[0] if cached else []

                data = await resp.json()

        # 解析 GraphQL 回應
        results = []
        if "data" in data and "popularTitles" in data["data"]:
            popular_data = data["data"]["popularTitles"]
            edges = popular_data.get("edges", [])

            for edge in edges:
                node = edge.get("node", {})
                content = node.get("content", {})

                # 只取得我們需要的欄位
                title = content.get("title", "未知標題")
                object_type = node.get("objectType", "").upper()  # SHOW or MOVIE
                show_id = node.get("id", "")
                poster_url_template = content.get("posterUrl", "")

                # 構建實際海報 URL
                poster_url = ""
                if (
                    poster_url_template
                    and "{profile}" in poster_url_template
                    and "{format}" in poster_url_template
                ):
                    # 使用常見的海報尺寸和格式
                    profile = "S166"  # 標準海報尺寸
                    image_format = "jpg"  # JPEG 格式
                    poster_url = f"https://images.justwatch.com{poster_url_template.replace('{profile}', profile).replace('{format}', image_format)}"

                # 根據物件類型過濾
                target_type = "SHOW" if content_type == "show" else "MOVIE"
                if object_type == target_type:
                    results.append(
                        {
                            "title": title,
                            "object_type": object_type,
                            "id": show_id,
                            "poster_url": poster_url,
                            "content_type": content_type,  # 為了向後相容
                            "release_year": "N/A",  # 暫時無法取得，保持向後相容
                        }
                    )

        # 更新快取
        _cache[cache_key] = (results, now)
        logger.info(f"JustWatch GraphQL 成功取得 {len(results)} 筆 {content_type} 資料")
        return results

    except Exception as e:
        logger.error(f"JustWatch GraphQL 請求異常: {e}")
        return cached[0] if cached else []
