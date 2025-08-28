import sqlite3
import gspread
import time
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from oauth2client.service_account import ServiceAccountCredentials

# === 雙向同步完整版本 ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bidirectional_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BidirectionalDBSheetSync:
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
        """初始化資料庫"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
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
        return int(time.time())
    
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
    
    def get_db_data(self) -> Tuple[List[str], List[Tuple]]:
        """讀取資料庫資料"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY user_id")
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]
            conn.close()
            
            logger.debug(f"DB 資料讀取成功: {len(rows)} 筆資料")
            return col_names, rows
        except Exception as e:
            logger.error(f"讀取資料庫失敗: {e}")
            return [], []
    
    def get_sheet_data(self) -> List[Dict]:
        """讀取 Google Sheet 資料"""
        try:
            all_values = self.sheet.get_all_values()
            logger.debug(f"Sheet 原始資料: {all_values}")
            
            if not all_values or len(all_values) < 2:
                logger.warning("Sheet 沒有資料或只有標題行")
                return []
            
            headers = all_values[0]
            logger.debug(f"Sheet 標題行: {headers}")
            
            data = []
            for i, row in enumerate(all_values[1:], start=2):
                if not any(cell.strip() for cell in row):  # 跳過空行
                    continue
                    
                row_dict = {}
                for j, header in enumerate(headers):
                    value = row[j] if j < len(row) else ""
                    
                    # 特殊處理數字欄位
                    if header in ['created_at', 'last_updated'] and value:
                        try:
                            row_dict[header] = int(float(value))
                        except (ValueError, TypeError):
                            row_dict[header] = 0
                            logger.warning(f"無法轉換時間戳 {header}: {value} (第{i}行)")
                    else:
                        row_dict[header] = str(value).strip()
                
                # 只添加有 user_id 的行
                if row_dict.get('user_id'):
                    data.append(row_dict)
                    logger.debug(f"Sheet 第{i}行資料: {row_dict}")
                else:
                    logger.warning(f"第{i}行缺少 user_id，跳過")
            
            logger.info(f"Sheet 有效資料: {len(data)} 筆")
            return data
            
        except Exception as e:
            logger.error(f"讀取 Google Sheet 失敗: {e}")
            return []
    
    def update_db_row(self, data: Dict) -> bool:
        """更新資料庫"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 確保必要欄位存在
            required_fields = ['user_id', 'username', 'email', 'created_at', 'last_updated', 'status']
            processed_data = {}
            
            for field in required_fields:
                if field in data:
                    processed_data[field] = data[field]
                elif field == 'status':
                    processed_data[field] = 'active'
                elif field in ['created_at', 'last_updated']:
                    processed_data[field] = data.get(field, self.get_current_timestamp())
                else:
                    processed_data[field] = data.get(field, '')
            
            logger.debug(f"準備更新 DB 的資料: {processed_data}")
            
            columns = list(processed_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            values = list(processed_data.values())
            
            query = f"INSERT OR REPLACE INTO users ({', '.join(columns)}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            conn.close()
            
            logger.info(f"✅ 成功更新 DB: {processed_data['user_id']}")
            return True
                
        except Exception as e:
            logger.error(f"更新資料庫失敗 (user_id: {data.get('user_id', 'unknown')}): {e}")
            return False
    
    def update_sheet_row(self, data: Dict, row_index: int = None) -> bool:
        """更新 Google Sheet 中的單行資料"""
        try:
            # 確保必要欄位存在
            required_fields = ['user_id', 'username', 'email', 'created_at', 'last_updated', 'status']
            
            # 獲取表頭
            headers = self.sheet.row_values(1)
            if not headers:
                logger.error("無法獲取 Sheet 表頭")
                return False
            
            # 準備要更新的資料
            row_data = []
            for header in headers:
                if header in data:
                    if header in ['created_at', 'last_updated']:
                        # 時間戳保持為數字格式
                        row_data.append(str(data[header]))
                    else:
                        row_data.append(str(data[header]))
                else:
                    row_data.append('')
            
            if row_index is None:
                # 新增行：找到第一個空行或附加到末尾
                all_values = self.sheet.get_all_values()
                row_index = len(all_values) + 1
                logger.debug(f"新增資料到第 {row_index} 行")
            else:
                logger.debug(f"更新第 {row_index} 行資料")
            
            # 更新整行
            range_name = f"A{row_index}:{chr(ord('A') + len(row_data) - 1)}{row_index}"
            self.sheet.update(range_name, [row_data])
            
            logger.info(f"✅ 成功更新 Sheet: {data.get('user_id', 'unknown')} (第{row_index}行)")
            return True
            
        except Exception as e:
            logger.error(f"更新 Sheet 失敗 (user_id: {data.get('user_id', 'unknown')}): {e}")
            return False
    
    def find_sheet_row_by_user_id(self, user_id: str) -> Optional[int]:
        """根據 user_id 找到在 Sheet 中的行號"""
        try:
            all_values = self.sheet.get_all_values()
            if not all_values:
                return None
            
            headers = all_values[0]
            user_id_col = None
            
            # 找到 user_id 欄位的索引
            for i, header in enumerate(headers):
                if header == 'user_id':
                    user_id_col = i
                    break
            
            if user_id_col is None:
                logger.error("Sheet 中找不到 user_id 欄位")
                return None
            
            # 查找對應的行
            for i, row in enumerate(all_values[1:], start=2):  # 從第2行開始
                if i - 2 < len(all_values) - 1 and user_id_col < len(row):
                    if str(row[user_id_col]).strip() == str(user_id).strip():
                        logger.debug(f"找到 user_id {user_id} 在第 {i} 行")
                        return i
            
            logger.debug(f"未找到 user_id {user_id} 對應的行")
            return None
            
        except Exception as e:
            logger.error(f"查找 Sheet 行號失敗: {e}")
            return None
    
    def bidirectional_sync(self):
        """雙向同步：DB ↔ Sheet"""
        logger.info("🔄 開始雙向同步...")
        
        try:
            # 1. 獲取資料
            col_names, db_rows = self.get_db_data()
            sheet_data = self.get_sheet_data()
            
            logger.info(f"📊 資料統計:")
            logger.info(f"  DB 資料筆數: {len(db_rows)}")
            logger.info(f"  Sheet 資料筆數: {len(sheet_data)}")
            
            # 2. 轉換格式
            db_dict = {}
            for row in db_rows:
                user_data = dict(zip(col_names, row))
                db_dict[str(row[0])] = user_data
            
            sheet_dict = {}
            for row in sheet_data:
                user_id = str(row.get("user_id", ""))
                if user_id:
                    sheet_dict[user_id] = row
            
            # 3. 統計變數
            sheet_to_db_updates = 0
            db_to_sheet_updates = 0
            new_in_sheet = 0
            new_in_db = 0
            
            # 4. Sheet → DB 同步
            logger.info("📥 Sheet → DB 同步開始...")
            for user_id, sheet_row in sheet_dict.items():
                db_row = db_dict.get(user_id)
                
                if not db_row:
                    # Sheet 中的新資料
                    logger.info(f"🆕 Sheet 中發現新資料: {user_id}")
                    sheet_row['created_at'] = sheet_row.get('created_at') or self.get_current_timestamp()
                    sheet_row['last_updated'] = self.get_current_timestamp()
                    
                    if self.update_db_row(sheet_row):
                        new_in_sheet += 1
                        self.log_sync_action("Sheet→DB", user_id, "INSERT", "新資料從 Sheet 加入 DB")
                else:
                    # 比較更新時間
                    sheet_time = int(sheet_row.get('last_updated', 0))
                    db_time = int(db_row.get('last_updated', 0))
                    
                    if sheet_time > db_time:
                        logger.info(f"⏰ Sheet 資料較新，更新到 DB: {user_id}")
                        if self.update_db_row(sheet_row):
                            sheet_to_db_updates += 1
                            self.log_sync_action("Sheet→DB", user_id, "UPDATE", 
                                               f"Sheet時間: {sheet_time}, DB時間: {db_time}")
            
            # 5. DB → Sheet 同步
            logger.info("📤 DB → Sheet 同步開始...")
            for user_id, db_row in db_dict.items():
                sheet_row = sheet_dict.get(user_id)
                
                if not sheet_row:
                    # DB 中的新資料
                    logger.info(f"🆕 DB 中發現新資料: {user_id}")
                    db_row['last_updated'] = self.get_current_timestamp()
                    
                    # 更新 DB 中的時間戳
                    self.update_db_row(db_row)
                    
                    if self.update_sheet_row(db_row):
                        new_in_db += 1
                        self.log_sync_action("DB→Sheet", user_id, "INSERT", "新資料從 DB 加入 Sheet")
                else:
                    # 比較更新時間
                    db_time = int(db_row.get('last_updated', 0))
                    sheet_time = int(sheet_row.get('last_updated', 0))
                    
                    if db_time > sheet_time:
                        logger.info(f"⏰ DB 資料較新，更新到 Sheet: {user_id}")
                        
                        # 找到 Sheet 中對應的行號
                        sheet_row_index = self.find_sheet_row_by_user_id(user_id)
                        
                        if self.update_sheet_row(db_row, sheet_row_index):
                            db_to_sheet_updates += 1
                            self.log_sync_action("DB→Sheet", user_id, "UPDATE", 
                                               f"DB時間: {db_time}, Sheet時間: {sheet_time}")
            
            # 6. 同步結果統計
            logger.info("=" * 60)
            logger.info("🎯 雙向同步完成!")
            logger.info(f"   📥 Sheet → DB:")
            logger.info(f"      新增: {new_in_sheet} 筆")
            logger.info(f"      更新: {sheet_to_db_updates} 筆")
            logger.info(f"   📤 DB → Sheet:")
            logger.info(f"      新增: {new_in_db} 筆") 
            logger.info(f"      更新: {db_to_sheet_updates} 筆")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"雙向同步失敗: {e}")
            raise
    
    def manual_add_to_db(self, user_data: Dict):
        """手動添加資料到資料庫"""
        logger.info(f"🔧 手動添加資料到 DB: {user_data}")
        
        # 自動設置時間戳
        current_time = self.get_current_timestamp()
        user_data['created_at'] = user_data.get('created_at', current_time)
        user_data['last_updated'] = current_time
        user_data['status'] = user_data.get('status', 'active')
        
        if self.update_db_row(user_data):
            logger.info(f"✅ 手動添加成功: {user_data.get('user_id')}")
            self.log_sync_action("MANUAL", user_data.get('user_id', 'unknown'), "INSERT", "手動添加到 DB")
            return True
        else:
            logger.error(f"❌ 手動添加失敗: {user_data.get('user_id')}")
            return False
    
    def manual_add_to_sheet(self, user_data: Dict):
        """手動添加資料到 Sheet"""
        logger.info(f"🔧 手動添加資料到 Sheet: {user_data}")
        
        # 自動設置時間戳
        current_time = self.get_current_timestamp()
        user_data['created_at'] = user_data.get('created_at', current_time)
        user_data['last_updated'] = current_time
        user_data['status'] = user_data.get('status', 'active')
        
        if self.update_sheet_row(user_data):
            logger.info(f"✅ 手動添加到 Sheet 成功: {user_data.get('user_id')}")
            self.log_sync_action("MANUAL", user_data.get('user_id', 'unknown'), "INSERT", "手動添加到 Sheet")
            return True
        else:
            logger.error(f"❌ 手動添加到 Sheet 失敗: {user_data.get('user_id')}")
            return False


# === 使用方法 ===
def main():
    CREDENTIALS_PATH = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_PATH = "user_data.db"
    
    try:
        syncer = BidirectionalDBSheetSync(CREDENTIALS_PATH, SHEET_URL, DB_PATH)
        
        print("選擇操作模式:")
        print("1. 雙向同步 (推薦)")
        print("2. 手動添加測試資料到 DB")
        print("3. 手動添加測試資料到 Sheet")
        print("4. 只執行一次同步")
        
        choice = input("請輸入選項 (1-4): ").strip()
        
        if choice == "1":
            # 持續同步模式
            while True:
                syncer.bidirectional_sync()
                print("等待 30 秒後進行下次同步... (Ctrl+C 停止)")
                time.sleep(30)
                
        elif choice == "2":
            # 手動添加測試資料到 DB
            test_data = {
                "user_id": f"test_db_{int(time.time())}",
                "username": "測試用戶DB",
                "email": "test_db@example.com",
                "status": "active"
            }
            syncer.manual_add_to_db(test_data)
            print("已添加測試資料到 DB，請選擇選項1進行同步")
            
        elif choice == "3":
            # 手動添加測試資料到 Sheet
            test_data = {
                "user_id": f"test_sheet_{int(time.time())}",
                "username": "測試用戶Sheet", 
                "email": "test_sheet@example.com",
                "status": "active"
            }
            syncer.manual_add_to_sheet(test_data)
            print("已添加測試資料到 Sheet，請選擇選項1進行同步")
            
        elif choice == "4":
            syncer.bidirectional_sync()
            
        else:
            syncer.bidirectional_sync()
            
    except KeyboardInterrupt:
        logger.info("用戶中止同步")
    except Exception as e:
        logger.error(f"程式執行失敗: {e}")

if __name__ == "__main__":
    main()
