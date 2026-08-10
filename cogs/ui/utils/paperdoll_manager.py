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
    "face": "20005",
    "hair": "30120",
    "skin": "12000",
    "top": "1040014",
    "bottom": "1060096",
    "shoes": "1072005",
    "gender": "male",
    "is_stunned": 0,
}

FEMALE_DEFAULT: Dict[str, Any] = {
    "face": "21731",
    "hair": "34410",
    "skin": "12000",
    "top": "1041004",
    "bottom": "1061008",
    "shoes": "1072005",
    "gender": "female",
    "is_stunned": 0,
}

# ============================================================
# 常數：從 fashion DB 動態載入的部件 ID 候選列表
# ============================================================

# 快取的 fashion DB 和部件 ID 列表（避免每次生成都讀取文件）
_FASHION_DB_CACHE = None
CHARACTER_VARIATIONS: Dict[str, list] = {}


def _extract_gender_from_name(name: str) -> Optional[str]:
    """
    從物品名稱中提取性別標籤 (male/female/None)。

    例如：
    - "黑色艾連臉型(女)" → 'female'
    - "黑色艾連臉型(男)" → 'male'
    - "黑色挑戰的臉型" → None（中性）
    """
    name_lower = name.lower()
    if "女" in name or "female" in name_lower:
        return "female"
    elif "男" in name or "male" in name_lower:
        return "male"
    return None


