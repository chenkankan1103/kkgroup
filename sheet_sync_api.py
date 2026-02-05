"""
Flask API 伺服器 - 提供 Google Sheets 同步介面
允許 Google Apps Script 或其他用戶端透過 HTTP 呼叫同步函數

使用新的 Sheet-Driven 數據庫引擎，支持：
1. 動態表頭識別 (SHEET Row 1 = schema 定義)
2. 自動欄位適應 (新欄位無需改代碼)
3. 通用型 API (不硬編碼特定欄位)
"""

from flask import Flask, request, jsonify
import json
import sys
import os
from datetime import datetime
import traceback
import logging

# 匯入同步管理器和 DB 引擎
from sheet_sync_manager import SheetSyncManager
from sheet_driven_db import SheetDrivenDB

app = Flask(__name__)

# 設置日誌
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 初始化同步管理器和 DB 引擎
sync_manager = SheetSyncManager('user_data.db')
db = SheetDrivenDB('user_data.db')

# ============================================================
# 全局錯誤處理器
# ============================================================

@app.errorhandler(Exception)
def handle_exception(e):
    """捕捉所有未處理的異常，返回 JSON"""
    logger.error(f"❌ 未捕捉的異常: {e}")
    logger.error(traceback.format_exc())
    
    return jsonify({
        "status": "error",
        "message": f"服務器內部錯誤: {str(e)}",
        "error_type": type(e).__name__,
        "timestamp": datetime.now().isoformat()
    }), 500

@app.errorhandler(400)
def handle_bad_request(e):
    """處理 400 錯誤"""
    return jsonify({
        "status": "error",
        "message": f"請求格式錯誤: {str(e)}",
        "timestamp": datetime.now().isoformat()
    }), 400

