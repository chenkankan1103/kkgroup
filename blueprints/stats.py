#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 統計 API 模組（Blueprint）
提供即時統計 API 端點供前端使用
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import os
import json

# 匯入資料庫適配層
from db_adapter import (
    get_all_users,
    get_central_reserve,
    get_reserve_pressure,
    get_reserve_announcement
)

stats_bp = Blueprint('stats', __name__, url_prefix='/api')

# ============================================================
# 統計 API 端點
# ============================================================

@stats_bp.route('/stats', methods=['GET'])
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


@stats_bp.route('/stats/detailed', methods=['GET'])
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


@stats_bp.route('/config', methods=['GET'])
def get_config():
    """獲取前端配置（Tunnel URL 等）"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "..", "docs", "config.json")
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
