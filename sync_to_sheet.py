import sqlite3
import gspread
import time
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from oauth2client.service_account import ServiceAccountCredentials

# === 配置和日誌設定 ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DCDBSheetSync:
    def __init__(self, credentials_path: str, sheet_url: str, db_path: str):
        self.credentials_path = credentials_path
        self.sheet_url = sheet_url
        self.db_path = db_path
        self.sheet = None
        self._init_google_sheet()
        self._init_database()
    
    def _init_google_sheet(self):
        """初始化 Google Sheet 連接"""
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_path, scope
            )
            client = gspread.authorize(creds)
            self.sheet = client.open_by_url(self.sheet_url).sheet1
            logger.info("Google Sheet 連接成功")
        except Exception as e:
            logger.error(f"Google Sheet 連接失敗: {e}")
            raise
    
    def _init_database(self):
        """初始化資料庫，確保表格存在"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 檢查表格是否存在，如果不存在則創建
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    email TEXT,
                    created_at INTEGER,
                    last_updated INTEGER,
                    status TEXT DEFAULT 'active'
                )
            """)
            
            # 創建同步記錄表
            cursor.execute("""
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
            logger.info("資料庫初始化完成")
        except Exception as e:
            logger.error(f"資料庫初始化失敗: {e}")
            raise
    
    def get_current_timestamp(self) -> int:
        """獲取當前時間戳"""
        return int(time.time())
    
    def get_db_data(self) -> Tuple[List[str], List[Tuple]]:
        """讀取資料庫資料"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]
            conn.close()
            return col_names, rows
        except Exception as e:
            logger.error(f"讀取資料庫失敗: {e}")
            return [], []
    
    def get_sheet_data(self) -> List[Dict]:
        """讀取 Google Sheet 資料"""
        try:
            # 先檢查是否有標題行
            if not self.sheet.get_all_values():
                # 如果 Sheet 是空的，添加標題行
                headers = ['user_id', 'username', 'email', 'created_at', 'last_updated', 'status']
                self.sheet.append_row(headers)
                return []
            
            data = self.sheet.get_all_records()
            # 確保數據類型正確
            for row in data:
                if 'created_at' in row:
                    row['created_at'] = int(row['created_at']) if row['created_at'] else 0
                if 'last_updated' in row:
                    row['last_updated'] = int(row['last_updated']) if row['last_updated'] else 0
            
            return data
        except Exception as e:
            logger.error(f"讀取 Google Sheet 失敗: {e}")
            return []
    
    def log_sync_action(self, direction: str, user_id: str, action: str, details: str = ""):
        """記錄同步操作"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_log (sync_time, direction, user_id, action, details)
                VALUES (?, ?, ?, ?, ?)
            """, (self.get_current_timestamp(), direction, user_id, action, details))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"記錄同步日誌失敗: {e}")
    
    def update_sheet_row(self, user_id: str, data: Dict):
        """更新 Google Sheet 中的特定行"""
        try:
            # 找到對應的行
            cell = self.sheet.find(str(user_id))
            if cell:
                # 獲取標題行來確定列順序
                headers = self.sheet.row_values(1)
                values = [str(data.get(header, '')) for header in headers]
                
                # 更新整行
                range_name = f"A{cell.row}:{chr(65 + len(headers) - 1)}{cell.row}"
                self.sheet.update(range_name, [values])
                return True
        except Exception as e:
            logger.error(f"更新 Sheet 行失敗 (user_id: {user_id}): {e}")
        return False
    
    def add_sheet_row(self, data: Dict):
        """添加新行到 Google Sheet"""
        try:
            headers = self.sheet.row_values(1)
            if not headers:
                # 如果沒有標題行，先添加
                headers = ['user_id', 'username', 'email', 'created_at', 'last_updated', 'status']
                self.sheet.append_row(headers)
            
            values = [str(data.get(header, '')) for header in headers]
            self.sheet.append_row(values)
            return True
        except Exception as e:
            logger.error(f"添加 Sheet 行失敗: {e}")
        return False
    
    def update_db_row(self, data: Dict):
        """更新資料庫中的資料"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 使用 REPLACE INTO 來插入或更新
            columns = list(data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            values = list(data.values())
            
            query = f"REPLACE INTO users ({', '.join(columns)}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"更新資料庫失敗: {e}")
        return False
    
    def sync(self):
        """執行雙向同步"""
        logger.info("開始執行同步...")
        
        try:
            # 獲取兩邊的資料
            col_names, db_rows = self.get_db_data()
            sheet_data = get_sheet_data()
            
            if not col_names:
                logger.warning("資料庫無資料或讀取失敗")
                return
            
            # 轉換為字典格式便於比較
            db_dict = {}
            for row in db_rows:
                user_data = dict(zip(col_names, row))
                db_dict[row[0]] = user_data  # 假設 user_id 在第一欄
            
            sheet_dict = {str(row.get("user_id", "")): row for row in sheet_data if row.get("user_id")}
            
            sync_stats = {
                "db_to_sheet_add": 0,
                "db_to_sheet_update": 0,
                "sheet_to_db_update": 0,
                "conflicts": 0
            }
            
            # 處理資料庫中的每一筆資料
            for user_id, db_row in db_dict.items():
                sheet_row = sheet_dict.get(str(user_id))
                
                if not sheet_row:
                    # Sheet 中沒有這筆資料，從 DB 添加到 Sheet
                    if self.add_sheet_row(db_row):
                        sync_stats["db_to_sheet_add"] += 1
                        self.log_sync_action("DB→Sheet", user_id, "ADD", "新增資料到 Sheet")
                        logger.info(f"🟢 DB → Sheet 新增: {user_id}")
                else:
                    # 比較 last_updated 時間戳
                    db_time = int(db_row.get("last_updated", 0))
                    sheet_time = int(sheet_row.get("last_updated", 0))
                    
                    if db_time > sheet_time:
                        # DB 資料較新，更新到 Sheet
                        if self.update_sheet_row(user_id, db_row):
                            sync_stats["db_to_sheet_update"] += 1
                            self.log_sync_action("DB→Sheet", user_id, "UPDATE", f"DB時間: {db_time}, Sheet時間: {sheet_time}")
                            logger.info(f"🟢 DB → Sheet 更新: {user_id}")
                    elif sheet_time > db_time:
                        # Sheet 資料較新，更新到 DB
                        # 更新 last_updated 時間戳
                        sheet_row["last_updated"] = sheet_time
                        if self.update_db_row(sheet_row):
                            sync_stats["sheet_to_db_update"] += 1
                            self.log_sync_action("Sheet→DB", user_id, "UPDATE", f"Sheet時間: {sheet_time}, DB時間: {db_time}")
                            logger.info(f"🔵 Sheet → DB 更新: {user_id}")
                    elif db_time == sheet_time and db_time > 0:
                        # 時間戳相同，檢查內容是否有差異
                        content_diff = False
                        for key in db_row.keys():
                            if key != "last_updated" and str(db_row.get(key, "")) != str(sheet_row.get(key, "")):
                                content_diff = True
                                break
                        
                        if content_diff:
                            sync_stats["conflicts"] += 1
                            logger.warning(f"⚠️  衝突檢測: {user_id} - 時間戳相同但內容不同")
            
            # 處理只在 Sheet 中存在的資料 (新增到 DB)
            for user_id, sheet_row in sheet_dict.items():
                if user_id not in db_dict:
                    # 設置創建時間和更新時間
                    current_time = self.get_current_timestamp()
                    sheet_row["created_at"] = sheet_row.get("created_at") or current_time
                    sheet_row["last_updated"] = current_time
                    
                    if self.update_db_row(sheet_row):
                        self.log_sync_action("Sheet→DB", user_id, "ADD", "從 Sheet 新增到 DB")
                        logger.info(f"🔵 Sheet → DB 新增: {user_id}")
            
            # 輸出同步統計
            logger.info("=" * 50)
            logger.info("同步完成統計:")
            logger.info(f"  DB → Sheet 新增: {sync_stats['db_to_sheet_add']} 筆")
            logger.info(f"  DB → Sheet 更新: {sync_stats['db_to_sheet_update']} 筆") 
            logger.info(f"  Sheet → DB 更新: {sync_stats['sheet_to_db_update']} 筆")
            logger.info(f"  衝突檢測: {sync_stats['conflicts']} 筆")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"同步過程發生錯誤: {e}")
            raise
    
    def force_db_to_sheet(self):
        """強制將資料庫資料覆蓋到 Sheet (慎用)"""
        logger.info("執行強制 DB → Sheet 同步...")
        
        col_names, db_rows = self.get_db_data()
        if not col_names:
            logger.warning("資料庫無資料")
            return
        
        # 清空 Sheet 並重新寫入
        self.sheet.clear()
        
        # 寫入標題行
        self.sheet.append_row(col_names)
        
        # 寫入資料行
        for row in db_rows:
            self.sheet.append_row([str(cell) for cell in row])
        
        logger.info(f"強制同步完成，共寫入 {len(db_rows)} 筆資料")
    
    def get_sync_history(self, limit: int = 50) -> List[Tuple]:
        """獲取同步歷史記錄"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sync_time, direction, user_id, action, details
                FROM sync_log 
                ORDER BY sync_time DESC 
                LIMIT ?
            """, (limit,))
            history = cursor.fetchall()
            conn.close()
            return history
        except Exception as e:
            logger.error(f"獲取同步歷史失敗: {e}")
            return []

# === 使用範例 ===
def main():
    # 配置參數
    CREDENTIALS_PATH = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_PATH = "user_data.db"
    
    try:
        # 創建同步器實例
        syncer = DCDBSheetSync(CREDENTIALS_PATH, SHEET_URL, DB_PATH)
        
        # 執行同步
        syncer.sync()
        
        # 可選：查看同步歷史
        history = syncer.get_sync_history(10)
        if history:
            print("\n最近同步記錄:")
            for record in history:
                timestamp = datetime.fromtimestamp(record[0]).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  {timestamp} - {record[1]} - {record[2]} - {record[3]}")
                
    except Exception as e:
        logger.error(f"程式執行失敗: {e}")

if __name__ == "__main__":
    main()
