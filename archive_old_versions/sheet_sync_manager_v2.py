"""
✨ 改進的 Google Sheets 同步系統 v2.0
真正的「以SHEET為主」架構 - 自動動態schema

核心特性：
✅ SHEET 表頭 = 唯一的欄位定義來源
✅ 自動檢測新欄位並添加到 DB（無需代碼修改）
✅ 智能類型推斷（id → INTEGER, coin → INTEGER, 等等）
✅ 雙層防禦：Apps Script 過濾 + Python 驗證
✅ 完全向後兼容現有 SQLite 數據庫
✅ 支持未來遷移到 PostgreSQL + JSONB
"""

import sqlite3
import hashlib
from datetime import datetime
from database_schema import infer_column_type, FIELD_TYPE_HINTS


class SheetSyncManagerV2:
    """改進的 SHEET 主導同步管理器"""
    
    def __init__(self, db_path='user_data.db'):
        self.db_path = db_path
        # 絕不排除任何欄位 - 所有 SHEET 欄位都應該被存儲
        self.EXCLUDE_FIELDS = set()
        print(f"📦 SheetSyncManager v2.0 已初始化 (DB: {db_path})")
    
    # ============================================================
    # 核心方法：根據 SHEET 表頭確保 DB Schema 匹配
    # ============================================================
    
    def ensure_db_schema(self, headers):
        """
        🎯 最重要的方法：確保 DB Schema 與 SHEET 表頭完全匹配
        
        流程：
        1. 連接 DB
        2. 檢查 users 表是否存在
        3. 如果不存在：根據表頭創建（第一次運行）
        4. 如果存在：檢查新欄位並添加（ALTER TABLE）
        
        ✨ 效果：無需手動修改代碼，新增欄位自動同步
        """
        if not headers:
            print("❌ 表頭為空，無法同步 schema")
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 檢查表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            table_exists = cursor.fetchone() is not None
            
            print(f"📊 檢查表結構... (表存在: {table_exists})")
            print(f"📋 SHEET 表頭 ({len(headers)} 列): {', '.join(headers[:5])}...")
            
            if not table_exists:
                # 第一次創建表
                self._create_table_from_headers(cursor, headers)
                print("✅ 新表已根據 SHEET 表頭創建")
            else:
                # 添加缺失的欄位
                added = self._add_missing_columns(cursor, headers)
                if added > 0:
                    print(f"✅ 添加了 {added} 個新欄位")
                else:
                    print("✅ Schema 已是最新（無新欄位）")
            
            conn.commit()
            
        except Exception as e:
            print(f"❌ Schema 同步失敗: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _create_table_from_headers(self, cursor, headers):
        """
        根據 SHEET 表頭創建 users 表
        
        規則：
        - user_id → INTEGER PRIMARY KEY（必須）
        - 其他欄位根據智能類型推斷
        - 自動添加 created_at, updated_at 時間戳
        """
        columns = [
            "user_id INTEGER PRIMARY KEY",
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ]
        
        # 添加所有非 user_id 的表頭欄位
        for header in headers:
            if header == 'user_id' or header in ['created_at', 'updated_at']:
                continue
            
            # 智能推斷欄位類型
            col_type = infer_column_type(header)
            columns.append(f'"{header}" {col_type}')
        
        # 構建 CREATE TABLE 語句
        sql = f"CREATE TABLE users ({', '.join(columns)})"
        
        print(f"📝 CREATE TABLE SQL (前 200 字):")
        print(f"   {sql[:200]}...")
        
        cursor.execute(sql)
        
        # 創建自動更新時間戳的觸發器
        trigger_sql = """
        CREATE TRIGGER IF NOT EXISTS update_users_timestamp 
        AFTER UPDATE ON users
        BEGIN
            UPDATE users SET updated_at = CURRENT_TIMESTAMP 
            WHERE user_id = NEW.user_id;
        END;
        """
        cursor.execute(trigger_sql)
        
        print("✅ 表已創建，自動更新觸發器已添加")
    
    def _add_missing_columns(self, cursor, headers):
        """
        檢查並添加缺失的欄位（ALTER TABLE）
        
        只添加新欄位，不刪除舊欄位（防止數據丟失）
        """
        # 獲取現有欄位
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        print(f"📊 現有欄位: {len(existing_columns)} 個")
        print(f"📋 表頭欄位: {len(headers)} 個")
        
        added_count = 0
        
        for header in headers:
            if header in existing_columns or header in ['created_at', 'updated_at']:
                continue
            
            # 智能推斷欄位類型
            col_type = infer_column_type(header)
            
            # ALTER TABLE 添加新欄位
            sql = f'ALTER TABLE users ADD COLUMN "{header}" {col_type}'
            
            try:
                print(f"➕ 添加欄位: {header} ({col_type})")
                cursor.execute(sql)
                added_count += 1
            except sqlite3.OperationalError as e:
                print(f"⚠️ 添加欄位 {header} 失敗: {e}")
        
        return added_count
    
    # ============================================================
    # 數據解析和驗證
    # ============================================================
    
    def parse_records(self, headers, data_rows):
        """
        將 SHEET 數據轉換為記錄字典列表
        
        流程：
        1. 檢查 user_id 欄位（自動偵測）
        2. 逐行解析
        3. 類型轉換和驗證
        4. 排除無效記錄
        """
        records = []
        
        # 確保 user_id 欄位存在
        if 'user_id' not in headers:
            detected_idx = self._detect_user_id_col(headers, data_rows)
            if detected_idx is not None:
                print(f"🔎 自動偵測 user_id 在第 {detected_idx + 1} 列")
                headers[detected_idx] = 'user_id'
            else:
                print(f"❌ 無法偵測 user_id 欄位！請確保 SHEET 表頭包含 user_id")
                return records
        
        print(f"📋 解析表頭 ({len(headers)} 列): {headers[:5]}...")
        
        # 解析每一行
        for row_idx, row_values in enumerate(data_rows, start=3):
            record = {}
            
            for col_idx, header in enumerate(headers):
                if col_idx >= len(row_values):
                    value = None
                else:
                    value = row_values[col_idx]
                
                # 類型轉換
                record[header] = self._convert_value(header, value)
            
            # 驗證 user_id
            user_id = record.get('user_id')
            if not self._is_valid_user_id(user_id):
                print(f"⏭️ 行 {row_idx} 被跳過: user_id 無效 (值: {user_id})")
                continue
            
            records.append(record)
        
        print(f"✅ 共解析 {len(records)} 筆有效記錄")
        return records
    
    def _convert_value(self, header, value):
        """
        根據欄位類型轉換值
        
        規則：
        - user_id: 必須是 16+ 位整數或 9-17 位數字（Discord ID）
        - 整數欄位: 嘗試轉換，失敗返回 0
        - 文字欄位: 轉為字符串
        - 時間欄位: 保持原樣或轉換為 ISO 格式
        """
        if value is None or value == '':
            return None
        
        # 確定期望的類型
        expected_type = infer_column_type(header)
        
        try:
            if expected_type == 'INTEGER' or expected_type.startswith('INTEGER'):
                return self._to_int(value)
            elif expected_type == 'TIMESTAMP' or expected_type.startswith('TIMESTAMP'):
                return self._to_timestamp(value)
            else:
                return str(value).strip()
        except Exception as e:
            print(f"⚠️ 轉換失敗 {header}={value}: {e}")
            return None
    
    def _to_int(self, val):
        """安全轉換為整數（支持科學記號）"""
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        
        val_str = str(val).strip()
        if not val_str:
            return None
        
        # 防禦性檢查：拒絕純字母或含有下劃線的字符串（可能是欄位名）
        if val_str.isalpha() or '_' in val_str:
            return None
        
        try:
            # 直接整數轉換
            return int(val_str)
        except ValueError:
            try:
                # 科學記號轉換（如 4.98503E+17）
                f = float(val_str)
                return int(f)
            except ValueError:
                return None
    
    def _to_timestamp(self, val):
        """轉換為時間戳"""
        if isinstance(val, str):
            return val
        return str(val)
    
    def _is_valid_user_id(self, user_id):
        """驗證 user_id 是否有效（Discord user_id 為 16-17 位整數）"""
        if user_id is None:
            return False
        if not isinstance(user_id, int):
            return False
        return 16 <= len(str(user_id)) <= 17 or 9 <= len(str(user_id)) <= 15
    
    def _detect_user_id_col(self, headers, data_rows):
        """
        自動檢測 user_id 所在的列
        
        啟發式算法：檢查前 200 行，找到最可能包含 Discord ID 的列
        特徵：16-17 位整數或科學記號格式的大數字
        """
        if not data_rows or not headers:
            return None
        
        col_count = len(headers)
        scores = [0] * col_count
        sample = data_rows[:200]
        
        for row in sample:
            for col_idx in range(min(col_count, len(row))):
                val = row[col_idx]
                val_str = str(val).strip()
                
                # 科學記號或大整數
                if 'e' in val_str.lower() or (val_str.isdigit() and len(val_str) >= 16):
                    scores[col_idx] += 1
        
        max_score = max(scores) if scores else 0
        if max_score > len(sample) * 0.5:
            return scores.index(max_score)
        
        return None
    
    # ============================================================
    # 數據庫操作
    # ============================================================
    
    def insert_records(self, records):
        """
        插入或更新記錄
        
        策略：
        - user_id 已存在：UPDATE
        - user_id 不存在：INSERT
        """
        if not records:
            return 0, 0, 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updated = 0
        inserted = 0
        errors = 0
        
        try:
            for record in records:
                try:
                    # 檢查 user_id 是否已存在
                    user_id = record.get('user_id')
                    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
                    exists = cursor.fetchone() is not None
                    
                    if exists:
                        # UPDATE
                        self._update_record(cursor, record)
                        updated += 1
                    else:
                        # INSERT
                        self._insert_record(cursor, record)
                        inserted += 1
                
                except Exception as e:
                    print(f"❌ 記錄處理失敗 (user_id={record.get('user_id')}): {e}")
                    errors += 1
            
            conn.commit()
            print(f"📊 同步完成: 更新 {updated}, 新增 {inserted}, 錯誤 {errors}")
            
        finally:
            conn.close()
        
        return updated, inserted, errors
    
    def _insert_record(self, cursor, record):
        """插入新記錄"""
        keys = list(record.keys())
        values = [record[k] for k in keys]
        
        placeholders = ', '.join(['?' for _ in keys])
        quoted_keys = ', '.join([f'"{k}"' for k in keys])
        
        sql = f"INSERT INTO users ({quoted_keys}) VALUES ({placeholders})"
        cursor.execute(sql, values)
    
    def _update_record(self, cursor, record):
        """更新現有記錄"""
        user_id = record.pop('user_id')
        
        if not record:
            return
        
        set_clause = ', '.join([f'"{k}" = ?' for k in record.keys()])
        values = list(record.values()) + [user_id]
        
        sql = f"UPDATE users SET {set_clause} WHERE user_id = ?"
        cursor.execute(sql, values)
    
    # ============================================================
    # 工具方法
    # ============================================================
    
    def get_schema_info(self):
        """獲取當前 DB Schema 信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(users)")
            columns = cursor.fetchall()
            
            schema = {
                'table_name': 'users',
                'columns': len(columns),
                'fields': [{'name': col[1], 'type': col[2]} for col in columns]
            }
            
            return schema
        finally:
            conn.close()
    
    def get_user_count(self):
        """獲取玩家總數"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]
        finally:
            conn.close()


# ============================================================
# 便捷函數
# ============================================================

def create_sync_manager(db_path='user_data.db'):
    """創建同步管理器實例"""
    return SheetSyncManagerV2(db_path)


if __name__ == '__main__':
    # 測試
    manager = SheetSyncManagerV2()
    
    # 示例表頭
    test_headers = [
        'user_id', 'nickname', 'level', 'xp', 'kkcoin',
        'hp', 'stamina', 'title', 'status', 'created_at'
    ]
    
    print("=" * 60)
    print("📦 SheetSyncManager v2.0 測試")
    print("=" * 60)
    
    # 初始化 schema
    manager.ensure_db_schema(test_headers)
    
    # 查看 schema
    schema = manager.get_schema_info()
    print(f"\n📊 當前 Schema:")
    print(f"   表名: {schema['table_name']}")
    print(f"   欄位數: {schema['columns']}")
    print(f"   欄位列表:")
    for field in schema['fields'][:5]:
        print(f"     - {field['name']}: {field['type']}")
    if len(schema['fields']) > 5:
        print(f"     ... 還有 {len(schema['fields']) - 5} 個欄位")
    
    print("\n✅ 測試完成")
