# -*- coding: utf-8 -*-
"""
KK 園區堡壘保衛戰 - 遊戲引擎
每 4 小時 Google Trends 更新 → 熱搜詞化為入侵敵軍
全服玩家聯合防守，守住有獎，失守…（封測暫無懲罰）
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from zoneinfo import ZoneInfo

logger = logging.getLogger("fortress_system")

TW_TZ = ZoneInfo("Asia/Taipei")

# ── 遊戲常數 ──────────────────────────────────────────────
FORTRESS_MAX_HP = 10000         # 堡壘最大 HP
BASE_DAMAGE_FREE = 100          # 免費出兵基礎傷害
BASE_DAMAGE_PAID = 500          # 付費強化基礎傷害
TAG_BONUS_MULTIPLIER = 2.0      # 興趣標籤加乘倍率
FREE_ACTIONS_PER_ROUND = 3      # 每輪免費出兵次數
PAID_COST_KKCOIN = 100          # 付費強化費用（KKCoin）

# 封測標誌：True = 失守時無懲罰
BETA_NO_PENALTY = True

# 各排名對應的敵人 HP（1=Boss, 10=雜兵）
ENEMY_HP_BY_RANK = {
    1: 5000, 2: 4000, 3: 3000,
    4: 2500, 5: 2000, 6: 1500,
    7: 1200, 8: 1000, 9: 700, 10: 500
}

# 興趣標籤 → 關鍵字對應表（用於比對趨勢詞）
INTEREST_KEYWORDS: Dict[str, List[str]] = {
    "科技/AI": ["AI", "人工智慧", "ChatGPT", "機器學習", "科技", "蘋果", "Google", "晶片", "半導體"],
    "動漫/遊戲": ["動漫", "漫畫", "遊戲", "電競", "NETFLIX", "動畫", "Switch", "Steam"],
    "體育": ["棒球", "籃球", "足球", "奧運", "世界盃", "台灣隊", "運動", "賽事"],
    "娛樂/明星": ["演唱會", "明星", "藝人", "綜藝", "電視劇", "電影", "KPOP", "韓劇"],
    "財經時事": ["股市", "台積電", "美元", "通貨膨脹", "經濟", "比特幣", "加密貨幣", "基金"],
    "健康/美食": ["美食", "餐廳", "健康", "飲食", "料理", "咖啡", "甜點", "運動"],
    "旅遊/生活": ["旅遊", "景點", "住宿", "交通", "出國", "日本", "韓國", "台灣"],
    "政治": ["政治", "選舉", "政府", "立院", "總統", "台美", "兩岸", "國會"],
}

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fortress_state.json")


# ── 資料結構 ──────────────────────────────────────────────

@dataclass
class EnemyUnit:
    name: str
    rank: int
    max_hp: int
    current_hp: int
    category: str = ""          # 來自 Google Trends 的分類
    defeated: bool = False

    def hp_bar(self, width: int = 10) -> str:
        """生成 HP 血量條"""
        if self.max_hp == 0:
            return "░" * width
        ratio = self.current_hp / self.max_hp
        filled = int(ratio * width)
        bar = "▓" * filled + "░" * (width - filled)
        pct = int(ratio * 100)
        return f"{bar} {pct}% ({self.current_hp}/{self.max_hp})"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DefenseAction:
    user_id: int
    action_type: str        # "free" | "paid"
    damage: int
    has_tag_bonus: bool
    spent_kkcoin: int
    timestamp: str


@dataclass
class FortressState:
    round_id: str
    fortress_hp: int
    fortress_max_hp: int
    enemies: List[EnemyUnit]
    defenders: Dict[int, List[DefenseAction]]   # user_id → actions
    status: str                                  # "active" | "victory" | "defeat"
    started_at: str
    ends_at: str                                 # 自動結算時間（4小時後）

    # 獎池（封測期間累積供測試）
    prize_pool_kkcoin: int = 0

    def total_damage_by_user(self) -> Dict[int, int]:
        result = {}
        for uid, actions in self.defenders.items():
            result[uid] = sum(a.damage for a in actions)
        return result

    def free_actions_used(self, user_id: int) -> int:
        actions = self.defenders.get(user_id, [])
        return sum(1 for a in actions if a.action_type == "free")

    def is_active(self) -> bool:
        return self.status == "active"

    def fortress_hp_bar(self, width: int = 12) -> str:
        if self.fortress_max_hp == 0:
            return "░" * width
        ratio = self.fortress_hp / self.fortress_max_hp
        filled = int(ratio * width)
        bar = "▓" * filled + "░" * (width - filled)
        pct = int(ratio * 100)
        return f"{bar} {pct}% ({self.fortress_hp:,}/{self.fortress_max_hp:,})"


# ── 核心計算函數 ──────────────────────────────────────────

def calculate_enemy_hp(rank: int, search_volume: Optional[int] = None) -> int:
    """根據排名計算敵人 HP，可選用搜尋量微調"""
    base = ENEMY_HP_BY_RANK.get(rank, 500)
    if search_volume:
        # 搜尋量 >10000 額外 +20% HP
        if search_volume > 10000:
            base = int(base * 1.2)
    return base


def user_interests_match(user_interests: List[str], trend_name: str) -> bool:
    """
    判斷用戶興趣標籤是否與某個趨勢詞匹配
    比對邏輯：標籤關鍵字 in 趨勢詞（或反向），不分大小寫
    """
    trend_lower = trend_name.lower()
    for interest in user_interests:
        keywords = INTEREST_KEYWORDS.get(interest, [interest])
        for kw in keywords:
            if kw.lower() in trend_lower or trend_lower in kw.lower():
                return True
    return False


def calculate_player_damage(
    action_type: str,
    has_tag_bonus: bool
) -> int:
    """計算玩家本次行動造成的總傷害"""
    if action_type == "free":
        base = BASE_DAMAGE_FREE
    else:
        base = BASE_DAMAGE_PAID

    if has_tag_bonus:
        base = int(base * TAG_BONUS_MULTIPLIER)
    return base


def trends_to_enemies(trends: List[Dict]) -> List[EnemyUnit]:
    """
    將 Google Trends 資料轉換為入侵敵人
    trends: [{"topic": str, "search_volume": int, "rank": int, ...}, ...]
    """
    enemies = []
    for i, trend in enumerate(trends[:10]):
        rank = trend.get("rank", i + 1)
        name = trend.get("topic", trend.get("name", f"未知趨勢{i+1}"))
        volume = trend.get("search_volume", 0)
        hp = calculate_enemy_hp(rank, volume)
        category = trend.get("category", "")
        enemies.append(EnemyUnit(
            name=name,
            rank=rank,
            max_hp=hp,
            current_hp=hp,
            category=category,
            defeated=False
        ))
    return enemies


# ── 狀態管理 ──────────────────────────────────────────────

def _load_state() -> Optional[FortressState]:
    """從 JSON 載入當前戰況"""
    try:
        if not os.path.exists(STATE_FILE):
            return None
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        enemies = [EnemyUnit(**e) for e in data["enemies"]]
        defenders = {}
        for uid_str, actions in data.get("defenders", {}).items():
            defenders[int(uid_str)] = [DefenseAction(**a) for a in actions]

        return FortressState(
            round_id=data["round_id"],
            fortress_hp=data["fortress_hp"],
            fortress_max_hp=data["fortress_max_hp"],
            enemies=enemies,
            defenders=defenders,
            status=data["status"],
            started_at=data["started_at"],
            ends_at=data["ends_at"],
            prize_pool_kkcoin=data.get("prize_pool_kkcoin", 0),
        )
    except Exception as e:
        logger.error(f"[Fortress] 載入狀態失敗: {e}")
        return None


def _save_state(state: FortressState):
    """持久化戰況至 JSON"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        data = {
            "round_id": state.round_id,
            "fortress_hp": state.fortress_hp,
            "fortress_max_hp": state.fortress_max_hp,
            "enemies": [e.to_dict() for e in state.enemies],
            "defenders": {
                str(uid): [asdict(a) for a in actions]
                for uid, actions in state.defenders.items()
            },
            "status": state.status,
            "started_at": state.started_at,
            "ends_at": state.ends_at,
            "prize_pool_kkcoin": state.prize_pool_kkcoin,
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[Fortress] 保存狀態失敗: {e}")


