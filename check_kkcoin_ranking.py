#!/usr/bin/env python3
"""查詢 GCP 上的 KK幣排行"""
import sqlite3

try:
    conn = sqlite3.connect("/home/e193752468/kkgroup/user_data.db")
    cursor = conn.cursor()
    
    # 查詢 KK幣排行 Top 10
    cursor.execute("SELECT user_id, nickname, kkcoin FROM users ORDER BY kkcoin DESC LIMIT 10")
    
    print("\n" + "="*50)
    print("KK幣排行 Top 10")
    print("="*50)
    
    for i, (user_id, nickname, kkcoin) in enumerate(cursor.fetchall(), 1):
        nickname_display = nickname if nickname else f"用戶{user_id}"
        print(f"{i:2d}. {nickname_display:20} {kkcoin:>10,} KK幣")
    
    # 統計信息
    cursor.execute("SELECT COUNT(*) FROM users WHERE kkcoin > 0")
    users_with_coin = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(kkcoin) FROM users")
    total_coin = cursor.fetchone()[0] or 0
    
    print("\n" + "="*50)
    print(f"擁有KK幣的玩家: {users_with_coin}")
    print(f"KK幣總計: {total_coin:,}")
    print("="*50 + "\n")
    
    conn.close()
    
except Exception as e:
    print(f"錯誤: {e}")
