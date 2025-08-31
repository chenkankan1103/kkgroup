#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

import gspread
from gspread.utils import rowcol_to_a1
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# 日誌設定：輪轉檔案 5MB x 3
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "sync.log")

logger = logging.getLogger("sync")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3)
fh.setFormatter(fmt)
sh = logging.StreamHandler()
sh.setFormatter(fmt)

# 避免重複加 handler
if not logger.handlers:
    logger.addHandler(fh)
    logger.addHandler(sh)


def parse_datetime_to_timestamp(value) -> int:
    """
    將各種日期格式轉 Unix timestamp（秒）。
    支援：
      - Unix 秒/毫秒（字串或數字）
      - ISO 與常見格式：2025-06-04T02:33:44、2025/06/04 02:33:44、2025-06-04 ...
      - Google Sheet/Excel 浮點日期（以 1899-12-30 為基準日）
    """
    if value is None or value == "":
        return 0

    # 已是數字或數字字串
    try:
        f = float(str(value).strip())
        # 可能是 Excel serial date（通常介於 2 萬到 6 萬）
        if 20000 <= f <= 60000:
            base = datetime(1899, 12, 30)  # Excel 起算日
            dt = base + timedelta(days=f)
            return int(dt.timestamp())
        # 可能是 Unix 毫秒
        if f > 10**12:
            return int(f / 1000)
        # 其餘視為 Unix 秒
        if f > 10**9:  # 大約 2001 年之後
            return int(f)
    except Exception:
        pass

    s = str(value).strip()

    patterns = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for p in patterns:
        try:
            dt = datetime.strptime(s, p)
            return int(dt.timestamp())
        except ValueError:
            continue

    logger.warning(f"[parse_datetime] 無法解析日期格式: '{value}'，以 0 代替")
    return 0


def timestamp_to_iso_string(ts: int) -> str:
    if not ts or ts <= 0:
        return datetime.now().isoformat()
    try:
        return datetime.fromtimestamp(int(ts)).isoformat()
    except Exception:
        return datetime.now().isoformat()


