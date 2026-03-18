#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 KKCoin 統一 API 伺服器
整合統計 API + Google Sheets 同步 API
"""

import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime
import logging

# 載入環境變數
load_dotenv()

# 建立 Flask 應用
app = Flask(__name__)

# 啟用 CORS
CORS(app)

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# 註冊 Blueprints
# ============================================================

from blueprints.stats import stats_bp
from blueprints.sheets import sheets_bp

app.register_blueprint(stats_bp)
app.register_blueprint(sheets_bp)

# ============================================================
# 全局錯誤處理器
# ============================================================

@app.errorhandler(Exception)
def handle_exception(e):
    """捕捉所有未處理的異常，返回 JSON"""
    logger.error(f"❌ 未捕捉的異常: {e}")
    import traceback
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
# 根路由
# ============================================================

@app.route('/', methods=['GET'])
def index():
    """API 根路由"""
    return jsonify({
        "status": "ok",
        "service": "KKCoin Unified API",
        "version": "2.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "endpoints": {
            "stats": {
                "GET /api/stats": "即時統計數據",
                "GET /api/stats/detailed": "詳細統計（包含玩家排名）",
                "GET /api/config": "前端配置"
            },
            "sheets": {
                "POST /api/sync": "同步 Google Sheets 資料到 DB",
                "GET|POST /api/export": "導出 DB 資料為 Sheets 格式",
                "POST /api/clean-virtual": "清理虛擬帳號",
                "GET /api/user/<id>": "取得用戶資料",
                "PUT /api/user/<id>": "更新用戶資料"
            },
            "system": {
                "GET /api/health": "健康檢查"
            }
        }
    }), 200


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({
        "status": "ok",
        "service": "KKCoin Unified API",
        "version": "2.0",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }), 200


# ============================================================
# 啟動伺服器
# ============================================================

if __name__ == '__main__':
    # 開發環境設置
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    host = os.getenv('API_HOST', '127.0.0.1')
    port = int(os.getenv('API_PORT', 5000))
    
    print(f"\n{'='*60}")
    print(f"🚀 KKCoin 統一 API 伺服器啟動")
    print(f"{'='*60}")
    print(f"📍 位置: {host}:{port}")
    print(f"🔧 Debug: {debug_mode}")
    print(f"📡 可用服務:")
    print(f"   ✅ 統計 API        (/api/stats, /api/stats/detailed)")
    print(f"   ✅ Sheets 同步 API (/api/sync, /api/export)")
    print(f"   ✅ 用戶管理 API    (/api/user/...)")
    print(f"   ✅ 系統監控       (/api/health)")
    print(f"{'='*60}\n")
    
    app.run(host=host, port=port, debug=debug_mode, threaded=True)
