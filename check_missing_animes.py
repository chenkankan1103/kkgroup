#!/usr/bin/env python3
import aiohttp
import asyncio
import sqlite3

db_path = "/home/e193752468/kkgroup/user_data.db"

async def check_missing():
    # 獲取 API 數據
    async with aiohttp.ClientSession() as session:
        try:
            url = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"API 錯誤: {resp.status}")
                    return
                
                data = await resp.json()
                schedule = data.get('data', {}).get('newAnimeSchedule', {})
                
                # Day 4 (星期四 05-04)
                day4_animes = schedule.get('4', [])
                api_times = set()
                api_videos = {}
                
                print("=== API 返回的 Day 4 動畫 ===")
                for anime in day4_animes:
                    time = anime.get('scheduleTime', '')
                    video_sn = anime.get('videoSn', '')
                    title = anime.get('title', '')
                    api_times.add(time)
                    api_videos[video_sn] = (time, title)
                    print(f"  {time:>5} | videoSn={video_sn:5} | {title}")
                
                # 查詢數據庫
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                
                print("\n=== 05-04 已推送的動畫 ===")
                c.execute("""
                    SELECT videoSn, anime_name, notified_at 
                    FROM anime_notified 
                    WHERE notified_at LIKE '2026-05-04%'
                    ORDER BY notified_at DESC
                """)
                
                pushed_videos = set()
                for row in c.fetchall():
                    video_sn, name, notified_at = row
                    pushed_videos.add(video_sn)
                    print(f"  {notified_at} | videoSn={video_sn:5} | {name}")
                
                print("\n=== 未被推送的動畫 ===")
                missing = set(api_videos.keys()) - pushed_videos
                if missing:
                    for video_sn in missing:
                        time, title = api_videos[video_sn]
                        print(f"  ⚠️ {time:>5} | videoSn={video_sn:5} | {title}")
                else:
                    print("  (全部推送過了)")
                
                conn.close()
                
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(check_missing())
