#!/usr/bin/env python3
import aiohttp
import asyncio
import json

API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"

async def check_api():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_ENDPOINT, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                schedule = data.get("data", {}).get("newAnimeSchedule", {})
                
                print("=== API newAnimeSchedule 結構 ===")
                print(f"Keys: {list(schedule.keys())}")
                print()
                
                # 顯示每個星期的第一個動畫
                for weekday, animes in sorted(schedule.items()):
                    if isinstance(animes, list) and len(animes) > 0:
                        anime = animes[0]
                        print(f"星期 {weekday}: {anime.get('animeTitle', 'N/A')}")
                        print(f"  scheduleTime: {anime.get('scheduleTime', 'N/A')}")
                        print(f"  keys: {list(anime.keys())}")
                        print()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(check_api())
