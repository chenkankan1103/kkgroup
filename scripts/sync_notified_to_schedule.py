#!/usr/bin/env python3
"""
scripts/sync_notified_to_schedule.py

簡單腳本：將 anime_notified 中已通知的 videoSn 同步到 anime_weekly_schedule，
把對應的時段標記為 pushed=1，避免補推機制重複推送已通知集數。

用法：
  - 直接執行（需設定 ANIME_DB_PATH 或在當前目錄有 anime.db）
  - 指定 --db /path/to/anime.db

範例：
  ANIME_DB_PATH=/home/ubuntu/kkgroup/data/anime.db python3 scripts/sync_notified_to_schedule.py
  python3 scripts/sync_notified_to_schedule.py --db /home/ubuntu/kkgroup/data/anime.db

此腳本為一次性修正工具，安全且幂等（可重覆執行）。
"""

import os
import sqlite3
import argparse
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

DEFAULT_DB_NAMES = [
    'anime.db',
    'anime.sqlite',
    'kkgroup_anime.db'
]


def find_default_db():
    # 優先檢查環境變數
    env_path = os.getenv('ANIME_DB_PATH') or os.getenv('ANIME_DB')
    if env_path and os.path.exists(env_path):
        return env_path

    # 嘗試當前目錄中的常見檔名
    for name in DEFAULT_DB_NAMES:
        candidate = os.path.join(os.getcwd(), name)
        if os.path.exists(candidate):
            return candidate

    return None


def sync_notified_to_schedule(db_path: str, week_start_date: str = None) -> int:
    """將 anime_notified 裡的 videoSn 同步到 anime_weekly_schedule 的 pushed=1

    Args:
        db_path: SQLite DB path
        week_start_date: optional, 只同步指定週（格式 YYYY-MM-DD），None 表示全庫同步

    Returns:
        int: 標記的行數
    """
    if not os.path.exists(db_path):
        logger.error(f"DB not found: {db_path}")
        return 0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT videoSn FROM anime_notified")
        rows = [r[0] for r in cursor.fetchall() if r[0] is not None]
        if not rows:
            logger.info("No videoSn found in anime_notified. Nothing to do.")
            return 0

        # Prepare placeholders and params
        placeholders = ','.join('?' * len(rows))
        params = list(rows)

        if week_start_date:
            sql = f"""
                UPDATE anime_weekly_schedule
                SET pushed = 1
                WHERE weekStartDate = ?
                AND CAST(json_extract(animeData, '$.videoSn') AS INTEGER) IN ({placeholders})
            """
            params = [week_start_date] + params
        else:
            sql = f"""
                UPDATE anime_weekly_schedule
                SET pushed = 1
                WHERE CAST(json_extract(animeData, '$.videoSn') AS INTEGER) IN ({placeholders})
            """

        cursor.execute(sql, params)
        updated = cursor.rowcount
        conn.commit()
        logger.info(f"Marked {updated} schedule rows as pushed (db={db_path})")
        return updated

    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 0
    finally:
        try:
            conn.close()
        except:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sync anime_notified -> anime_weekly_schedule (mark pushed)')
    parser.add_argument('--db', '-d', help='Path to SQLite DB')
    parser.add_argument('--week', '-w', help='Optional weekStartDate to limit sync (YYYY-MM-DD)')
    args = parser.parse_args()

    db = args.db or find_default_db()
    if not db:
        logger.error('Could not find DB. Set ANIME_DB_PATH env or pass --db')
        raise SystemExit(1)

    start = datetime.now()
    logger.info(f"Starting sync at {start.isoformat()} -> db={db} week={args.week}")
    updated = sync_notified_to_schedule(db, args.week)
    logger.info(f"Done. Updated {updated} rows in {datetime.now()-start}")
