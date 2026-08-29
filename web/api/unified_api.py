#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 KKCoin 統一 API 伺服器
整合統計 API + Google Sheets 同步 API + Discord OAuth 認證
"""

import base64
import logging
import os
from datetime import datetime, timedelta
# 載入環境變數 - 明確指定 .env 路徑確保正確加載
from pathlib import Path

import requests as req_lib
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# 定義靜態文件路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_FOLDER = os.path.join(BASE_DIR, "game", "web", "static")  # 遊戲靜態文件
WEB_PORTAL_FOLDER = os.path.join(BASE_DIR, "game", "web")  # 遊戲網頁文件
PORTAL_FOLDER = os.path.join(BASE_DIR, "..", "portal")  # portal 頁面（admin 等）

# 建立 Flask 應用，配置靜態文件和模板路徑
app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path="/static")

# Session 配置
app.secret_key = os.getenv("SESSION_SECRET", os.urandom(32).hex())
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# 啟用 CORS
CORS(app, supports_credentials=True)

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# 註冊 Blueprints
# ============================================================

from web.api.game_api import game_bp, init_game_api
from web.blueprints.discord_auth import discord_auth_bp
from web.blueprints.knowledge_api import knowledge_api_bp
from web.blueprints.sheets import sheets_bp
from web.blueprints.stats import stats_bp
from web.blueprints.stocks_api import stocks_api_bp
from web.blueprints.webhook import webhook_bp

app.register_blueprint(stats_bp)
app.register_blueprint(sheets_bp)
app.register_blueprint(discord_auth_bp)
app.register_blueprint(knowledge_api_bp)
app.register_blueprint(stocks_api_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(game_bp)

# 初始化遊戲 API
init_game_api(bot=None)

logger.info("✅ 已註冊所有 Blueprints")
logger.info("  - Stats API")
logger.info("  - Sheets API")
logger.info("  - Discord Auth API")
logger.info("  - Knowledge API")
logger.info("  - Stocks API")
logger.info("  - Webhook (GitHub 自動部署)")
logger.info("  - Game API (紙娃娃 RPG)")

# ============================================================
# 資料庫導入（用於使用者 CRUD）
# ============================================================
import sys as _sys

_sys.path.insert(0, os.path.join(BASE_DIR, "..", ".."))

try:
    from shared.db.db_adapter import (count_users, get_all_users, get_db_stats,
                                      get_user, set_user)
    from shared.db.sheet_driven_db import get_db_instance

    _db = get_db_instance("user_data.db")
    logger.info("✅ db_adapter 已載入（使用者 CRUD）")
except Exception as _e:
    logger.error(f"❌ 無法載入 db_adapter: {_e}")
    get_user = get_all_users = set_user = get_db_stats = count_users = None
    _db = None


# ============================================================
# 權限驗證裝飾器
# ============================================================
from blueprints.discord_auth import user_sessions as _discord_sessions

ADMIN_ROLE_ID = os.getenv("ADMIN_ROLE_ID", "")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _get_auth_user():
    """從 request header 提取 Discord token 並回傳 session user，失敗回傳 None"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return None
    return _discord_sessions.get(token)


def _check_api_key():
    """檢查 X-Admin-Key 備用 API Key"""
    key = request.headers.get("X-Admin-Key", "")
    return ADMIN_API_KEY and key == ADMIN_API_KEY


# ============================================================
# 輔助函數：將 user_id 轉為字串避免 JS 精度丟失
# JavaScript Number.MAX_SAFE_INTEGER = 9007199254740991（約16位）
# Discord ID 高達 18 位數，必須轉為字串傳輸
# ============================================================


