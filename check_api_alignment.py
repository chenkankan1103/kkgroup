#!/usr/bin/env python3
import aiohttp
import asyncio
import json

async def test_api_details():
    async with aiohttp.ClientSession() as session:
        try:
            url = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    schedule = data.get('data', {}).get('newAnimeSchedule', {})
                    
                    print("=== API 返回的完整日程 ===\n")
                    
                    for day in sorted(schedule.keys(), key=lambda x: int(x)):
                        animes = schedule[day]
                        print(f"Day {day} ({len(animes)} 集):")
                        for anime in animes:
                            title = anime.get('title', '(無名稱)')
                            time = anime.get('scheduleTime', '(無時間)')
                            video_sn = anime.get('videoSn', '(無 videoSn)')
                            anime_sn = anime.get('animeSn', '(無 animeSn)')
                            print(f"  {time:>5} | {title:40} | videoSn={video_sn}, animeSn={anime_sn}")
                        print()
                        
                else:
                    print(f"❌ API 返回狀態碼: {resp.status}")
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(test_api_details())