def _load_fashion_db():
    """
    從 twms_fashion_db.json 載入有效的物品 ID，按性別分類。
    結果會被快取以提高性能。
    """
    global _FASHION_DB_CACHE, CHARACTER_VARIATIONS

    if _FASHION_DB_CACHE is not None:
        return _FASHION_DB_CACHE

    try:
        # 找到 twms_fashion_db.json 的路徑
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        fashion_db_path = os.path.join(base_dir, "twms_fashion_db.json")

        if not os.path.exists(fashion_db_path):
            raise FileNotFoundError(f"找不到 fashion DB: {fashion_db_path}")

        with open(fashion_db_path, "r", encoding="utf-8") as f:
            fashion_items = json.load(f)

        _FASHION_DB_CACHE = fashion_items

        # 按部件和性別分類並提取 ID
        CHARACTER_VARIATIONS.clear()
        categories = {
            "face": "Face",
            "hair": "Hair",
            "skin": "Skin",  # 注意：MapleStory 中沒有 "Skin" 分類，用 10000-12100 範圍代替
            "top": "Top",
            "bottom": "Bottom",
            "shoes": "Shoes",
        }

        for part, category in categories.items():
            if part == "skin":
                # 特殊處理：膚色是系統預設值，不在 fashion DB 中
                # 使用標準膚色 ID 12000（MapleStory 中的標準膚色）
                CHARACTER_VARIATIONS["skin"] = ["12000"]
                CHARACTER_VARIATIONS["skin_male"] = ["12000"]
                CHARACTER_VARIATIONS["skin_female"] = ["12000"]
            else:
                # 提取所有 ID 和按性別分類的 ID
                items_in_cat = [
                    item for item in fashion_items if item["category"] == category
                ]
                all_ids = [str(item["id"]) for item in items_in_cat]

                # 按名稱中的性別標籤分類
                male_ids = [
                    str(item["id"])
                    for item in items_in_cat
                    if _extract_gender_from_name(item.get("name", "")) == "male"
                ]
                female_ids = [
                    str(item["id"])
                    for item in items_in_cat
                    if _extract_gender_from_name(item.get("name", "")) == "female"
                ]
                neutral_ids = [
                    str(item["id"])
                    for item in items_in_cat
                    if _extract_gender_from_name(item.get("name", "")) is None
                ]

                # 保存所有 ID
                CHARACTER_VARIATIONS[part] = all_ids

                # 如果沒有性別標籤，就用中性的；否則用特定性別 + 中性
                CHARACTER_VARIATIONS[f"{part}_male"] = (
                    male_ids + neutral_ids if male_ids else all_ids
                )
                CHARACTER_VARIATIONS[f"{part}_female"] = (
                    female_ids + neutral_ids if female_ids else all_ids
                )

        print("✓ 成功載入 fashion DB（含性別分類）")
        print(
            f"  Face: {len(CHARACTER_VARIATIONS.get('face', []))} 個 (男:{len(CHARACTER_VARIATIONS.get('face_male', []))} / 女:{len(CHARACTER_VARIATIONS.get('face_female', []))})"
        )
        print(
            f"  Hair: {len(CHARACTER_VARIATIONS.get('hair', []))} 個 (男:{len(CHARACTER_VARIATIONS.get('hair_male', []))} / 女:{len(CHARACTER_VARIATIONS.get('hair_female', []))})"
        )
        print(
            f"  Top: {len(CHARACTER_VARIATIONS.get('top', []))} 個 (男:{len(CHARACTER_VARIATIONS.get('top_male', []))} / 女:{len(CHARACTER_VARIATIONS.get('top_female', []))})"
        )
        print(
            f"  Bottom: {len(CHARACTER_VARIATIONS.get('bottom', []))} 個 (男:{len(CHARACTER_VARIATIONS.get('bottom_male', []))} / 女:{len(CHARACTER_VARIATIONS.get('bottom_female', []))})"
        )
        print(
            f"  Shoes: {len(CHARACTER_VARIATIONS.get('shoes', []))} 個 (男:{len(CHARACTER_VARIATIONS.get('shoes_male', []))} / 女:{len(CHARACTER_VARIATIONS.get('shoes_female', []))})"
        )

        return fashion_items

    except Exception as e:
        print(f"⚠️ 載入 fashion DB 失敗，使用預設值: {e}")
        # 回退到預設值（所有 ID 來自 fashion DB 驗證）
        CHARACTER_VARIATIONS.update(
            {
                "face": [
                    "20000",
                    "20001",
                    "20002",
                    "20003",
                    "20004",
                    "20005",
                    "20006",
                    "20007",
                    "20008",
                    "20009",
                ],
                "face_male": [
                    "20000",
                    "20001",
                    "20002",
                    "20003",
                    "20004",
                    "20005",
                    "20006",
                    "20007",
                    "20008",
                    "20009",
                ],
                "face_female": [
                    "20000",
                    "20001",
                    "20002",
                    "20003",
                    "20004",
                    "20005",
                    "20006",
                    "20007",
                    "20008",
                    "20009",
                ],
                "hair": [
                    "30000",
                    "30001",
                    "30002",
                    "30003",
                    "30004",
                    "30005",
                    "30006",
                    "30007",
                    "30033",
                    "30034",
                ],
                "hair_male": [
                    "30000",
                    "30001",
                    "30002",
                    "30003",
                    "30004",
                    "30005",
                    "30006",
                    "30007",
                    "30033",
                    "30034",
                ],
                "hair_female": [
                    "30000",
                    "30001",
                    "30002",
                    "30003",
                    "30004",
                    "30005",
                    "30006",
                    "30007",
                    "30033",
                    "30034",
                ],
                "skin": [
                    "12000"
                ],  # 皮膚色：系統預設值，不在 fashion DB 中，使用標準膚色
                "skin_male": ["12000"],
                "skin_female": ["12000"],
                "top": [
                    "1040001",
                    "1040005",
                    "1040027",
                    "1040045",
                    "1040046",
                    "1040047",
                    "1040051",
                    "1040052",
                    "1040053",
                    "1040054",
                ],
                "top_male": [
                    "1040001",
                    "1040005",
                    "1040027",
                    "1040045",
                    "1040046",
                    "1040047",
                    "1040051",
                    "1040052",
                    "1040053",
                    "1040054",
                ],
                "top_female": [
                    "1040001",
                    "1040005",
                    "1040027",
                    "1040045",
                    "1040046",
                    "1040047",
                    "1040051",
                    "1040052",
                    "1040053",
                    "1040054",
                ],
                "bottom": [
                    "1060001",
                    "1060003",
                    "1060034",
                    "1060035",
                    "1060036",
                    "1060040",
                    "1060041",
                    "1060042",
                    "1060047",
                    "1060048",
                ],
                "bottom_male": [
                    "1060001",
                    "1060003",
                    "1060034",
                    "1060035",
                    "1060036",
                    "1060040",
                    "1060041",
                    "1060042",
                    "1060047",
                    "1060048",
                ],
                "bottom_female": [
                    "1060001",
                    "1060003",
                    "1060034",
                    "1060035",
                    "1060036",
                    "1060040",
                    "1060041",
                    "1060042",
                    "1060047",
                    "1060048",
                ],
                "shoes": [
                    "1073711",
                    "1070001",
                    "1070002",
                    "1070003",
                    "1070004",
                    "1070005",
                    "1070006",
                    "1070007",
                    "1070008",
                    "1070009",
                ],
                "shoes_male": [
                    "1073711",
                    "1070001",
                    "1070002",
                    "1070003",
                    "1070004",
                    "1070005",
                    "1070006",
                    "1070007",
                    "1070008",
                    "1070009",
                ],
                "shoes_female": [
                    "1073711",
                    "1070001",
                    "1070002",
                    "1070003",
                    "1070004",
                    "1070005",
                    "1070006",
                    "1070007",
                    "1070008",
                    "1070009",
                ],
            }
        )
        return None