# ── 公開 API ──────────────────────────────────────────────

def start_new_battle(trends: List[Dict]) -> FortressState:
    """
    開始新一輪戰鬥，由趨勢更新排程呼叫。
    trends: get_trending_topics() 的回傳值
    """
    now = datetime.now(TW_TZ)
    round_id = now.strftime("%Y-%m-%d-%H")
    ends_at = (now + timedelta(hours=4)).isoformat()

    enemies = trends_to_enemies(trends)
    total_enemy_hp = sum(e.max_hp for e in enemies)
    fortress_hp = max(FORTRESS_MAX_HP, total_enemy_hp // 2)

    state = FortressState(
        round_id=round_id,
        fortress_hp=fortress_hp,
        fortress_max_hp=fortress_hp,
        enemies=enemies,
        defenders={},
        status="active",
        started_at=now.isoformat(),
        ends_at=ends_at,
        prize_pool_kkcoin=0,
    )
    _save_state(state)
    logger.info(f"[Fortress] 新一輪開始 round={round_id}, 敵人={len(enemies)}, 堡壘HP={fortress_hp}")
    return state


def get_current_battle() -> Optional[FortressState]:
    """取得目前活躍的戰況（可能已結束）"""
    return _load_state()


def apply_defense_action(
    user_id: int,
    action_type: str,       # "free" | "paid"
    user_interests: List[str],
    current_enemy_names: Optional[List[str]] = None,
) -> Tuple[bool, str, int]:
    """
    玩家執行防守行動。
    回傳：(success, message, damage_dealt)
    """
    state = _load_state()
    if not state or not state.is_active():
        return False, "目前沒有進行中的戰鬥", 0

    # 免費次數檢查
    if action_type == "free":
        used = state.free_actions_used(user_id)
        if used >= FREE_ACTIONS_PER_ROUND:
            return False, f"本輪免費出兵次數已用完（上限 {FREE_ACTIONS_PER_ROUND} 次）", 0

    # 判斷標籤加乘：只要用戶興趣標籤與任一存活敵人匹配即觸發
    alive_enemies = [e.name for e in state.enemies if not e.defeated]
    has_bonus = any(
        user_interests_match(user_interests, name)
        for name in alive_enemies
    )

    damage = calculate_player_damage(action_type, has_bonus)

    # 依序對存活敵人扣血（從排名最高的開始）
    remaining = damage
    for enemy in sorted(state.enemies, key=lambda e: e.rank):
        if enemy.defeated:
            continue
        dealt = min(remaining, enemy.current_hp)
        enemy.current_hp -= dealt
        remaining -= dealt
        if enemy.current_hp <= 0:
            enemy.current_hp = 0
            enemy.defeated = True
            logger.info(f"[Fortress] 敵人 [{enemy.name}] 已被消滅！")
        if remaining <= 0:
            break

    # 記錄行動
    action = DefenseAction(
        user_id=user_id,
        action_type=action_type,
        damage=damage,
        has_tag_bonus=has_bonus,
        spent_kkcoin=PAID_COST_KKCOIN if action_type == "paid" else 0,
        timestamp=datetime.now(TW_TZ).isoformat(),
    )
    state.defenders.setdefault(user_id, []).append(action)

    # 勝利判定
    all_defeated = all(e.defeated for e in state.enemies)
    if all_defeated:
        state.status = "victory"
        logger.info(f"[Fortress] 🎉 勝利！round={state.round_id}")

    _save_state(state)

    bonus_text = "（🏷️ 標籤加乘 ×2）" if has_bonus else ""
    return True, f"造成 **{damage}** 傷害 {bonus_text}", damage


def apply_fortress_damage(damage: int) -> Tuple[FortressState, bool]:
    """對堡壘造成傷害（每輪結算時呼叫）。回傳 (state, defeated)"""
    state = _load_state()
    if not state:
        raise RuntimeError("無戰況可更新")
    state.fortress_hp = max(0, state.fortress_hp - damage)
    if state.fortress_hp <= 0:
        state.status = "defeat"
    _save_state(state)
    return state, state.status == "defeat"


def settle_battle() -> Dict:
    """
    4 小時後強制結算，回傳結算結果。
    若敵人未全滅 → 計算剩餘敵人總傷害 → 打堡壘。
    """
    state = _load_state()
    if not state or state.status != "active":
        return {"success": False, "reason": "無活躍戰況"}

    # 計算未消滅敵人的「潰堤傷害」
    alive_damage = sum(e.current_hp for e in state.enemies if not e.defeated)
    if alive_damage > 0:
        state.fortress_hp = max(0, state.fortress_hp - alive_damage)

    if state.fortress_hp <= 0 or any(not e.defeated for e in state.enemies):
        state.status = "defeat"
    else:
        state.status = "victory"

    _save_state(state)

    # 計算每位防守者的貢獻比例（用於獎勵分配）
    damage_map = state.total_damage_by_user()
    total_damage = sum(damage_map.values()) or 1
    contributions = {
        uid: round(dmg / total_damage * 100, 1)
        for uid, dmg in damage_map.items()
    }

    result = {
        "success": True,
        "round_id": state.round_id,
        "status": state.status,
        "fortress_hp_remaining": state.fortress_hp,
        "enemies_defeated": sum(1 for e in state.enemies if e.defeated),
        "enemies_total": len(state.enemies),
        "contributions": contributions,       # {user_id: 貢獻%}
        "damage_map": damage_map,             # {user_id: total_damage}
        "prize_pool_kkcoin": state.prize_pool_kkcoin,
        "beta_no_penalty": BETA_NO_PENALTY,
    }
    logger.info(f"[Fortress] 結算完成: {state.status}, round={state.round_id}")
    return result


def get_leaderboard(top_n: int = 10) -> List[Tuple[int, int]]:
    """本輪傷害排行榜，回傳 [(user_id, damage), ...]"""
    state = _load_state()
    if not state:
        return []
    damage_map = state.total_damage_by_user()
    return sorted(damage_map.items(), key=lambda x: x[1], reverse=True)[:top_n]
