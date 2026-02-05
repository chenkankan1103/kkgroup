"""
✨ 改進的 Flask REST API v2.0
與 sheet_sync_manager_v2.py 配套
支持動態schema、自動欄位檢測、生產就緒

特性：
✅ 自動 schema 同步
✅ 詳細的錯誤報告
✅ 欄位診斷端點
✅ 性能監控
✅ 完整的繁體中文支持
"""

from flask import Flask, request, jsonify
from datetime import datetime
import json
import traceback
import logging

# 導入新版本的同步管理器
try:
    from sheet_sync_manager_v2 import SheetSyncManagerV2
except ImportError:
    from sheet_sync_manager import SheetSyncManager as SheetSyncManagerV2

# ============================================================
# Flask 應用設置
# ============================================================

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 支持繁體中文

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化同步管理器
sync_manager = SheetSyncManagerV2('user_data.db')

# ============================================================
# 核心同步端點
# ============================================================

@app.route('/api/sync', methods=['POST'])
def sync_from_sheet():
    """
    🎯 核心同步端點
    
    輸入:
    {
        "headers": ["user_id", "nickname", "level", ...],
        "rows": [[123456789, "玩家名", 10, ...], ...]
    }
    
    流程:
    1. 驗證輸入格式
    2. 自動確保 DB schema 與表頭匹配
    3. 解析和驗證數據
    4. 插入/更新記錄
    5. 返回統計信息
    """
    try:
        start_time = datetime.now()
        
        # 1. 解析請求
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "message": "❌ 請求體為空或格式不正確"
            }), 400
        
        headers = data.get('headers', [])
        rows = data.get('rows', [])
        
        print(f"\n{'='*60}")
        print(f"📥 收到同步請求 (時間: {datetime.now().strftime('%H:%M:%S')})")
        print(f"   表頭: {len(headers)} 列")
        print(f"   資料行: {len(rows)} 筆")
        print(f"{'='*60}")
        
        # 驗證
        if not headers or len(headers) == 0:
            return jsonify({
                "status": "error",
                "message": "❌ 表頭為空"
            }), 400
        
        if not rows or len(rows) == 0:
            return jsonify({
                "status": "warning",
                "message": "⚠️ 沒有資料行",
                "stats": {"updated": 0, "inserted": 0, "errors": 0}
            }), 200
        
        # 2. 自動同步 schema（最重要的改進）
        print(f"🔧 正在同步資料庫 Schema...")
        sync_manager.ensure_db_schema(headers)
        
        # 3. 解析記錄
        print(f"📊 正在解析 {len(rows)} 筆記錄...")
        records = sync_manager.parse_records(headers, rows)
        
        if not records:
            return jsonify({
                "status": "warning",
                "message": "⚠️ 沒有有效的記錄（所有行都被過濾）",
                "stats": {"updated": 0, "inserted": 0, "errors": len(rows)}
            }), 200
        
        # 4. 插入/更新記錄
        print(f"💾 正在插入/更新 {len(records)} 筆記錄...")
        updated, inserted, errors = sync_manager.insert_records(records)
        
        # 5. 計算耗時
        duration = (datetime.now() - start_time).total_seconds()
        
        # 6. 返回結果
        result = {
            "status": "success",
            "message": f"✅ 同步完成",
            "stats": {
                "updated": updated,
                "inserted": inserted,
                "errors": errors,
                "total_processed": updated + inserted + errors,
                "duration_seconds": round(duration, 2)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"✅ 同步成功: 更新 {updated}, 新增 {inserted}, 錯誤 {errors}")
        print(f"   耗時: {duration:.2f} 秒\n")
        
        return jsonify(result), 200
    
    except Exception as e:
        print(f"❌ 同步失敗: {e}")
        traceback.print_exc()
        
        return jsonify({
            "status": "error",
            "message": f"❌ 同步出錯: {str(e)}",
            "error_detail": traceback.format_exc()
        }), 500


# ============================================================
# 診斷端點
# ============================================================

@app.route('/api/schema', methods=['GET'])
def get_schema():
    """
    獲取當前資料庫 Schema 信息
    
    用途：診斷欄位是否正確對齊
    """
    try:
        schema = sync_manager.get_schema_info()
        
        return jsonify({
            "status": "success",
            "schema": schema,
            "message": f"✅ Schema 包含 {schema['columns']} 個欄位"
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"❌ 無法獲取 Schema: {str(e)}"
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    獲取資料庫統計信息
    """
    try:
        import sqlite3
        
        conn = sqlite3.connect('user_data.db')
        cursor = conn.cursor()
        
        # 玩家數量
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # KKCoin 總計
        cursor.execute("SELECT SUM(kkcoin) FROM users WHERE kkcoin IS NOT NULL")
        total_kkcoin = cursor.fetchone()[0] or 0
        
        # 平均等級
        cursor.execute("SELECT AVG(level) FROM users WHERE level IS NOT NULL")
        avg_level = cursor.fetchone()[0] or 0
        
        # 最高等級
        cursor.execute("SELECT MAX(level) FROM users WHERE level IS NOT NULL")
        max_level = cursor.fetchone()[0] or 0
        
        schema = sync_manager.get_schema_info()
        
        conn.close()
        
        return jsonify({
            "status": "ok",
            "stats": {
                "total_users": total_users,
                "total_kkcoin": int(total_kkcoin),
                "avg_level": round(avg_level, 2),
                "max_level": max_level,
                "total_columns": schema['columns']
            },
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"❌ 無法獲取統計資訊: {str(e)}"
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    API 健康檢查
    """
    try:
        user_count = sync_manager.get_user_count()
        schema = sync_manager.get_schema_info()
        
        return jsonify({
            "status": "ok",
            "message": "✅ API 健康，準備就緒",
            "database": {
                "file": "user_data.db",
                "users": user_count,
                "columns": schema['columns']
            },
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"❌ 資料庫連接失敗: {str(e)}"
        }), 500


# ============================================================
# 清理端點
# ============================================================

@app.route('/api/clean-virtual', methods=['POST'])
def clean_virtual_accounts():
    """
    清理虛擬帳號（Unknown_% 的記錄）
    """
    try:
        import sqlite3
        
        conn = sqlite3.connect('user_data.db')
        cursor = conn.cursor()
        
        # 刪除虛擬帳號
        cursor.execute("DELETE FROM users WHERE nickname LIKE 'Unknown_%'")
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success" if deleted > 0 else "warning",
            "message": f"✅ 清理完成，刪除 {deleted} 個虛擬帳號",
            "stats": {"deleted": deleted},
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"❌ 清理失敗: {str(e)}"
        }), 500


# ============================================================
# 輔助端點
# ============================================================

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """
    測試端點 - 用於驗證 API 是否正常運行
    """
    return jsonify({
        "status": "success",
        "message": "✅ 測試成功",
        "version": "2.0",
        "features": [
            "✅ 自動 Schema 同步",
            "✅ 智能類型推斷",
            "✅ 動態欄位檢測",
            "✅ 完整的日誌記錄",
            "✅ 詳細的錯誤報告"
        ]
    }), 200


# ============================================================
# 錯誤處理
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """404 處理"""
    return jsonify({
        "status": "error",
        "message": "❌ 端點不存在",
        "available_endpoints": [
            "POST /api/sync",
            "GET /api/schema",
            "GET /api/stats",
            "GET /api/health",
            "POST /api/clean-virtual",
            "GET /api/test"
        ]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """500 處理"""
    return jsonify({
        "status": "error",
        "message": "❌ 伺服器內部錯誤",
        "error": str(error)
    }), 500


# ============================================================
# 應用啟動
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask REST API v2.0 啟動")
    print("=" * 60)
    print("✅ 特性:")
    print("   - 自動 Schema 同步")
    print("   - 智能類型推斷")
    print("   - 動態欄位檢測")
    print("   - 完整的日誌記錄")
    print("=" * 60)
    print(f"\n📍 在 http://0.0.0.0:5000 監聽")
    print("📋 可用端點:")
    print("   POST /api/sync          - 同步 SHEET 數據")
    print("   GET  /api/schema        - 獲取 DB Schema")
    print("   GET  /api/stats         - 獲取統計信息")
    print("   GET  /api/health        - 健康檢查")
    print("   POST /api/clean-virtual - 清理虛擬帳號")
    print("   GET  /api/test          - 測試端點")
    print("\n")
    
    # 開發環境
    app.run(host='0.0.0.0', port=5000, debug=True)
    
    # 生產環境（使用 Gunicorn）
    # gunicorn -w 4 -b 0.0.0.0:5000 sheet_sync_api_v2:app
