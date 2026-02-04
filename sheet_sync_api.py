"""
Flask API 伺服器 - 提供 Google Sheets 同步介面
允許 Google Apps Script 或其他用戶端透過 HTTP 呼叫同步函數
"""

from flask import Flask, request, jsonify
import json
import sys
import os
from datetime import datetime

# 匯入同步管理器
from sheet_sync_manager import SheetSyncManager

app = Flask(__name__)

# 初始化同步管理器
sync_manager = SheetSyncManager('user_data.db')

# ============================================================
# API 端點
# ============================================================

@app.route('/api/sync', methods=['POST'])
def api_sync_sheet():
    """
    同步 Google Sheets 資料到資料庫
    
    請求體格式:
    {
        "headers": ["user_id", "nickname", "level", "kkcoin", ...],
        "rows": [
            ["123456789", "Player1", "5", "1000", ...],
            ["987654321", "Player2", "3", "500", ...],
            ...
        ]
    }
    
    傳回:
    {
        "status": "success|error",
        "message": "...",
        "stats": {
            "updated": int,
            "inserted": int,
            "errors": int,
            "total_parsed": int
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "請求體為空或不是有效的 JSON"
            }), 400
        
        headers = data.get('headers', [])
        rows = data.get('rows', [])
        
        print(f"\n{'='*60}")
        print(f"📥 [API 同步請求] 時間: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        print(f"📋 表頭 ({len(headers)} 列): {headers[:5]}...")
        print(f"📊 資料行: {len(rows)} 筆")
        
        if not headers:
            return jsonify({
                "status": "error",
                "message": "表頭不能為空"
            }), 400
        
        if not rows:
            return jsonify({
                "status": "success",
                "message": "沒有資料行要同步",
                "stats": {
                    "updated": 0,
                    "inserted": 0,
                    "errors": 0,
                    "total_parsed": 0
                }
            }), 200
        
        # 1. 確保 DB schema（自動新增缺失的欄位）
        print(f"\n🔧 確保 DB schema...")
        sync_manager.ensure_db_schema(headers)
        
        # 2. 解析記錄
        print(f"\n📝 解析記錄...")
        records = sync_manager.parse_records(headers, rows)
        print(f"✅ 解析完成: {len(records)} 筆有效記錄")
        
        # 3. 同步到 DB
        print(f"\n📤 同步到 DB...")
        updated, inserted, errors = sync_manager.sync_records(records)
        
        result = {
            "status": "success",
            "message": f"同步完成: 更新 {updated} 筆，新增 {inserted} 筆，錯誤 {errors} 筆",
            "stats": {
                "updated": updated,
                "inserted": inserted,
                "errors": errors,
                "total_parsed": len(records)
            }
        }
        
        print(f"\n✅ API 同步完成")
        print(f"{'='*60}\n")
        
        return jsonify(result), 200
    
    except Exception as e:
        print(f"\n❌ API 同步失敗: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        
        return jsonify({
            "status": "error",
            "message": f"同步失敗: {str(e)}",
            "stats": {
                "updated": 0,
                "inserted": 0,
                "errors": 1,
                "total_parsed": 0
            }
        }), 500


@app.route('/api/health', methods=['GET'])
def api_health():
    """健康檢查端點"""
    return jsonify({
        "status": "ok",
        "message": "Sheet Sync API 運行中",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """取得資料庫統計資訊"""
    try:
        import sqlite3
        conn = sqlite3.connect('user_data.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE nickname NOT LIKE 'Unknown_%'")
        real_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(kkcoin) FROM users WHERE nickname NOT LIKE 'Unknown_%'")
        total_kkcoin = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE nickname LIKE 'Unknown_%'")
        virtual_accounts = cursor.fetchone()[0]
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            "status": "ok",
            "stats": {
                "total_users": total_users,
                "real_users": real_users,
                "virtual_accounts": virtual_accounts,
                "total_kkcoin": total_kkcoin,
                "total_columns": len(columns),
                "columns": columns[:10]  # 只顯示前 10 列
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/clean-virtual', methods=['POST'])
def api_clean_virtual():
    """清理虛擬帳號（Apps Script 呼叫）"""
    try:
        deleted, errors = sync_manager.clean_virtual_accounts()
        
        return jsonify({
            "status": "success" if errors == 0 else "warning",
            "message": f"清理完成: 刪除 {deleted} 筆虛擬帳號",
            "stats": {
                "deleted": deleted,
                "errors": errors
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================
# 啟動
# ============================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Sheet Sync API 啟動中...")
    print("="*60)
    print("📍 介面:")
    print("   POST   /api/sync          - 同步 SHEET 資料到 DB")
    print("   GET    /api/health        - 健康檢查")
    print("   GET    /api/stats         - 資料庫統計")
    print("   POST   /api/clean-virtual - 清理虛擬帳號")
    print("="*60 + "\n")
    
    # 開發模式：監聽 0.0.0.0:5000（允許遠端存取）
    app.run(host='0.0.0.0', port=5000, debug=True)
