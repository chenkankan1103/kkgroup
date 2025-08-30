import sqlite3
import gspread
import time
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from oauth2client.service_account import ServiceAccountCredentials
import re

def parse_datetime_to_timestamp(date_str: str) -> int:
    """將各種日期格式轉換為 Unix 時間戳"""
    if not date_str:
        return 0
    
    date_str = str(date_str).strip()
    
    # 如果已經是數字（Unix 時間戳）
    try:
        if date_str.replace('.', '').isdigit():
            return int(float(date_str))
    except:
        pass
    
    # 嘗試解析 ISO 格式日期
    patterns = [
        '%Y-%m-%dT%H:%M:%S.%f',      # 2025-06-04T02:33:44.454156
        '%Y-%m-%dT%H:%M:%S',         # 2025-06-04T02:33:44
        '%Y-%m-%d %H:%M:%S.%f',      # 2025-06-04 02:33:44.454156
        '%Y-%m-%d %H:%M:%S',         # 2025-06-04 02:33:44
        '%Y/%m/%d %H:%M:%S',         # 2025/06/04 02:33:44
        '%Y-%m-%d',                  # 2025-06-04
        '%Y/%m/%d',                  # 2025/06/04
    ]
    
    for pattern in patterns:
        try:
            dt = datetime.strptime(date_str, pattern)
            return int(dt.timestamp())
        except ValueError:
            continue
    
    # 如果都解析不了，記錄錯誤並回傳 0
    logging.warning(f"無法解析日期格式: '{date_str}'")
    return 0

def timestamp_to_iso_string(timestamp: int) -> str:
    """將 Unix 時間戳轉換為 ISO 格式字串"""
    try:
        if timestamp <= 0:
            return datetime.now().isoformat()
        return datetime.fromtimestamp(timestamp).isoformat()
    except:
        return datetime.now().isoformat()

# 修正版的方法 - 加入您的 BidirectionalDBSheetSync 類別中

def get_sheet_data(self) -> List[Dict]:
    """讀取 Google Sheet 資料 - 支援多種日期格式"""
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
                
                # 特殊處理時間欄位
                if header in ['created_at', 'last_updated'] and value:
                    timestamp = parse_datetime_to_timestamp(value)
                    row_dict[header] = timestamp
                    logger.debug(f"轉換時間戳 {header}: '{value}' → {timestamp}")
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
        import traceback
        logger.error(f"詳細錯誤: {traceback.format_exc()}")
        return []

def update_sheet_row(self, data: Dict, row_index: int = None) -> bool:
    """更新 Google Sheet 中的單行資料 - 使用 ISO 格式日期"""
    try:
        logger.debug(f"開始更新 Sheet: {data}, 行號: {row_index}")
        
        # 獲取表頭
        headers = self.sheet.row_values(1)
        if not headers:
            logger.error("無法獲取 Sheet 表頭")
            return False
        
        logger.debug(f"Sheet 表頭: {headers}")
        
        # 準備要更新的資料
        row_data = []
        for header in headers:
            if header in data:
                if header in ['created_at', 'last_updated']:
                    # 將時間戳轉換為 ISO 格式字串
                    timestamp = data[header]
                    if isinstance(timestamp, (int, float)) and timestamp > 0:
                        iso_string = timestamp_to_iso_string(int(timestamp))
                        row_data.append(iso_string)
                        logger.debug(f"轉換時間戳輸出 {header}: {timestamp} → '{iso_string}'")
                    else:
                        iso_string = datetime.now().isoformat()
                        row_data.append(iso_string)
                        logger.debug(f"使用當前時間 {header}: '{iso_string}'")
                else:
                    row_data.append(str(data[header]))
            else:
                row_data.append('')
        
        logger.debug(f"準備寫入的資料: {row_data}")
        
        if row_index is None:
            # 新增行
            all_values = self.sheet.get_all_values()
            row_index = len(all_values) + 1
            logger.debug(f"新增資料到第 {row_index} 行")
        else:
            logger.debug(f"更新第 {row_index} 行資料")
        
        # 更新整行
        range_name = f"A{row_index}:{chr(ord('A') + len(row_data) - 1)}{row_index}"
        logger.debug(f"更新範圍: {range_name}")
        
        result = self.sheet.update(range_name, [row_data])
        logger.debug(f"Sheet 更新結果: {result}")
        
        time.sleep(0.1)  # 避免 API 限制
        
        logger.info(f"✅ 成功更新 Sheet: {data.get('user_id', 'unknown')} (第{row_index}行)")
        return True
        
    except Exception as e:
        logger.error(f"更新 Sheet 失敗 (user_id: {data.get('user_id', 'unknown')}): {e}")
        import traceback
        logger.error(f"詳細錯誤: {traceback.format_exc()}")
        return False

