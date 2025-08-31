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
    if value is None or value == "" or value == "0":
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
        # 小於合理範圍的數字
        if f <= 0:
            return 0
    except Exception:
        pass

    s = str(value).strip()
    if not s or s == "0":
        return 0

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
            # 確保表頭存在（加入 sync_flag 欄位）
            if not self.sheet.get_all_values():
                headers = [
                    "user_id",
                    "username", 
                    "email",
                    "created_at",
                    "last_updated",
                    "status",
                    "sync_flag"  # 新增：同步標記欄位
                ]
                self.sheet.update("A1", [headers])
                logger.info("Sheet 空白，已建立標題列（含 sync_flag）")
            else:
                # 檢查是否需要加入 sync_flag 欄
                headers = self.sheet.row_values(1)
                if "sync_flag" not in headers:
                    headers.append("sync_flag")
                    self.sheet.update("A1", [headers])
                    logger.info("已在現有 Sheet 加入 sync_flag 欄位")
        except Exception as e:
            logger.error(f"Google Sheet 連接失敗: {e}")
            raise

    def _init_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            # users 表（加入 sync_flag 欄位）
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    email TEXT,
                    created_at INTEGER,
                    last_updated INTEGER,
                    status TEXT DEFAULT 'active',
                    sync_flag TEXT DEFAULT 'N'
                )
                """
            )
            
            # 檢查並新增 sync_flag 欄位（如果不存在）
            cur.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cur.fetchall()]
            if 'sync_flag' not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN sync_flag TEXT DEFAULT 'N'")
                logger.info("已在 DB users 表加入 sync_flag 欄位")
            
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
            # 確保必要欄位有預設值
            if not data.get("created_at"):
                data["created_at"] = self._now_ts()
            if not data.get("last_updated"):
                data["last_updated"] = self._now_ts()
            if not data.get("status"):
                data["status"] = "active"
            if not data.get("sync_flag"):
                data["sync_flag"] = "N"
                
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

    def reset_db_sync_flags(self) -> int:
        """重設 DB 中所有記錄的 sync_flag 為 'N'"""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("UPDATE users SET sync_flag = 'N' WHERE sync_flag != 'N'")
            count = cur.rowcount
            conn.commit()
            conn.close()
            return count
        except Exception as e:
            logger.error(f"重設 DB sync_flag 失敗: {e}")
            return 0

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
                "sync_flag"
            ]
            self.sheet.update("A1", [headers])
        elif "sync_flag" not in headers:
            headers.append("sync_flag")
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
                
                # 確保必要欄位有預設值
                if not item.get("created_at"):
                    item["created_at"] = 0
                if not item.get("last_updated"):
                    item["last_updated"] = 0
                if not item.get("status"):
                    item["status"] = "active"
                if not item.get("sync_flag"):
                    item["sync_flag"] = "N"
                    
                if item.get("user_id"):
                    data.append(item)
                else:
                    logger.warning(f"第 {r_idx} 行缺少 user_id，已跳過")
            return data
        except Exception as e:
            logger.error(f"讀取 Sheet 失敗: {e}")
            return []

    def find_sheet_row_by_user_id(self, user_id: str) -> Optional[int]:
        """找到 user_id 對應的 Sheet 行號"""
        try:
            cells = self.sheet.findall(str(user_id))
            if not cells:
                return None
            
            for cell in cells:
                if cell.row > 1 and cell.col == 1:  # 跳過標題行，確認在 A 欄
                    return cell.row
            return None
        except Exception as e:
            logger.error(f"查找 Sheet 行號失敗 (user_id={user_id}): {e}")
            return None

    def update_sheet_row(self, data: Dict, row_index: Optional[int] = None) -> bool:
        """更新/新增單行"""
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
                all_values = self.sheet.get_all_values()
                next_row = len(all_values) + 1
                rng = f"A{next_row}:{rowcol_to_a1(next_row, len(row_data))}"
            else:
                rng = f"A{row_index}:{rowcol_to_a1(row_index, len(row_data))}"

            self.sheet.update(rng, [row_data])
            time.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"更新 Sheet 失敗 (user_id={data.get('user_id')}): {e}")
            return False

    def reset_sheet_sync_flags(self) -> int:
        """重設 Sheet 中所有記錄的 sync_flag 為 'N'"""
        try:
            headers = self.get_sheet_headers()
            if "sync_flag" not in headers:
                return 0
                
            sync_flag_col = headers.index("sync_flag") + 1  # gspread 使用 1-based 索引
            all_values = self.sheet.get_all_values()
            
            # 批次更新所有 sync_flag 欄位
            updates = []
            for row_idx in range(2, len(all_values) + 1):  # 從第2行開始
                updates.append({
                    "range": f"{rowcol_to_a1(row_idx, sync_flag_col)}",
                    "values": [["N"]]
                })
            
            if updates:
                self.sheet.spreadsheet.values_batch_update({
                    "value_input_option": "RAW",
                    "data": updates
                })
                logger.info(f"已重設 Sheet 中 {len(updates)} 行的 sync_flag 為 'N'")
                return len(updates)
            return 0
        except Exception as e:
            logger.error(f"重設 Sheet sync_flag 失敗: {e}")
            return 0

    # -------------------------
    # 基於標記的同步邏輯
    # -------------------------
    def flag_based_sync(self):
        """基於 sync_flag 標記的同步邏輯"""
        logger.info("🚩 開始基於標記的同步")
        try:
            cols, db_rows = self.get_db_data()
            sheet_rows = self.get_sheet_data()

            logger.info(f"DB 筆數: {len(db_rows)} | Sheet 筆數: {len(sheet_rows)}")

            # 轉換為字典格式
            db_dict: Dict[str, Dict] = {}
            for r in db_rows:
                d = dict(zip(cols, r))
                d["created_at"] = int(d.get("created_at") or 0)
                d["last_updated"] = int(d.get("last_updated") or 0)
                if not d["created_at"]:
                    d["created_at"] = self._now_ts()
                if not d["last_updated"]:
                    d["last_updated"] = self._now_ts()
                if not d.get("sync_flag"):
                    d["sync_flag"] = "N"
                db_dict[str(d["user_id"])] = d

            sheet_dict: Dict[str, Dict] = {}
            for d in sheet_rows:
                sheet_dict[str(d["user_id"])] = d

            # 統計
            stats = {
                "sheet_to_db": 0,
                "db_to_sheet": 0,
                "flags_reset": 0,
            }

            headers = self.get_sheet_headers()

            # ===== 第一階段：處理 Sheet 中標記為 'Y' 的記錄 =====
            logger.info("📥 處理 Sheet → DB (sync_flag = 'Y')")
            sheet_updates_to_reset = []  # 需要重設標記的 Sheet 行
            
            for uid, srow in sheet_dict.items():
                if str(srow.get("sync_flag", "")).upper() == "Y":
                    logger.info(f"發現 Sheet 標記同步: {uid}")
                    
                    # 同步到 DB
                    srow_copy = srow.copy()
                    srow_copy["last_updated"] = self._now_ts()
                    srow_copy["sync_flag"] = "N"  # 重設標記
                    
                    if self.update_db_row(srow_copy):
                        db_dict[uid] = srow_copy
                        stats["sheet_to_db"] += 1
                        self.log_sync_action("Sheet→DB", uid, "SYNC", "基於 sync_flag=Y 同步")
                        
                        # 記錄需要重設 Sheet 標記的行
                        row_index = self.find_sheet_row_by_user_id(uid)
                        if row_index:
                            sheet_updates_to_reset.append((row_index, uid))

            # ===== 第二階段：處理 DB 中標記為 'Y' 的記錄 =====
            logger.info("📤 處理 DB → Sheet (sync_flag = 'Y')")
            
            # 建立 user_id 到行號的映射
            user_id_to_row = {}
            all_values = self.sheet.get_all_values()
            for row_idx, row in enumerate(all_values[1:], start=2):
                if row and len(row) > 0 and row[0].strip():
                    user_id_to_row[str(row[0]).strip()] = row_idx

            # 轉出寫入 Sheet 的列資料
            def to_sheet_row_values(row_dict: Dict) -> List[str]:
                out: List[str] = []
                for h in headers:
                    if h in ("created_at", "last_updated"):
                        out.append(timestamp_to_iso_string(row_dict.get(h) or 0))
                    else:
                        out.append(str(row_dict.get(h, "")))
                return out

            batch_updates = []  # 批次更新
            batch_appends = []  # 批次新增

            for uid, drow in db_dict.items():
                if str(drow.get("sync_flag", "")).upper() == "Y":
                    logger.info(f"發現 DB 標記同步: {uid}")
                    
                    # 準備同步到 Sheet 的資料
                    drow_copy = drow.copy()
                    drow_copy["last_updated"] = self._now_ts()
                    drow_copy["sync_flag"] = "N"  # 重設標記
                    
                    # 先更新 DB 中的標記
                    self.update_db_row(drow_copy)
                    db_dict[uid] = drow_copy
                    
                    srow = sheet_dict.get(uid)
                    row_vals = to_sheet_row_values(drow_copy)
                    
                    if not srow:
                        # 新增到 Sheet
                        batch_appends.append(row_vals)
                        stats["db_to_sheet"] += 1
                        self.log_sync_action("DB→Sheet", uid, "INSERT", "基於 sync_flag=Y 新增")
                    else:
                        # 更新 Sheet 現有行
                        row_index = user_id_to_row.get(uid)
                        if row_index:
                            batch_updates.append((row_index, row_vals))
                            stats["db_to_sheet"] += 1
                            self.log_sync_action("DB→Sheet", uid, "UPDATE", "基於 sync_flag=Y 更新")

            # ===== 第三階段：批次寫入 Sheet =====
            # 處理更新
            if batch_updates or sheet_updates_to_reset:
                all_updates = []
                
                # 加入需要重設標記的更新
                for row_index, uid in sheet_updates_to_reset:
                    srow = sheet_dict[uid]
                    srow["sync_flag"] = "N"
                    row_vals = to_sheet_row_values(srow)
                    all_updates.append((row_index, row_vals))
                    stats["flags_reset"] += 1
                
                # 加入 DB→Sheet 的更新
                all_updates.extend(batch_updates)
                
                if all_updates:
                    logger.info(f"批次更新 Sheet：{len(all_updates)} 行")
                    try:
                        ranges = []
                        for row_index, row_vals in all_updates:
                            rng = f"A{row_index}:{rowcol_to_a1(row_index, len(row_vals))}"
                            ranges.append({"range": rng, "values": [row_vals]})
                        
                        self.sheet.spreadsheet.values_batch_update({
                            "value_input_option": "RAW",
                            "data": ranges,
                        })
                        logger.info(f"批次更新成功：{len(all_updates)} 行")
                        time.sleep(0.3)
                    except Exception as e:
                logger.error(f"設定 Sheet sync_flag 失敗: {e}")

    def reset_all_sync_flags(self):
        """重設所有同步標記為 'N'"""
        logger.info("🔄 重設所有同步標記")
        
        db_count = self.reset_db_sync_flags()
        sheet_count = self.reset_sheet_sync_flags()
        
        logger.info(f"已重設 DB: {db_count} 筆, Sheet: {sheet_count} 筆")
        return db_count + sheet_count

    # -------------------------
    # 相容性方法（保留舊版同步）
    # -------------------------
    def bidirectional_sync(self):
        """原有的雙向同步（基於時間戳），現在建議使用 flag_based_sync()"""
        logger.warning("⚠️ 使用舊版時間戳同步，建議改用 flag_based_sync()")
        # 這裡可以保留原來的實現，或者直接調用新版
        self.flag_based_sync()


# -------------------------
# 測試與便利函數
# -------------------------
def test_flag_sync():
    """測試基於標記的同步功能"""
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_FILE = "user_data.db"
    
    syncer = DCDBSheetSync(CREDENTIALS_JSON, SHEET_URL, DB_FILE)
    
    # 檢查當前標記狀態
    syncer.debug_sync_flags()
    
    # 新增一個測試記錄到 DB 並標記為需要同步
    test_data = {
        "user_id": "test_flag_123",
        "username": "標記測試用戶",
        "email": "test_flag@example.com",
        "created_at": int(time.time()) - 3600,
        "last_updated": int(time.time()),
        "status": "active",
        "sync_flag": "Y"  # 標記需要同步
    }
    
    print(f"\n插入測試資料到 DB 並標記同步: {test_data}")
    syncer.update_db_row(test_data)
    
    # 也可以測試設定現有記錄的標記
    # syncer.set_test_sync_flags(["existing_user_id"], "db")
    
    # 執行基於標記的同步
    print("\n執行基於標記的同步...")
    syncer.flag_based_sync()
    
    # 再次檢查標記狀態
    print("\n同步後檢查:")
    syncer.debug_sync_flags()


def reset_all_flags():
    """重設所有同步標記的便利函數"""
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_FILE = "user_data.db"
    
    syncer = DCDBSheetSync(CREDENTIALS_JSON, SHEET_URL, DB_FILE)
    syncer.reset_all_sync_flags()


def main():
    # === 依你的實際檔名/URL 調整 ===
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_FILE = "user_data.db"

    syncer = DCDBSheetSync(CREDENTIALS_JSON, SHEET_URL, DB_FILE)
    
    # 檢查同步標記狀態
    syncer.debug_sync_flags()
    
    # 執行基於標記的同步（推薦）
    syncer.flag_based_sync()

    # 查看最近同步記錄
    hist = syncer.get_sync_history(10)
    if hist:
        print("\n最近同步記錄：")
        for t, d, u, a, msg in hist:
            ts = datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  {ts} - {d} - {u} - {a} - {msg}")


if __name__ == "__main__":
    # 選擇要執行的功能
    # test_flag_sync()      # 測試標記同步
    # reset_all_flags()     # 重設所有標記
    main()                  # 正常執行同步 as e:
                        logger.error(f"批次更新失敗: {e}")
                        # 降級為單行更新
                        for row_index, row_vals in all_updates:
                            try:
                                rng = f"A{row_index}:{rowcol_to_a1(row_index, len(row_vals))}"
                                self.sheet.update(rng, [row_vals])
                                time.sleep(0.1)
                            except Exception as single_e:
                                logger.error(f"單行更新失敗 (行 {row_index}): {single_e}")

            # 處理新增
            if batch_appends:
                logger.info(f"批次新增 Sheet：{len(batch_appends)} 行")
                try:
                    current_all_values = self.sheet.get_all_values()
                    start_row = len(current_all_values) + 1
                    end_row = start_row + len(batch_appends) - 1
                    rng = f"A{start_row}:{rowcol_to_a1(end_row, len(headers))}"
                    self.sheet.update(rng, batch_appends)
                    logger.info(f"批次新增成功：{len(batch_appends)} 行")
                    time.sleep(0.3)
                except Exception as e:
                    logger.error(f"批次新增失敗: {e}")
                    # 降級為單行新增
                    for row_vals in batch_appends:
                        try:
                            current_all_values = self.sheet.get_all_values()
                            next_row = len(current_all_values) + 1
                            rng = f"A{next_row}:{rowcol_to_a1(next_row, len(row_vals))}"
                            self.sheet.update(rng, [row_vals])
                            time.sleep(0.1)
                        except Exception as single_e:
                            logger.error(f"單行新增失敗: {single_e}")

            # ===== 統計輸出 =====
            logger.info("=" * 60)
            logger.info("🎯 基於標記的同步完成")
            logger.info(f"   Sheet → DB: {stats['sheet_to_db']} 筆")
            logger.info(f"   DB → Sheet: {stats['db_to_sheet']} 筆")
            logger.info(f"   標記重設: {stats['flags_reset']} 筆")
            logger.info("=" * 60)

        except Exception as e:
            logger.exception(f"基於標記的同步失敗: {e}")
            raise

    # -------------------------
    # 調試與工具方法
    # -------------------------
    def debug_sync_flags(self):
        """調試：檢查同步標記狀態"""
        logger.info("🔍 檢查同步標記狀態")
        
        try:
            cols, db_rows = self.get_db_data()
            sheet_rows = self.get_sheet_data()
            
            db_dict = {}
            for r in db_rows:
                d = dict(zip(cols, r))
                db_dict[str(d["user_id"])] = d
            
            sheet_dict = {str(d["user_id"]): d for d in sheet_rows}
            
            print("\n=== 同步標記狀態報告 ===")
            print(f"DB 總數: {len(db_dict)}")
            print(f"Sheet 總數: {len(sheet_dict)}")
            
            # 檢查 DB 中的 Y 標記
            db_y_flags = [uid for uid, d in db_dict.items() if str(d.get("sync_flag", "")).upper() == "Y"]
            if db_y_flags:
                print(f"\nDB 中標記為 'Y' 的記錄: {db_y_flags}")
            
            # 檢查 Sheet 中的 Y 標記
            sheet_y_flags = [uid for uid, d in sheet_dict.items() if str(d.get("sync_flag", "")).upper() == "Y"]
            if sheet_y_flags:
                print(f"\nSheet 中標記為 'Y' 的記錄: {sheet_y_flags}")
                
            if not db_y_flags and not sheet_y_flags:
                print("\n✅ 沒有發現需要同步的標記 (sync_flag='Y')")
                
        except Exception as e:
            logger.error(f"檢查同步標記失敗: {e}")
            print(f"檢查同步標記失敗: {e}")

    def set_test_sync_flags(self, user_ids: List[str], location: str = "db"):
        """測試用：設定指定 user_id 的 sync_flag 為 'Y'"""
        logger.info(f"🧪 設定測試同步標記: {user_ids} (位置: {location})")
        
        if location.lower() == "db":
            try:
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                for uid in user_ids:
                    cur.execute(
                        "UPDATE users SET sync_flag = 'Y', last_updated = ? WHERE user_id = ?",
                        (self._now_ts(), uid)
                    )
                    if cur.rowcount > 0:
                        logger.info(f"DB 中設定 {uid} sync_flag = 'Y'")
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"設定 DB sync_flag 失敗: {e}")
        
        elif location.lower() == "sheet":
            try:
                headers = self.get_sheet_headers()
                if "sync_flag" in headers:
                    sync_flag_col = headers.index("sync_flag") + 1
                    for uid in user_ids:
                        row_index = self.find_sheet_row_by_user_id(uid)
                        if row_index:
                            self.sheet.update(
                                f"{rowcol_to_a1(row_index, sync_flag_col)}",
                                "Y"
                            )
                            logger.info(f"Sheet 中設定 {uid} sync_flag = 'Y'")
                            time.sleep(0.1)
            except Exception
