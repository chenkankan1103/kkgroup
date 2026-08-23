#!/usr/bin/env python3
"""強制刷新週動畫排程（繞過 22:00 檢查）"""
import asyncio
import sys
import os

project_root = "/home/e193752468/kkgroup"
sys.path.insert(0, project_root)
os.chdir(project_root)

from cogs.ui.schedule_tracker import AnimeScheduleTracker
from cogs.ui.anime_tracker import AnimeTracker
from shared.db.async_db import AsyncSheetDrivenDB
from shared.db.manager import DatabaseManager
from datetime import datetime
from zoneinfo import ZoneInfo

TW_TZ = ZoneInfo('Asia/Taipei')

async def main():
    db_path = "user_data.db"
    await DatabaseManager.initialize(db_path)
    db = AsyncSheetDrivenDB(db_path)
    db._pool = await DatabaseManager.get_pool_or_init()

    tracker = AnimeScheduleTracker(db_path)
    tracker.db = db

    # Create anime_tracker instance for rescheduling push jobs
    anime_tracker = AnimeTracker(None, db)  # bot=None for CLI usage
    anime_tracker.schedule_tracker = tracker

    now = datetime.now(TW_TZ)
    print(f"目前台灣時間: {now}")

    # 直接執行刷新邏輯，不檢查時間
    from cogs.ui.push_core import API_ENDPOINT, API_TIMEOUT, API_HEADERS, get_week_start_date
    import aiohttp

    # 1. 拉取完整週表
    schedule = {}
    try:
        async with aiohttp.ClientSession(headers=API_HEADERS) as session:
            async with session.get(
                API_ENDPOINT, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
            ) as response:
                if response.status != 200:
                    print(f"❌ API returned status {response.status}")
                else:
                    data = await response.json()
                    schedule = data.get("data", {}).get("newAnimeSchedule", {})
                    print(f"✅ API 獲取到 {sum(len(v) for v in schedule.values())} 筆時程")
    except Exception as e:
        print(f"❌ Error fetching schedule: {e}")

    # 如果 API 失敗，嘗試首頁爬取
    if not schedule:
        print("⚠️ API 失敗，嘗試首頁爬取...")
        try:
            from cogs.ui.bahamut_web_scraper import BahamutWebScraper
            scraper = BahamutWebScraper()
            homepage_schedule = await scraper.fetch_weekly_schedule_from_homepage()
            if homepage_schedule:
                schedule = {}
                for entry in homepage_schedule:
                    day_str = str(entry['day_of_week'])
                    if day_str not in schedule:
                        schedule[day_str] = []
                    schedule[day_str].append({
                        'videoSn': entry['video_sn'],
                        'animeSn': entry['anime_sn'],
                        'scheduleTime': entry['scheduled_time'],
                        'animeTitle': entry['title'],
                        'episode': entry['episode']
                    })
                print(f"✅ 從首頁爬取到 {len(homepage_schedule)} 筆時程")
        except Exception as e:
            print(f"❌ 首頁爬取失敗: {e}")

    if not schedule:
        print("❌ 無法取得時程表")
        await DatabaseManager.close()
        return

    # 2. 計算 week_start_date (api_week=True)
    week_start_str = get_week_start_date(now, api_week=True)
    print(f"📅 週起始日期: {week_start_str}")

    # 3. 建立 videoSn -> animeSn 映射
    video_to_anime_map = await tracker._build_video_to_anime_map()

    # 4. 準備排程資料
    schedule_data = []
    enriched_count = 0
    for day_offset in range(7):
        day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
        day_key = str(day_of_week)

        if day_key in schedule:
            for anime in schedule[day_key]:
                scheduled_time = anime.get("scheduleTime", "")
                if scheduled_time:
                    video_sn = anime.get("videoSn")
                    if video_sn and video_sn in video_to_anime_map:
                        enriched_anime = anime.copy()
                        enriched_anime["animeSn"] = video_to_anime_map[video_sn]
                        enriched_count += 1
                    else:
                        enriched_anime = anime

                    schedule_data.append(
                        {
                            "day_of_week": day_of_week,
                            "scheduled_time": scheduled_time,
                            "anime_data": enriched_anime,
                        }
                    )

    print(f"📊 爬蟲映射表大小: {len(video_to_anime_map)}, 成功豐富: {enriched_count}/{len(schedule_data)}")

    # 5. 全量覆蓋週表
    if schedule_data:
        db.save_weekly_schedule(week_start_str, schedule_data)
        print(f"✅ 週表全量覆蓋完成 ({len(schedule_data)} 個時刻)")

    # 6. 清理舊週記錄
    if hasattr(db, "cleanup_old_weeks"):
        deleted = db.cleanup_old_weeks()
        if deleted > 0:
            print(f"🧹 清理舊週記錄: {deleted} 筆")

    # 7. 重新排程推送任務
    try:
        await anime_tracker._reschedule_push_jobs()
        print("✅ 推送任務重新排程完成")
    except Exception as e:
        print(f"⚠️ 推送任務重新排程失敗 (等 uibot 重啟自動重排): {e}")

    print("✅ 強制週排程刷新完成！")
    await DatabaseManager.close()

if __name__ == "__main__":
    asyncio.run(main())