@app.errorhandler(404)
def handle_not_found(e):
    """處理 404 錯誤"""
    return jsonify({
        "status": "error",
        "message": f"端點不存在: {request.path}",
        "timestamp": datetime.now().isoformat()
    }), 404

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
        logger.info("📥 [API 同步請求] 開始處理")
        
        # 安全地取得 JSON
        try:
            data = request.get_json(force=True, silent=False)
        except Exception as json_err:
            logger.error(f"❌ JSON 解析失敗: {json_err}")
            return jsonify({
                "status": "error",
                "message": f"請求體不是有效的 JSON: {str(json_err)}",
                "timestamp": datetime.now().isoformat()
            }), 400
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "請求體為空"
            }), 400
        
        headers = data.get('headers', [])
        rows = data.get('rows', [])
        
        logger.info(f"📋 表頭: {len(headers)} 列, 數據: {len(rows)} 筆")
        
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
            logger.info("⚠️ 沒有資料行要同步")
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
        logger.info("✅ DB schema 已確保")
        
        # 2. 解析記錄
        print(f"\n📝 解析記錄...")
        records = sync_manager.parse_records(headers, rows)
        logger.info(f"✅ 解析完成: {len(records)} 筆有效記錄")
        print(f"✅ 解析完成: {len(records)} 筆有效記錄")
        
        if len(records) == 0:
            logger.warning("⚠️ 沒有有效的記錄（所有記錄都被過濾）")
            return jsonify({
                "status": "success",
                "message": "沒有有效的記錄",
                "stats": {
                    "updated": 0,
                    "inserted": 0,
                    "errors": 0,
                    "total_parsed": 0
                }
            }), 200
        
        # 3. 同步到 DB
        print(f"\n📤 同步到 DB...")
        updated, inserted, errors = sync_manager.sync_records(records)
        logger.info(f"✅ 同步完成: 更新 {updated}, 新增 {inserted}, 錯誤 {errors}")
        
        result = {
            "status": "success",
            "message": f"同步完成: 更新 {updated} 筆，新增 {inserted} 筆，錯誤 {errors} 筆",
            "stats": {
                "updated": updated,
                "inserted": inserted,
                "errors": errors,
                "total_parsed": len(records)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"\n✅ API 同步完成")
        print(f"{'='*60}\n")
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"❌ API 同步失敗: {e}")
        logger.error(traceback.format_exc())
        print(f"\n❌ API 同步失敗: {e}")
        print(f"{traceback.format_exc()}")
        print(f"{'='*60}\n")
        
        return jsonify({
            "status": "error",
            "message": f"同步失敗: {str(e)}",
            "error_type": type(e).__name__,
            "stats": {
                "updated": 0,
                "inserted": 0,
                "errors": 1,
                "total_parsed": 0
            },
            "timestamp": datetime.now().isoformat()
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
    """
    取得資料庫統計資訊
    使用新的 DB 引擎計算，支持任意欄位
    """
    try:
        # 使用新的 DB 引擎取得統計
        db_stats = db.get_stats()
        
        return jsonify({
            "status": "ok",
            "stats": {
                "total_users": db_stats.get('total_users', 0),
                "total_columns": db_stats.get('total_columns', 0),
                "columns": db_stats.get('columns', [])[:15],  # 顯示前 15 列
                "level_avg": db_stats.get('level_avg', 0),
                "level_max": db_stats.get('level_max', 0),
                "level_min": db_stats.get('level_min', 0),
                "xp_avg": db_stats.get('xp_avg', 0),
                "kkcoin_avg": db_stats.get('kkcoin_avg', 0),
                "kkcoin_max": db_stats.get('kkcoin_max', 0),
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


@app.route('/api/user/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    """取得特定用戶的完整資料"""
    try:
        user = db.get_user(user_id)
        
        if user is None:
            return jsonify({
                "status": "error",
                "message": f"用戶不存在: {user_id}"
            }), 404
        
        return jsonify({
            "status": "ok",
            "user": user
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/user/<int:user_id>', methods=['PUT'])
def api_update_user(user_id):
    """更新特定用戶的資料"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "請求體為空"
            }), 400
        
        success = db.set_user(user_id, data)
        
        if success:
            return jsonify({
                "status": "ok",
                "message": f"用戶 {user_id} 已更新"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"更新用戶 {user_id} 失敗"
            }), 500
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/user/<int:user_id>/<field>', methods=['GET'])
def api_get_field(user_id, field):
    """取得用戶特定欄位的值"""
    try:
        value = db.get_user_field(user_id, field)
        
        return jsonify({
            "status": "ok",
            "user_id": user_id,
            "field": field,
            "value": value
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/user/<int:user_id>/<field>', methods=['PUT'])
def api_set_field(user_id, field):
    """設置用戶特定欄位的值"""
    try:
        data = request.get_json()
        value = data.get('value') if data else None
        
        success = db.set_user_field(user_id, field, value)
        
        if success:
            return jsonify({
                "status": "ok",
                "message": f"欄位 {field} 已更新"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"更新欄位失敗"
            }), 500
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/user/<int:user_id>/<field>/add', methods=['POST'])
def api_add_field(user_id, field):
    """增加用戶特定欄位的值 (僅限數字)"""
    try:
        data = request.get_json()
        amount = data.get('amount', 0) if data else 0
        
        success = db.update_user_field(user_id, field, amount)
        
        if success:
            new_value = db.get_user_field(user_id, field)
            return jsonify({
                "status": "ok",
                "message": f"欄位 {field} 已增加 {amount}",
                "new_value": new_value
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"增加欄位失敗"
            }), 500
    
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
    print("📍 端點列表:")
    print("   POST   /api/sync                    - 同步 SHEET → DB")
    print("   GET    /api/health                  - 健康檢查")
    print("   GET    /api/stats                   - DB 統計資訊")
    print("   POST   /api/clean-virtual           - 清理虛擬帳號")
    print("   GET    /api/user/<user_id>          - 取得用戶資料")
    print("   PUT    /api/user/<user_id>          - 更新用戶資料")
    print("   GET    /api/user/<user_id>/<field>  - 取得用戶欄位")
    print("   PUT    /api/user/<user_id>/<field>  - 設置用戶欄位")
    print("   POST   /api/user/<user_id>/<field>/add - 增加用戶欄位")
    print("="*60 + "\n")
    
    # 開發模式：監聽 0.0.0.0:5000（允許遠端存取）
    app.run(host='0.0.0.0', port=5000, debug=True)
