import sqlite3
import gspread
import time
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from oauth2client.service_account import ServiceAccountCredentials

# === 詳細調試版本 ===
logging.basicConfig(
    level=logging.DEBUG,  # 設為 DEBUG 級別
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DCDBSheetSyncDebug:
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
            logger.debug(f"DB 欄位: {col_names}")
            
            return col_names, rows
        except Exception as e:
            logger.error(f"讀取資料庫失敗: {e}")
            return [], []
    
    def get_sheet_data(self) -> List[Dict]:
        """讀取 Google Sheet 資料 (增強調試)"""
        try:
            # 獲取所有數值
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
                            row_dict[header] = int(float(value))  # 處理可能的浮點數
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
        """更新資料庫 (增強調試)"""
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
                    processed_data[field] = 'active'  # 預設值
                elif field in ['created_at', 'last_updated']:
                    processed_data[field] = data.get(field, self.get_current_timestamp())
                else:
                    processed_data[field] = data.get(field, '')
            
            logger.debug(f"準備更新 DB 的資料: {processed_data}")
            
            # 使用 INSERT OR REPLACE
            columns = list(processed_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            values = list(processed_data.values())
            
            query = f"INSERT OR REPLACE INTO users ({', '.join(columns)}) VALUES ({placeholders})"
            logger.debug(f"執行 SQL: {query}")
            logger.debug(f"參數: {values}")
            
            cursor.execute(query, values)
            conn.commit()
            
            # 驗證是否成功寫入
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (processed_data['user_id'],))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                logger.info(f"✅ 成功更新 DB: {processed_data['user_id']}")
                return True
            else:
                logger.error(f"❌ DB 更新失敗，找不到記錄: {processed_data['user_id']}")
                return False
                
        except Exception as e:
            logger.error(f"更新資料庫失敗 (user_id: {data.get('user_id', 'unknown')}): {e}")
            return False
    
    def sync_debug(self):
        """調試版同步方法"""
        logger.info("🔍 開始調試同步...")
        
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
                logger.debug(f"DB 資料 {row[0]}: {user_data}")
            
            sheet_dict = {}
            for row in sheet_data:
                user_id = str(row.get("user_id", ""))
                if user_id:
                    sheet_dict[user_id] = row
                    logger.debug(f"Sheet 資料 {user_id}: {row}")
            
            logger.info(f"🔄 開始比較和同步...")
            
            # 3. Sheet → DB 同步 (重點關注)
            sheet_to_db_updates = 0
            for user_id, sheet_row in sheet_dict.items():
                logger.info(f"--- 處理 Sheet 中的 {user_id} ---")
                
                db_row = db_dict.get(user_id)
                
                if not db_row:
                    # Sheet 中的新資料，加到 DB
                    logger.info(f"🆕 Sheet 中發現新資料: {user_id}")
                    sheet_row['created_at'] = sheet_row.get('created_at') or self.get_current_timestamp()
                    sheet_row['last_updated'] = self.get_current_timestamp()
                    
                    if self.update_db_row(sheet_row):
                        sheet_to_db_updates += 1
                        logger.info(f"✅ Sheet → DB 新增成功: {user_id}")
                    else:
                        logger.error(f"❌ Sheet → DB 新增失敗: {user_id}")
                else:
                    # 比較時間戳
                    sheet_time = int(sheet_row.get('last_updated', 0))
                    db_time = int(db_row.get('last_updated', 0))
                    
                    logger.debug(f"時間比較 - Sheet: {sheet_time}, DB: {db_time}")
                    logger.debug(f"Sheet 時間: {datetime.fromtimestamp(sheet_time) if sheet_time > 0 else 'N/A'}")
                    logger.debug(f"DB 時間: {datetime.fromtimestamp(db_time) if db_time > 0 else 'N/A'}")
                    
                    if sheet_time > db_time:
                        logger.info(f"⏰ Sheet 資料較新，需要更新到 DB: {user_id}")
                        
                        if self.update_db_row(sheet_row):
                            sheet_to_db_updates += 1
                            logger.info(f"✅ Sheet → DB 更新成功: {user_id}")
                        else:
                            logger.error(f"❌ Sheet → DB 更新失敗: {user_id}")
                    elif db_time > sheet_time:
                        logger.info(f"⏰ DB 資料較新: {user_id} (此版本只關注 Sheet→DB)")
                    else:
                        logger.info(f"⚖️  資料同步，無需更新: {user_id}")
            
            # 4. 統計結果
            logger.info("=" * 60)
            logger.info("🎯 調試同步完成!")
            logger.info(f"   Sheet → DB 更新: {sheet_to_db_updates} 筆")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"調試同步失敗: {e}")
            raise
    
    def test_sheet_to_db_single(self, user_id: str):
        """測試單一用戶的 Sheet → DB 同步"""
        logger.info(f"🧪 測試單一用戶同步: {user_id}")
        
        sheet_data = self.get_sheet_data()
        target_row = None
        
        for row in sheet_data:
            if str(row.get('user_id')) == str(user_id):
                target_row = row
                break
        
        if not target_row:
            logger.error(f"在 Sheet 中找不到 user_id: {user_id}")
            return False
        
        logger.info(f"找到 Sheet 資料: {target_row}")
        
        # 手動設置更新時間為當前時間，強制同步
        target_row['last_updated'] = self.get_current_timestamp()
        
        result = self.update_db_row(target_row)
        logger.info(f"測試結果: {'成功' if result else '失敗'}")
        
        return result

# === 使用方法 ===
def main():
    CREDENTIALS_PATH = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    DB_PATH = "user_data.db"
    
    try:
        syncer = DCDBSheetSyncDebug(CREDENTIALS_PATH, SHEET_URL, DB_PATH)
        
        # 選擇執行方式
        print("選擇執行模式:")
        print("1. 調試完整同步")
        print("2. 測試單一用戶同步")
        
        choice = input("請輸入選項 (1/2): ").strip()
        
        if choice == "1":
            syncer.sync_debug()
        elif choice == "2":
            user_id = input("請輸入要測試的 user_id: ").strip()
            syncer.test_sheet_to_db_single(user_id)
        else:
            syncer.sync_debug()
            
    except Exception as e:
        logger.error(f"程式執行失敗: {e}")

if __name__ == "__main__":
    main()
