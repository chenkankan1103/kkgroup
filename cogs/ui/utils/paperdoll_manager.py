# -*- coding: utf-8 -*-
"""
紙娃娃管理器 - 統一的楓之谷角色配置模組

負責：
- 預設角色配置（男/女）
- 隨機角色配置生成
- MapleStory API URL 建構
- 角色數據驗證

使用方式：
    from cogs.ui.utils.paperdoll_manager import (
        get_random, get_defaults, build_api_url, validate,
        MALE_DEFAULT, FEMALE_DEFAULT
    )
"""

import random
import json
import base64
import os
from typing import Optional, Dict, Any

# ============================================================
# 常數：預設角色配置（所有值皆為字串，與資料庫一致）
# ============================================================

MALE_DEFAULT: Dict[str, Any] = {
    'face':      '20005',
    'hair':      '30120',
    'skin':      '12000',
    'top':       '1040014',
    'bottom':    '1060096',
    'shoes':     '1072005',
    'gender':    'male',
    'is_stunned': 0,
}

FEMALE_DEFAULT: Dict[str, Any] = {
    'face':      '21731',
    'hair':      '34410',
    'skin':      '12000',
    'top':       '1041004',
    'bottom':    '1061008',
    'shoes':     '1072005',
    'gender':    'female',
    'is_stunned': 0,
}

# ============================================================
# 常數：隨機生成時使用的部件 ID 候選列表（整數，生成時轉字串）
# ============================================================

CHARACTER_VARIATIONS: Dict[str, list] = {
    'face':   [20000, 20001, 20005, 20100, 20400, 20402, 20405],
    'hair':   [30000, 30030, 30120, 30220, 30260, 30300, 30320],
    'skin':   [10000, 10001, 10002, 12000, 12100],
    'top':    [1040010, 1040014, 1041002, 1040060, 1042003],
    'bottom': [1060002, 1060096, 1060127, 1061112],
    'shoes':  [1072005, 1072014, 1072267, 1072410],
}

# MapleStory API 基底網址
MAPLESTORY_API_BASE = "https://maplestory.io/api/character"

# ============================================================
# 公開 API
# ============================================================

def get_defaults(gender: str = 'male') -> Dict[str, Any]:
    """
    取得指定性別的預設角色配置（所有值為字串）。

    Args:
        gender: 'male' 或 'female'

    Returns:
        預設角色配置的副本，避免外部修改污染常數。
    """
    return FEMALE_DEFAULT.copy() if gender == 'female' else MALE_DEFAULT.copy()


def get_random(preserve_gender: Optional[str] = None) -> Dict[str, Any]:
    """
    生成隨機角色配置。

    Args:
        preserve_gender: 指定性別 ('male'/'female')；None 則隨機選擇。

    Returns:
        包含角色配置的字典，所有部件值皆為字串（與資料庫一致）。
    """
    return {
        'face':      str(random.choice(CHARACTER_VARIATIONS['face'])),
        'hair':      str(random.choice(CHARACTER_VARIATIONS['hair'])),
        'skin':      str(random.choice(CHARACTER_VARIATIONS['skin'])),
        'top':       str(random.choice(CHARACTER_VARIATIONS['top'])),
        'bottom':    str(random.choice(CHARACTER_VARIATIONS['bottom'])),
        'shoes':     str(random.choice(CHARACTER_VARIATIONS['shoes'])),
        'is_stunned': 0,
        'gender':    preserve_gender if preserve_gender else random.choice(['male', 'female']),
    }


