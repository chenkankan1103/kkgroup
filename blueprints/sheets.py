#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📋 Google Sheets 同步 API 模組（Blueprint）
提供 Google Sheets 同步介面
"""

from flask import Blueprint, request, jsonify
import logging
from datetime import datetime
import traceback

# 匯入同步管理器和 DB 引擎
from sheet_sync_manager import SheetSyncManager
from sheet_driven_db import SheetDrivenDB

sheets_bp = Blueprint('sheets', __name__, url_prefix='/api')

# 設置日誌
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 全局變數 - 延遲初始化（Lazy Initialization）
_sync_manager = None
_db = None

def get_sync_manager():
    """獲取同步管理器（延遲初始化）"""
    global _sync_manager
    if _sync_manager is None:
        logger.info("📥 初始化 SheetSyncManager...")
        _sync_manager = SheetSyncManager('user_data.db')
        logger.info("✅ SheetSyncManager 已初始化")
    return _sync_manager

def get_db():
    """獲取數據庫引擎（延遲初始化）"""
    global _db
    if _db is None:
        logger.info("📥 初始化 SheetDrivenDB...")
        _db = SheetDrivenDB('user_data.db')
        logger.info("✅ SheetDrivenDB 已初始化")
    return _db

# ============================================================
# Google Sheets 同步端點
# ============================================================

@sheets_bp.route('/sync', methods=['POST'])
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
        print(f"📋 表頭 ({len(headers)} 列): {headers}")
        print(f"📊 資料行: {len(rows)} 筆")
        
        # 🔍 詳細記錄前 3 行
        if rows:
            print(f"\n📋 前 3 行數據預覽:")
            for i, row in enumerate(rows[:3], 1):
                print(f"   [行 {i}] {row}")
        
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
        get_sync_manager().ensure_db_schema(headers)
        logger.info("✅ DB schema 已確保")
        
        # 2. 解析記錄
        print(f"\n📝 解析記錄...")
        records = get_sync_manager().parse_records(headers, rows)
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
        sync_stats = get_sync_manager()._sync_records_to_db(records)
        logger.info(f"✅ 同步完成: 新增 {sync_stats['inserted']}, 更新 {sync_stats['updated']}, 錯誤 {sync_stats['errors']}, 重複 {sync_stats['duplicates']}")
        
        result = {
            "status": "success",
            "message": f"同步完成: 新增 {sync_stats['inserted']} 筆，更新 {sync_stats['updated']} 筆，重複 {sync_stats['duplicates']} 筆，錯誤 {sync_stats['errors']} 筆",
            "stats": {
                "inserted": sync_stats['inserted'],
                "updated": sync_stats['updated'],
                "errors": sync_stats['errors'],
                "duplicates": sync_stats.get('duplicates', 0),
                "total_parsed": len(records)
            },
            "error_details": sync_stats.get('error_details', [])[:20],  # 只返回前 20 個錯誤
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


@sheets_bp.route('/export', methods=['GET', 'POST'])
def api_export_db():
    """
    反向同步：將數據庫數據導出為 Google Sheets 格式
    
    用途：定期從 DB 導出數據，更新 Google Sheet 上的遊戲數據（如 KK幣、等級等變化）
    
    支援按 SHEET 表頭順序導出（以 SHEET 為主）
    """
    try:
        logger.info("📤 [DB 導出] 開始導出數據庫...")
        
        print(f"\n{'='*60}")
        print(f"📤 [DB 導出] 時間: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        
        # 獲取 SHEET 的表頭順序（如果有提供）
        sheet_headers = None
        if request.method == 'POST':
            data = request.get_json() or {}
            sheet_headers = data.get('headers')
            if sheet_headers:
                logger.info(f"📋 使用提供的 SHEET 表頭順序（{len(sheet_headers)} 欄位）")
                print(f"📋 使用 SHEET 表頭順序: {sheet_headers[:5]}...")
        
        # 取得數據庫中的所有用戶數據
        db = get_db()
        
        if sheet_headers:
            # ✅ 新方式：按 SHEET 表頭順序導出
            logger.info("🔄 按 SHEET 表頭順序重新排列數據...")
            headers, rows = db.export_to_sheet_format_ordered(sheet_headers)
            print(f"✅ 按 SHEET 表頭順序導出完成")
        else:
            # ❌ 舊方式：按 DB 順序導出（向後相容）
            logger.warning("⚠️ 未提供 SHEET 表頭，使用 DB 順序導出（建議提供表頭以保持對齊）")
            headers, rows = db.export_to_sheet_format()
            print(f"⚠️ 按 DB 順序導出（需要提供 SHEET 表頭以防止欄位錯位）")
        
        logger.info(f"✅ 導出完成: {len(headers)} 欄位, {len(rows)} 行資料")
        
        print(f"✅ 導出完成:")
        print(f"   表頭: {headers[:5]}...")
        print(f"   行數: {len(rows)}")
        
        result = {
            "status": "success",
            "message": f"導出 {len(rows)} 筆用戶資料（按 {'SHEET' if sheet_headers else 'DB'} 順序）",
            "headers": headers,
            "rows": rows,
            "stats": {
                "total_rows": len(rows),
                "total_columns": len(headers),
                "exported_at": datetime.now().isoformat()
            },
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"{'='*60}\n")
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"❌ 導出失敗: {e}")
        logger.error(traceback.format_exc())
        
        return jsonify({
            "status": "error",
            "message": f"導出失敗: {str(e)}",
            "error_type": type(e).__name__,
            "timestamp": datetime.now().isoformat()
        }), 500


@sheets_bp.route('/clean-virtual', methods=['POST'])
def api_clean_virtual():
    """清理虛擬帳號（Apps Script 呼叫）"""
    try:
        deleted, errors = get_sync_manager().clean_virtual_accounts()
        
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


@sheets_bp.route('/user/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    """取得特定用戶的完整資料"""
    try:
        user = get_db().get_user(user_id)
        
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


@sheets_bp.route('/user/<int:user_id>', methods=['PUT'])
def api_update_user(user_id):
    """更新特定用戶的資料"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "請求體為空"
            }), 400
        
        success = get_db().set_user(user_id, data)
        
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
