#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试脚本：检查动画推送系统状态
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pytz

TW_TZ = pytz.timezone('Asia/Taipei')
db_path = Path(__file__).resolve().parent / "user_data.db"

try:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    print("=" * 80)
    print("🎬 动画推送系统数据库诊断")
    print("=" * 80)
    
    # 1. Check anime tables
    print("\n【1】检查数据库表...")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'anime%' ORDER BY name")
    tables = cur.fetchall()
    print(f"   找到表: {[t[0] for t in tables]}")
    
    # 2. Check bootstrap status
    print("\n【2】Bootstrap 状态...")
    cur.execute("SELECT COUNT(*) FROM anime_bootstrap")
    bootstrap_count = cur.fetchone()[0]
    print(f"   Bootstrap 表行数: {bootstrap_count}")
    if bootstrap_count > 0:
        cur.execute("SELECT bootstrap_completed, completed_at FROM anime_bootstrap LIMIT 1")
        row = cur.fetchone()
        print(f"   状态: completed={row[0]}, 时间={row[1]}")
    
    # 3. Check notified episodes
    print("\n【3】已通知集集数...")
    cur.execute("SELECT COUNT(*) FROM anime_notified")
    notified_count = cur.fetchone()[0]
    print(f"   已通知: {notified_count} 集")
    if notified_count > 0:
        cur.execute("SELECT anime_name, COUNT(*) FROM anime_notified GROUP BY anime_name ORDER BY COUNT(*) DESC LIMIT 5")
        print("   最多的5个动画:")
        for anime_name, count in cur.fetchall():
            print(f"     - {anime_name}: {count} 集")
    
    # 4. Check recent check history
    print("\n【4】最近的检查历史（防重复）...")
    cur.execute("SELECT COUNT(*) FROM anime_check_history")
    history_count = cur.fetchone()[0]
    print(f"   总共检查记录: {history_count} 条")
    
    cur.execute("SELECT check_date, scheduled_time, checked_at FROM anime_check_history ORDER BY checked_at DESC LIMIT 10")
    if history_count > 0:
        print("   最近10条记录:")
        for check_date, scheduled_time, checked_at in cur.fetchall():
            print(f"     - [{check_date} {scheduled_time}] checked_at={checked_at}")
    else:
        print("   ⚠️ 没有检查历史，推送系统可能未运行过")
    
    # 5. Analyze frequency
    print("\n【5】检查频率分析...")
    now = datetime.now(TW_TZ)
    one_hour_ago = (now - timedelta(hours=1)).date()
    two_hours_ago = (now - timedelta(hours=2)).date()
    
    cur.execute("SELECT COUNT(*) FROM anime_check_history WHERE check_date >= ?", (one_hour_ago,))
    last_1h = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM anime_check_history WHERE check_date >= ?", (two_hours_ago,))
    last_2h = cur.fetchone()[0]
    
    print(f"   最后1小时检查: {last_1h} 次")
    print(f"   最后2小时检查: {last_2h} 次")
    print(f"   现在台湾时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 6. Check anime schedule availability
    print("\n【6】动画API数据...")
    import aiohttp
    import asyncio
    
    async def check_api():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.gamer.com.tw/mobile_app/anime/v3/index.php",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        schedule = data.get("data", {}).get("newAnimeSchedule", {})
                        new_anime = data.get("data", {}).get("newAnime", [])
                        print(f"   ✅ API 可达")
                        print(f"   日程表日期数: {len(schedule)}")
                        print(f"   最新动画集数: {len(new_anime)}")
                        if new_anime:
                            print(f"   最新的3个集:")
                            for ep in new_anime[:3]:
                                print(f"     - {ep.get('title')} vol.{ep.get('volume')}")
                    else:
                        print(f"   ❌ API 返回状态 {resp.status}")
        except Exception as e:
            print(f"   ❌ API 查询失败: {e}")
    
    asyncio.run(check_api())
    
    print("\n" + "=" * 80)
    conn.close()
    
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
