#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def add_sync_flag_to_sheet():
    """手動檢查並添加 sync_flag 欄位到 Google Sheet"""
    
    # 設定你的憑證和 Sheet URL
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    
    try:
        # 連接 Google Sheet
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CREDENTIALS_JSON, scope
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        
        print("✅ 成功連接到 Google Sheet")
        
        # 檢查當前表頭
        try:
            headers = sheet.row_values(1)
            print(f"📋 當前表頭: {headers}")
        except:
            headers = []
            print("⚠️ 無法讀取表頭，可能是空白 Sheet")
        
        # 檢查是否已有 sync_flag 欄位
        if "sync_flag" in headers:
            print("✅ sync_flag 欄位已存在")
            return
        
        # 如果沒有表頭，建立完整表頭
        if not headers or len(headers) == 0:
            new_headers = [
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
                "sync_flag"
            ]
            sheet.update("A1", [new_headers])
            print(f"🆕 建立新表頭: {new_headers}")
            
        else:
            # 在現有表頭後面添加 sync_flag
            next_col_index = len(headers) + 1
            next_col_letter = chr(64 + next_col_index)  # A=65, 所以 64+1=A
            
            # 如果超過 Z，需要處理 AA, AB 等情況
            if next_col_index > 26:
                first_letter = chr(64 + (next_col_index - 1) // 26)
                second_letter = chr(64 + (next_col_index - 1) % 26 + 1)
                next_col_letter = first_letter + second_letter
            
            print(f"🔧 在第 {next_col_index} 欄 ({next_col_letter}) 添加 sync_flag")
            
            # 添加新表頭
            headers.append("sync_flag")
            sheet.update("A1", [headers])
            
            # 為現有的所有行添加預設值 'N'
            all_values = sheet.get_all_values()
            if len(all_values) > 1:  # 有資料行
                # 為每個資料行在新欄位填入 'N'
                sync_flag_values = [["N"] for _ in range(len(all_values) - 1)]
                start_row = 2  # 從第二行開始（跳過表頭）
                end_row = len(all_values)
                range_notation = f"{next_col_letter}{start_row}:{next_col_letter}{end_row}"
                
                sheet.update(range_notation, sync_flag_values)
                print(f"📝 為 {len(sync_flag_values)} 行資料添加了預設值 'N'")
            
            print(f"✅ 成功添加 sync_flag 欄位")
            print(f"📋 新表頭: {headers}")
        
        # 驗證結果
        final_headers = sheet.row_values(1)
        print(f"🔍 最終表頭: {final_headers}")
        
        if "sync_flag" in final_headers:
            sync_flag_col = final_headers.index("sync_flag") + 1
            print(f"✅ sync_flag 位於第 {sync_flag_col} 欄")
            
            # 顯示前幾行的資料作為確認
            try:
                sample_data = sheet.get_all_values()[:5]  # 只取前5行
                print("\n📊 前5行資料預覽:")
                for i, row in enumerate(sample_data):
                    print(f"  第 {i+1} 行: {row}")
            except:
                print("⚠️ 無法讀取資料預覽")
        
    except Exception as e:
        print(f"❌ 操作失敗: {e}")
        return False
    
    return True

def check_sheet_structure():
    """檢查 Sheet 結構"""
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CREDENTIALS_JSON, scope
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        
        print("=== Sheet 結構檢查 ===")
        
        # 檢查表頭
        headers = sheet.row_values(1)
        print(f"表頭 ({len(headers)} 個欄位): {headers}")
        
        # 檢查總行數
        all_values = sheet.get_all_values()
        print(f"總行數: {len(all_values)} (含表頭)")
        print(f"資料行數: {len(all_values) - 1}")
        
        # 檢查每欄的資料狀況
        if len(all_values) > 1:
            print("\n各欄位的資料預覽 (第2行):")
            second_row = all_values[1] if len(all_values) > 1 else []
            for i, (header, value) in enumerate(zip(headers, second_row), 1):
                print(f"  第 {i} 欄 '{header}': '{value}'")
        
        # 特別檢查 sync_flag 欄位
        if "sync_flag" in headers:
            sync_col_index = headers.index("sync_flag") + 1
            print(f"\n🚩 sync_flag 位於第 {sync_col_index} 欄")
            
            # 檢查 sync_flag 欄位的值
            sync_flag_values = sheet.col_values(sync_col_index)[1:]  # 跳過表頭
            unique_values = set(sync_flag_values)
            print(f"sync_flag 可能的值: {unique_values}")
            
            y_count = sync_flag_values.count('Y')
            n_count = sync_flag_values.count('N')
            empty_count = sync_flag_values.count('')
            
            print(f"  'Y' (需要同步): {y_count} 行")
            print(f"  'N' (不需同步): {n_count} 行")
            print(f"  空值: {empty_count} 行")
        else:
            print("\n❌ 未發現 sync_flag 欄位")
        
    except Exception as e:
        print(f"檢查失敗: {e}")

def set_test_sync_flag():
    """設定測試用的 sync_flag"""
    CREDENTIALS_JSON = "kkgroup-0441c30231b7.json"
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
    
    try:
        scope = [
            "https://spreadsheets.google.com/feeds", 
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CREDENTIALS_JSON, scope
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        
        headers = sheet.row_values(1)
        if "sync_flag" not in headers:
            print("❌ sync_flag 欄位不存在，請先執行 add_sync_flag_to_sheet()")
            return
        
        sync_col_index = headers.index("sync_flag") + 1
        
        # 將第2行的 sync_flag 設為 'Y' (測試用)
        sheet.update_cell(2, sync_col_index, 'Y')
        print("✅ 已將第2行的 sync_flag 設為 'Y' (測試用)")
        
        # 確認結果
        test_value = sheet.cell(2, sync_col_index).value
        print(f"🔍 確認第2行 sync_flag = '{test_value}'")
        
    except Exception as e:
        print(f"設定失敗: {e}")

if __name__ == "__main__":
    print("Google Sheet sync_flag 欄位管理工具")
    print("=" * 40)
    
    while True:
        print("\n請選擇操作:")
        print("1. 檢查 Sheet 結構")
        print("2. 添加 sync_flag 欄位")
        print("3. 設定測試 sync_flag")
        print("4. 退出")
        
        choice = input("\n輸入選項 (1-4): ").strip()
        
        if choice == "1":
            check_sheet_structure()
        elif choice == "2":
            add_sync_flag_to_sheet()
        elif choice == "3":
            set_test_sync_flag()
        elif choice == "4":
            print("再見！")
            break
        else:
            print("無效選項，請重新選擇")
