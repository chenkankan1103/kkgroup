"""
改進的 Google Sheets 同步系統 - 完全 SHEET 驅動

架構：
1. SHEET Row 1 = 完整欄位定義 (真實來源)
2. SHEET Column A = user_id (主鍵)
3. DB 自動適應 SHEET 結構 (新欄位自動添加)
4. 使用 SheetDrivenDB 引擎 (無硬編碼欄位)

使用示例:
    manager = SheetSyncManager('user_data.db')
    manager.sync_sheet_to_db(headers, rows)  # 同步整張表
    user = manager.get_user(user_id)         # 獲取用戶
    manager.set_user(user_id, data)         # 設置用戶
"""

from sheet_driven_db import SheetDrivenDB
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from status_dashboard import add_log


class SheetSyncManager:
    """SHEET 驅動的同步管理器"""
    
    def __init__(self, db_path: str = 'user_data.db'):
        """初始化同步管理器
        
        Args:
            db_path: SQLite 數據庫文件路徑
        """
        self.db_path = db_path
        self.db = SheetDrivenDB(db_path)
    
    # ============================================================
    # SHEET 解析
    # ============================================================
    
    def get_sheet_headers(self, all_values: List[List[str]]) -> List[str]:
        """
        從 SHEET 的原始數據取得表頭
        
        假設結構：
        - Row 1 (index 0): 可選的分組標題或標籤（忽略）
        - Row 2 (index 1) 或 Row 1: 實際表頭
        
        自動偵測表頭所在的行
        """
        if not all_values:
            raise ValueError("SHEET 數據為空")
        
        # 嘗試從第 2 行讀取表頭
        if len(all_values) >= 2:
            potential_headers = [str(h).strip() for h in all_values[1] if h]
            # 如果第 2 行看起來像表頭，使用它
            if potential_headers:
                return potential_headers
        
        # 否則使用第 1 行
        return [str(h).strip() for h in all_values[0] if h]
    
    def get_sheet_data_rows(self, all_values: List[List[str]]) -> List[List[str]]:
        """
        從 SHEET 提取數據行（跳過表頭和空行）
        """
        if not all_values:
            return []
        
        # 判斷表頭從第幾行開始
        headers_row_idx = 1 if len(all_values) >= 2 else 0
        
        data_rows = []
        for row_values in all_values[headers_row_idx + 1:]:
            # 跳過完全空的行
            if not any(row_values):
                continue
            data_rows.append(row_values)
        
        return data_rows
    
    # ============================================================
    # 用戶數據操作 (代理到 DB 引擎)
    # ============================================================
    
    def get_user(self, user_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        """獲取用戶完整數據"""
        return self.db.get_user(user_id)
    
    def set_user(self, user_id: Union[int, str], data: Dict[str, Any]) -> bool:
        """設置用戶數據"""
        return self.db.set_user(user_id, data)
    
    def get_user_field(self, user_id: Union[int, str], field: str, default: Any = None) -> Any:
        """獲取用戶特定欄位"""
        return self.db.get_user_field(user_id, field, default)
    
    def set_user_field(self, user_id: Union[int, str], field: str, value: Any) -> bool:
        """設置用戶特定欄位"""
        return self.db.set_user_field(user_id, field, value)
    
    def update_user_field(self, user_id: Union[int, str], field: str, amount: Union[int, float]) -> bool:
        """增減用戶特定欄位"""
        return self.db.update_user_field(user_id, field, amount)
    
    # ============================================================
    # SHEET 同步主方法
    # ============================================================
    
    def sync_sheet_to_db(self, headers: List[str], rows: List[List[str]]) -> Dict[str, int]:
        """
        從 SHEET 數據同步到數據庫 (主方法)
        
        Args:
            headers: SHEET 表頭 (Row 1 或 Row 2)
            rows: SHEET 數據行 (Row 2+ 或 Row 3+)
            
        Returns:
            統計信息 {'inserted': n, 'updated': n, 'errors': n, 'total_parsed': n}
        """
        add_log("bot", f"🔄 SHEET → DB 同步開始: {len(headers)} 列, {len(rows)} 筆數據")
        
        # 1. 確保所有欄位存在
        add_log("bot", f"🔧 確保 DB schema...")
        self.db.ensure_columns(headers)
        
        # 2. 解析並同步記錄
        add_log("bot", f"📝 解析記錄...")
        records = self._parse_records(headers, rows)
        add_log("bot", f"✅ 解析完成: {len(records)} 筆有效記錄")
        
        # 3. 同步到 DB
        add_log("bot", f"📤 同步到 DB...")
        stats = self._sync_records_to_db(records)
        
        add_log("bot", f"✅ 同步完成: 新增 {stats['inserted']}, 更新 {stats['updated']}, 錯誤 {stats['errors']}, 總計 {stats['total_parsed']}")
        
        return stats
    
    def parse_records(self, headers: List[str], rows: List[List[str]]) -> List[Dict[str, Any]]:
        """
        將 SHEET 數據轉換為記錄字典列表 (向後相容版本)
        """
        return self._parse_records(headers, rows)
    
    def _parse_records(self, headers: List[str], rows: List[List[str]]) -> List[Dict[str, Any]]:
        """
        內部方法：將 SHEET 數據轉換為記錄字典列表
        
        流程：
        1. 自動偵測 user_id 欄位 (如果尚未識別)
        2. 逐行處理，跳過無效 user_id 和虛擬帳號
        3. 使用 DB 引擎的類型轉換（重要！）
        """
        records = []
        
        # 確保有 user_id 欄位
        headers = list(headers)  # 複製，以免修改原列表
        if 'user_id' not in headers:
            detected_idx = self._detect_user_id_col(headers, rows)
            if detected_idx is not None:
                add_log("bot", f"🔎 自動偵測 user_id: 第 {detected_idx+1} 列 ('{headers[detected_idx]}')")
                headers[detected_idx] = 'user_id'
            else:
                add_log("bot", f"❌ 無法偵測 user_id 欄位，使用第 1 列作為 user_id")
                headers[0] = 'user_id'
        
        # 解析每一行
        for row_idx, row_values in enumerate(rows, start=1):
            try:
                # 跳過空行
                if not any(row_values):
                    continue
                
                # 構建記錄字典（使用類型轉換！）
                record = {}
                for col_idx, header in enumerate(headers):
                    if col_idx < len(row_values):
                        value = row_values[col_idx]
                        # ✅ 關鍵：使用 DB 引擎的類型轉換
                        record[header] = self.db._convert_value(header, value)
                
                # 🔄 欄位映射：確保 nickname 有值
                # 如果 nickname 為空但 user_name 有值，用 user_name 填充 nickname
                if (not record.get('nickname') or record.get('nickname') == '') and record.get('user_name'):
                    record['nickname'] = record.get('user_name')
                
                # 驗證 user_id
                user_id_val = record.get('user_id')
                if user_id_val is None:
                    continue
                
                # user_id 應該已經被轉換為整數
                if not isinstance(user_id_val, int):
                    try:
                        user_id = int(float(str(user_id_val)))
                        record['user_id'] = user_id
                    except:
                        continue
                
                # 跳過虛擬帳號 (nickname 為 Unknown_*)
                nickname = record.get('nickname', '')
                if nickname and str(nickname).startswith('Unknown_'):
                    add_log("bot", f"⏭️ 行 {row_idx} 跳過虛擬帳號: {nickname}")
                    continue
                
                add_log("bot", f"✓ 行 {row_idx}: user_id={record['user_id']}, nickname={nickname}")
                records.append(record)
            
            except Exception as e:
                add_log("bot", f"⚠️ 行 {row_idx} 解析失敗: {e}")
        
        # 🔍 去重邏輯：檢測同名異 ID（可能是 ID 精度損失產生的幽靈帳號）
        add_log("bot", f"🔍 檢測同名異 ID 幽靈帳號...")
        
        # 按 nickname 分組
        nickname_to_records = {}
        for record in records:
            nickname = record.get('nickname', '')
            if nickname:
                if nickname not in nickname_to_records:
                    nickname_to_records[nickname] = []
                nickname_to_records[nickname].append(record)
        
        # 去重：每個 nickname 只保留最小 user_id
        deduped_records = []
        removed_ghosts = 0
        
        for nickname, same_name_recs in nickname_to_records.items():
            if len(same_name_recs) > 1:
                # 有多個同名用戶
                min_record = min(same_name_recs, key=lambda r: int(r.get('user_id', float('inf'))))
                deduped_records.append(min_record)
                
                # 其他都是幽靈帳號
                for rec in same_name_recs:
                    if rec['user_id'] != min_record['user_id']:
                        add_log("bot", f"👻 過濾幽靈帳號: {nickname} (user_id {rec['user_id']}) → 保留 {min_record['user_id']}")
                        removed_ghosts += 1
            else:
                # 只有一個
                deduped_records.append(same_name_recs[0])
        
        if removed_ghosts > 0:
            add_log("bot", f"✅ 過濾掉 {removed_ghosts} 個同名異 ID 幽靈帳號")
        
        return deduped_records
    
    def _sync_records_to_db(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        將記錄同步到 DB（支援去重）
        
        Returns:
            {'inserted': n, 'updated': n, 'errors': n, 'total_parsed': n, 'duplicates': n, 'error_details': [...]}
        """
        stats = {
            'inserted': 0, 
            'updated': 0, 
            'errors': 0, 
            'total_parsed': len(records), 
            'duplicates': 0,
            'error_details': []  # 記錄每個錯誤的詳細信息
        }
        seen_user_ids = set()  # 去重: 追蹤本次同步中的用戶 ID
        
        for i, record in enumerate(records, 1):
            try:
                user_id = record.get('user_id')
                if not user_id:
                    error_msg = f"用戶ID為空"
                    add_log("bot", f"⚠️ 記錄 {i}: {error_msg}")
                    stats['errors'] += 1
                    stats['error_details'].append({'record': i, 'reason': error_msg})
                    continue
                
                # ✅ 新增驗證: 確保 user_id 有效（不為 0）
                try:
                    user_id = int(user_id)
                    if user_id == 0:
                        error_msg = f"user_id 為 0，無效的用戶"
                        add_log("bot", f"⏭️ 記錄 {i}: {error_msg}")
                        stats['errors'] += 1
                        stats['error_details'].append({'record': i, 'reason': error_msg})
                        continue
                except (ValueError, TypeError) as e:
                    error_msg = f"user_id 無效或無法轉換: '{record.get('user_id')}' ({str(e)})"
                    add_log("bot", f"❌ 記錄 {i}: {error_msg}")
                    stats['errors'] += 1
                    stats['error_details'].append({'record': i, 'reason': error_msg})
                    continue
                
                # 檢查本次同步中的重複（去重）
                if user_id in seen_user_ids:
                    add_log("bot", f"⚠️ 記錄 {i}: 在本次同步中有重複的 user_id {user_id} (已跳過)")
                    stats['duplicates'] += 1
                    continue
                
                seen_user_ids.add(user_id)
                
                # 🔧 清理記錄：移除 NULL 值，允許 DB DEFAULT 被使用
                # 這防止虛擬人物記錄（空的 kkcoin、level 等）
                cleaned_record = {}
                for key, value in record.items():
                    if value is not None:
                        cleaned_record[key] = value
                    # 移除 None 值，讓 DB DEFAULT 值被使用
                
                # 檢查用戶是否在數據庫中存在
                existing_user = self.db.get_user(user_id)
                
                if existing_user:
                    stats['updated'] += 1
                    action = "更新"
                else:
                    stats['inserted'] += 1
                    action = "新增"
                
                # 保存用戶 (db.set_user 會自動 INSERT 或 REPLACE)
                add_log("bot", f"✓ 記錄 {i}: [{action}] user_id={user_id}, 欄位數={len(cleaned_record)}")
                try:
                    success = self.db.set_user(user_id, cleaned_record)
                except Exception as set_user_exc:
                    success = False
                    add_log("bot", f"❌ set_user 拋出異常: {set_user_exc}")
                    import traceback
                    traceback.print_exc()
                
                if not success:
                    error_msg = f"set_user 返回失敗"
                    add_log("bot", f"❌ 記錄 {i}: {error_msg}")
                    stats['errors'] += 1
                    # 撤銷之前的計數
                    if action == "更新":
                        stats['updated'] -= 1
                    else:
                        stats['inserted'] -= 1
                    stats['error_details'].append({'record': i, 'user_id': user_id, 'reason': error_msg, 'data_keys': list(record.keys())})
            
            except Exception as e:
                error_msg = str(e)
                stats['errors'] += 1
                add_log("bot", f"❌ 記錄 {i} 同步失敗: {error_msg}")
                stats['error_details'].append({'record': i, 'reason': error_msg})
                import traceback
                traceback.print_exc()
        
        # 打印統計信息
        add_log("bot", f"✅ 同步記錄完成: 新增 {stats['inserted']} 個用戶, 更新 {stats['updated']} 個用戶, 重複 {stats['duplicates']} 行, 錯誤 {stats['errors']} 行")
        
        # 如果有錯誤，打印詳細信息
        if stats['error_details']:
            add_log("bot", f"📋 錯誤詳情 ({len(stats['error_details'])} 個):")
            for err in stats['error_details'][:5]:  # 只顯示前 5 個錯誤
                add_log("bot", f"   - 記錄 {err.get('record')}: {err['reason']}")
            if len(stats['error_details']) > 5:
                add_log("bot", f"   ... 還有 {len(stats['error_details']) - 5} 個錯誤")
        
        return stats
    
    def sync_records(self, records: List[Dict[str, Any]]) -> Tuple[int, int, int]:
        """
        舊版本的 sync_records 方法 (向後相容)
        
        Returns:
            (updated, inserted, errors)
        """
        stats = self._sync_records_to_db(records)
        return stats['updated'], stats['inserted'], stats['errors']
    
    # ============================================================
    # 輔助方法
    # ============================================================
    
    def _detect_user_id_col(self, headers: List[str], rows: List[List[str]]) -> Optional[int]:
        """
        自動偵測哪一欄最有可能是 user_id (Discord 用戶 ID)
        
        啟發式方法：
        - Discord user_id 通常是 18-20 位的數字
        - 或以科學計數法表示 (1e18 級別)
        """
        if not rows or not headers:
            return None
        
        col_count = len(headers)
        scores = [0] * col_count
        sample = rows[:min(200, len(rows))]
        
        for row in sample:
            for col_idx in range(col_count):
                if col_idx >= len(row):
                    continue
                
                val = str(row[col_idx]).strip()
                if not val:
                    continue
                
                # 檢查是否是長數字
                digits = ''.join(c for c in val if c.isdigit())
                if len(digits) >= 16:
                    scores[col_idx] += 1
                else:
                    # 檢查科學計數法
                    try:
                        f = float(val)
                        if f >= 1e15:
                            scores[col_idx] += 1
                    except:
                        pass
        
        if not any(scores):
            return None
        
        max_score = max(scores)
        max_idx = scores.index(max_score)
        threshold = max(1, len(sample) // 5)  # 至少 20% 命中率
        
        if max_score >= threshold:
            return max_idx
        
        return None
    
    # ============================================================
    # 清理和統計
    # ============================================================
    
    def clean_virtual_accounts(self) -> Tuple[int, int]:
        """
        清理數據庫中的虛擬帳號 (nickname 為 Unknown_*)
        
        Returns:
            (deleted_count, error_count)
        """
        try:
            all_users = self.db.get_all_users()
            
            virtual_users = [u for u in all_users if str(u.get('nickname', '')).startswith('Unknown_')]
            
            if virtual_users:
                add_log("bot", f"🧹 檢測到 {len(virtual_users)} 個虛擬帳號")
                for user in virtual_users[:5]:
                    add_log("bot", f"   - {user.get('user_id')}: {user.get('nickname')}")
                if len(virtual_users) > 5:
                    add_log("bot", f"   ... 及其他 {len(virtual_users) - 5} 個")
                
                for user in virtual_users:
                    self.db.delete_user(user['user_id'])
                
                add_log("bot", f"✅ 已刪除 {len(virtual_users)} 個虛擬帳號")
                return len(virtual_users), 0
            else:
                add_log("bot", "✅ 沒有虛擬帳號")
                return 0, 0
        
        except Exception as e:
            add_log("bot", f"❌ 清理失敗: {e}")
            return 0, 1
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取數據庫統計信息"""
        return self.db.get_stats()
    
    def export_to_json(self, filename: str) -> bool:
        """導出所有數據到 JSON"""
        return self.db.export_json(filename)
    
    def import_from_json(self, filename: str) -> bool:
        """從 JSON 導入數據"""
        return self.db.import_json(filename)
    
    def export_to_sheet_format(self) -> Tuple[List[str], List[List[str]]]:
        """導出數據為 SHEET 格式"""
        return self.db.export_to_sheet_format()
    
    def generate_hash(self, headers: List[str], records: List[Dict[str, Any]]) -> Optional[str]:
        """
        生成 SHEET 內容的 hash (用於檢測變化)
        只對關鍵欄位計算
        """
        if not records:
            return None
        
        key_fields = ['user_id', 'level', 'xp', 'kkcoin']
        data = []
        
        for record in records:
            row_data = tuple(str(record.get(f, '')) for f in key_fields)
            data.append(row_data)
        
        return hashlib.md5(str(data).encode()).hexdigest()
    
    def ensure_db_schema(self, headers: List[str]):
        """(向後相容) 確保 DB schema 包含所有表頭欄位"""
        self.db.ensure_columns(headers)


# ============================================================
# 模擬示例
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🧪 Sheet-Driven 同步系統演示")
    print("=" * 60)
    
    # 創建示例數據 (模擬 SHEET)
    mock_sheet_data = [
        ['user_id', 'nickname', 'level', 'xp', 'kkcoin', 'title', 'hp', 'stamina', 'new_field'],
        ['123456789123456789', 'Player1', '5', '1000', '5000', '武士', '100', '100', 'value1'],
        ['987654321987654321', 'Player2', '3', '500', '2000', '新手', '80', '80', 'value2'],
        ['111111111111111111', 'Unknown_Bot001', '1', '0', '0', '虛擬帳號', '100', '100', 'bot'],
    ]
    
    try:
        manager = SheetSyncManager('user_data_test.db')
        
        # 提取表頭和數據
        headers = manager.get_sheet_headers(mock_sheet_data)
        rows = manager.get_sheet_data_rows(mock_sheet_data)
        
        print(f"\n📋 表頭: {headers}")
        print(f"📊 數據行: {len(rows)} 筆\n")
        
        # 同步到 DB
        stats = manager.sync_sheet_to_db(headers, rows)
        
        # 驗證結果
        print("\n✅ 驗證:")
        db_stats = manager.get_stats()
        print(f"   - 用戶總數: {db_stats['total_users']}")
        print(f"   - 欄位總數: {db_stats['total_columns']}")
        
        # 查詢用戶
        user = manager.get_user(123456789123456789)
        if user:
            print(f"\n👤 查詢用戶 123456789123456789:")
            for k, v in list(user.items())[:5]:
                print(f"   - {k}: {v}")
        
        print("\n✅ 演示完成!")
    
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
