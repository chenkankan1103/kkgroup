"""
股市 Web API Blueprint
為前端提供虛擬股市交易的 REST 接口
"""

import os
import json
import asyncio
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import logging

# 導入數據庫和股票 API 函數
from db_adapter import (
    get_user_stocks, set_user_stocks, add_stock_position, 
    close_stock_position, get_user_total_stock_value, 
    get_user_kkcoin, update_user_kkcoin, get_all_users, 
    get_user_field
)
from utils.stock_api import fetch_price as async_fetch_price
from blueprints.discord_auth import user_sessions

# 同步包裝函數
def fetch_price(symbol: str):
    """同步包裝 async fetch_price"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(async_fetch_price(symbol))
    except Exception as e:
        logger.error(f"⚠️ 獲取 {symbol} 價格失敗: {e}")
        return None
    finally:
        loop.close()

logger = logging.getLogger(__name__)

stocks_api_bp = Blueprint('stocks_api', __name__, url_prefix='/api/stocks')


# ============================================================
# 認證裝飾器（複用 discord_auth 的 user_sessions）
# ============================================================

from functools import wraps


def require_stocks_auth(f):
    """股市 API 認證裝飾器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not auth_token or auth_token not in user_sessions:
            return jsonify({"status": "error", "message": "未認證"}), 401
        
        # 從 session 中提取用戶 ID
        user_session = user_sessions[auth_token]
        user_id = user_session.get('user_id')
        request.user_id = user_id
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================
# API 端點
# ============================================================

