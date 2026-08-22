import sys
sys.path.insert(0, '/home/e193752468/kkgroup')

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

TW_TZ = ZoneInfo('Asia/Taipei')

async def manual_trigger_push_check():
    print(f"=== 手動觸發推送檢查 {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 直接初始化完整的依賴鏈
    from cogs.ui.push_core import AnimePushCore, AnimeDatabase, AnimeDBImpl
    from cogs.ui.schedule_tracker import AnimeScheduleTracker
    from cogs.ui.anime_tracker import AnimeTracker, BahamutWebScraper
    from cogs.ui.ranking_stats import RankingStats
    
    # 初始化所有依賴
    db_path = '/home/e193752468/kkgroup/user_data.db'
    
    db_impl = AnimeDBImpl(db_path)
    db = AnimeDatabase(db_impl)
    
    # 創建schedule_tracker
    schedule_tracker = AnimeScheduleTracker(db_path)
    
    # 創建push_core
    push_core = AnimePushCore(db)
    
    # 創建ranking_stats
    ranking_stats = RankingStats(db)
    
    # 設置依賴（模擬bot為None）
    class MockBot:
        def get_cog(self, name):
            return None
        def get_channel(self, channel_id):
            return None
    
    mock_bot = MockBot()
    
    push_core.set_dependencies(mock_bot, db, None)
    schedule_tracker.set_dependencies(mock_bot, db, push_core, None)
    ranking_stats.set_dependencies(mock_bot, db)
    
    # 檢查今日時程
    today_schedule = schedule_tracker.get_today_schedule()
    print(f"今日時程筆數: {len(today_schedule)}")
    
    for item in today_schedule:
        anime_sn = item.get("anime_sn")
        video_sn = item.get("video_sn")
        scheduled_time = item.get("scheduled_time")
        day_of_week = item.get("day_of_week")
        print(f"  - anime_sn={anime_sn}, video_sn={video_sn}, time={scheduled_time}, day={day_of_week}")
        
        # 檢查anime_notified表中是否已推送
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM anime_notified WHERE video_sn=? AND anime_sn=?", (video_sn, anime_sn))
        count = cursor.fetchone()[0]
        conn.close()
        
        if count > 0:
            print(f"    ⏭️ 已推送過，跳過")
        else:
            print(f"    📢 需要推送！")
            # 這裡可以測試實際推送
            # result = await push_core.send_anime_push(anime_sn, video_sn)
            # print(f"    推送結果: {result}")

asyncio.run(manual_trigger_push_check())