def build_api_url(
    user_data: Dict[str, Any],
    pose: str = 'stand1',
    preview_item: Optional[Dict] = None,
    region: str = 'TWMS',
    version: str = '256',
    include_accessories: bool = False,
    resize: int = 3,
    flip_x: bool = True,
) -> Optional[str]:
    """
    建構 MapleStory 角色圖片 API URL。

    Args:
        user_data:           用戶角色數據（支援字串或整數值）。
        pose:                動作姿勢名稱，例如 'stand1'、'prone'、'walk1'。
                             若角色處於眩暈狀態 (is_stunned=1) 且 pose='stand1'，
                             會自動改為 'prone'。
        preview_item:        預覽裝備，格式 {'id': int, 'category': str}。
                             可用於商店試穿功能，會取代對應部位。
        region:              MapleStory 伺服器區域，'TWMS' 或 'GMS'。
        version:             版本號字串，例如 '256'、'217'。
        include_accessories: True 時加入帽子、臉部配件、耳環、手套等附屬裝備。
        resize:              圖片縮放倍率（整數）。
        flip_x:              True 時水平翻轉角色。

    Returns:
        API URL 字串；發生任何例外時回傳 None。
    """
    try:
        def _to_int(val: Any, default: int) -> int:
            """安全轉換為整數，失敗時使用預設值。"""
            try:
                return int(val) if val else default
            except (ValueError, TypeError):
                return default

        # ── 核心部件 ──────────────────────────────────────────
        face_id   = _to_int(user_data.get('face'),   20005)
        hair_id   = _to_int(user_data.get('hair'),   30120)
        skin_id   = _to_int(user_data.get('skin'),   12000)  # 皮膚色 ID（必須）
        # 支援 overall（整套服）優先於 top
        top_id    = _to_int(user_data.get('overall') or user_data.get('top'), 1040014)
        bottom_id = _to_int(user_data.get('bottom'), 1060096)
        shoes_id  = _to_int(user_data.get('shoes'),  1072005)

        # ── 眩暈狀態自動調整姿勢 ──────────────────────────────
        is_stunned = user_data.get('is_stunned', 0) == 1
        if pose == 'stand1' and is_stunned:
            pose = 'prone'

        # ── 建立部件列表 ──────────────────────────────────────
        # MapleStory API：skinId 必須包含（決定膚色/臉部外觀）
        items: list = [
            {"itemId": skin_id},  # 🎯 皮膚色（必須包含，否則無法正確渲染臉部）
            {"itemId": face_id, **({"animationName": "stunned"} if is_stunned else {})},
            {"itemId": hair_id},
            {"itemId": top_id},
            {"itemId": bottom_id},
            {"itemId": shoes_id},
        ]

        # ── 附屬裝備（商店試穿等場景使用）────────────────────
        if include_accessories:
            for field in ('hat', 'face_accessory', 'eye_decoration', 'earrings', 'glove'):
                val = _to_int(user_data.get(field), 0)
                if val:
                    items.append({"itemId": val, "region": region, "version": version})

        # ── 預覽裝備替換（試穿功能）──────────────────────────
        if preview_item:
            _apply_preview_item(items, user_data, preview_item, region, version)

        # 移除 itemId 為 0 的部件（無效項目）
        items = [it for it in items if it.get('itemId', 0)]

        # ── 組合 URL ──────────────────────────────────────────
        item_path = ",".join(json.dumps(it, separators=(',', ':')) for it in items)
        flip_param = str(flip_x).lower()
        params = (
            f"showears=false&showLefEars=false&showHighLefEars=false"
            f"&resize={resize}&flipX={flip_param}"
        )
        
        # 使用舊的 API 格式：/api/character/{items}/{animation}/animated
        # 其中 items 包含 skin_id 作為第一個 item
        maplestory_url = f"https://maplestory.io/api/character/{item_path}/{pose}/animated?{params}"
        
        # ✅ 調試：URL 成功生成
        if maplestory_url and len(maplestory_url) > 100:
            print(f"[paperdoll_manager] ✅ MapleStory URL 生成成功 (長度: {len(maplestory_url)})")
            print(f"[paperdoll_manager]    skinId: {skin_id}, pose: {pose}")
        
        # 🔄 使用代理 URL 來解決 Discord 無法加載紙娃娃的問題
        # 原因：MapleStory API 要求 User-Agent header，Discord 沒有發送 → 403 Forbidden
        # 解決：我們的統一 API 提供代理端點，轉發請求並添加 User-Agent header
        print(f"[paperdoll_manager] 📍 即將調用 _wrap_with_proxy...")
        proxy_url = _wrap_with_proxy(maplestory_url)
        print(f"[paperdoll_manager] 📍 _wrap_with_proxy 返回: {proxy_url[:100] if proxy_url else 'None'}")
        return proxy_url

    except Exception as e:
        import traceback
        print(f"[paperdoll_manager] ❌ 構建 API URL 失敗: {e}")
        print(f"[paperdoll_manager]    數據: {user_data}")
        print(f"[paperdoll_manager]    堆棧:\n{traceback.format_exc()}")
        return None