def _user_id_to_str(data):
    """遞迴將字典中的 user_id 欄位轉為字串，避免 JS 大數字精度丟失"""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k == "user_id":
                logger.info(
                    f"_user_id_to_str: converting user_id {v!r} ({type(v).__name__}) to str"
                )
                result[k] = str(v)
            elif k == "user_id" and isinstance(v, (int, float)):
                result[k] = str(v)
            elif isinstance(v, dict):
                result[k] = _user_id_to_str(v)
            elif isinstance(v, list):
                result[k] = [
                    _user_id_to_str(item) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                result[k] = v
        return result
    return data


# ============================================================
# 使用者 CRUD API
# ============================================================


@app.route("/api/user/<user_id>", methods=["GET", "PUT", "DELETE"])
def api_user(user_id):
    """單一使用者查詢、更新或刪除（GET=成員, PUT/DELETE=管理員）"""
    if get_user is None:
        return jsonify({"status": "error", "message": "資料庫未連線"}), 500

    # 權限驗證
    if request.method == "GET":
        user_ok, auth_response = _check_member_or_key()
    else:
        user_ok, auth_response = _check_admin_or_key()
    if not user_ok:
        return auth_response

    if request.method == "GET":
        user = get_user(user_id)
        if user:
            return jsonify({"status": "ok", "user": _user_id_to_str(user)})
        return (
            jsonify({"status": "error", "message": f"找不到使用者 ID: {user_id}"}),
            404,
        )

    elif request.method == "PUT":
        data = request.get_json(force=True, silent=True) or {}
        try:
            if set_user(user_id, data):
                return jsonify({"status": "ok", "message": "更新成功"})
            return jsonify({"status": "error", "message": "更新失敗"}), 400
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    elif request.method == "DELETE":
        from shared.db.db_adapter import delete_user

        if delete_user(user_id):
            return jsonify({"status": "ok", "message": "已刪除"})
        return jsonify({"status": "error", "message": "刪除失敗"}), 400


def _check_member_or_key():
    """驗證群組成員或 API Key，回傳 (通過, 錯誤響應)"""
    if _check_api_key():
        return True, None
    user = _get_auth_user()
    if not user:
        return (
            False,
            jsonify({"status": "error", "message": "未認證，請先 Discord 登入"}),
            401,
        )
    if not user.get("is_member"):
        return (
            False,
            jsonify({"status": "error", "message": "你不是群組成員，無法查看"}),
            403,
        )
    return True, None


def _check_admin_or_key():
    """驗證管理員或 API Key，返回 (通過, 錯誤響應)"""
    if _check_api_key():
        return True, None
    user = _get_auth_user()
    if not user:
        return (
            False,
            jsonify({"status": "error", "message": "未認證，請先 Discord 登入"}),
            401,
        )
    if not user.get("is_member"):
        return False, jsonify({"status": "error", "message": "你不是群組成員"}), 403
    if ADMIN_ROLE_ID and ADMIN_ROLE_ID not in user.get("roles", []):
        return (
            False,
            jsonify({"status": "error", "message": "只有管理員才能修改資料"}),
            403,
        )
    return True, None


@app.route("/api/users", methods=["GET"])
def api_users_list():
    """列出所有使用者（可選 ?limit=N 和 ?offset=N）— 需群組成員"""
    if get_all_users is None:
        return jsonify({"status": "error", "message": "資料庫未連線"}), 500

    ok, err = _check_member_or_key()
    if not ok:
        return err

    try:
        limit = request.args.get("limit", type=int)
        offset = request.args.get("offset", type=int, default=0)
        all_users = get_all_users()
        if limit:
            all_users = all_users[offset : offset + limit]
        return jsonify(
            {
                "status": "ok",
                "count": len(all_users),
                "users": [_user_id_to_str(u) for u in all_users],
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/search", methods=["GET"])
def api_search_users():
    """搜尋使用者（支援 user_id / username 模糊匹配）— 需群組成員"""
    if get_all_users is None:
        return jsonify({"status": "error", "message": "資料庫未連線"}), 500

    ok, err = _check_member_or_key()
    if not ok:
        return err

    try:
        q = request.args.get("q", "").lower().strip()
        field = request.args.get("field", "").lower()
        all_users = get_all_users()
        if not q:
            return jsonify(
                {
                    "status": "ok",
                    "count": len(all_users),
                    "users": [_user_id_to_str(u) for u in all_users],
                }
            )
        results = []
        for u in all_users:
            uid = str(u.get("user_id", "")).lower()
            username = str(u.get("username", "")).lower()
            if field == "user_id":
                if uid == q:
                    results.append(u)
            elif field == "username":
                if q in username:
                    results.append(u)
            else:
                # 模糊搜尋：user_id 或 username 任一匹配
                if q in uid or q in username:
                    results.append(u)
        return jsonify(
            {
                "status": "ok",
                "count": len(results),
                "users": [_user_id_to_str(u) for u in results],
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/db/stats", methods=["GET"])
def api_db_stats():
    """資料庫統計資訊"""
    if get_db_stats is None:
        return jsonify({"status": "error", "message": "資料庫未連線"}), 500
    try:
        stats = get_db_stats()
        stats["total_users"] = count_users() if count_users else -1
        return jsonify({"status": "ok", "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
# 網頁遊戲服務 (必須在 Blueprint 之後、404 handler 之前)
# ============================================================


@app.route("/rpg-game", methods=["GET"])
@app.route("/rpg-game.html", methods=["GET"])
def serve_rpg_game():
    """提供紙娃娃 RPG 遊戲頁面"""
    rpg_game_path = os.path.join(WEB_PORTAL_FOLDER, "rpg-game.html")
    logger.info(f"嘗試加載遊戲頁面: {rpg_game_path}")
    logger.info(f"文件存在: {os.path.exists(rpg_game_path)}")
    if os.path.exists(rpg_game_path):
        with open(rpg_game_path, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    return jsonify({"error": "遊戲頁面不存在", "path": rpg_game_path}), 404


@app.route("/game.html", methods=["GET"])
@app.route("/game", methods=["GET"])
def serve_game():
    """提供遊戲首頁（指向紙娃娃 RPG）"""
    game_path = os.path.join(WEB_PORTAL_FOLDER, "rpg-game.html")
    if os.path.exists(game_path):
        with open(game_path, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    return jsonify({"error": "遊戲首頁不存在"}), 404


@app.route("/admin", methods=["GET"])
@app.route("/admin.html", methods=["GET"])
def serve_admin():
    """提供管理後台頁面"""
    admin_path = os.path.join(PORTAL_FOLDER, "admin.html")
    if os.path.exists(admin_path):
        with open(admin_path, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    return jsonify({"error": "管理頁面不存在"}), 404


@app.route("/config.json", methods=["GET"])
def serve_portal_config():
    """提供 portal 的 config.json（供 admin 頁面讀取 API_BASE）"""
    config_path = os.path.join(PORTAL_FOLDER, "config.json")
    if os.path.exists(config_path):
        return send_from_directory(PORTAL_FOLDER, "config.json")
    return jsonify({"error": "設定檔不存在"}), 404


@app.route("/static/<path:filename>", methods=["GET"])
def serve_static(filename):
    """提供靜態文件"""
    if os.path.exists(os.path.join(STATIC_FOLDER, filename)):
        return send_from_directory(STATIC_FOLDER, filename)
    return jsonify({"error": "靜態文件不存在"}), 404


@app.route("/web/<path:filename>", methods=["GET"])
def serve_web_portal(filename):
    """提供 web_portal 中的文件"""
    if os.path.exists(os.path.join(WEB_PORTAL_FOLDER, filename)):
        return send_from_directory(WEB_PORTAL_FOLDER, filename)
    return jsonify({"error": "文件不存在"}), 404


# ============================================================
# 紙娃娃代理端點（解決 Discord 無法直接載入 maplestory.io 圖片的問題）
# ============================================================


@app.route("/api/proxy/paperdoll", methods=["GET"])
def proxy_paperdoll():
    """代理 MapleStory 紙娃娃 API 請求

    Discord 無法直接載入 maplestory.io 圖片（缺少 User-Agent 會返回 403）。
    此端點接收 base64 編碼的原始 URL，代為請求並回傳圖片。
    """
    encoded_url = request.args.get("url", "")
    if not encoded_url:
        return jsonify({"error": "缺少 url 參數"}), 400

    try:
        # Base64 解碼原始 URL
        maplestory_url = base64.b64decode(encoded_url).decode("utf-8")

        # 安全性：只允許代理 maplestory.io 的 URL
        if "maplestory.io" not in maplestory_url:
            logger.warning(
                f"[proxy_paperdoll] 拒絕非 maplestory.io URL: {maplestory_url[:80]}"
            )
            return jsonify({"error": "不支援的代理目標"}), 403

        # 代理請求，加上必要的 User-Agent
        resp = req_lib.get(
            maplestory_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/gif, image/webp, image/apng, image/png, image/*",
                "Referer": "https://maplestory.io/",
            },
            timeout=15,
            stream=True,
        )

        if resp.status_code != 200:
            logger.warning(f"[proxy_paperdoll] maplestory.io 返回 {resp.status_code}")
            return jsonify({"error": f"上游返回 {resp.status_code}"}), 502

        content_type = resp.headers.get("Content-Type", "image/gif")
        return Response(resp.content, status=200, mimetype=content_type)

    except Exception as e:
        logger.error(f"[proxy_paperdoll] 錯誤: {e}")
        return jsonify({"error": "代理失敗"}), 502


# ============================================================
# 全局錯誤處理器
# ============================================================


@app.errorhandler(Exception)
def handle_exception(e):
    """捕捉所有未處理的異常，返回 JSON"""
    from werkzeug.exceptions import HTTPException

    # HTTP 異常（如 405 Method Not Allowed）應該返回原狀態碼而不是 500
    if isinstance(e, HTTPException):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": e.description,
                    "error_code": e.code,
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            e.code,
        )

    # 其他異常才返回 500
    logger.error(f"❌ 未捕捉的異常: {e}")
    import traceback

    logger.error(traceback.format_exc())

    return (
        jsonify(
            {
                "status": "error",
                "message": f"服務器內部錯誤: {str(e)}",
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat(),
            }
        ),
        500,
    )


@app.errorhandler(400)
def handle_bad_request(e):
    """處理 400 錯誤"""
    return (
        jsonify(
            {
                "status": "error",
                "message": f"請求格式錯誤: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            }
        ),
        400,
    )


@app.errorhandler(404)
def handle_not_found(e):
    """處理 404 錯誤 - 提供可用端點列表"""
    return (
        jsonify(
            {
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
                    "/api/game/*",
                    "/api/proxy/paperdoll?url=<base64>",
                ],
                "timestamp": datetime.now().isoformat(),
            }
        ),
        404,
    )


# ============================================================
# 根路由
# ============================================================


@app.route("/", methods=["GET"])
def index():
    """API 根路由"""
    return (
        jsonify(
            {
                "status": "ok",
                "service": "KKCoin Unified API",
                "version": "2.0",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "endpoints": {
                    "stats": {
                        "GET /api/stats": "即時統計數據",
                        "GET /api/stats/detailed": "詳細統計（包含玩家排名）",
                        "GET /api/config": "前端配置",
                    },
                    "sheets": {
                        "POST /api/sync": "同步 Google Sheets 資料到 DB",
                        "GET|POST /api/export": "導出 DB 資料為 Sheets 格式",
                        "POST /api/clean-virtual": "清理虛擬帳號",
                        "GET /api/user/<id>": "取得用戶資料",
                        "PUT /api/user/<id>": "更新用戶資料",
                    },
                    "system": {"GET /api/health": "健康檢查"},
                },
            }
        ),
        200,
    )


@app.route("/api/health", methods=["GET"])
def health_check():
    """健康檢查端點"""
    return (
        jsonify(
            {
                "status": "ok",
                "service": "KKCoin Unified API",
                "version": "2.0",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ),
        200,
    )


# ============================================================
# 啟動伺服器
# ============================================================

if __name__ == "__main__":
    # 開發環境設置
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", 5000))

    print(f"\n{'='*60}")
    print("🚀 KKCoin 統一 API 伺服器啟動")
    print(f"{'='*60}")
    print(f"📍 位置: {host}:{port}")
    print(f"🔧 Debug: {debug_mode}")
    print("📡 可用服務:")
    print("   ✅ 統計 API        (/api/stats, /api/stats/detailed)")
    print("   ✅ Sheets 同步 API (/api/sync, /api/export)")
    print("   ✅ 用戶管理 API    (/api/user/...)")
    print("   ✅ 系統監控       (/api/health)")
    print("   ✅ GitHub Webhook  (/webhook/github - 自動部署)")
    print("   ✅ 網頁遊戲       (/rpg-game 或 /game.html)")
    print("🎮 遊戲網址:")
    print(f"   • http://{host}:{port}/rpg-game")
    print(f"   • http://{host}:{port}/rpg-game.html")
    print(f"   • http://{host}:{port}/game.html")
    print(f"{'='*60}\n")

    app.run(host=host, port=port, debug=debug_mode, threaded=True)
