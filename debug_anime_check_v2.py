#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试脚本：完整检查动画推送系统的所有问题
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import sys
import json

TW_TZ = pytz.timezone('Asia/Taipei')
db_path = Path(__file__).resolve().parent / "user_data.db"

print("\n" + "=" * 80)
print("🎬 动画推送系统完整诊断 (2026-05-03 22:07)")
print("=" * 80)

try:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    # 1. 检查数据库完整性
    print("\n【1】数据库表完整性...")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'anime%' ORDER BY name")
    tables = [t[0] for t in cur.fetchall()]
    print(f"   ✅ 找到表: {tables}")
    
    # 2. Bootstrap 状态
    print("\n【2】Bootstrap 状态...")
    cur.execute("SELECT COUNT(*) FROM anime_bootstrap WHERE bootstrap_completed=1")
    bootstrap = cur.fetchone()[0]
    if bootstrap > 0:
        print(f"   ✅ Bootstrap 已完成")
    else:
        print(f"   ❌ Bootstrap 未完成")
    
    # 3. 已通知集数
    print("\n【3】已通知集统计...")
    cur.execute("SELECT COUNT(*) FROM anime_notified")
    notified = cur.fetchone()[0]
    print(f"   总数: {notified} 集")
    
    cur.execute("SELECT animeSn, anime_name, COUNT(*) cnt FROM anime_notified GROUP BY animeSn ORDER BY cnt DESC LIMIT 5")
    for row in cur.fetchall():
        print(f"     - {row[1]}: {row[2]} 集")
    
    # 4. 检查频率 - 关键诊断
    print("\n【4】检查频率诊断 (最后48小时)...")
    now = datetime.now(TW_TZ)
    
    # 按日期统计
    cur.execute("""
        SELECT check_date, COUNT(*) cnt 
        FROM anime_check_history 
        WHERE check_date >= date('now', '-2 days')
        GROUP BY check_date 
        ORDER BY check_date DESC
    """)
    
    date_stats = cur.fetchall()
    for check_date, count in date_stats:
        print(f"   [{check_date}]: {count} 次检查")
    
    # 5. 最后一次检查时间
    print("\n【5】最后一次检查记录...")
    cur.execute("SELECT check_date, scheduled_time, checked_at FROM anime_check_history ORDER BY checked_at DESC LIMIT 1")
    last_check = cur.fetchone()
    if last_check:
        check_date, sched_time, checked_at = last_check
        print(f"   时刻: [{check_date} {sched_time}]")
        print(f"   检查于: {checked_at} (UTC)")
        
        # 转换为台湾时间
        dt_utc = datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
        dt_tw = dt_utc.astimezone(TW_TZ)
        print(f"   台湾时间: {dt_tw.strftime('%Y-%m-%d %H:%M:%S')}")
        
        time_diff = (now - dt_tw).total_seconds() / 60
        print(f"   距现在: {time_diff:.0f} 分钟前")
    else:
        print(f"   ❌ 没有检查记录")
    
    # 6. 检查是否有重复
    print("\n【6】检查是否有重复...")
    cur.execute("""
        SELECT check_date, scheduled_time, COUNT(*) cnt 
        FROM anime_check_history 
        GROUP BY check_date, scheduled_time 
        HAVING COUNT(*) > 1
    """)
    duplicates = cur.fetchall()
    if duplicates:
        print(f"   ⚠️ 发现 {len(duplicates)} 个重复时刻:")
        for date, time, cnt in duplicates[:5]:
            print(f"     - [{date} {time}]: {cnt} 次")
    else:
        print(f"   ✅ 没有重复")
    
    # 7. 分析最近3小时的活动
    print("\n【7】最近3小时活动分析...")
    three_hours_ago = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(f"""
        SELECT scheduled_time, COUNT(*) cnt 
        FROM anime_check_history 
        WHERE checked_at >= '{three_hours_ago}'
        GROUP BY scheduled_time
        ORDER BY scheduled_time DESC
    """)
    
    recent = cur.fetchall()
    if recent:
        print(f"   发现 {len(recent)} 个时刻被检查")
        for sched_time, cnt in recent[:10]:
            print(f"     - {sched_time}: {cnt} 次")
    else:
        print(f"   ❌ 最近3小时没有检查活动")
    
    # 8. 消息追踪
    print("\n【8】已发送消息追踪...")
    cur.execute("SELECT COUNT(*) FROM anime_messages")
    msg_count = cur.fetchone()[0]
    print(f"   总数: {msg_count} 条消息")
    
    # 9. 投票统计
    print("\n【9】投票统计...")
    cur.execute("SELECT COUNT(*) FROM anime_votes")
    votes = cur.fetchone()[0]
    print(f"   总投票: {votes} 次")
    
    # 10. API 可达性检查
    print("\n【10】API 可达性...")
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
                        print(f"   ✅ API 可达 (status={resp.status})")
                        
                        # 分析数据结构
                        schedule = data.get("data", {}).get("newAnimeSchedule", {})
                        new_anime = data.get("data", {}).get("newAnime", {})
                        
                        print(f"   日程表: {type(schedule)} with {len(schedule)} 日期")
                        print(f"   最新动画: {type(new_anime)}")
                        
                        if isinstance(new_anime, dict):
                            print(f"     - 键: {list(new_anime.keys())}")
                            if 'date' in new_anime:
                                print(f"     - date 类型: {type(new_anime['date'])}, 长度: {len(new_anime['date'])}")
                        
                        return True
                    else:
                        print(f"   ❌ API 返回状态 {resp.status}")
                        return False
        except Exception as e:
            print(f"   ❌ API 连接失败: {e}")
            return False
    
    api_ok = asyncio.run(check_api())
    
    # 11. 现在时间信息
    print("\n【11】当前时间...")
    print(f"   UTC: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   台湾: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   星期几: {['周一', '周二', '周三', '周四', '周五', '周六', '周日'][now.weekday()]}")
    
    # 12. 问题总结
    print("\n【12】问题总结...")
    
    if last_check:
        check_dt = datetime.fromisoformat(last_check[2].replace('Z', '+00:00')).astimezone(TW_TZ)
        mins_since = (now - check_dt).total_seconds() / 60
        
        if mins_since > 10:
            print(f"   ⚠️ 【推送延迟】最后检查已是 {mins_since:.0f} 分钟前")
            print(f"        - 任务应该每分钟运行一次")
            print(f"        - 现在延迟了 {mins_since:.0f} 分钟")
        
        if len(date_stats) < 2:
            print(f"   ⚠️ 【检查频率低】最近48小时只有 {len(date_stats)} 天的记录")
    
    print(f"\n   ✅ 数据库完整")
    if api_ok:
        print(f"   ✅ API 可达")
    else:
        print(f"   ❌ API 不可达")
    
    print("\n" + "=" * 80)
    conn.close()
    
except Exception as e:
    print(f"\n❌ 诊断错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