class DCDBSheetSync:
    def __init__(self, credentials_path: str, sheet_url: str, db_path: str):
        self.credentials_path = os.path.join(BASE_DIR, credentials_path)
        self.sheet_url = sheet_url
        self.db_path = os.path.join(BASE_DIR, db_path)
        self.sheet = None
        self._init_google_sheet()
        self._init_database()

    # -------------------------
    # 基礎初始化
    # -------------------------
    def _init_google_sheet(self):
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_path, scope
            )
            client = gspread.authorize(creds)
            self.sheet = client.open_by_url(self.sheet_url).sheet1
            logger.info("Google Sheet 連線成功")
            # 確保表頭存在
            if not self.sheet.get_all_values():
                headers = [
                    "user_id",
                    "username",
                    "email",
                    "created_at",
                    "last_updated",
                    "status",
                ]
                self.sheet.update("A1", [headers])
                logger.info("Sheet 空白，已建立標題列")
        except Exception as e:
            logger.error(f"Google Sheet 連接失敗: {e}")
            raise

    def _init_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            # users 表
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    email TEXT,
                    created_at INTEGER,
                    last_updated INTEGER,
                    status TEXT DEFAULT 'active'
                )
                """
            )
            # 同步歷史
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_time INTEGER,
                    direction TEXT,
                    user_id TEXT,
                    action TEXT,
                    details TEXT
                )
                """
            )
            conn.commit()
            conn.close()
            logger.info("資料庫初始化完成")
        except Exception as e:
            logger.error(f"資料庫初始化失敗: {e}")
            raise

    def _now_ts(self) -> int:
        return int(time.time())

    # -------------------------
    # 讀寫：DB
    # -------------------------
    def get_db_data(self) -> Tuple[List[str], List[Tuple]]:
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT * FROM users")
            rows = cur.fetchall()
            col_names = [d[0] for d in cur.description]
            conn.close()
            return col_names, rows
        except Exception as e:
            logger.error(f"讀取 DB 失敗: {e}")
            return [], []

    def update_db_row(self, data: Dict) -> bool:
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cols = list(data.keys())
            placeholders = ", ".join(["?"] * len(cols))
            q = f"REPLACE INTO users ({', '.join(cols)}) VALUES ({placeholders})"
            cur.execute(q, [data[c] for c in cols])
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"更新 DB 失敗: {e}")
            return False

    def log_sync_action(self, direction: str, user_id: str, action: str, details: str = ""):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO sync_log (sync_time, direction, user_id, action, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self._now_ts(), direction, user_id, action, details),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"寫入 sync_log 失敗: {e}")

    def get_sync_history(self, limit: int = 50) -> List[Tuple]:
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT sync_time, direction, user_id, action, details
                FROM sync_log
                ORDER BY sync_time DESC LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"讀取 sync_log 失敗: {e}")
            return []

    # -------------------------
    # 讀寫：Sheet
    # -------------------------
    def get_sheet_headers(self) -> List[str]:
        headers = self.sheet.row_values(1)
        if not headers:
            headers = [
                "user_id",
                "username",
                "email",
                "created_at",
                "last_updated",
                "status",
            ]
            self.sheet.update("A1", [headers])
        return headers

    def get_sheet_data(self) -> List[Dict]:
        try:
            all_values = self.sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                return []
            headers = all_values[0]
            data: List[Dict] = []
            for r_idx, row in enumerate(all_values[1:], start=2):
                # 跳過空白行
                if not any(str(c).strip() for c in row):
                    continue
                item: Dict = {}
                for j, h in enumerate(headers):
                    val = row[j] if j < len(row) else ""
                    if h in ("created_at", "last_updated"):
                        item[h] = parse_datetime_to_timestamp(val)
                    else:
                        item[h] = str(val).strip()
                if item.get("user_id"):
                    data.append(item)
                else:
                    logger.warning(f"第 {r_idx} 行缺少 user_id，已跳過")
            return data
        except Exception as e:
            logger.error(f"讀取 Sheet 失敗: {e}")
            return []

    def find_sheet_row_by_user_id(self, user_id: str) -> Optional[int]:
        try:
            cell = self.sheet.find(str(user_id))
            return cell.row if cell else None
        except Exception:
            return None

    def update_sheet_row(self, data: Dict, row_index: Optional[int] = None) -> bool:
        """
        更新/新增單行（會將 created_at / last_updated 轉為 ISO 字串寫入）
        提醒：大量寫入建議改用 batch 更新（本檔也有提供）。
        """
        try:
            headers = self.get_sheet_headers()
            row_data: List[str] = []
            for h in headers:
                if h in data:
                    if h in ("created_at", "last_updated"):
                        row_data.append(timestamp_to_iso_string(data[h]))
                    else:
                        row_data.append(str(data[h]))
                else:
                    row_data.append("")

            if row_index is None:
                # append
                rng = f"A{len(self.sheet.get_all_values()) + 1}:{rowcol_to_a1(1, len(row_data)).replace('1', str(len(self.sheet.get_all_values()) + 1))}"
            else:
                rng = f"A{row_index}:{rowcol_to_a1(row_index, len(row_data))}"

            self.sheet.update(rng, [row_data])
            time.sleep(0.1)  # 降低配額壓力
            return True
        except Exception as e:
            logger.error(f"更新 Sheet 失敗 (user_id={data.get('user_id')}): {e}")
            return False

    # -------------------------
    # 同步邏輯
    # -------------------------
    def bidirectional_sync(self):
        logger.info("🔄 開始雙向同步")
        try:
            cols, db_rows = self.get_db_data()
            sheet_rows = self.get_sheet_data()

            logger.info(f"DB 筆數: {len(db_rows)} | Sheet 筆數: {len(sheet_rows)}")

            # 轉換 DB → dict
            db_dict: Dict[str, Dict] = {}
            for r in db_rows:
                d = dict(zip(cols, r))
                # 確保整數型時間
                d["created_at"] = int(d.get("created_at") or 0)
                d["last_updated"] = int(d.get("last_updated") or 0)
                db_dict[str(d["user_id"])] = d

            # 轉換 Sheet → dict
            sheet_dict: Dict[str, Dict] = {}
            for d in sheet_rows:
                sheet_dict[str(d["user_id"])] = d

            # 統計與批次暫存
            sheet_updates_batch: List[Tuple[int, List[str]]] = []  # (row_index, row_values)
            sheet_appends_batch: List[List[str]] = []

            stats = {
                "sheet_to_db_insert": 0,
                "sheet_to_db_update": 0,
                "db_to_sheet_insert": 0,
                "db_to_sheet_update": 0,
            }

            headers = self.get_sheet_headers()

            # ===== Sheet → DB =====
            logger.info("📥 Sheet → DB 同步中...")
            for uid, srow in sheet_dict.items():
                drow = db_dict.get(uid)
                if not drow:
                    # 新增到 DB
                    if not srow.get("created_at"):
                        srow["created_at"] = self._now_ts()
                    if not srow.get("last_updated"):
                        srow["last_updated"] = self._now_ts()
                    if self.update_db_row(srow):
                        db_dict[uid] = srow
                        stats["sheet_to_db_insert"] += 1
                        self.log_sync_action("Sheet→DB", uid, "INSERT", "Sheet 新增到 DB")
                else:
                    st = int(srow.get("last_updated") or 0)
                    dt = int(drow.get("last_updated") or 0)
                    if st > dt:
                        # Sheet 比較新 → 覆寫 DB
                        if self.update_db_row(srow):
                            db_dict[uid] = srow
                            stats["sheet_to_db_update"] += 1
                            self.log_sync_action("Sheet→DB", uid, "UPDATE", f"Sheet:{st} > DB:{dt}")

            # ===== DB → Sheet =====
            logger.info("📤 DB → Sheet 同步中...")
            all_values_count = len(self.sheet.get_all_values())
            next_append_row = max(all_values_count, 1) + 1  # 目前最後一列之後

            for uid, drow in db_dict.items():
                srow = sheet_dict.get(uid)
                if not drow.get("last_updated"):
                    drow["last_updated"] = self._now_ts()
                    self.update_db_row(drow)

                # 轉出寫入 Sheet 的列資料（ISO 字串）
                def to_sheet_row_values(row_dict: Dict) -> List[str]:
                    out: List[str] = []
                    for h in headers:
                        if h in ("created_at", "last_updated"):
                            out.append(timestamp_to_iso_string(row_dict.get(h) or 0))
                        else:
                            out.append(str(row_dict.get(h, "")))
                    return out

                if not srow:
                    # 需要插入
                    row_vals = to_sheet_row_values(drow)
                    sheet_appends_batch.append(row_vals)
                    stats["db_to_sheet_insert"] += 1
                    self.log_sync_action("DB→Sheet", uid, "INSERT", "DB 新增到 Sheet")
                else:
                    dt = int(drow.get("last_updated") or 0)
                    st = int(srow.get("last_updated") or 0)
                    if dt > st:
                        row_index = self.find_sheet_row_by_user_id(uid)
                        if row_index:
                            row_vals = to_sheet_row_values(drow)
                            sheet_updates_batch.append((row_index, row_vals))
                            stats["db_to_sheet_update"] += 1
                            self.log_sync_action("DB→Sheet", uid, "UPDATE", f"DB:{dt} > Sheet:{st}")

            # ===== 批次寫入 Sheet（合併請求，降低配額）=====
            # 批次更新（現有行）
            if sheet_updates_batch:
                logger.info(f"批次更新現有行：{len(sheet_updates_batch)}")
                data = []
                ranges = []
                for row_index, row_vals in sheet_updates_batch:
                    rng = f"A{row_index}:{rowcol_to_a1(row_index, len(row_vals))}"
                    ranges.append({"range": rng, "values": [row_vals]})
                # 使用 batch_update
                self.sheet.spreadsheet.values_batch_update(
                    {
                        "value_input_option": "RAW",
                        "data": ranges,
                    }
                )
                time.sleep(0.2)

            # 批次新增（尾端追加）
            if sheet_appends_batch:
                logger.info(f"批次新增新行：{len(sheet_appends_batch)}")
                start_row = len(self.sheet.get_all_values()) + 1
                end_row = start_row + len(sheet_appends_batch) - 1
                rng = f"A{start_row}:{rowcol_to_a1(end_row, len(headers))}"
                self.sheet.update(rng, sheet_appends_batch)
                time.sleep(0.2)

            # ===== 統計輸出 =====
            logger.info("=" * 60)
            logger.info("🎯 雙向同步完成")
            logger.info(f"   Sheet → DB  新增: {stats['sheet_to_db_insert']}  更新: {stats['sheet_to_db_update']}")
            logger.info(f"   DB → Sheet  新增: {stats['db_to_sheet_insert']}  更新: {stats['db_to_sheet_update']}")
            logger.info("=" * 60)

        except Exception as e:
            logger.exception(f"雙向同步失敗: {e}")
            raise

    def force_db_to_sheet(self):
        """
        慎用：清空 Sheet，完全以 DB 覆蓋（單向寫入，最省配額）
        """
        logger.info("⚠️ 開始強制 DB → Sheet（清空重寫）")
        cols, rows = self.get_db_data()
        if not cols:
            logger.warning("DB 沒資料或讀取失敗")
            return

        headers = self.get_sheet_headers()
        # 重新鋪資料（一次性大範圍 update）
        values = [headers]
        for r in rows:
            d = dict(zip(cols, r))
            values.append(
                [
                    str(d.get("user_id", "")),
                    str(d.get("username", "")),
                    str(d.get("email", "")),
                    timestamp_to_iso_string(d.get("created_at") or 0),
                    timestamp_to_iso_string(d.get("last_updated") or 0),
                    str(d.get("status", "")),
                ]
            )

        end_row = len(values)
        end_col = len(headers)
        rng = f"A1:{rowcol_to_a1(end_row, end_col)}"
        self.sheet.clear()
        self.sheet.update(rng, values)
        logger.info(f"已重寫 {end_row-1} 筆資料到 Sheet")


def main():
    # === 依你的實際檔名/URL 調整 ===
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_FILE = "user_data.db"

    syncer = DCDBSheetSync(CREDENTIALS_JSON, SHEET_URL, DB_FILE)
    # 常用：雙向同步
    syncer.bidirectional_sync()

    # 若你想看最近歷史：
    hist = syncer.get_sync_history(10)
    if hist:
        print("\n最近同步記錄：")
        for t, d, u, a, msg in hist:
            ts = datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  {ts} - {d} - {u} - {a} - {msg}")


if __name__ == "__main__":
    main()
