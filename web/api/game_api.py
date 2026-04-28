"""
遊戲 API 端點
提供紙娃娃遊戲所需的數據接口
"""

from flask import Blueprint, jsonify, request, send_file, redirect
import json
from typing import Optional
from db_adapter import get_user, set_user_field, get_user_field
from cogs.shop.merchant.paperdoll_system import EnhancedPaperDollSystem
import io

# 建立 Blueprint
game_bp = Blueprint('game_api', __name__, url_prefix='/api/game')

# 初始化紙娃娃系統
paperdoll_system = None

def init_game_api(bot=None):
    """
    初始化遊戲 API
    
    Args:
        bot: Discord bot 實例（可選，用於高級功能）
    """
    global paperdoll_system
    try:
        # 即使沒有 bot 也能初始化
        paperdoll_system = EnhancedPaperDollSystem(bot) if bot else None
        if paperdoll_system:
            print("✅ 遊戲 API：PaperdollSystem 已初始化")
    except Exception as e:
        print(f"⚠️ 遊戲 API：PaperdollSystem 初始化失敗: {e}")
        # 失敗時使用簡化版本（直接調用 MapleStory.io API）
        paperdoll_system = None

# ==================== 紙娃娃角色數據接口 ====================

@game_bp.route('/user/<user_id>/paperdoll', methods=['GET'])
def get_user_paperdoll(user_id: str):
    """
    獲取用戶的紙娃娃配置
    
    返回格式：
    {
        "user_id": "user_id",
        "nickname": "玩家名稱",
        "level": 99,
        "paperdoll": {
            "face": 20005,
            "hair": 30120,
            "skin": 12000,
            "top": 1040014,
            "bottom": 1060096,
            "shoes": 1072005,
            "hat": null,
            "overall": null,
            "cape": null,
            "glove": null
        },
        "is_stunned": false,
        "image_url": "/api/game/user/user_id/paperdoll/image"
    }
    """
    try:
        user = get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        paperdoll_data = {
            "face": user.get('face', 20005),
            "hair": user.get('hair', 30120),
            "skin": user.get('skin', 12000),
            "top": user.get('top', 1040014),
            "bottom": user.get('bottom', 1060096),
            "shoes": user.get('shoes', 1072005),
            "hat": user.get('hat'),
            "overall": user.get('overall'),
            "cape": user.get('cape'),
            "glove": user.get('glove'),
            "is_stunned": user.get('is_stunned', 0) == 1
        }
        
        return jsonify({
            "user_id": user_id,
            "nickname": user.get('nickname', 'Anonymous'),
            "level": user.get('level', 1),
            "paperdoll": paperdoll_data,
            "image_url": f"/api/game/user/{user_id}/paperdoll/image",
            "stats": {
                "kkcoin": user.get('kkcoin', 0),
                "experience": user.get('experience', 0),
                "achievements": user.get('achievements', 0)
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@game_bp.route('/user/<user_id>/paperdoll/image', methods=['GET'])
def get_paperdoll_image(user_id: str):
    """
    獲取用戶紙娃娃的 PNG 圖片
    
    查詢參數：
    - cache: true/false (默認: true)
    - size: small/medium/large (默認: medium)
    """
    try:
        user = get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        use_cache = request.args.get('cache', 'true').lower() == 'true'
        
        # 使用統一的 paperdoll_manager 取得圖片 URL
        try:
            from cogs.ui.utils import paperdoll_manager
            image_url = paperdoll_manager.build_api_url(user)
            # 重定向到 MapleStory.io API
            return redirect(image_url, code=302)
        except Exception as inner_e:
            return jsonify({"error": str(inner_e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@game_bp.route('/user/<user_id>/inventory', methods=['GET'])
def get_user_inventory(user_id: str):
    """
    獲取用戶的紙娃娃部位庫存
    
    返回格式：
    {
        "user_id": "user_id",
        "inventory": {
            "face": [20000, 20005, 21731],
            "hair": [30000, 30120, 34410],
            "top": [1040010, 1040014],
            ...
        }
    }
    """
    try:
        from shop_commands.merchant.paperdoll_merchant import PaperdollMerchantSystem
        
        user = get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        inventory = PaperdollMerchantSystem.get_user_inventory(user_id)
        
        return jsonify({
            "user_id": user_id,
            "inventory": inventory,
            "equipped": PaperdollMerchantSystem.get_equipped_paperdoll(user_id)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@game_bp.route('/user/<user_id>/paperdoll/change', methods=['POST'])
def change_paperdoll_part(user_id: str):
    """
    更改用戶紙娃娃的某個部位
    
    POST 數據：
    {
        "category": "face",  # hair, top, bottom, shoes 等
        "item_id": 20005
    }
    """
    try:
        data = request.get_json()
        category = data.get('category')
        item_id = data.get('item_id')
        
        if not category or item_id is None:
            return jsonify({"error": "Missing category or item_id"}), 400
        
        user = get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # 驗證 item_id 是否在庫存中
        from shop_commands.merchant.paperdoll_merchant import PaperdollMerchantSystem
        inventory = PaperdollMerchantSystem.get_user_inventory(user_id)
        
        if category not in inventory or item_id not in inventory.get(category, []):
            return jsonify({"error": f"Item {item_id} not in inventory"}), 400
        
        # 更新用戶資料
        set_user_field(user_id, category, item_id)
        
        # 返回新的紙娃娃配置
        user = get_user(user_id)
        return jsonify({
            "success": True,
            "message": f"Updated {category} to {item_id}",
            "paperdoll": {
                "face": user.get('face', 20005),
                "hair": user.get('hair', 30120),
                "skin": user.get('skin', 12000),
                "top": user.get('top', 1040014),
                "bottom": user.get('bottom', 1060096),
                "shoes": user.get('shoes', 1072005),
            },
            "image_url": f"/api/game/user/{user_id}/paperdoll/image"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== 遊戲數據統計接口 ====================

@game_bp.route('/stats/leaderboard', methods=['GET'])
def get_leaderboard():
    """
    獲取排行榜（按等級、經驗值排序）
    
    查詢參數：
    - sort_by: level/experience/kkcoin (默認: level)
    - limit: 結果數量 (默認: 10)
    """
    try:
        sort_by = request.args.get('sort_by', 'level')
        limit = int(request.args.get('limit', 10))
        
        # 從數據庫查詢（這是示意，實際需要調整）
        # 暫時返回示例數據
        return jsonify({
            "leaderboard": [
                {
                    "rank": i + 1,
                    "user_id": f"user_{i}",
                    "nickname": f"Player {i}",
                    "level": 100 - i * 5,
                    "experience": (100 - i * 5) * 1000,
                    "kkcoin": (100 - i * 5) * 500
                }
                for i in range(limit)
            ],
            "sort_by": sort_by
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@game_bp.route('/user/<user_id>/stats', methods=['GET'])
def get_user_stats(user_id: str):
    """
    獲取用戶詳細統計
    """
    try:
        user = get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "user_id": user_id,
            "stats": {
                "level": user.get('level', 1),
                "experience": user.get('experience', 0),
                "kkcoin": user.get('kkcoin', 0),
                "nickname": user.get('nickname', 'Anonymous'),
                "created_at": user.get('created_at'),
                "last_updated": user.get('updated_at')
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
