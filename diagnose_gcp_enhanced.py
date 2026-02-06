#!/usr/bin/env python3
"""
GCP Discord ID 完整診斷工具 - 增強版
支持詳細診斷和自動修正
"""

import sqlite3
import json
import base64
from datetime import datetime
from pathlib import Path

DB_PATH = './user_data.db'
REPORT_DIR = Path('/tmp/kk_reports')
REPORT_DIR.mkdir(exist_ok=True)

def diagnose():
    """執行完整診斷"""
    result = {
        'timestamp': datetime.now().isoformat(),
        'status': 'success',
        'data': {}
    }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 基本統計
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        
        # 獲取所有用戶
        cursor.execute("SELECT user_id, nickname FROM users ORDER BY user_id DESC")
        users = cursor.fetchall()
        
        short_ids = []
        valid_ids = []
        test_patterns = ['test', 'Test', 'TEST', 'Player', 'TestA', 'TestB']
        
        for user_id, nick in users:
            if user_id < 100000000000000000:
                short_ids.append({'id': user_id, 'nick': nick})
            else:
                valid_ids.append({'id': user_id, 'nick': nick})
        
        result['data'] = {
            'total_users': total,
            'valid_users': len(valid_ids),
            'invalid_ids': len(short_ids),
            'valid_list': valid_ids,
            'invalid_list': short_ids,
        }
        
        conn.close()
        
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
    
    return result

def print_report(result):
    """打印報告"""
    print("\n" + "="*70)
    print("📊 GCP Discord ID 診斷報告")
    print("="*70)
    
    if result['status'] != 'success':
        print(f"❌ 錯誤: {result.get('error', '未知錯誤')}")
        return
    
    data = result['data']
    print(f"\n總用戶數: {data['total_users']}")
    print(f"有效ID: {data['valid_users']}")
    print(f"無效/短ID: {data['invalid_ids']}")
    
    if data['valid_list']:
        print(f"\n✅ 有效用戶 ({len(data['valid_list'])})")
        print("-" * 70)
        for u in data['valid_list']:
            nick = (u['nick'] or '(無昵稱)')[:40]
            print(f"  {u['id']:>20} | {nick:<40}")
    
    if data['invalid_list']:
        print(f"\n❌ 無效用戶/短ID ({len(data['invalid_list'])})")
        print("-" * 70)
        for u in data['invalid_list']:
            nick = (u['nick'] or '(無昵稱)')[:40]
            print(f"  {u['id']:>20} | {nick:<40}")

if __name__ == '__main__':
    result = diagnose()
    print_report(result)
    
    # 保存 JSON 報告
    report_file = REPORT_DIR / 'diagnosis.json'
    with open(report_file, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 保存 Base64 編碼版本（便於 SSH 傳輸）
    b64_content = base64.b64encode(json.dumps(result).encode()).decode()
    b64_file = REPORT_DIR / 'diagnosis.b64'
    with open(b64_file, 'w') as f:
        f.write(b64_content)
    
    print(f"\n✅ 報告已保存到: {report_file}")
    print(f"📝 Base64 版本: {b64_file}")
