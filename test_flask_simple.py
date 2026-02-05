#!/usr/bin/env python3
"""
簡化的 Flask 測試應用 - 用於診斷 sheet_sync_api 啟動問題
"""

import sys
import traceback
from datetime import datetime
from flask import Flask, jsonify

app = Flask(__name__)

@app.errorhandler(Exception)
def handle_exception(e):
    """捕捉所有未處理的異常，返回 JSON"""
    print(f"❌ 未捕捉的異常: {e}")
    print(traceback.format_exc())
    
    return jsonify({
        "status": "error",
        "message": f"服務器內部錯誤: {str(e)}",
        "error_type": type(e).__name__,
        "timestamp": datetime.now().isoformat()
    }), 500

@app.route('/api/health', methods=['GET'])
def health():
    """健康檢查"""
    return jsonify({
        "status": "ok",
        "message": "簡化版 API 運行中",
        "timestamp": datetime.now().isoformat()
    }), 200

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 簡化的 Flask API 啟動中...")
    print("="*60)
    print("📍 測試端點:")
    print("   GET  /api/health  - 健康檢查")
    print("="*60 + "\n")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        print(f"\n❌ 啟動失敗: {e}")
        print(traceback.format_exc())
        sys.exit(1)
