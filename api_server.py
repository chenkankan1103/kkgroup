#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 KKCoin API Server
提供即時統計 API 端點供前端使用
"""

import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 匯入資料庫適配層
from db_adapter import (
    get_all_users,
    get_central_reserve,
    get_reserve_pressure,
    get_reserve_announcement
)

app = Flask(__name__)
# 啟用 CORS，允許前端跨域請求
CORS(app)

# ============================================================
# API 端點
# ============================================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    獲取即時統計數據
    
    Returns:
    {
        "total_traders": 玩家總數,
        "total_volume": 交易總量,
        "active_traders": 有 KKCoin 的活躍玩家,
        "reserve": 儲備金餘額,
        "reserve_pressure": 儲備金壓力 (0-100),
        "reserve_announcement": 儲備金公告,
        "timestamp": ISO 時間戳
    }
    """
    try:
        all_users = get_all_users()
        
        # 計算統計數據
        total_traders = len(all_users)
        total_volume = sum(float(u.get('kkcoin', 0) or 0) for u in all_users)
        active_traders = len([u for u in all_users if float(u.get('kkcoin', 0) or 0) > 0])
        
        reserve = get_central_reserve()
        reserve_pressure = get_reserve_pressure()
        reserve_announcement = get_reserve_announcement()
        
        from datetime import datetime
        
        return jsonify({
            "status": "success",
            "data": {
                "total_traders": total_traders,
                "total_volume": int(total_volume),
                "active_traders": active_traders,
                "reserve": int(reserve),
                "reserve_pressure": float(reserve_pressure),
                "reserve_announcement": reserve_announcement,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }), 200
    
    except Exception as e:
        print(f"❌ 獲取統計數據失敗: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@app.route('/api/stats/detailed', methods=['GET'])
def get_stats_detailed():
    """
    獲取詳細統計數據（包含用戶信息）
    """
    try:
        all_users = get_all_users()
        
        # 構建用戶統計
        users_by_balance = []
        for u in all_users:
            kkcoin = float(u.get('kkcoin', 0) or 0)
            digital_usd = float(u.get('digital_usd', 0) or 0)
            if kkcoin > 0 or digital_usd > 0:
                users_by_balance.append({
                    "user_id": u.get('user_id'),
                    "kkcoin": kkcoin,
                    "digital_usd": digital_usd,
                    "total_assets": kkcoin + (digital_usd / 35)  # 轉換匯率
                })
        
        # 按總資產排序
        users_by_balance.sort(key=lambda x: x['total_assets'], reverse=True)
        
        return jsonify({
            "status": "success",
            "data": {
                "total_users": len(all_users),
                "active_users": len(users_by_balance),
                "top_users": users_by_balance[:10],
                "reserve": int(get_central_reserve()),
                "reserve_pressure": float(get_reserve_pressure())
            }
        }), 200
    
    except Exception as e:
        print(f"❌ 獲取詳細統計失敗: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({
        "status": "ok",
        "service": "KKCoin API Server",
        "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
    }), 200


@app.route('/api/config', methods=['GET'])
def get_config():
    """獲取前端配置（Tunnel URL 等）"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "docs", "config.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return jsonify({
            "status": "success",
            "data": config
        }), 200
    
    except Exception as e:
        print(f"❌ 獲取配置失敗: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# ============================================================
# 錯誤處理
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "error": "Endpoint not found"
    }), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({
        "status": "error",
        "error": "Internal server error"
    }), 500


# ============================================================
# 啟動伺服器
# ============================================================

if __name__ == '__main__':
    # 開發環境設置
    debug_mode = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    host = os.getenv('API_HOST', '127.0.0.1')
    port = int(os.getenv('API_PORT', 5000))
    
    print(f"\n{'='*60}")
    print(f"🚀 KKCoin API 伺服器啟動")
    print(f"{'='*60}")
    print(f"📍 位置: {host}:{port}")
    print(f"🔧 Debug: {debug_mode}")
    print(f"📡 可用端點:")
    print(f"   - GET  /api/stats          (即時統計)")
    print(f"   - GET  /api/stats/detailed (詳細統計)")
    print(f"   - GET  /api/config         (前端配置)")
    print(f"   - GET  /api/health         (健康檢查)")
    print(f"{'='*60}\n")
    
    app.run(host=host, port=port, debug=debug_mode, threaded=True)
