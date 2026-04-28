#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 KKCoin 統一 API 伺服器
整合統計 API + Google Sheets 同步 API + Discord OAuth 認證
"""

import os
from flask import Flask, jsonify, request, send_from_directory, render_template_string, Response
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging
import requests
import base64
from urllib.parse import unquote

# 載入環境變數 - 明確指定 .env 路徑確保正確加載
from pathlib import Path
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

# 定義靜態文件路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_FOLDER = os.path.join(BASE_DIR, 'game', 'web', 'static')  # 遊戲靜態文件
WEB_PORTAL_FOLDER = os.path.join(BASE_DIR, 'game', 'web')  # 遊戲網頁文件

# 建立 Flask 應用，配置靜態文件和模板路徑
app = Flask(
    __name__,
    static_folder=STATIC_FOLDER,
    static_url_path='/static'
)

# Session 配置
app.secret_key = os.getenv('SESSION_SECRET', os.urandom(32).hex())
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# 啟用 CORS
CORS(app, supports_credentials=True)

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# 註冊 Blueprints
# ============================================================

from blueprints.stats import stats_bp
from blueprints.sheets import sheets_bp
from blueprints.discord_auth import discord_auth_bp
from blueprints.stocks_api import stocks_api_bp
from blueprints.webhook import webhook_bp
from api.game_api import game_bp, init_game_api

app.register_blueprint(stats_bp)
app.register_blueprint(sheets_bp)
app.register_blueprint(discord_auth_bp)
app.register_blueprint(stocks_api_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(game_bp)

# 初始化遊戲 API
init_game_api(bot=None)

logger.info("✅ 已註冊所有 Blueprints")
logger.info(f"  - Stats API")
logger.info(f"  - Sheets API")
logger.info(f"  - Discord Auth API")
logger.info(f"  - Stocks API")
logger.info(f"  - Webhook (GitHub 自動部署)")
logger.info(f"  - Game API (紙娃娃 RPG)")

# ============================================================
# 網頁遊戲服務 (必須在 Blueprint 之後、404 handler 之前)
# ============================================================

@app.route('/api/proxy/paperdoll', methods=['GET'])
def proxy_paperdoll():
    """
    紙娃娃 API 代理端點
    解決 Discord 無法加載 MapleStory API 圖片的問題
    
    原因：MapleStory API 要求 User-Agent header，Discord 沒有發送
    解決：我們充當代理，轉發請求並添加 User-Agent header
    
    使用方法：
    - 生成 MapleStory API URL
    - Base64 編碼該 URL
    - 訪問 /api/proxy/paperdoll?url=<base64_url>
    - Discord 加載此代理 URL，獲取圖片
    
    無額外出站流量（只是轉發），無下載/上傳浪費
    """
    try:
        encoded_url = request.args.get('url', '')
        if not encoded_url:
            return jsonify({'error': '缺少 url 參數'}), 400
        
        # 解碼 URL
        try:
            decoded_url = base64.b64decode(encoded_url).decode('utf-8')
        except Exception as e:
            logger.error(f"❌ Base64 解碼失敗: {e}")
            return jsonify({'error': 'Base64 解碼失敗'}), 400
        
        # 驗證 URL 來自 MapleStory API
        if not decoded_url.startswith('https://maplestory.io/'):
            logger.warning(f"⚠️ 拒絕非 MapleStory API 的 URL: {decoded_url[:50]}")
            return jsonify({'error': '只接受 MapleStory API 的 URL'}), 400
        
        logger.info(f"🔄 代理紙娃娃請求: {decoded_url[:80]}...")
        
        # 轉發到 MapleStory API，添加 User-Agent header
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(decoded_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 驗證是圖片內容
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            logger.error(f"❌ 非圖片內容類型: {content_type}")
            return jsonify({'error': '非圖片內容'}), 400
        
        # 返回圖片給 Discord，帶有緩存控制
        return Response(
            response.content,
            content_type=content_type,
            headers={
                'Cache-Control': 'public, max-age=86400',  # 緩存 1 天
                'Access-Control-Allow-Origin': '*'
            }
        )
        
    except requests.Timeout:
        logger.error(f"❌ MapleStory API 超時")
        return jsonify({'error': 'API 超時'}), 504
    except requests.RequestException as e:
        logger.error(f"❌ 代理請求失敗: {e}")
        return jsonify({'error': f'代理失敗: {str(e)[:100]}'}), 502
    except Exception as e:
        logger.error(f"❌ 代理錯誤: {e}")
        return jsonify({'error': f'代理錯誤: {str(e)[:100]}'}), 500

@app.route('/rpg-game', methods=['GET'])
@app.route('/rpg-game.html', methods=['GET'])
def serve_rpg_game():
    """提供紙娃娃 RPG 遊戲頁面"""
    rpg_game_path = os.path.join(WEB_PORTAL_FOLDER, 'rpg-game.html')
    logger.info(f"嘗試加載遊戲頁面: {rpg_game_path}")
    logger.info(f"文件存在: {os.path.exists(rpg_game_path)}")
    if os.path.exists(rpg_game_path):
        with open(rpg_game_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return jsonify({"error": "遊戲頁面不存在", "path": rpg_game_path}), 404


@app.route('/game.html', methods=['GET'])
@app.route('/game', methods=['GET'])
def serve_game():
    """提供遊戲首頁（指向紙娃娃 RPG）"""
    game_path = os.path.join(WEB_PORTAL_FOLDER, 'rpg-game.html')
    if os.path.exists(game_path):
        with open(game_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return jsonify({"error": "遊戲首頁不存在"}), 404


@app.route('/static/<path:filename>', methods=['GET'])
def serve_static(filename):
    """提供靜態文件"""
    if os.path.exists(os.path.join(STATIC_FOLDER, filename)):
        return send_from_directory(STATIC_FOLDER, filename)
    return jsonify({"error": "靜態文件不存在"}), 404


@app.route('/web/<path:filename>', methods=['GET'])
def serve_web_portal(filename):
    """提供 web_portal 中的文件"""
    if os.path.exists(os.path.join(WEB_PORTAL_FOLDER, filename)):
        return send_from_directory(WEB_PORTAL_FOLDER, filename)
    return jsonify({"error": "文件不存在"}), 404

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
    """處理 404 錯誤 - 提供可用端點列表"""
    return jsonify({
        "status": "error",
        "message": f"端點不存在: {request.path}",
        "available_endpoints": [
            "/",
            "/api/stats",
            "/api/stats/detailed",
            "/api/config",
            "/api/health",
            "/api/sync",
            "/api/export",
            "/api/clean-virtual",
            "/api/user/<id>",
            "/api/game/*"
        ],
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
    print(f"   ✅ GitHub Webhook  (/webhook/github - 自動部署)")
    print(f"   ✅ 網頁遊戲       (/rpg-game 或 /game.html)")
    print(f"🎮 遊戲網址:")
    print(f"   • http://{host}:{port}/rpg-game")
    print(f"   • http://{host}:{port}/rpg-game.html")
    print(f"   • http://{host}:{port}/game.html")
    print(f"{'='*60}\n")
    
    app.run(host=host, port=port, debug=debug_mode, threaded=True)
