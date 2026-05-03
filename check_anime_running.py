#!/usr/bin/env python3
"""
檢查動畫推播系統是否在正常運行
"""
import sqlite3
from datetime import datetime, timedelta
import pytz

# 台灣時區
TW_TZ = pytz.timezone("Asia/Taipei")

def check_anime_status():
    """檢查動畫推播系統狀態"""
    try:
        # 連接 VM 上的數據庫
        conn = sqlite3.connect("kkgroup.db")
        cursor = conn.cursor()
        
        # 獲取最新的檢查記錄
        cursor.execute("""
            SELECT check_date, scheduled_time, created_at 
            FROM anime_check_history 
            ORDER BY created_at DESC 
            LIMIT 30
        """)
        records = cursor.fetchall()
        
        if not records:
            print("❌ 無任何檢查記錄")
            return False
        
        print("\n📊 最新 30 筆檢查記錄：\n")
        print(f"{'日期':<12} {'預定時刻':<10} {'實際檢查時間':<20}")
        print("-" * 45)
        
        now = datetime.now(TW_TZ)
        min_time = None
        max_time = None
        
        for date_str, time_str, created_at in records:
            # 解析時間戳
            check_time = datetime.fromisoformat(created_at)
            
            print(f"{date_str:<12} {time_str:<10} {created_at:<20}")
            
            if min_time is None or check_time < min_time:
                min_time = check_time
            if max_time is None or check_time > max_time:
                max_time = check_time
        
        # 分析數據
        if min_time and max_time:
            time_span = max_time - min_time
            num_records = len(records)
            
            print("\n📈 統計分析：\n")
            print(f"  紀錄數量：{num_records} 筆")
            print(f"  時間跨度：{time_span.total_seconds() / 60:.1f} 分鐘")
            print(f"  平均間隔：{time_span.total_seconds() / (num_records - 1) / 60:.1f} 分鐘")
            
            # 檢查是否正常運行（應該約 1-2 分鐘間隔）
            avg_interval = time_span.total_seconds() / (num_records - 1)
            if 40 < avg_interval < 80:  # 1-2 分鐘
                print(f"\n✅ 動畫檢查任務正在正常運行（平均間隔 {avg_interval:.0f} 秒）")
                return True
            else:
                print(f"\n⚠️ 動畫檢查任務運行異常（平均間隔 {avg_interval:.0f} 秒）")
                return False
        
        conn.close()
    
    except Exception as e:
        print(f"❌ 檢查失敗: {e}")
        return False

if __name__ == "__main__":
    check_anime_status()
