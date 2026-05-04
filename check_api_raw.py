#!/usr/bin/env python3
import aiohttp
import asyncio
import json

async def test_api_raw():
    async with aiohttp.ClientSession() as session:
        try:
            url = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    schedule = data.get('data', {}).get('newAnimeSchedule', {})
                    
                    print("=== 星期一 Day 1 的所有動畫 ===\n")
                    
                    day1_animes = schedule.get('1', [])
                    for idx, anime in enumerate(day1_animes):
                        print(f"集 #{idx}:")
                        # 打印所有鍵
                        for key, value in anime.items():
                            print(f"  {key}: {value}")
                        print()
                    
                    print("\n=== 星期四 Day 4 的所有動畫 ===\n")
                    
                    day4_animes = schedule.get('4', [])
                    for idx, anime in enumerate(day4_animes):
                        print(f"集 #{idx}:")
                        for key, value in anime.items():
                            print(f"  {key}: {value}")
                        print()
                        
                else:
                    print(f"❌ API 返回狀態碼: {resp.status}")
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(test_api_raw())
