#!/usr/bin/env python3
"""
weekly_backup.py - 每週自動備份 DB 至本機 + Google Sheets
執行方式: venv/bin/python weekly_backup.py
排程: crontab -e  →  0 3 * * 1 cd /home/e193752468/kkgroup && venv/bin/python weekly_backup.py >> /tmp/weekly_backup.log 2>&1
"""

import os
import shutil
import sqlite3
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

DB_PATH = "/home/e193752468/kkgroup/user_data.db"
BACKUP_DIR = "/home/e193752468/kkgroup/backups"
SHEET_ID = "1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM"
CREDS_PATH = "/home/e193752468/kkgroup/google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
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


def backup_to_sheets(db_path):
    """將 DB 用戶資料備份至 Google Sheets 的「DB備份」分頁"""
    try:
        creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(SHEET_ID)

        # 找或建立「DB備份」分頁
        backup_sheet_name = "DB備份"
        try:
            ws = spreadsheet.worksheet(backup_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=backup_sheet_name, rows=5000, cols=30)
            print(f"[SHEETS] 建立新分頁: {backup_sheet_name}")

        # 讀取 DB 全部用戶資料
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM users").fetchall()
        if not rows:
            print("[SHEETS] ⚠️  DB 無資料，跳過 Sheets 備份")
            conn.close()
            return

        cols = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
        conn.close()

        # 組合寫入內容（標題列 + 時間戳 + 資料）
        ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = [f"備份時間: {ts_str}"] + [""] * (len(cols) - 1)
        col_row = cols
        data_rows = []
        for row in rows:
            d = dict(row)
            data_rows.append([str(d.get(c, "") or "") for c in cols])

        # 清空並重寫（避免累積垃圾資料）
        ws.clear()
        all_data = [header, col_row] + data_rows
        ws.update("A1", all_data, value_input_option="RAW")

        print(f"[SHEETS] ✅ 已寫入 {len(data_rows)} 筆用戶資料 → {backup_sheet_name}")
        print(f"[SHEETS]    欄位數: {len(cols)}, 試算表: {spreadsheet.title}")

    except Exception as e:
        print(f"[SHEETS] ❌ 備份失敗: {e}")
        import traceback

        traceback.print_exc()


def main():
    print(f'\n{"="*50}')
    print(f'🗄️  每週備份開始 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"="*50}')

    if not os.path.exists(DB_PATH):
        print(f"❌ DB 不存在: {DB_PATH}")
        return

    db_size = os.path.getsize(DB_PATH)
    print(f"DB 大小: {db_size/1024:.1f}KB")

    # 1. 本機備份
    dest = backup_local()

    # 2. Sheets 備份
    if os.path.exists(CREDS_PATH):
        backup_to_sheets(DB_PATH)
    else:
        print(f"[SHEETS] ⚠️  找不到 credentials: {CREDS_PATH}，跳過 Sheets 備份")

    print(f'\n✅ 備份完成 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')


if __name__ == "__main__":
    main()