# 首次導入時載入 fashion DB
_load_fashion_db()

# MapleStory API 基底網址
MAPLESTORY_API_BASE = "https://maplestory.io/api/character"

# ============================================================
# 公開 API
# ============================================================


def get_defaults(gender: str = "male") -> Dict[str, Any]:
    """
    取得指定性別的預設角色配置（所有值為字串）。

    Args:
        gender: 'male' 或 'female'

    Returns:
        預設角色配置的副本，避免外部修改污染常數。
    """
    return FEMALE_DEFAULT.copy() if gender == "female" else MALE_DEFAULT.copy()


def get_random(preserve_gender: Optional[str] = None) -> Dict[str, Any]:
    """
    生成隨機角色配置，根據性別選擇對應的部件。

    從 twms_fashion_db.json 中隨機選擇有效的物品 ID，
    確保：
    1. 不會出現無效的物品 ID（如已刪除的 1060127）
    2. 女性角色選擇女性臉型/髮型/衣服
    3. 男性角色選擇男性臉型/髮型/衣服

    Args:
        preserve_gender: 指定性別 ('male'/'female')；None 則隨機選擇。

    Returns:
        包含角色配置的字典，所有部件值皆為字串（與資料庫一致）。
    """
    # 確保 CHARACTER_VARIATIONS 已載入
    if not CHARACTER_VARIATIONS or all(
        len(v) == 0 for v in CHARACTER_VARIATIONS.values()
    ):
        _load_fashion_db()

    # 決定性別
    gender = preserve_gender if preserve_gender else random.choice(["male", "female"])

    # 根據性別選擇對應的部件
    gender_suffix = f"_{gender}"

    return {
        "face": str(
            random.choice(
                CHARACTER_VARIATIONS.get(
                    f"face{gender_suffix}", CHARACTER_VARIATIONS.get("face", ["20005"])
                )
            )
        ),
        "hair": str(
            random.choice(
                CHARACTER_VARIATIONS.get(
                    f"hair{gender_suffix}", CHARACTER_VARIATIONS.get("hair", ["30120"])
                )
            )
        ),
        "skin": str(
            random.choice(CHARACTER_VARIATIONS.get("skin", ["12000"]))
        ),  # Skin 不分性別
        "top": str(
            random.choice(
                CHARACTER_VARIATIONS.get(
                    f"top{gender_suffix}", CHARACTER_VARIATIONS.get("top", ["1040014"])
                )
            )
        ),
        "bottom": str(
            random.choice(
                CHARACTER_VARIATIONS.get(
                    f"bottom{gender_suffix}",
                    CHARACTER_VARIATIONS.get("bottom", ["1060096"]),
                )
            )
        ),
        "shoes": str(
            random.choice(
                CHARACTER_VARIATIONS.get(
                    f"shoes{gender_suffix}",
                    CHARACTER_VARIATIONS.get("shoes", ["1072005"]),
                )
            )
        ),
        "is_stunned": 0,
        "gender": gender,
    }


def infer_gender_from_appearance(user_data: Dict[str, Any]) -> Optional[str]:
    """
    根據現有紙娃娃部件推斷角色性別。

    只計算在 male/female 候選集合中明確偏向單一性別的部件；
    若分數相同或全部是中性部件，則回傳 None。
    """
    if not CHARACTER_VARIATIONS or all(
        len(v) == 0 for v in CHARACTER_VARIATIONS.values()
    ):
        _load_fashion_db()

    score = {"male": 0, "female": 0}
    for field in ("face", "hair", "top", "bottom", "shoes"):
        value = user_data.get(field)
        if value in (None, "", 0, "0"):
            continue

        item_id = str(value)
        male_pool = set(CHARACTER_VARIATIONS.get(f"{field}_male", []))
        female_pool = set(CHARACTER_VARIATIONS.get(f"{field}_female", []))

        in_male = item_id in male_pool
        in_female = item_id in female_pool

        if in_male and not in_female:
            score["male"] += 1
        elif in_female and not in_male:
            score["female"] += 1

    if score["male"] > score["female"]:
        return "male"
    if score["female"] > score["male"]:
        return "female"
    return None


