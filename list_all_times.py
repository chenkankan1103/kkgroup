#!/usr/bin/env python3
import aiohttp
import asyncio

async def check_api():
    async with aiohttp.ClientSession() as session:
        try:
            url = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"API 錯誤: {resp.status}")
                    return
                
                data = await resp.json()
                schedule = data.get('data', {}).get('newAnimeSchedule', {})
                
                print("=== API 返回的所有日的時刻 ===\n")
                
                for day_key in sorted(schedule.keys(), key=lambda x: int(x)):
                    animes = schedule[day_key]
                    times = {}
                    for anime in animes:
                        time = anime.get('scheduleTime', '')
                        title = anime.get('title', '')
                        video_sn = anime.get('videoSn', '')
                        if time not in times:
                            times[time] = []
                        times[time].append((video_sn, title))
                    
                    print(f"Day {day_key}:")
                    for time in sorted(times.keys()):
                        count = len(times[time])
                        print(f"  {time:>5} - {count} 部")
                        for video_sn, title in times[time]:
                            print(f"           videoSn={video_sn}")
                    print()
                
                # 特別查找有沒有 10:00 的時刻
                print("=== 搜尋 10:00 的動畫 ===")
                found_10 = False
                for day_key, animes in schedule.items():
                    for anime in animes:
                        if anime.get('scheduleTime', '') == '10:00':
                            print(f"  Day {day_key} | 10:00 | videoSn={anime.get('videoSn')} | {anime.get('title')}")
                            found_10 = True
                
                if not found_10:
                    print("  (沒有找到任何 10:00 的動畫)")
                
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(check_api())
