"""
Sheet-Driven Database Engine - 完全以 SHEET 為主導的數據庫系統

核心概念：
1. SHEET Row 1 = 數據庫表頭定義 (真實來源)
2. SHEET Column A = user_id (主鍵)
3. DB 自動適應 SHEET 結構 (添加新欄位無需改代碼)
4. 所有操作都通過統一 API (無硬編碼列名)
5. 支持任意類型轉換 (int, str, float, json)

使用示例:
    db = SheetDrivenDB('user_data.db')
    
    # 讀取用戶
    user = db.get_user(123456789)
    print(user['level'])  # 動態讀取任意欄位
    
    # 更新用戶
    db.set_user(123456789, {'level': 10, 'xp': 5000})
    
    # 同步 SHEET
    db.sync_from_sheet(headers, rows)
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union


class SheetDrivenDB:
    """Sheet-Driven 數據庫引擎"""
    
    def __init__(self, db_path: str = 'user_data.db'):
        """
        初始化數據庫引擎
        
        Args:
            db_path: SQLite 數據庫文件路徑
        """
        self.db_path = db_path
        self.table_name = 'users'
        
        # 初始化數據庫
        self._init_db()
    
    def _init_db(self):
        """初始化數據庫連接與表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 允許按列名訪問
        cursor = conn.cursor()
        
        # 檢查 users 表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """, (self.table_name,))
        
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            # 創建初始表（只有必須的 user_id 字段）
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    user_id INTEGER PRIMARY KEY,
                    _created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    _updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print(f"✅ 創建了表: {self.table_name}")
        
        conn.commit()
        conn.close()
    
    def _get_connection(self) -> sqlite3.Connection:
        """獲取數據庫連接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # ============================================================
    # Schema 管理
    # ============================================================
    
    def get_existing_columns(self) -> set:
        """獲取現有表的所有列名"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"PRAGMA table_info({self.table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        
        conn.close()
        return columns
    
    def ensure_columns(self, headers: List[str]):
        """
        確保表中存在所有欄位
        如果 SHEET 中有新欄位，自動添加到 DB
        
        Args:
            headers: SHEET 表頭列表 (來自 Row 1)
        """
        existing_columns = self.get_existing_columns()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        added_count = 0
        for header in headers:
            # 跳過已存在的列
            if header in existing_columns:
                continue
            
            # 跳過系統列
            if header.startswith('_'):
                continue
            
            # 推測適當的 SQL 類型
            col_type = self._infer_sql_type(header)
            
            # 添加新列
            sql = f'ALTER TABLE {self.table_name} ADD COLUMN "{header}" {col_type}'
            try:
                cursor.execute(sql)
                print(f"➕ 添加欄位: {header} ({col_type})")
                added_count += 1
            except sqlite3.OperationalError as e:
                print(f"⚠️ 添加欄位失敗: {header} - {e}")
        
        if added_count > 0:
            cursor.execute(f'UPDATE {self.table_name} SET _updated_at = CURRENT_TIMESTAMP')
            print(f"✅ 新增 {added_count} 個欄位")
        
        conn.commit()
        conn.close()
    
    def _infer_sql_type(self, header: str) -> str:
        """
        根據欄位名推測 SQL 類型
        
        Args:
            header: 欄位名稱
            
        Returns:
            SQL 類型字符串
        """
        header_lower = header.lower()
        
        # 整數型欄位
        if any(word in header_lower for word in 
               ['id', 'level', 'xp', 'coin', 'kkcoin', 'hp', 'stamina', 
                'streak', 'count', 'num', 'amount', 'is_', 'unlocked']):
            return 'INTEGER DEFAULT 0'
        
        # 時間戳欄位
        if any(word in header_lower for word in 
               ['date', 'time', 'timestamp', 'at']):
            return 'TEXT DEFAULT NULL'
        
        # JSON 欄位 (用於複雜結構)
        if any(word in header_lower for word in 
               ['config', 'setting', 'data', 'json', 'info', 'inventory']):
            return 'TEXT DEFAULT \'{}\'  -- JSON格式'
        
        # 默認為文本
        return 'TEXT DEFAULT \'\''
    
    # ============================================================
    # 用戶數據操作
    # ============================================================
    
    def get_user(self, user_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        """
        獲取用戶完整數據
        
        Args:
            user_id: 用戶 ID
            
        Returns:
            用戶數據字典，或 None 如果用戶不存在
        """
        user_id = int(user_id)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT * FROM {self.table_name} WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if not row:
            return None
        
        # 轉換為字典，並解析 JSON 字段
        return self._row_to_dict(row)
    
    def set_user(self, user_id: Union[int, str], data: Dict[str, Any]) -> bool:
        """
        更新用戶數據 (INSERT OR REPLACE)
        
        Args:
            user_id: 用戶 ID
            data: 要更新的數據 {'field': value, ...}
            
        Returns:
            是否成功
        """
        user_id = int(user_id)
        
        try:
            # 🔑 第一步：確保所有列存在（在獨立的連接中完成）
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 先獲取現有用戶數據和確定需要的列
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE user_id = ?", (user_id,))
            existing_row = cursor.fetchone()
            
            if existing_row:
                # 更新現有用戶
                existing_data = self._row_to_dict(existing_row)
                existing_data.update(data)
                existing_data['_updated_at'] = datetime.now().isoformat()
            else:
                # 創建新用戶
                existing_data = {'user_id': user_id, '_updated_at': datetime.now().isoformat()}
                existing_data.update(data)
            
            conn.close()  # ✅ 關閉原連接，避免 ALTER TABLE 時的連接狀態問題
            
            # 🔑 第二步：確保所有列都存在（在獨立連接中）
            try:
                self.ensure_columns(list(existing_data.keys()))
            except Exception as col_err:
                print(f"⚠️ 添加欄位失敗: {col_err}")
                # 繼續執行，可能欄位已存在
            
            # 🔑 第三步：執行 INSERT OR REPLACE（在新連接中）
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 構建 SQL INSERT OR REPLACE
            columns = list(existing_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            columns_str = ', '.join([f'"{col}"' for col in columns])
            
            sql = f"INSERT OR REPLACE INTO {self.table_name} ({columns_str}) VALUES ({placeholders})"
            values = [existing_data.get(col) for col in columns]
            
            # 轉換複雜類型為 JSON
            converted_values = []
            for i, col in enumerate(columns):
                val = values[i]
                if isinstance(val, (dict, list)):
                    converted_values.append(json.dumps(val, ensure_ascii=False))
                else:
                    converted_values.append(val)
            
            cursor.execute(sql, converted_values)
            conn.commit()
            
            # ✅ 驗證寫入
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE user_id = ?", (user_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                print(f"✅ user_id {user_id} 成功寫入數據庫")
                conn.close()
                return True
            else:
                print(f"❌ user_id {user_id} 寫入驗證失敗（計數為 0）")
                conn.close()
                return False
            
        except sqlite3.IntegrityError as ie:
            print(f"❌ 數據完整性錯誤 (user_id {user_id}): {ie}")
            return False
        except sqlite3.OperationalError as oe:
            print(f"❌ 操作錯誤 (user_id {user_id}): {oe}")
            return False
        except Exception as e:
            print(f"❌ 未預期的錯誤 (user_id {user_id}): {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_user_field(self, user_id: Union[int, str], field: str, default: Any = None) -> Any:
        """
        獲取用戶特定欄位的值
        
        Args:
            user_id: 用戶 ID
            field: 欄位名
            default: 預設值
            
        Returns:
            欄位值
        """
        user = self.get_user(user_id)
        
        if user is None:
            return default
        
        return user.get(field, default)
    
    def set_user_field(self, user_id: Union[int, str], field: str, value: Any) -> bool:
        """
        更新用戶特定欄位
        
        Args:
            user_id: 用戶 ID
            field: 欄位名
            value: 新值
            
        Returns:
            是否成功
        """
        return self.set_user(user_id, {field: value})
    
    def update_user_field(self, user_id: Union[int, str], field: str, amount: Union[int, float]) -> bool:
        """
        增減用戶特定欄位的值 (僅限數字類型)
        
        Args:
            user_id: 用戶 ID
            field: 欄位名
            amount: 增量 (可為負)
            
        Returns:
            是否成功
        """
        user_id = int(user_id)
        current = self.get_user_field(user_id, field, 0)
        
        if isinstance(current, str) and current.isdigit():
            current = int(current)
        
        if not isinstance(current, (int, float)):
            print(f"❌ 欄位 {field} 不是數字類型")
            return False
        
        new_value = current + amount
        return self.set_user_field(user_id, field, new_value)
    
    # ============================================================
    # 批量操作
    # ============================================================
    
    def get_all_users(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """獲取所有用戶"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        sql = f"SELECT * FROM {self.table_name}"
        if limit:
            sql += f" LIMIT {limit}"
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        conn.close()
        
        return [self._row_to_dict(row) for row in rows]
    
    def delete_user(self, user_id: Union[int, str]) -> bool:
        """刪除用戶"""
        user_id = int(user_id)
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"DELETE FROM {self.table_name} WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            print(f"❌ 刪除用戶失敗: {e}")
            return False
    
    # ============================================================
    # SHEET 同步
    # ============================================================
    
    def sync_from_sheet(self, headers: List[str], rows: List[List[str]]) -> Dict[str, int]:
        """
        從 SHEET 數據同步到數據庫（支持去重和增量同步）
        
        Args:
            headers: SHEET 表頭 (Row 1)
            rows: SHEET 數據行 (Row 2+)
            
        Returns:
            統計信息 {'inserted': n, 'updated': n, 'errors': n, 'duplicates': n}
        """
        print(f"\n🔄 開始同步 SHEET 到數據庫...")
        print(f"   表頭數: {len(headers)}")
        print(f"   數據行: {len(rows)}")
        
        # 1. 確保所有欄位存在
        self.ensure_columns(headers)
        
        # 2. 解析並同步記錄 (去重)
        stats = {'inserted': 0, 'updated': 0, 'errors': 0, 'duplicates': 0}
        seen_user_ids = set()  # 追蹤本次同步中的用戶 ID (去重)
        
        for i, row in enumerate(rows):
            try:
                # 過濾空行 (更嚴格的檢查)
                if not row or not any(cell and str(cell).strip() for cell in row):
                    continue
                
                # 構建記錄字典
                record = {}
                for j, header in enumerate(headers):
                    if j < len(row):
                        value = row[j]
                        # 轉換類型
                        record[header] = self._convert_value(header, value)
                
                # 必須有 user_id
                if 'user_id' not in record or not record['user_id']:
                    stats['errors'] += 1
                    continue
                
                try:
                    user_id = int(record['user_id'])
                except (ValueError, TypeError):
                    print(f"⚠️ 第 {i+2} 行: user_id 無效 '{record.get('user_id')}'")
                    stats['errors'] += 1
                    continue
                
                # 檢查本次同步中的重複
                if user_id in seen_user_ids:
                    print(f"⚠️ 第 {i+2} 行: 在本次同步中有重複的 user_id {user_id} (已跳過)")
                    stats['duplicates'] += 1
                    continue
                
                seen_user_ids.add(user_id)
                
                # 檢查用戶是否已存在於數據庫
                existing_user = self.get_user(user_id)
                if existing_user:
                    stats['updated'] += 1
                    action = "更新"
                else:
                    stats['inserted'] += 1
                    action = "新增"
                
                # 保存用戶 (INSERT OR REPLACE)
                self.set_user(user_id, record)
                print(f"   ✓ [{action}] 用戶 {user_id}")
            
            except Exception as e:
                print(f"⚠️ 第 {i+2} 行錯誤: {e}")
                stats['errors'] += 1
        
        print(f"\n✅ 同步完成:")
        print(f"   新增: {stats['inserted']} 個用戶")
        print(f"   更新: {stats['updated']} 個用戶")
        print(f"   重複: {stats['duplicates']} 行 (已移除)")
        print(f"   錯誤: {stats['errors']} 行")
        
        return stats
    
    def export_to_sheet_format(self) -> Tuple[List[str], List[List[str]]]:
        """
        導出數據庫數據為 SHEET 格式
        
        Returns:
            (headers, rows) 元組
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 獲取所有列名 (除了系統列)
        cursor.execute(f"PRAGMA table_info({self.table_name})")
        all_columns = [row[1] for row in cursor.fetchall()]
        
        headers = [col for col in all_columns if not col.startswith('_')]
        
        # 獲取所有數據
        quoted_headers = [f'"{col}"' for col in headers]
        columns_str = ', '.join(quoted_headers)
        cursor.execute(f"SELECT {columns_str} FROM {self.table_name} ORDER BY user_id")
        rows = []
        for row in cursor.fetchall():
            row_list = []
            for col, val in zip(headers, row):
                # 如果是 JSON，保持為字符串
                if isinstance(val, str) and (val.startswith('{') or val.startswith('[')):
                    row_list.append(val)
                else:
                    row_list.append(str(val) if val is not None else '')
            rows.append(row_list)
        
        conn.close()
        
        return headers, rows
    
    # ============================================================
    # 輔助方法
    # ============================================================
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """將 SQLite Row 轉換為字典，解析 JSON 字段"""
        data = dict(row)
        
        # 嘗試解析 JSON 字段
        for key, value in data.items():
            if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                try:
                    data[key] = json.loads(value)
                except:
                    pass  # 保持原值
        
        return data
    
    def _convert_value(self, header: str, value: str) -> Any:
        """
        根據欄位名將字符串值轉換為適當的類型
        
        Args:
            header: 欄位名
            value: 字符串值
            
        Returns:
            轉換後的值
        """
        if not value or value == '':
            return None
        
        header_lower = header.lower()
        
        # 整數型
        if any(word in header_lower for word in 
               ['id', 'level', 'xp', 'coin', 'kkcoin', 'hp', 'stamina', 
                'streak', 'count', 'num', 'amount', 'unlocked']):
            try:
                return int(float(value))
            except:
                return 0
        
        # 布爾型 (is_stunned, is_locked 等)
        if header_lower.startswith('is_'):
            if isinstance(value, str):
                return 1 if value.lower() in ['1', 'true', 'yes'] else 0
            return 1 if value else 0
        
        # 浮點數
        if any(word in header_lower for word in ['rate', 'percent', 'ratio']):
            try:
                return float(value)
            except:
                return 0.0
        
        # 默認為字符串
        return str(value)
    
    # ============================================================
    # 統計查詢
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取數據庫統計信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 用戶總數
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        total_users = cursor.fetchone()[0]
        
        # 獲取所有列
        cursor.execute(f"PRAGMA table_info({self.table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        
        stats = {
            'total_users': total_users,
            'total_columns': len(columns),
            'columns': sorted(list(columns))
        }
        
        # 嘗試計算一些常見欄位的統計
        for field in ['level', 'xp', 'kkcoin', 'hp', 'stamina']:
            if f'"{field}"' in columns or field in columns:
                try:
                    cursor.execute(f"SELECT AVG(\"{field}\"), MAX(\"{field}\"), MIN(\"{field}\") FROM {self.table_name}")
                    avg, max_val, min_val = cursor.fetchone()
                    stats[f'{field}_avg'] = round(avg, 2) if avg else 0
                    stats[f'{field}_max'] = max_val
                    stats[f'{field}_min'] = min_val
                except:
                    pass
        
        conn.close()
        
        return stats
    
    def export_json(self, filename: str) -> bool:
        """將所有數據導出為 JSON 文件"""
        try:
            data = self.get_all_users()
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ 已導出 {len(data)} 個用戶到 {filename}")
            return True
        except Exception as e:
            print(f"❌ 導出失敗: {e}")
            return False
    
    def import_json(self, filename: str) -> bool:
        """從 JSON 文件導入數據"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            count = 0
            for user_data in data:
                if 'user_id' in user_data:
                    self.set_user(user_data['user_id'], user_data)
                    count += 1
            
            print(f"✅ 已導入 {count} 個用戶")
            return True
        except Exception as e:
            print(f"❌ 導入失敗: {e}")
            return False


# ============================================================
# 便捷函數 (為了向後相容)
# ============================================================

_db_instance: Optional[SheetDrivenDB] = None

def get_db_instance(db_path: str = 'user_data.db') -> SheetDrivenDB:
    """獲取全局 DB 實例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = SheetDrivenDB(db_path)
    return _db_instance

# 快捷函數
def get_user(user_id: Union[int, str]) -> Optional[Dict[str, Any]]:
    """獲取用戶"""
    return get_db_instance().get_user(user_id)

def set_user(user_id: Union[int, str], data: Dict[str, Any]) -> bool:
    """設置用戶"""
    return get_db_instance().set_user(user_id, data)

def get_field(user_id: Union[int, str], field: str, default: Any = None) -> Any:
    """獲取用戶欄位"""
    return get_db_instance().get_user_field(user_id, field, default)

def set_field(user_id: Union[int, str], field: str, value: Any) -> bool:
    """設置用戶欄位"""
    return get_db_instance().set_user_field(user_id, field, value)

def add_field(user_id: Union[int, str], field: str, amount: Union[int, float]) -> bool:
    """增加用戶欄位值"""
    return get_db_instance().update_user_field(user_id, field, amount)
