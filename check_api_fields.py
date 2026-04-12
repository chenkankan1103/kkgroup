#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速檢查 API 返回的完整字段"""

import asyncio
import aiohttp
import json

async def check_api():
    api_url = "https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn=300000"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    anime = data.get("data", {}).get("anime", {})
                    print("=== API 返回的完整字段 ===")
                    for k, v in anime.items():
                        if isinstance(v, (list, dict)):
                            print(f"{k}: <{type(v).__name__}> (length: {len(v)})")
                        else:
                            print(f"{k}: {v}")
                else:
                    print(f"API 返回狀態碼: {resp.status}")
    except Exception as e:
        print(f"錯誤: {e}")

if __name__ == "__main__":
    asyncio.run(check_api())
