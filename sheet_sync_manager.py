"""
改進的 Google Sheets 同步系統 - SHEET 主導 + 動態 DB 適應

架構：
1. SHEET 是真實數據源（Row 2 定義所有欄位）
2. DB 根據 SHEET 結構自動調整（自動添加新欄位）
3. 動態映射，無需手動維護欄位列表
"""

import sqlite3
import hashlib
from datetime import datetime

class SheetSyncManager:
    """SHEET 主導的同步管理器"""
    
    # 定義哪些欄位是必須存在於 DB 中的（核心業務欄位）
    CORE_FIELDS = {'user_id', 'level', 'xp', 'kkcoin', 'title'}
    
    # 定義欄位類型映射（SHEET → DB SQL 類型）
    FIELD_TYPES = {
        'user_id': 'INTEGER PRIMARY KEY',
        'level': 'INTEGER DEFAULT 1',
        'xp': 'INTEGER DEFAULT 0',
        'kkcoin': 'INTEGER DEFAULT 0',
        'title': 'TEXT DEFAULT "新手"',
        'hp': 'INTEGER DEFAULT 100',
        'stamina': 'INTEGER DEFAULT 100',
        'streak': 'INTEGER DEFAULT 0',
        'is_stunned': 'INTEGER DEFAULT 0',
        'is_locked': 'INTEGER DEFAULT 0',
    }
    
    # 欄位排除列表（SHEET 中有但 DB 不需要的）
    EXCLUDE_FIELDS = {'nickname'}  # nickname 只在 SHEET 中，不同步到 DB
    
    def __init__(self, db_path='user_data.db'):
        self.db_path = db_path
    
    def get_sheet_headers(self, all_values):
        """
        從 SHEET 的原始數據取得表頭
        
        假設結構：
        - Row 1: 分組標題（忽略）
        - Row 2: 實際表頭
        """
        if len(all_values) < 2:
            raise ValueError("SHEET 數據不足")
        
        headers = all_values[1]  # 第 2 行是實際表頭
        return [h for h in headers if h and h.strip()]  # 過濾空列
    
    def get_sheet_data_rows(self, all_values):
        """
        從 SHEET 提取數據行（跳過標題和空行）
        """
        if len(all_values) < 3:
            return []
        
        data_rows = []
        for row_values in all_values[2:]:
            # 跳過完全空的行
            if not any(row_values):
                continue
            data_rows.append(row_values)
        
        return data_rows
    
    def ensure_db_schema(self, headers):
        """
        確保 DB 的 schema 與 SHEET 的欄位一致
        
        流程：
        1. 檢查 users 表是否存在
        2. 對於 SHEET 中的每個欄位，確保 DB 有該欄位
        3. 自動添加缺失的欄位（使用合適的 SQL 類型）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 檢查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='users'
        """)
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            # 創建表
            print("🆕 創建 users 表...")
            self._create_table(cursor, headers)
        else:
            # 表存在，檢查並添加缺失的欄位
            self._migrate_schema(cursor, headers)
        
        conn.commit()
        conn.close()
    
    def _create_table(self, cursor, headers):
        """創建初始表"""
        columns = []
        
        for header in headers:
            if header in self.EXCLUDE_FIELDS:
                continue
            
            # 使用預定義的類型，如果沒有則使用 TEXT
            col_type = self.FIELD_TYPES.get(header, 'TEXT')
            columns.append(f"{header} {col_type}")
        
        # 確保 user_id 是 PRIMARY KEY
        if 'user_id' not in [h.split()[0] for h in columns]:
            columns.insert(0, "user_id INTEGER PRIMARY KEY")
        
        sql = f"CREATE TABLE users ({', '.join(columns)})"
        print(f"📝 SQL: {sql[:100]}...")
        cursor.execute(sql)
        print("✅ users 表已建立")
    
    def _migrate_schema(self, cursor, headers):
        """添加 SHEET 中有但 DB 中缺失的欄位"""
        # 獲取現有欄位
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        added_count = 0
        for header in headers:
            if header in self.EXCLUDE_FIELDS:
                continue
            
            if header not in existing_columns:
                # 添加新欄位
                col_type = self.FIELD_TYPES.get(header, 'TEXT')
                sql = f"ALTER TABLE users ADD COLUMN {header} {col_type}"
                print(f"➕ 添加欄位: {header}")
                try:
                    cursor.execute(sql)
                    added_count += 1
                except sqlite3.OperationalError as e:
                    print(f"⚠️ 添加欄位失敗: {e}")
        
        if added_count > 0:
            print(f"✅ 新增 {added_count} 個欄位")
    
    def parse_records(self, headers, data_rows):
        """
        將 SHEET 數據轉換為記錄字典列表
        
        流程：
        1. 逐行處理
        2. 跳過無效的 user_id
        3. 轉換數據類型
        4. 排除 EXCLUDE_FIELDS
        """
        records = []
        
        for row_idx, row_values in enumerate(data_rows, start=3):
            record = {}
            
            # 逐列解析
            for col_idx, header in enumerate(headers):
                if header in self.EXCLUDE_FIELDS:
                    continue  # 不存儲排除的欄位
                
                value = row_values[col_idx] if col_idx < len(row_values) else ''
                
                # 類型轉換
                if header in {'user_id', 'level', 'xp', 'kkcoin', 'hp', 'stamina', 
                               'face', 'hair', 'skin', 'top', 'bottom', 'shoes', 
                               'streak', 'is_stunned', 'is_locked'}:
                    record[header] = self._to_int(value)
                elif header in {'is_stunned', 'is_locked'}:
                    record[header] = 1 if str(value).upper() == 'TRUE' else 0
                else:
                    record[header] = str(value).strip()
            
            # 驗證必須欄位
            user_id = record.get('user_id')
            if not user_id or user_id == 0:
                print(f"⏭️ 行 {row_idx} 跳過: user_id 無效")
                continue
            
            records.append(record)
        
        return records
    
    def _to_int(self, val):
        """安全地轉換為整數"""
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        
        val_str = str(val).strip()
        if not val_str:
            return 0
        
        try:
            return int(val_str)
        except ValueError:
            try:
                return int(float(val_str))
            except ValueError:
                return 0
    
    def sync_records(self, records):
        """
        同步記錄到 DB（INSERT 或 UPDATE）
        
        返回: (updated, inserted, errors)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updated = 0
        inserted = 0
        errors = 0
        
        for record in records:
            try:
                user_id = record['user_id']
                
                # 檢查是否已存在
                cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
                exists = cursor.fetchone() is not None
                
                if exists:
                    # UPDATE：只更新 record 中有的欄位
                    set_clause = ', '.join([f"{k}=?" for k in record.keys() if k != 'user_id'])
                    values = [v for k, v in record.items() if k != 'user_id']
                    values.append(user_id)
                    cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id=?", values)
                    updated += 1
                else:
                    # INSERT：創建新記錄
                    columns = ', '.join(record.keys())
                    placeholders = ', '.join(['?' for _ in record.keys()])
                    values = list(record.values())
                    cursor.execute(f"INSERT INTO users ({columns}) VALUES ({placeholders})", values)
                    inserted += 1
            
            except Exception as e:
                errors += 1
                print(f"❌ 同步失敗 (user_id {record.get('user_id')}): {e}")
        
        conn.commit()
        conn.close()
        
        return updated, inserted, errors
    
    def generate_hash(self, headers, records):
        """
        生成 SHEET 內容的 hash（用於檢測變化）
        只對關鍵欄位計算
        """
        if not records:
            return None
        
        key_fields = ['user_id', 'kkcoin', 'level', 'xp', 'title']
        data = []
        
        for record in records:
            row_data = tuple(str(record.get(f, '')) for f in key_fields if f in record)
            data.append(row_data)
        
        return hashlib.md5(str(data).encode()).hexdigest()


# 使用示例：
if __name__ == '__main__':
    manager = SheetSyncManager()
    
    # 模擬 SHEET 數據
    mock_sheet_data = [
        ['【# 第1欄】', '【第2欄】', '【第3欄】'],  # Row 1: 分組標題
        ['user_id', 'nickname', 'level', 'kkcoin', 'title', 'new_field'],  # Row 2: 實際標題
        ['123456789', 'TestUser1', '1', '1000', '新手', 'value1'],  # Row 3+: 數據
        ['987654321', 'TestUser2', '2', '5000', '武士', 'value2'],
    ]
    
    print("=" * 60)
    print("📋 SHEET 主導同步系統演示")
    print("=" * 60)
    
    try:
        # 1. 提取表頭
        headers = manager.get_sheet_headers(mock_sheet_data)
        print(f"\n✅ SHEET 表頭 (共 {len(headers)} 列):")
        print(f"   {headers}")
        
        # 2. 提取數據
        data_rows = manager.get_sheet_data_rows(mock_sheet_data)
        print(f"\n✅ SHEET 數據行: {len(data_rows)} 筆")
        
        # 3. 確保 DB schema
        print(f"\n🔧 自動調整 DB schema...")
        manager.ensure_db_schema(headers)
        
        # 4. 解析記錄
        records = manager.parse_records(headers, data_rows)
        print(f"\n✅ 解析記錄: {len(records)} 筆")
        for i, rec in enumerate(records[:2], 1):
            print(f"   記錄 {i}: {rec}")
        
        # 5. 同步到 DB
        print(f"\n📤 同步到 DB...")
        updated, inserted, errors = manager.sync_records(records)
        print(f"✅ 同步完成: 更新 {updated}, 新增 {inserted}, 錯誤 {errors}")
        
        # 6. 驗證
        conn = sqlite3.connect('user_data.db')
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        db_columns = [row[1] for row in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM users")
        db_count = cursor.fetchone()[0]
        conn.close()
        
        print(f"\n📊 DB 驗證:")
        print(f"   - 欄位數: {len(db_columns)}")
        print(f"   - 記錄數: {db_count}")
        print(f"   - 欄位: {db_columns}")
    
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
