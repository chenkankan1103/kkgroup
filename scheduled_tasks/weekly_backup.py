#!/usr/bin/env python3
"""
weekly_backup.py - 每週自動備份 DB 至本機
執行方式: cd /home/e193752468/kkgroup && venv/bin/python scheduled_tasks/weekly_backup.py
排程: crontab -e  →  0 3 * * 1 cd /home/e193752468/kkgroup && venv/bin/python scheduled_tasks/weekly_backup.py >> /home/e193752468/kkgroup/logs/weekly_backup.log 2>&1
"""

import os
import shutil
from datetime import datetime

DB_PATH = "/home/e193752468/kkgroup/user_data.db"
BACKUP_DIR = "/home/e193752468/kkgroup/backups"
MAX_LOCAL_BACKUPS = 8  # 保留最近 8 週


def backup_local():
    """備份 DB 至本機 backups/ 資料夾"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"user_data_weekly_{ts}.db")
    shutil.copy2(DB_PATH, dest)
    size = os.path.getsize(dest)
    print(f"[LOCAL] ✅ 備份至 {dest} ({size/1024:.1f}KB)")

    # 清理舊備份，只保留最近 N 個
    backups = sorted(
        [
            os.path.join(BACKUP_DIR, f)
            for f in os.listdir(BACKUP_DIR)
            if f.startswith("user_data_weekly_") and f.endswith(".db")
        ]
    )
    while len(backups) > MAX_LOCAL_BACKUPS:
        old = backups.pop(0)
        os.remove(old)
        print(f"[LOCAL] 🗑️  清除舊備份: {old}")
    return dest


def main():
    print(f'\n{"="*50}')
    print(f'🗄️  每週備份開始 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"="*50}')

    if not os.path.exists(DB_PATH):
        print(f"❌ DB 不存在: {DB_PATH}")
        return

    db_size = os.path.getsize(DB_PATH)
    print(f"DB 大小: {db_size/1024:.1f}KB")

    # 本機備份
    backup_local()

    print(f'\n✅ 備份完成 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')


if __name__ == "__main__":
    main()
