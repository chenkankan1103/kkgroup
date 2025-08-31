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
LOG_PATH = os.path.join(BASE_DIR, "game_sync.log")

logger = logging.getLogger("game_sync")
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
    """解析日期時間為時間戳"""
    if value is None or value == "" or value == "0":
        return 0

    try:
        f = float(str(value).strip())
        if 20000 <= f <= 60000:
            base = datetime(1899, 12, 30)
            dt = base + timedelta(days=f)
            return int(dt.timestamp())
        if f > 10**12:
            return int(f / 1000)
        if f > 10**9:
            return int(f)
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
        return ""
    try:
        return datetime.fromtimestamp(int(ts)).isoformat()
    except Exception:
        return ""


class GameUserSync:
    def __init__(self, credentials_path: str, sheet_url: str, db_path: str):
        self.credentials_path = os.path.join(BASE_DIR, credentials_path)
        self.sheet_url = sheet_url
        self.db_path = os.path.join(BASE_DIR, db_path)
        self.sheet = None
        
        # 定義遊戲用戶資料的欄位結構
        self.game_fields = [
            "user_id",
            "level", 
            "xp",
            "kkcoin",
            "title",
            "hp",
            "stamina",
            "inventory",
            "character_config",
            "face",
            "hair",
            "skin",
            "top",
            "bottom",
            "shoes",
            "streak",
            "last_work_date",
            "last_action_date", 
            "actions_used",
            "gender",
            "is_stunned",
            "is_locked",
            "last_recovery",
            "sync_flag"  # 同步控制欄位
        ]
        
        # 定義需要特殊處理的欄位
        self.date_fields = ["last_work_date", "last_action_date", "last_recovery"]
        self.json_fields = ["inventory", "character_config"]  # JSON 字串欄位
        self.boolean_fields = ["is_stunned", "is_locked"]  # 布林值欄位
        self.numeric_fields = ["level", "xp", "kkcoin", "hp", "stamina", "actions_used", "streak"]
        
        self._init_google_sheet()
        self._init_database()

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
            
            # 檢查並確保表頭完整
            headers = self.sheet.row_values(1) if self.sheet.get_all_values() else []
            if not headers:
                self.sheet.update("A1", [self.game_fields])
                logger.info("Sheet 空白，已建立遊戲用戶資料表頭")
            elif "sync_flag" not in headers:
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
            
            # 建立遊戲用戶表
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS game_users (
                    user_id TEXT PRIMARY KEY,
                    level INTEGER DEFAULT 1,
                    xp INTEGER DEFAULT 0,
                    kkcoin INTEGER DEFAULT 0,
                    title TEXT DEFAULT '',
                    hp INTEGER DEFAULT 100,
                    stamina INTEGER DEFAULT 100,
                    inventory TEXT DEFAULT '{{}}',
                    character_config TEXT DEFAULT '{{}}',
                    face TEXT DEFAULT '',
                    hair TEXT DEFAULT '',
                    skin TEXT DEFAULT '',
                    top TEXT DEFAULT '',
                    bottom TEXT DEFAULT '',
                    shoes TEXT DEFAULT '',
                    streak INTEGER DEFAULT 0,
                    last_work_date INTEGER DEFAULT 0,
                    last_action_date INTEGER DEFAULT 0,
                    actions_used INTEGER DEFAULT 0,
                    gender TEXT DEFAULT '',
                    is_stunned INTEGER DEFAULT 0,
                    is_locked INTEGER DEFAULT 0,
                    last_recovery INTEGER DEFAULT 0,
                    sync_flag TEXT DEFAULT 'N'
                )
            """)
            
            # 檢查並新增缺少的欄位
            cur.execute("PRAGMA table_info(game_users)")
            existing_columns = [row[1] for row in cur.fetchall()]
            
            for field in self.game_fields:
                if field not in existing_columns:
                    if field in self.numeric_fields:
                        cur.execute(f"ALTER TABLE game_users ADD COLUMN {field} INTEGER DEFAULT 0")
                    elif field in self.boolean_fields:
                        cur.execute(f"ALTER TABLE game_users ADD COLUMN {field} INTEGER DEFAULT 0")
                    else:
                        cur.execute(f"ALTER TABLE game_users ADD COLUMN {field} TEXT DEFAULT ''")
                    logger.info(f"已在 DB 加入欄位: {field}")
            
            # 同步歷史表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_time INTEGER,
                    direction TEXT,
                    user_id TEXT,
                    action TEXT,
                    details TEXT
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("遊戲用戶資料庫初始化完成")
            
        except Exception as e:
            logger.error(f"資料庫初始化失敗: {e}")
            raise

    def _now_ts(self) -> int:
        return int(time.time())

    def _convert_value_for_db(self, field: str, value) -> any:
        """轉換 Sheet 值為 DB 格式"""
        if field in self.date_fields:
            return parse_datetime_to_timestamp(value)
        elif field in self.boolean_fields:
            if isinstance(value, str):
                return 1 if value.lower() in ('true', '1', 'yes', 'y') else 0
            return 1 if value else 0
        elif field in self.numeric_fields:
            try:
                return int(float(str(value) or 0))
            except:
                return 0
        else:
            return str(value) if value is not None else ""

    def _convert_value_for_sheet(self, field: str, value) -> str:
        """轉換 DB 值為 Sheet 格式"""
        if field in self.date_fields:
            return timestamp_to_iso_string(value) if value else ""
        elif field in self.boolean_fields:
            return "TRUE" if value else "FALSE"
        else:
            return str(value) if value is not None else ""

    # -------------------------
    # 資料操作方法
    # -------------------------
    def get_db_data(self) -> Tuple[List[str], List[Tuple]]:
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT * FROM game_users")
            rows = cur.fetchall()
            col_names = [d[0] for d in cur.description]
            conn.close()
            return col_names, rows
        except Exception as e:
            logger.error(f"讀取 DB 失敗: {e}")
            return [], []

    def update_db_row(self, data: Dict) -> bool:
        try:
            # 轉換資料格式
            converted_data = {}
            for field in self.game_fields:
                if field in data:
                    converted_data[field] = self._convert_value_for_db(field, data[field])
                elif field == "sync_flag":
                    converted_data[field] = "N"
            
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cols = list(converted_data.keys())
            placeholders = ", ".join(["?"] * len(cols))
            q = f"REPLACE INTO game_users ({', '.join(cols)}) VALUES ({placeholders})"
            cur.execute(q, [converted_data[c] for c in cols])
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"更新 DB 失敗: {e}")
            return False

    def get_sheet_data(self) -> List[Dict]:
        try:
            all_values = self.sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                return []
            
            headers = all_values[0]
            data: List[Dict] = []
            
            for r_idx, row in enumerate(all_values[1:], start=2):
                if not any(str(c).strip() for c in row):
                    continue
                    
                item: Dict = {}
                for j, h in enumerate(headers):
                    val = row[j] if j < len(row) else ""
                    item[h] = str(val).strip()
                
                # 確保有 user_id
                if item.get("user_id"):
                    # 設定預設值
                    if not item.get("sync_flag"):
                        item["sync_flag"] = "N"
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
            for cell in cells:
                if cell.row > 1 and cell.col == 1:
                    return cell.row
            return None
        except Exception as e:
            logger.error(f"查找 Sheet 行號失敗 (user_id={user_id}): {e}")
            return None

    def log_sync_action(self, direction: str, user_id: str, action: str, details: str = ""):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sync_log (sync_time, direction, user_id, action, details) VALUES (?, ?, ?, ?, ?)",
                (self._now_ts(), direction, user_id, action, details)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"寫入 sync_log 失敗: {e}")

    # -------------------------
    # 基於標記的同步邏輯
    # -------------------------
    def flag_based_sync(self):
        """基於 sync_flag 標記的遊戲用戶資料同步"""
        logger.info("🚩 開始遊戲用戶資料同步")
        
        try:
            cols, db_rows = self.get_db_data()
            sheet_rows = self.get_sheet_data()

            logger.info(f"DB 筆數: {len(db_rows)} | Sheet 筆數: {len(sheet_rows)}")

            # 轉換為字典格式
            db_dict: Dict[str, Dict] = {}
            for r in db_rows:
                d = dict(zip(cols, r))
                db_dict[str(d["user_id"])] = d

            sheet_dict: Dict[str, Dict] = {}
            for d in sheet_rows:
                sheet_dict[str(d["user_id"])] = d

            stats = {
                "sheet_to_db": 0,
                "db_to_sheet": 0,
                "flags_reset": 0,
            }

            headers = self.sheet.row_values(1)

            # ===== Sheet → DB 同步 =====
            logger.info("📥 處理 Sheet → DB (sync_flag = 'Y')")
            sheet_updates_to_reset = []

            for uid, srow in sheet_dict.items():
                if str(srow.get("sync_flag", "")).upper() == "Y":
                    logger.info(f"同步 Sheet → DB: {uid}")
                    
                    if self.update_db_row(srow):
                        stats["sheet_to_db"] += 1
                        self.log_sync_action("Sheet→DB", uid, "SYNC", "遊戲資料同步")
                        
                        row_index = self.find_sheet_row_by_user_id(uid)
                        if row_index:
                            sheet_updates_to_reset.append((row_index, uid))

            # ===== DB → Sheet 同步 =====
            logger.info("📤 處理 DB → Sheet (sync_flag = 'Y')")
            
            batch_updates = []
            batch_appends = []

            def to_sheet_row_values(row_dict: Dict) -> List[str]:
                out: List[str] = []
                for h in headers:
                    if h in row_dict:
                        out.append(self._convert_value_for_sheet(h, row_dict[h]))
                    else:
                        out.append("")
                return out

            for uid, drow in db_dict.items():
                if str(drow.get("sync_flag", "")).upper() == "Y":
                    logger.info(f"同步 DB → Sheet: {uid}")
                    
                    # 重設標記
                    drow_copy = drow.copy()
                    drow_copy["sync_flag"] = "N"
                    self.update_db_row(drow_copy)
                    
                    srow = sheet_dict.get(uid)
                    row_vals = to_sheet_row_values(drow_copy)
                    
                    if not srow:
                        batch_appends.append(row_vals)
                        stats["db_to_sheet"] += 1
                        self.log_sync_action("DB→Sheet", uid, "INSERT", "新增遊戲用戶")
                    else:
                        row_index = self.find_sheet_row_by_user_id(uid)
                        if row_index:
                            batch_updates.append((row_index, row_vals))
                            stats["db_to_sheet"] += 1
                            self.log_sync_action("DB→Sheet", uid, "UPDATE", "更新遊戲用戶")

            # ===== 批次寫入 Sheet =====
            # 重設 Sheet 中的標記
            if sheet_updates_to_reset:
                for row_index, uid in sheet_updates_to_reset:
                    srow = sheet_dict[uid].copy()
                    srow["sync_flag"] = "N"
                    row_vals = to_sheet_row_values(srow)
                    batch_updates.append((row_index, row_vals))
                    stats["flags_reset"] += 1

            # 執行批次更新
            if batch_updates:
                logger.info(f"批次更新 Sheet：{len(batch_updates)} 行")
                self._batch_update_sheet(batch_updates)

            # 執行批次新增
            if batch_appends:
                logger.info(f"批次新增 Sheet：{len(batch_appends)} 行")
                self._batch_append_sheet(batch_appends, headers)

            # 統計輸出
            logger.info("=" * 60)
            logger.info("🎯 遊戲用戶資料同步完成")
            logger.info(f"   Sheet → DB: {stats['sheet_to_db']} 筆")
            logger.info(f"   DB → Sheet: {stats['db_to_sheet']} 筆") 
            logger.info(f"   標記重設: {stats['flags_reset']} 筆")
            logger.info("=" * 60)

        except Exception as e:
            logger.exception(f"同步失敗: {e}")
            raise

    def _batch_update_sheet(self, updates: List[Tuple[int, List[str]]]):
        """批次更新 Sheet"""
        try:
            ranges = []
            for row_index, row_vals in updates:
                rng = f"A{row_index}:{rowcol_to_a1(row_index, len(row_vals))}"
                ranges.append({"range": rng, "values": [row_vals]})
            
            self.sheet.spreadsheet.values_batch_update({
                "value_input_option": "RAW",
                "data": ranges,
            })
            logger.info(f"批次更新成功：{len(updates)} 行")
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"批次更新失敗: {e}")
            # 降級為單行更新
            for row_index, row_vals in updates:
                try:
                    rng = f"A{row_index}:{rowcol_to_a1(row_index, len(row_vals))}"
                    self.sheet.update(rng, [row_vals])
                    time.sleep(0.1)
                except Exception as single_e:
                    logger.error(f"單行更新失敗 (行 {row_index}): {single_e}")

    def _batch_append_sheet(self, appends: List[List[str]], headers: List[str]):
        """批次新增到 Sheet"""
        try:
            current_all_values = self.sheet.get_all_values()
            start_row = len(current_all_values) + 1
            end_row = start_row + len(appends) - 1
            rng = f"A{start_row}:{rowcol_to_a1(end_row, len(headers))}"
            self.sheet.update(rng, appends)
            logger.info(f"批次新增成功：{len(appends)} 行")
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"批次新增失敗: {e}")
            # 降級為單行新增
            for row_vals in appends:
                try:
                    current_all_values = self.sheet.get_all_values()
                    next_row = len(current_all_values) + 1
                    rng = f"A{next_row}:{rowcol_to_a1(next_row, len(row_vals))}"
                    self.sheet.update(rng, [row_vals])
                    time.sleep(0.1)
                except Exception as single_e:
                    logger.error(f"單行新增失敗: {single_e}")

    # -------------------------
    # 調試與工具方法
    # -------------------------
    def debug_sync_flags(self):
        """檢查同步標記狀態"""
        logger.info("🔍 檢查遊戲用戶同步標記狀態")
        
        try:
            cols, db_rows = self.get_db_data()
            sheet_rows = self.get_sheet_data()
            
            db_dict = {str(dict(zip(cols, r))["user_id"]): dict(zip(cols, r)) for r in db_rows}
            sheet_dict = {str(d["user_id"]): d for d in sheet_rows}
            
            print(f"\n=== 遊戲用戶同步狀態報告 ===")
            print(f"DB 總數: {len(db_dict)}")
            print(f"Sheet 總數: {len(sheet_dict)}")
            
            # 檢查待同步的記錄
            db_y_flags = [uid for uid, d in db_dict.items() if str(d.get("sync_flag", "")).upper() == "Y"]
            sheet_y_flags = [uid for uid, d in sheet_dict.items() if str(d.get("sync_flag", "")).upper() == "Y"]
            
            if db_y_flags:
                print(f"\nDB 中標記為 'Y' 的記錄: {db_y_flags}")
            if sheet_y_flags:
                print(f"Sheet 中標記為 'Y' 的記錄: {sheet_y_flags}")
                
            if not db_y_flags and not sheet_y_flags:
                print("\n✅ 沒有發現需要同步的標記")
                
        except Exception as e:
            logger.error(f"檢查失敗: {e}")

    def get_sync_history(self, limit: int = 10) -> List[Tuple]:
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT sync_time, direction, user_id, action, details FROM sync_log ORDER BY sync_time DESC LIMIT ?",
                (limit,)
            )
            rows = cur.fetchall()
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"讀取 sync_log 失敗: {e}")
            return []


def main():
    # 設定你的檔案路徑
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_FILE = "game_users.db"

    syncer = GameUserSync(CREDENTIALS_JSON, SHEET_URL, DB_FILE)
    
    # 檢查同步標記狀態
    syncer.debug_sync_flags()
    
    # 執行同步
    syncer.flag_based_sync()

    # 查看同步歷史
    hist = syncer.get_sync_history(5)
    if hist:
        print("\n最近同步記錄：")
        for t, d, u, a, msg in hist:
            ts = datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  {ts} - {d} - {u} - {a} - {msg}")


if __name__ == "__main__":
    main()
