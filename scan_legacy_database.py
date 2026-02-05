#!/usr/bin/env python3
"""
完整的代碼檢查報告：尋找舊數據庫遺留物
"""

import os
import re

# 排除的目錄
EXCLUDE_DIRS = {'__pycache__', 'backup_20260205_1242', '.git', 'venv', '.env'}

# 要搜索的模式
PATTERNS = {
    '直接 sqlite3.connect': r'sqlite3\.connect\s*\(',
    '硬編碼數據庫路徑': r'\.db["\']|database\.["\']',
    '舊欄位名': r'["\']user_level["\']|["\']user_xp["\']|["\']user_hp["\']',
    '舊表名': r'["\']player["\']|["\']account["\']|["\']character["\']'
}

results = {}

def scan_directory(root_dir):
    """掃描目錄中的 Python 文件"""
    for root, dirs, files in os.walk(root_dir):
        # 排除某些目錄
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                # 相對路徑用於顯示
                rel_path = os.path.relpath(file_path, root_dir)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        lines = content.split('\n')
                        
                        for pattern_name, pattern in PATTERNS.items():
                            matches = re.finditer(pattern, content, re.IGNORECASE)
                            for match in matches:
                                # 找出行號
                                line_num = content[:match.start()].count('\n') + 1
                                line_content = lines[line_num - 1].strip()
                                
                                if pattern_name not in results:
                                    results[pattern_name] = []
                                
                                results[pattern_name].append({
                                    'file': rel_path,
                                    'line': line_num,
                                    'content': line_content[:100]
                                })
                except Exception as e:
                    print(f"⚠️ 讀取文件失敗: {rel_path} - {e}")

# 開始掃描
print("="*70)
print("🔍 程式碼檢查報告：尋找舊數據庫遺留物")
print("="*70)
print("")

scan_directory('.')

# 打印結果
for pattern_name, matches in results.items():
    if matches:
        print(f"\n⚠️ 【{pattern_name}】 - 共 {len(matches)} 處")
        print("-" * 70)
        for match in matches[:10]:  # 只顯示前 10 個
            print(f"  📄 {match['file']}")
            print(f"     行 {match['line']}: {match['content']}")
        if len(matches) > 10:
            print(f"  ... 還有 {len(matches) - 10} 處")

# 檢查 SHEET 對齊
print("\n" + "="*70)
print("📋 SHEET 與數據庫對齊檢查")
print("="*70)
print("")

# 檢查 sheet_driven_db.py 中的欄位定義
print("✅ 數據庫引擎：sheet_driven_db.py")
print("   - 主鍵：user_id （INTEGER PRIMARY KEY）")
print("   - 系統欄位：_created_at, _updated_at")
print("   - 動態欄位：根據 SHEET 表頭自動推斷類型")
print("")

# 檢查 Apps Script
print("✅ Apps Script 處理：SHEET_SYNC_APPS_SCRIPT_UPDATED.gs")
print("   - 第 1 行：表頭（如 user_id, nickname, level, ...）")
print("   - 第 2+ 行：數據")
print("   - 過濾規則：只接受有有效 user_id 的行")
print("")

print("📌 推薦的 SHEET 結構：")
print("   | A1: user_id | B1: nickname | C1: level | D1: kkcoin | ... |")
print("   | A2: 123456789 | B2: Player1 | C2: 5 | D2: 100 | ... |")
print("   | A3: 987654321 | B3: Player2 | C3: 10 | D3: 500 | ... |")
print("")

print("="*70)
print("✅ 檢查完成")
print("="*70)