def build_api_url(
    user_data: Dict[str, Any],
    pose: str = "stand1",
    preview_item: Optional[Dict] = None,
    region: str = "TWMS",
    version: str = "256",
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
        face_id = _to_int(user_data.get("face"), 20005)
        hair_id = _to_int(user_data.get("hair"), 30120)
        skin_id = _to_int(user_data.get("skin"), 12000)  # 皮膚色 ID（必須）
        # 支援 overall（整套服）優先於 top
        top_id = _to_int(user_data.get("overall") or user_data.get("top"), 1040014)
        bottom_id = _to_int(user_data.get("bottom"), 1060096)
        shoes_id = _to_int(user_data.get("shoes"), 1072005)

        # ── 眩暈狀態自動調整姿勢 ──────────────────────────────
        is_stunned = user_data.get("is_stunned", 0) == 1
        if pose == "stand1" and is_stunned:
            pose = "prone"

        # ── 建立部件列表 ──────────────────────────────────────
        items: list = [
            {
                "itemId": skin_id,
                "region": region,
                "version": version,
            },  # 🎯 皮膚色（必須包含，否則無法正確渲染臉部）
            {"itemId": 2000, "region": region, "version": version},
            {
                "itemId": face_id,
                **({"animationName": "stunned"} if is_stunned else {}),
                "region": region,
                "version": version,
            },
            {"itemId": hair_id, "region": region, "version": version},
            {"itemId": top_id, "region": region, "version": version},
            {"itemId": bottom_id, "region": region, "version": version},
            {"itemId": shoes_id, "region": region, "version": version},
        ]

        # ── 附屬裝備（商店試穿等場景使用）────────────────────
        if include_accessories:
            for field in (
                "hat",
                "face_accessory",
                "eye_decoration",
                "earrings",
                "glove",
            ):
                val = _to_int(user_data.get(field), 0)
                if val:
                    items.append({"itemId": val, "region": region, "version": version})

        # ── 預覽裝備替換（試穿功能）──────────────────────────
        if preview_item:
            _apply_preview_item(items, user_data, preview_item, region, version)

        # 移除 itemId 為 0 的部件（無效項目）
        items = [it for it in items if it.get("itemId", 0)]

        # ── 組合 URL ──────────────────────────────────────────
        item_path = ",".join(json.dumps(it, separators=(",", ":")) for it in items)
        flip_param = str(flip_x).lower()
        params = (
            f"showears=false&showLefEars=false&showHighLefEars=false"
            f"&resize={resize}&flipX={flip_param}"
        )
        maplestory_url = f"{MAPLESTORY_API_BASE}/{item_path}/{pose}/animated?{params}"

        # ✅ 直接回傳 maplestory.io URL
        # Discord 顯示 embed 圖片時會通過自己的 CDN proxy（media.discordapp.net）抓取，
        # 會帶上 User-Agent，maplestory.io 不需要額外代理。
        return maplestory_url

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
        # Base64 編碼原始 URL
        encoded = base64.b64encode(maplestory_url.encode()).decode()

        # 優先從 config.json 取得隧道 URL
        api_url = None
        try:
            import json as json_lib

            config_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "config", "config.json"
            )
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json_lib.load(f)
                    api_url = config.get("url") or config.get("API_BASE")
        except Exception:
            pass

        # 回退到環境變數
        if not api_url:
            api_url = os.getenv("UNIFIED_API_URL")

        # 再回退到本地主機
        if not api_url:
            api_url = "http://localhost:5000"

        proxy_url = f"{api_url}/api/proxy/paperdoll?url={encoded}"

        return proxy_url
    except Exception as e:
        print(f"[paperdoll_manager] ⚠️ 代理 URL 包裝失敗: {e}")
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
    required = ("face", "hair", "top", "bottom", "shoes")
    return all(user_data.get(f) is not None for f in required)


# ============================================================
# 內部輔助函式
# ============================================================

# 商店試穿分類 → 資料庫欄位名稱對照表
_CATEGORY_TO_FIELD: Dict[str, str] = {
    "Hair": "hair",
    "Face": "face",
    "Hat": "hat",
    "Top": "top",
    "Overall": "top",
    "Bottom": "bottom",
    "Shoes": "shoes",
    "Face Accessory": "face_accessory",
    "Eye Decoration": "eye_decoration",
    "Earrings": "earrings",
    "Glove": "glove",
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
    field = _CATEGORY_TO_FIELD.get(preview_item.get("category", ""))
    if not field:
        return

    preview_id = preview_item.get("id", 0)
    if not preview_id:
        return

    try:
        original_id = int(user_data.get(field) or 0)
    except (ValueError, TypeError):
        original_id = 0

    # 嘗試取代現有部件
    for item in items:
        if item.get("itemId") == original_id:
            item["itemId"] = preview_id
            return

    # 若找不到對應部件，直接附加
    items.append({"itemId": preview_id, "region": region, "version": version})
