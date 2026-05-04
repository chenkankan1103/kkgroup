#!/usr/bin/env python3
import sqlite3
from datetime import datetime

db_path = "/home/e193752468/kkgroup/user_data.db"

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 刪除錯誤的預標記記錄 (05-04 01:00 應該等到凌晨才檢查，不應該在 05-03 下午提前標記)
    print("清理錯誤的預標記記錄...")
    c.execute("DELETE FROM anime_check_history WHERE check_date = '2026-05-04' AND scheduled_time = '01:00'")
    deleted = c.rowcount
    print(f"  ✅ 刪除了 {deleted} 筆記錄 (2026-05-04 01:00)")
    
    # 查看清理後的記錄
    print("\n=== 清理後的 05-04 時刻記錄 ===")
    c.execute("SELECT * FROM anime_check_history WHERE check_date = '2026-05-04' ORDER BY checked_at DESC")
    for row in c.fetchall():
        print(f"  {row}")
    
    conn.commit()
    conn.close()
    print("\n✅ 數據庫已更新")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