@stocks_api_bp.route('/portfolio', methods=['GET'])
@require_stocks_auth
def get_portfolio():
    """
    📊 獲取用戶持倉列表
    
    Returns:
        {
            "status": "success",
            "portfolio": [
                {
                    "symbol": "2330.TW",
                    "shares": 100,
                    "average_cost": 650.5,
                    "current_price": 680.0,
                    "value": 68000.0,
                    "unrealized_pnl": 2950.0,
                    "unrealized_pnl_percent": 4.54
                }
            ],
            "cash": 250000.0,
            "total_value": 318000.0,
            "total_pnl": 2950.0
        }
    """
    try:
        user_id = request.user_id
        
        # 獲取用戶持倉
        stocks = get_user_stocks(user_id) or []
        
        # 獲取用戶現金
        kkcoin = get_user_kkcoin(user_id) or 0
        
        # 轉換為前端格式
        portfolio = []
        total_value = kkcoin  # 現金部分
        total_pnl = 0
        
        for stock in stocks:
            symbol = stock.get('symbol')
            shares = stock.get('shares', 0)
            avg_cost = stock.get('average_cost', 0)
            
            # 獲取當前價格
            current_price = fetch_price(symbol) if symbol else 0
            if current_price is None:
                current_price = avg_cost  # 無法取得則用成本價
            
            value = shares * current_price if current_price else 0
            unrealized_pnl = (current_price - avg_cost) * shares if current_price else 0
            unrealized_pnl_percent = ((current_price - avg_cost) / avg_cost * 100) if avg_cost else 0
            
            portfolio.append({
                "symbol": symbol,
                "shares": shares,
                "average_cost": round(avg_cost, 2),
                "current_price": round(current_price, 2) if current_price else 0,
                "value": round(value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_percent": round(unrealized_pnl_percent, 2)
            })
            
            total_value += value
            total_pnl += unrealized_pnl
        
        return jsonify({
            "status": "success",
            "portfolio": portfolio,
            "cash": round(kkcoin, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 獲取持倉失敗: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@stocks_api_bp.route('/quotes', methods=['POST'])
@require_stocks_auth
def get_quotes():
    """
    📈 獲取股票報價
    
    Request:
        {
            "symbols": ["2330.TW", "BTC-USD", "GC=F"]
        }
    
    Returns:
        {
            "status": "success",
            "quotes": {
                "2330.TW": 680.5,
                "BTC-USD": 42500.0
            }
        }
    """
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        
        quotes = {}
        for symbol in symbols:
            price = fetch_price(symbol)
            if price:
                quotes[symbol] = round(price, 2)
        
        return jsonify({
            "status": "success",
            "quotes": quotes
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 獲取報價失敗: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@stocks_api_bp.route('/trade', methods=['POST'])
@require_stocks_auth
def execute_trade():
    """
    💱 執行交易（買入/賣出）
    
    Request:
        {
            "action": "buy" | "sell",
            "symbol": "2330.TW",
            "shares": 100,
            "price": 680.5
        }
    
    Returns:
        {
            "status": "success",
            "transaction": {
                "action": "buy",
                "symbol": "2330.TW",
                "shares": 100,
                "price": 680.5,
                "total": 68050.0,
                "fee": 170.125,
                "net_total": 68220.125
            },
            "new_cash": 181779.875,
            "portfolio_value": 249779.875
        }
    """
    try:
        user_id = request.user_id
        data = request.get_json()
        
        action = data.get('action')  # "buy" or "sell"
        symbol = data.get('symbol')
        shares = int(data.get('shares', 0))
        price = float(data.get('price', 0))
        
        if not symbol or shares <= 0 or price <= 0:
            return jsonify({"status": "error", "message": "無效的交易參數"}), 400
        
        if action not in ['buy', 'sell']:
            return jsonify({"status": "error", "message": "action 必須是 'buy' 或 'sell'"}), 400
        
        # 計算手續費（假設 0.25%）
        fee_rate = 0.0025
        total_cost = shares * price
        fee = total_cost * fee_rate
        net_total = total_cost + fee
        
        if action == 'buy':
            # 檢查現金是否充足
            kkcoin = get_user_kkcoin(user_id) or 0
            if kkcoin < net_total:
                return jsonify({
                    "status": "error",
                    "message": f"資金不足。需要: {net_total:.2f} KKB，現有: {kkcoin:.2f} KKB"
                }), 400
            
            # 執行買入
            add_stock_position(user_id, symbol, shares, price)
            update_user_kkcoin(user_id, kkcoin - net_total)
            
            new_cash = kkcoin - net_total
            
        else:  # sell
            # 檢查持倉
            stocks = get_user_stocks(user_id) or []
            position = next((s for s in stocks if s['symbol'] == symbol), None)
            
            if not position or position['shares'] < shares:
                return jsonify({
                    "status": "error",
                    "message": f"持倉不足。需要: {shares} 股，現有: {position['shares'] if position else 0} 股"
                }), 400
            
            # 執行賣出
            success, realized_pnl = close_stock_position(user_id, symbol, shares, price)
            if not success:
                return jsonify({"status": "error", "message": "賣出失敗"}), 500
            
            kkcoin = get_user_kkcoin(user_id) or 0
            new_cash = kkcoin + net_total  # 賣出所得
            update_user_kkcoin(user_id, new_cash)
        
        # 計算新的投資組合價值
        stocks = get_user_stocks(user_id) or []
        portfolio_value = new_cash
        for stock in stocks:
            s_price = fetch_price(stock['symbol'])
            if s_price:
                portfolio_value += stock['shares'] * s_price
        
        return jsonify({
            "status": "success",
            "transaction": {
                "action": action,
                "symbol": symbol,
                "shares": shares,
                "price": round(price, 2),
                "total": round(total_cost, 2),
                "fee": round(fee, 2),
                "net_total": round(net_total, 2)
            },
            "new_cash": round(new_cash, 2),
            "portfolio_value": round(portfolio_value, 2)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 交易執行失敗: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@stocks_api_bp.route('/leaderboard', methods=['GET'])
@require_stocks_auth
def get_leaderboard():
    """
    🏆 獲取損益排行榜
    
    Query params:
        - limit=10 (預設)
        - metric=pnl|return (預設: pnl)
    
    Returns:
        {
            "status": "success",
            "leaderboard": [
                {
                    "rank": 1,
                    "user_id": "123456789",
                    "username": "chen",
                    "total_pnl": 50000.0,
                    "portfolio_value": 350000.0,
                    "roi": 16.67
                }
            ]
        }
    """
    try:
        limit = int(request.args.get('limit', 10))
        metric = request.args.get('metric', 'pnl')  # 'pnl' for absolute, 'return' for ROI
        
        if limit > 100:
            limit = 100
        
        # 獲取所有用戶
        all_users = get_all_users()
        if not all_users:
            return jsonify({"status": "success", "leaderboard": []}), 200
        
        # 計算每個用戶的損益
        user_metrics = []
        for user in all_users:
            user_id = user.get('id')
            username = user.get('username', f"User_{user_id}")
            
            kkcoin = get_user_kkcoin(user_id) or 0
            stocks = get_user_stocks(user_id) or []
            
            # 計算投資組合價值
            portfolio_value = kkcoin
            total_invested = 0
            
            for stock in stocks:
                shares = stock.get('shares', 0)
                avg_cost = stock.get('average_cost', 0)
                
                current_price = fetch_price(stock['symbol'])
                if current_price is None:
                    current_price = avg_cost
                
                value = shares * current_price if current_price else 0
                portfolio_value += value
                total_invested += shares * avg_cost
            
            # 計算損益
            total_pnl = portfolio_value - (total_invested + kkcoin)
            roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0
            
            user_metrics.append({
                "user_id": user_id,
                "username": username,
                "total_pnl": round(total_pnl, 2),
                "portfolio_value": round(portfolio_value, 2),
                "roi": round(roi, 2)
            })
        
        # 排序
        if metric == 'pnl':
            user_metrics.sort(key=lambda x: x['total_pnl'], reverse=True)
        else:  # 'return'
            user_metrics.sort(key=lambda x: x['roi'], reverse=True)
        
        # 添加排名並截取前 limit 個
        leaderboard = [
            {**user, "rank": idx + 1}
            for idx, user in enumerate(user_metrics[:limit])
        ]
        
        return jsonify({
            "status": "success",
            "leaderboard": leaderboard
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 獲取排行榜失敗: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@stocks_api_bp.route('/health', methods=['GET'])
def health_check():
    """健康檢查"""
    return jsonify({
        "status": "ok",
        "service": "stocks_api",
        "timestamp": datetime.utcnow().isoformat()
    }), 200
