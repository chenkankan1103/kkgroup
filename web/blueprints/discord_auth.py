"""
Discord OAuth 2.0 認證系統
支持用戶登錄、會話管理、用戶信息獲取
"""

import os
import json
import requests
from flask import Blueprint, request, jsonify, redirect
from datetime import datetime, timedelta
from functools import wraps
import logging

logger = logging.getLogger(__name__)

discord_auth_bp = Blueprint("discord_auth", __name__, url_prefix="/api/auth")

# Discord API 配置
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")
DISCORD_API_BASE = "https://discord.com/api/v10"

# 簡單的會話存儲（生產應使用 Redis 或數據庫）
user_sessions = {}


def _get_redirect_uri():
    """動態獲取 redirect URI：優先讀取 config.json 中的 tunnel URL"""
    try:
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "config.json"
        )
        config_path = os.path.abspath(config_path)
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            base_url = config.get("API_BASE") or config.get("url", "")
            if base_url:
                return f"{base_url.rstrip('/')}/api/auth/callback"
    except Exception as e:
        logger.warning(
            f"無法讀取 config.json，使用 .env 中的 DISCORD_REDIRECT_URI: {e}"
        )
    # fallback 到 .env
    return os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/api/auth/callback")


def require_auth(f):
    """認證裝飾器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not auth_token or auth_token not in user_sessions:
            return jsonify({"status": "error", "message": "未認證"}), 401
        request.user = user_sessions[auth_token]
        return f(*args, **kwargs)

    return decorated_function


@discord_auth_bp.route("/login", methods=["GET"])
def login():
    """🔐 產生 Discord OAuth 登錄 URL"""

    if not DISCORD_CLIENT_ID:
        return jsonify(
            {"status": "error", "message": "Discord 配置不完整", "oauth_url": None}
        ), 500

    redirect_uri = _get_redirect_uri()
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize?"
        f"client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=identify%20email%20guilds"
    )

    return jsonify(
        {
            "status": "success",
            "oauth_url": oauth_url,
            "message": "請複製此 URL 到瀏覽器進行認證",
        }
    ), 200


@discord_auth_bp.route("/callback", methods=["GET"])
def oauth_callback():
    """📍 Discord OAuth 回調端點"""

    code = request.args.get("code")
    state = request.args.get("state")  # 可選的狀態參數

    if not code:
        return jsonify({"status": "error", "message": "缺少授權碼"}), 400

    try:
        # 1️⃣ 交換 token
        token_data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _get_redirect_uri(),
            "scope": "identify email guilds",
        }

        response = requests.post(
            f"{DISCORD_API_BASE}/oauth2/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"❌ Token 交換失敗: {response.text}")
            return jsonify({"status": "error", "message": "無法獲取 token"}), 400

        token_info = response.json()
        access_token = token_info.get("access_token")

        # 2️⃣ 獲取用戶信息
        user_response = requests.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if user_response.status_code != 200:
            logger.error(f"❌ 用戶信息獲取失敗: {user_response.text}")
            return jsonify({"status": "error", "message": "無法獲取用戶信息"}), 400

        user_data = user_response.json()

        # 3️⃣ 獲取伺服器成員信息
        guild_id = os.getenv("GUILD_ID", "")
        member_response = requests.get(
            f"{DISCORD_API_BASE}/users/@me/guilds/{guild_id}/member",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        is_member = member_response.status_code == 200
        member_data = member_response.json() if is_member else {}

        # 4️⃣ 創建會話
        session_token = os.urandom(32).hex()
        user_sessions[session_token] = {
            "user_id": user_data.get("id"),
            "username": user_data.get("username"),
            "email": user_data.get("email"),
            "avatar": user_data.get("avatar"),
            "discriminator": user_data.get("discriminator"),
            "is_member": is_member,
            "roles": member_data.get("roles", []),
            "access_token": access_token,
            "refresh_token": token_info.get("refresh_token"),
            "token_expires": datetime.utcnow()
            + timedelta(seconds=token_info.get("expires_in", 604800)),
            "created_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"✅ 用戶認證成功: {user_data.get('username')} (ID: {user_data.get('id')})"
        )

        # 5️⃣ 重定向回遊戲或前端
        # 檢查是否是遊戲的登入（通過 referrer 或固定目標）
        redirect_url = None

        # 優先重定向到遊戲
        if request.referrer and (
            "/rpg-game" in request.referrer or "/game" in request.referrer
        ):
            redirect_url = (
                f"/rpg-game?auth_token={session_token}&user_id={user_data.get('id')}"
            )
        # 檢查是否是管理後台的登入
        elif request.referrer and "/admin" in request.referrer:
            redirect_url = f"/admin?auth_token={session_token}"
        else:
            # 預設重定向到管理後台（同一個域）
            redirect_url = (
                f"/admin?auth_token={session_token}&user={user_data.get('username')}"
            )

        return redirect(redirect_url)

    except Exception as e:
        logger.error(f"❌ OAuth 回調異常: {str(e)}")
        return jsonify({"status": "error", "message": f"認證失敗: {str(e)}"}), 500


@discord_auth_bp.route("/verify", methods=["GET"])
def verify_token():
    """✅ 驗證會話 token"""

    auth_token = request.headers.get("Authorization", "").replace("Bearer ", "")

    if not auth_token or auth_token not in user_sessions:
        return jsonify(
            {"status": "error", "authenticated": False, "message": "無效或過期的 token"}
        ), 401

    user = user_sessions[auth_token]

    return jsonify(
        {
            "status": "success",
            "authenticated": True,
            "user": {
                "id": user.get("user_id"),
                "username": user.get("username"),
                "email": user.get("email"),
                "avatar_url": f"https://cdn.discordapp.com/avatars/{user.get('user_id')}/{user.get('avatar')}.png"
                if user.get("avatar")
                else None,
                "is_member": user.get("is_member"),
                "roles": user.get("roles"),
            },
        }
    ), 200


@discord_auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    """🚪 登出（摧毀會話）"""

    auth_token = request.headers.get("Authorization", "").replace("Bearer ", "")

    if auth_token in user_sessions:
        del user_sessions[auth_token]
        logger.info(f"✅ 用戶已登出: {request.user.get('username')}")

    return jsonify({"status": "success", "message": "已登出"}), 200


@discord_auth_bp.route("/user", methods=["GET"])
@require_auth
def get_user():
    """👤 獲取當前認證用戶的信息"""

    user = request.user

    return jsonify(
        {
            "status": "success",
            "user": {
                "id": user.get("user_id"),
                "username": user.get("username"),
                "email": user.get("email"),
                "avatar_url": f"https://cdn.discordapp.com/avatars/{user.get('user_id')}/{user.get('avatar')}.png"
                if user.get("avatar")
                else None,
                "is_member": user.get("is_member"),
                "roles": user.get("roles"),
                "created_at": user.get("created_at"),
            },
        }
    ), 200


@discord_auth_bp.route("/user-info", methods=["GET"])
def get_user_info():
    """🎮 獲取用戶信息（遊戲用）- 支持 Bearer token"""

    auth_token = request.headers.get("Authorization", "").replace("Bearer ", "")

    if not auth_token or auth_token not in user_sessions:
        return jsonify({"status": "error", "message": "無效的 token"}), 401

    user = user_sessions[auth_token]

    return jsonify(
        {
            "status": "success",
            "user_id": int(user.get("user_id", 0)),  # 轉換為整數用於遊戲
            "username": user.get("username"),
            "email": user.get("email"),
            "is_member": user.get("is_member"),
        }
    ), 200


@discord_auth_bp.route("/status", methods=["GET"])
def auth_status():
    """📊 獲取認證系統狀態"""

    return jsonify(
        {
            "status": "ok",
            "service": "Discord OAuth 認證",
            "configured": bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET),
            "active_sessions": len(user_sessions),
            "endpoints": {
                "GET /api/auth/login": "獲取 OAuth URL",
                "GET /api/auth/callback": "OAuth 回調（由 Discord 調用）",
                "GET /api/auth/verify": "驗證 token 有效性",
                "POST /api/auth/logout": "登出（需要認證）",
                "GET /api/auth/user": "獲取用戶信息（需要認證）",
            },
        }
    ), 200