def bidirectional_sync(self):
    """雙向同步：DB ↔ Sheet - 修正版"""
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
            logger.debug(f"DB 資料: {user_data}")
        
        sheet_dict = {}
        for row in sheet_data:
            user_id = str(row.get("user_id", ""))
            if user_id:
                sheet_dict[user_id] = row
                logger.debug(f"Sheet 資料: {row}")
        
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
                if not sheet_row.get('created_at'):
                    sheet_row['created_at'] = self.get_current_timestamp()
                sheet_row['last_updated'] = self.get_current_timestamp()
                
                if self.update_db_row(sheet_row):
                    new_in_sheet += 1
                    self.log_sync_action("Sheet→DB", user_id, "INSERT", "新資料從 Sheet 加入 DB")
            else:
                # 比較更新時間
                try:
                    sheet_time = int(sheet_row.get('last_updated', 0))
                    db_time = int(db_row.get('last_updated', 0))
                    
                    logger.debug(f"時間比較 {user_id}: Sheet={sheet_time} ({datetime.fromtimestamp(sheet_time) if sheet_time else 'N/A'}), DB={db_time} ({datetime.fromtimestamp(db_time) if db_time else 'N/A'})")
                    
                    if sheet_time > db_time:
                        logger.info(f"⏰ Sheet 資料較新，更新到 DB: {user_id}")
                        if self.update_db_row(sheet_row):
                            sheet_to_db_updates += 1
                            self.log_sync_action("Sheet→DB", user_id, "UPDATE", 
                                               f"Sheet時間: {sheet_time}, DB時間: {db_time}")
                    elif sheet_time == 0 and db_time > 0:
                        # Sheet 時間戳為 0 但 DB 有時間戳，強制同步一次
                        logger.info(f"🔧 Sheet 時間戳無效，強制更新: {user_id}")
                        sheet_row['last_updated'] = self.get_current_timestamp()
                        if self.update_db_row(sheet_row):
                            sheet_to_db_updates += 1
                            self.log_sync_action("Sheet→DB", user_id, "FORCE_UPDATE", "Sheet 時間戳無效")
                        
                except (ValueError, TypeError) as e:
                    logger.error(f"時間戳比較錯誤 {user_id}: {e}")
                    # 如果時間戳比較失敗，強制同步
                    logger.info(f"🔧 時間戳比較失敗，強制更新: {user_id}")
                    sheet_row['last_updated'] = self.get_current_timestamp()
                    if self.update_db_row(sheet_row):
                        sheet_to_db_updates += 1
                        self.log_sync_action("Sheet→DB", user_id, "ERROR_RECOVER", str(e))
        
        # 5. DB → Sheet 同步
        logger.info("📤 DB → Sheet 同步開始...")
        for user_id, db_row in db_dict.items():
            sheet_row = sheet_dict.get(user_id)
            
            if not sheet_row:
                # DB 中的新資料
                logger.info(f"🆕 DB 中發現新資料: {user_id}")
                
                if not db_row.get('last_updated'):
                    db_row['last_updated'] = self.get_current_timestamp()
                    self.update_db_row(db_row)
                
                if self.update_sheet_row(db_row):
                    new_in_db += 1
                    self.log_sync_action("DB→Sheet", user_id, "INSERT", "新資料從 DB 加入 Sheet")
            else:
                # 比較更新時間
                try:
                    db_time = int(db_row.get('last_updated', 0))
                    sheet_time = int(sheet_row.get('last_updated', 0))
                    
                    logger.debug(f"時間比較 {user_id}: DB={db_time}, Sheet={sheet_time}")
                    
                    if db_time > sheet_time:
                        logger.info(f"⏰ DB 資料較新，更新到 Sheet: {user_id}")
                        
                        sheet_row_index = self.find_sheet_row_by_user_id(user_id)
                        
                        if self.update_sheet_row(db_row, sheet_row_index):
                            db_to_sheet_updates += 1
                            self.log_sync_action("DB→Sheet", user_id, "UPDATE", 
                                               f"DB時間: {db_time}, Sheet時間: {sheet_time}")
                        
                except (ValueError, TypeError) as e:
                    logger.error(f"時間戳比較錯誤 {user_id}: {e}")
        
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
        import traceback
        logger.error(f"詳細錯誤: {traceback.format_exc()}")
        raise

def convert_sheet_timestamps_to_unix(self):
    """將 Sheet 中的 ISO 日期格式轉換為 Unix 時間戳"""
    logger.info("🔄 開始轉換 Sheet 時間格式...")
    
    try:
        all_values = self.sheet.get_all_values()
        if not all_values:
            logger.warning("Sheet 沒有資料")
            return
        
        headers = all_values[0]
        
        # 找到時間欄位的位置
        time_columns = {}
        for i, header in enumerate(headers):
            if header in ['created_at', 'last_updated']:
                time_columns[header] = i
        
        if not time_columns:
            logger.warning("沒有找到時間欄位")
            return
        
        logger.info(f"找到時間欄位: {time_columns}")
        
        # 批量更新
        updates = []
        for row_index in range(2, len(all_values) + 1):  # 從第2行開始
            row = all_values[row_index - 1]  # 陣列索引
            
            for col_name, col_index in time_columns.items():
                if col_index < len(row):
                    original_value = row[col_index]
                    if original_value:
                        timestamp = parse_datetime_to_timestamp(original_value)
                        if timestamp > 0:
                            cell_range = f"{chr(ord('A') + col_index)}{row_index}"
                            updates.append({
                                'range': cell_range,
                                'value': str(timestamp),
                                'original': original_value
                            })
        
        logger.info(f"準備更新 {len(updates)} 個時間戳...")
        
        # 執行更新
        for i, update in enumerate(updates):
            try:
                self.sheet.update(update['range'], [[update['value']]])
                logger.debug(f"✅ 更新 {update['range']}: '{update['original']}' → {update['value']}")
                
                # 避免 API 限制
                if i % 10 == 0:
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"❌ 更新 {update['range']} 失敗: {e}")
        
        logger.info(f"🎯 時間格式轉換完成，共處理 {len(updates)} 個時間戳")
        
    except Exception as e:
        logger.error(f"轉換時間格式失敗: {e}")
        import traceback
        logger.error(f"詳細錯誤: {traceback.format_exc()}")