def _wrap_with_proxy(maplestory_url: str) -> str:
    """
    將 MapleStory API URL 包裝為代理 URL
    
    使用統一 API 的代理端點轉發請求，添加必要的 User-Agent header
    來解決 Discord 無法加載紙娃娃的問題。
    
    Args:
        maplestory_url: 原始 MapleStory API URL
        
    Returns:
        代理 URL，格式：{base_url}/api/proxy/paperdoll?url=<base64_encoded_maplestory_url>
    """
    try:
        print(f"[paperdoll_manager._wrap_with_proxy] 📍 開始處理 URL (長度: {len(maplestory_url)})")
        
        # Base64 編碼原始 URL
        encoded = base64.b64encode(maplestory_url.encode()).decode()
        print(f"[paperdoll_manager._wrap_with_proxy] 📍 Base64 編碼完成 (編碼後長度: {len(encoded)})")
        
        # 優先從 config.json 取得隧道 URL
        api_url = None
        try:
            import json as json_lib
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'config', 'config.json')
            print(f"[paperdoll_manager._wrap_with_proxy] 📍 嘗試讀取 config.json: {config_path}")
            print(f"[paperdoll_manager._wrap_with_proxy] 📍 config.json 是否存在: {os.path.exists(config_path)}")
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json_lib.load(f)
                    api_url = config.get('url') or config.get('API_BASE')
                    print(f"[paperdoll_manager._wrap_with_proxy] 📍 從 config.json 取得 api_url: {api_url}")
        except Exception as e:
            print(f"[paperdoll_manager._wrap_with_proxy] ⚠️ 讀取 config.json 失敗: {e}")
            import traceback
            traceback.print_exc()
        
        # 回退到環境變數
        if not api_url:
            api_url = os.getenv('UNIFIED_API_URL')
            print(f"[paperdoll_manager._wrap_with_proxy] 📍 從環境變數取得 api_url: {api_url}")
        
        # 再回退到本地主機
        if not api_url:
            api_url = 'http://localhost:5000'
            print(f"[paperdoll_manager._wrap_with_proxy] 📍 使用預設本地主機 URL: {api_url}")
        
        proxy_url = f"{api_url}/api/proxy/paperdoll?url={encoded}"
        print(f"[paperdoll_manager._wrap_with_proxy] ✅ 最終代理 URL 已生成 (長度: {len(proxy_url)})")
        print(f"[paperdoll_manager._wrap_with_proxy] ✅ 代理 URL 預覽: {proxy_url[:150]}...")
        
        return proxy_url
    except Exception as e:
        print(f"[paperdoll_manager] ⚠️ 代理 URL 包裝失敗: {e}")
        import traceback
        print(f"[paperdoll_manager]    堆棧:\n{traceback.format_exc()}")
        # 失敗時回退到原始 URL
        return maplestory_url


def validate(user_data: Dict[str, Any]) -> bool:
    """
    驗證角色數據是否包含全部必要欄位且不為 None。

    Args:
        user_data: 角色數據字典。

    Returns:
        True 表示數據完整，False 表示缺失欄位。
    """
    required = ('face', 'hair', 'top', 'bottom', 'shoes')
    return all(user_data.get(f) is not None for f in required)


# ============================================================
# 內部輔助函式
# ============================================================

# 商店試穿分類 → 資料庫欄位名稱對照表
_CATEGORY_TO_FIELD: Dict[str, str] = {
    "Hair":             "hair",
    "Face":             "face",
    "Hat":              "hat",
    "Top":              "top",
    "Overall":          "top",
    "Bottom":           "bottom",
    "Shoes":            "shoes",
    "Face Accessory":   "face_accessory",
    "Eye Decoration":   "eye_decoration",
    "Earrings":         "earrings",
    "Glove":            "glove",
}


def _apply_preview_item(
    items: list,
    user_data: Dict[str, Any],
    preview_item: Dict,
    region: str,
    version: str,
) -> None:
    """
    將預覽裝備套用到部件列表（就地修改）。

    若對應部位已存在於 items 中，則替換；否則直接附加。
    """
    field = _CATEGORY_TO_FIELD.get(preview_item.get('category', ''))
    if not field:
        return

    preview_id = preview_item.get('id', 0)
    if not preview_id:
        return

    try:
        original_id = int(user_data.get(field) or 0)
    except (ValueError, TypeError):
        original_id = 0

    # 嘗試取代現有部件
    for item in items:
        if item.get('itemId') == original_id:
            item['itemId'] = preview_id
            return

    # 若找不到對應部件，直接附加
    items.append({"itemId": preview_id, "region": region, "version": version})
