"""
KK園區 AI 代理工具箱 (Agent Tools)
=====================================

包含所有 AI 可主動呼叫的「技能函數」。
每個函數都帶有 Docstring，供 Gemini Function Calling 識別。

🔧 新增工具的方法（只需三步，無需改動 AI.py）：
    1. 定義一個普通 Python 函數
    2. 加上 @register_tool(name, description, parameters) 裝飾器
    3. 重啟 Bot — AI 自動學會新技能

🔒 權限防火牆：
    敏感函數開頭會驗證 caller_id == LEADER_ID。
    即使 Gemini 指示呼叫，代碼層級也會擋下未授權操作。

📦 獨立測試：
    python agent_tools.py
    （無需啟動 Discord Bot 即可驗證所有工具）
"""

import os
import subprocess
import json
import datetime
from typing import Any, Dict, List, Optional

# ==================== 權限設定 ====================

LEADER_ID: int = int(os.getenv("LEADER_DISCORD_ID", "0"))


# ==================== 工具登記系統 ====================

_TOOL_REGISTRY: Dict[str, Dict] = {}


def register_tool(name: str, description: str, parameters: Dict):
    """
    裝飾器：將函數登記為 AI 可呼叫的工具。

    Args:
        name (str):        工具識別名稱（英文、無空格，Gemini 會用此名稱呼叫）
        description (str): 工具用途說明（Gemini 靠此判斷何時應呼叫此工具）
        parameters (dict): Gemini Function Calling 的 JSON Schema 參數定義
    """
    def decorator(func):
        _TOOL_REGISTRY[name] = {
            "func": func,
            "spec": {
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        }
        return func
    return decorator


# ==================== 工具定義 ====================

@register_tool(
    name="get_kkcoin_balance",
    description=(
        "查詢指定 Discord 用戶的 KK幣 (KKCoin) 餘額與數位美金 (digital_usd) 餘額。"
        "當用戶問到『我有多少 KK幣』、『查一下xxx的餘額』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "user_id": {
                "type": "STRING",
                "description": "要查詢的 Discord 用戶 ID（純數字字串）"
            }
        },
        "required": ["user_id"]
    }
)
def get_kkcoin_balance(user_id: str = "", *, caller_id: Optional[int] = None) -> str:
    """
    查詢指定用戶的 KK幣與數位美金餘額。
    
    ⭐ 智能 ID 判斷：
      如果 user_id 為空或無效，自動使用 caller_id（當前請求者）
      這樣用戶問「我有多少 KK幣」時，會自動查詢自己的餘額

    Args:
        user_id (str):   要查詢的 Discord 用戶 ID（可選，為空時使用 caller_id）
        caller_id (int): 呼叫此工具的 Discord 用戶 ID（由系統注入）

    Returns:
        str: 包含 KK幣和數位美金餘額的文字描述
    """
    try:
        from db_adapter import get_user_field
        
        # ⭐ 智能判斷：如果 user_id 為空或不是數字，使用 caller_id
        if not user_id or not user_id.isdigit():
            if caller_id:
                user_id = str(caller_id)
            else:
                return "❌ 無法確定要查詢哪個用戶的 KK幣。請提供用戶 ID 或 @tag 我來查詢你的餘額。"
        
        kkcoin = float(get_user_field(user_id, 'kkcoin', default=0) or 0)
        digital_usd = float(get_user_field(user_id, 'digital_usd', default=0) or 0)
        return f"用戶 {user_id} — KK幣：{kkcoin:.1f} KKC，數位美金：${digital_usd:.2f}"
    except Exception as e:
        return f"查詢 KK幣餘額失敗：{e}"


@register_tool(
    name="get_user_stats",
    description=(
        "查詢指定用戶的完整遊戲資料，包括等級、經驗值、HP、體力、KK幣。"
        "當用戶問到『我的狀態』、『xxx打了什麼等級』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "user_id": {
                "type": "STRING",
                "description": "Discord 用戶 ID"
            }
        },
        "required": ["user_id"]
    }
)
def get_user_stats(user_id: str = "", *, caller_id: Optional[int] = None) -> str:
    """
    查詢指定用戶的完整遊戲數據。

    ⭐ 智能 ID 判斷：
      如果 user_id 為空或無效，自動使用 caller_id（當前請求者）
      這樣用戶問「我的狀態」時，會自動查詢自己的數據

    Args:
        user_id (str):   Discord 用戶 ID（可選，為空時使用 caller_id）
        caller_id (int): 呼叫者 ID（系統注入）

    Returns:
        str: 用戶完整屬性的文字摘要
    """
    try:
        from db_adapter import get_user
        
        # ⭐ 智能判斷：如果 user_id 為空或不是數字，使用 caller_id
        if not user_id or not user_id.isdigit():
            if caller_id:
                user_id = str(caller_id)
            else:
                return "❌ 無法確定要查詢哪個用戶的狀態。請提供用戶 ID 或 @tag 我來查詢你的狀態。"
        
        user = get_user(user_id)
        if not user:
            return f"找不到用戶 {user_id} 的資料。"
        level   = user.get('level', 1)
        xp      = user.get('xp', 0)
        hp      = user.get('hp', 100)
        stamina = user.get('stamina', 100)
        kkcoin  = float(user.get('kkcoin', 0) or 0)
        digital_usd = float(user.get('digital_usd', 0) or 0)
        return (
            f"用戶 {user_id} 的狀態：\n"
            f"  等級：{level} | 經驗值：{xp}\n"
            f"  HP：{hp} | 體力：{stamina}\n"
            f"  KK幣：{kkcoin:.1f} KKC | 數位美金：${digital_usd:.2f}"
        )
    except Exception as e:
        return f"查詢用戶資料失敗：{e}"


@register_tool(
    name="get_top_kkcoin_leaderboard",
    description=(
        "取得 KK幣排行榜前 N 名，顯示各玩家的排名與 KK幣財富。"
        "當用戶問到『誰最有錢』、『排行榜』、『前幾名』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "top_n": {
                "type": "INTEGER",
                "description": "要顯示的名次數量，預設為 10，最多 20"
            }
        },
        "required": []
    }
)
def get_top_kkcoin_leaderboard(top_n: int = 10, *, caller_id: Optional[int] = None) -> str:
    """
    查詢 KK幣排行榜前 N 名。

    Args:
        top_n (int):     要列出的名次（上限 20）
        caller_id (int): 呼叫者 ID（系統注入）

    Returns:
        str: 排行榜文字清單
    """
    try:
        from db_adapter import get_all_users
        top_n = min(int(top_n), 20)
        all_users = get_all_users()
        if not all_users:
            return "暫無用戶數據。"
        sorted_users = sorted(
            all_users,
            key=lambda u: float(u.get('kkcoin', 0) or 0),
            reverse=True
        )[:top_n]
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"🏆 KK幣排行榜 Top {top_n}："]
        for i, u in enumerate(sorted_users, 1):
            medal = medals[i - 1] if i <= 3 else f"{i}."
            uid   = u.get('id', '???')
            kkcoin = float(u.get('kkcoin', 0) or 0)
            lines.append(f"  {medal} 用戶 {uid} — {kkcoin:.1f} KKC")
        return "\n".join(lines)
    except Exception as e:
        return f"取得排行榜失敗：{e}"


@register_tool(
    name="get_bot_status",
    description=(
        "取得 KK園區 Bot 目前的運行狀態，包括查詢時間與啟動時間。"
        "當用戶問到『Bot 還活著嗎』、『系統狀態』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {},
        "required": []
    }
)
def get_bot_status(*, caller_id: Optional[int] = None) -> str:
    """
    回傳 Bot 基本運行狀態。

    Args:
        caller_id (int): 呼叫者 ID（系統注入）

    Returns:
        str: Bot 狀態文字摘要
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bot_start_time.txt")
    start_time = "未知"
    try:
        if os.path.exists(uptime_file):
            with open(uptime_file, "r", encoding="utf-8") as f:
                start_time = f.read().strip()
    except Exception:
        pass
    return f"🤖 Bot 狀態：運行中\n⏱️ 查詢時間：{now}\n📅 啟動時間：{start_time}"


@register_tool(
    name="trigger_git_push",
    description=(
        "【高權限】觸發 Git 提交並推送最新變更到遠端倉庫。"
        "僅限園區管理員。當管理員要求『推送代碼』、『git push』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "commit_message": {
                "type": "STRING",
                "description": "Git commit 描述訊息（例如：'update: AI記憶同步'）"
            }
        },
        "required": ["commit_message"]
    }
)
def trigger_git_push(commit_message: str, *, caller_id: Optional[int] = None) -> str:
    """
    執行 git add → git commit → git push 流程。

    ⚠️ 敏感操作：需要 LEADER_ID 驗證。

    Args:
        commit_message (str): commit 描述
        caller_id (int):      呼叫者 Discord ID（系統注入，用於權限驗證）

    Returns:
        str: 操作結果或錯誤訊息
    """
    # 🔒 權限防火牆：非管理員一律拒絕
    if LEADER_ID and caller_id != LEADER_ID:
        return "存取拒絕：git push 僅限園區管理員。"

    repo_path = os.path.abspath(os.path.dirname(__file__))
    try:
        # 1. git add
        res = subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return f"git add 失敗：{res.stderr.strip()}"

        # 2. 檢查是否有變更
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True, timeout=10
        )
        if not status.stdout.strip():
            return "無需提交：工作區無變更。"

        # 3. git commit
        res = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return f"git commit 失敗：{res.stderr.strip()}"

        # 4. git push
        res = subprocess.run(
            ["git", "push"],
            cwd=repo_path, capture_output=True, text=True, timeout=60
        )
        if res.returncode != 0:
            return f"git push 失敗：{res.stderr.strip()}"

        return f"✅ Git 推送成功！Commit：{commit_message}"
    except subprocess.TimeoutExpired:
        return "Git 操作超時，請手動執行。"
    except Exception as e:
        return f"Git 操作失敗：{e}"


# ==================== 楓之谷紙娃娃配裝系統 ====================

@register_tool(
    name="get_maplestory_equipment",
    description=(
        "查詢指定用戶的楓之谷紙娃娃配裝。"
        "顯示目前穿著的所有裝備（武器、防具、飾品等）。"
        "當用戶問到『我的配裝』、『看我的裝備』、『配裝清單』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "user_id": {
                "type": "STRING",
                "description": "Discord 用戶 ID"
            }
        },
        "required": ["user_id"]
    }
)
def get_maplestory_equipment(user_id: str, *, caller_id: Optional[int] = None) -> str:
    """
    查詢用戶的楓之谷配裝
    
    Args:
        user_id (str):   Discord 用戶 ID
        caller_id (int): 呼叫者 ID（系統注入）
    
    Returns:
        str: 配裝清單文字
    """
    try:
        from db_adapter import get_user_field
        equipped_json = get_user_field(user_id, 'maplestory_equipment', default='{}')
        
        if isinstance(equipped_json, str):
            equipped = json.loads(equipped_json) if equipped_json else {}
        else:
            equipped = equipped_json if equipped_json else {}
        
        if not equipped:
            return f"用戶 {user_id} 尚未配置楓之谷裝備。"
        
        lines = [f"🎮 用戶 {user_id} 的楓之谷配裝："]
        for slot, item_info in sorted(equipped.items()):
            if isinstance(item_info, dict):
                name = item_info.get('name', '未知')
                power = item_info.get('power', 0)
                lines.append(f"  {slot}: {name} (力量: {power})")
            else:
                lines.append(f"  {slot}: {item_info}")
        return "\n".join(lines)
    except Exception as e:
        return f"查詢配裝失敗：{e}"


@register_tool(
    name="set_maplestory_equipment_item",
    description=(
        "【配裝修改】穿上或更換楓之谷某個位置的裝備。"
        "支援的位置：weapon, secondary, hat, face, eye, earring, top, bottom, shoe, glove, cape, belt, necklace, ring。"
        "當用戶說『換上xxx裝備』、『穿上xxx』、『裝備xxx』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "user_id": {
                "type": "STRING",
                "description": "Discord 用戶 ID"
            },
            "slot": {
                "type": "STRING",
                "description": "裝備位置（例如 'weapon', 'hat', 'top', 'ring' 等）"
            },
            "item_name": {
                "type": "STRING",
                "description": "裝備名稱"
            },
            "power": {
                "type": "INTEGER",
                "description": "裝備力量值（可選，預設 0）"
            }
        },
        "required": ["user_id", "slot", "item_name"]
    }
)
def set_maplestory_equipment_item(
    user_id: str, 
    slot: str, 
    item_name: str, 
    power: int = 0, 
    *, 
    caller_id: Optional[int] = None
) -> str:
    """
    穿上 / 更換裝備
    
    Args:
        user_id (str):   Discord 用戶 ID
        slot (str):      裝備位置
        item_name (str): 裝備名稱
        power (int):     力量值（可選）
        caller_id (int): 呼叫者 ID（系統注入）
    
    Returns:
        str: 操作結果字串
    """
    try:
        from db_adapter import get_user_field, set_user_field
        
        # 🔒 權限檢查：玩家只能修改自己的裝備
        if caller_id and int(user_id) != caller_id:
            return "存取拒絕：只能修改自己的配裝。"
        
        equipped_json = get_user_field(user_id, 'maplestory_equipment', default='{}')
        if isinstance(equipped_json, str):
            equipped = json.loads(equipped_json) if equipped_json else {}
        else:
            equipped = equipped_json if equipped_json else {}
        
        # 放置新裝備
        equipped[slot] = {
            'name': item_name,
            'power': int(power),
            'equipped_at': datetime.datetime.now().isoformat()
        }
        
        # 儲存回資料庫
        set_user_field(user_id, 'maplestory_equipment', json.dumps(equipped, ensure_ascii=False))
        
        return f"✅ 已穿上 {slot} 位置的裝備：{item_name} (力量: {power})"
    except Exception as e:
        return f"穿上裝備失敗：{e}"


@register_tool(
    name="remove_maplestory_equipment_item",
    description=(
        "【配裝修改】卸下楓之谷某個位置的裝備。"
        "當用戶說『脫掉xxx』、『移除xxx』、『卸下xxx』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "user_id": {
                "type": "STRING",
                "description": "Discord 用戶 ID"
            },
            "slot": {
                "type": "STRING",
                "description": "裝備位置（例如 'weapon', 'hat' 等）"
            }
        },
        "required": ["user_id", "slot"]
    }
)
def remove_maplestory_equipment_item(user_id: str, slot: str, *, caller_id: Optional[int] = None) -> str:
    """
    卸下指定位置的裝備
    
    Args:
        user_id (str):   Discord 用戶 ID
        slot (str):      裝備位置
        caller_id (int): 呼叫者 ID（系統注入）
    
    Returns:
        str: 操作結果字串
    """
    try:
        from db_adapter import get_user_field, set_user_field
        
        # 🔒 權限檢查：玩家只能修改自己的裝備
        if caller_id and int(user_id) != caller_id:
            return "存取拒絕：只能修改自己的配裝。"
        
        equipped_json = get_user_field(user_id, 'maplestory_equipment', default='{}')
        if isinstance(equipped_json, str):
            equipped = json.loads(equipped_json) if equipped_json else {}
        else:
            equipped = equipped_json if equipped_json else {}
        
        if slot not in equipped:
            return f"該位置 ({slot}) 沒有裝備。"
        
        removed_item = equipped.pop(slot)
        set_user_field(user_id, 'maplestory_equipment', json.dumps(equipped, ensure_ascii=False))
        
        item_name = removed_item.get('name', '?') if isinstance(removed_item, dict) else removed_item
        return f"✅ 已卸下 {slot} 位置的裝備：{item_name}"
    except Exception as e:
        return f"卸下裝備失敗：{e}"


@register_tool(
    name="clear_maplestory_equipment",
    description=(
        "【配裝重置】清空用戶的全部楓之谷裝備。"
        "當用戶說『清除配裝』、『重置裝備』、『全部脫掉』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "user_id": {
                "type": "STRING",
                "description": "Discord 用戶 ID"
            }
        },
        "required": ["user_id"]
    }
)
def clear_maplestory_equipment(user_id: str, *, caller_id: Optional[int] = None) -> str:
    """
    清空全部裝備
    
    Args:
        user_id (str):   Discord 用戶 ID
        caller_id (int): 呼叫者 ID（系統注入）
    
    Returns:
        str: 操作結果字串
    """
    try:
        from db_adapter import set_user_field
        
        # 🔒 權限檢查
        if caller_id and int(user_id) != caller_id:
            return "存取拒絕：只能修改自己的配裝。"
        
        set_user_field(user_id, 'maplestory_equipment', json.dumps({}))
        return f"✅ 已清空用戶 {user_id} 的全部楓之谷裝備。"
    except Exception as e:
        return f"清空裝備失敗：{e}"


@register_tool(
    name="get_maplestory_total_power",
    description=(
        "計算用戶楓之谷配裝的總力量值。"
        "當用戶問到『我的配裝有多強』、『總力量』、『配裝力量』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "user_id": {
                "type": "STRING",
                "description": "Discord 用戶 ID"
            }
        },
        "required": ["user_id"]
    }
)
def get_maplestory_total_power(user_id: str, *, caller_id: Optional[int] = None) -> str:
    """
    計算配裝的總力量
    
    Args:
        user_id (str):   Discord 用戶 ID
        caller_id (int): 呼叫者 ID（系統注入）
    
    Returns:
        str: 力量統計字串
    """
    try:
        from db_adapter import get_user_field
        equipped_json = get_user_field(user_id, 'maplestory_equipment', default='{}')
        
        if isinstance(equipped_json, str):
            equipped = json.loads(equipped_json) if equipped_json else {}
        else:
            equipped = equipped_json if equipped_json else {}
        
        total_power = 0
        items_count = 0
        for item_info in equipped.values():
            if isinstance(item_info, dict):
                total_power += item_info.get('power', 0)
                items_count += 1
        
        avg_power = total_power / items_count if items_count > 0 else 0
        
        return (
            f"⚔️ 用戶 {user_id} 的楓之谷配裝力量統計：\n"
            f"  裝備數量：{items_count} 件\n"
            f"  總力量值：{total_power}\n"
            f"  平均力量：{avg_power:.1f}"
        )
    except Exception as e:
        return f"計算力量失敗：{e}"


@register_tool(
    name="list_maplestory_equipment_slots",
    description=(
        "列出楓之谷的所有可用裝備位置（槽位）。"
        "當用戶問到『有哪些裝備位置』、『可以穿什麼』、『裝備槽位』時呼叫此工具。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {},
        "required": []
    }
)
def list_maplestory_equipment_slots(*, caller_id: Optional[int] = None) -> str:
    """
    列出所有裝備槽位
    
    Args:
        caller_id (int): 呼叫者 ID（系統注入）
    
    Returns:
        str: 槽位清單
    """
    slots = {
        'weapon': '武器',
        'secondary': '副武器/盾牌',
        'hat': '帽子',
        'face': '臉部飾品',
        'eye': '眼睛飾品',
        'earring': '耳環',
        'top': '上衣',
        'bottom': '褲子',
        'shoe': '鞋子',
        'glove': '手套',
        'cape': '披風',
        'belt': '腰帶',
        'necklace': '項鍊',
        'ring': '戒指（可多個）'
    }
    lines = ["📖 楓之谷裝備槽位清單："]
    for slot_id, slot_name in slots.items():
        lines.append(f"  • {slot_id}: {slot_name}")
    return "\n".join(lines)


# ==================== Shell Agent 工具 ====================

@register_tool(
    name="run_terminal",
    description=(
        "【高權限 Shell Agent 專用】在伺服器上執行 Shell 指令並回傳輸出結果。"
        "僅限園區管理員，且每次執行前必須由管理員在 Discord 確認。"
        "適用情境：查看伺服器狀態、檢查日誌、管理進程等。"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "description": "要執行的 Shell 指令（例如：'systemctl status bot.service'）"
            },
            "timeout_sec": {
                "type": "INTEGER",
                "description": "指令最長執行時間（秒），預設 30，最大 120"
            }
        },
        "required": ["command"]
    }
)
def run_terminal(command: str, timeout_sec: int = 30, *, caller_id: Optional[int] = None) -> str:
    """
    在伺服器執行 Shell 指令並回傳 stdout/stderr 結果。

    ⚠️ 高危函數：此工具在 Shell Agent 框架中透過 Discord Button 確認機制調用，
       確認邏輯位於 commands/shell_agent.py。直接呼叫仍需 LEADER_ID 驗證。

    Args:
        command (str):      Shell 指令字串
        timeout_sec (int):  最長執行秒數（上限 120）
        caller_id (int):    呼叫者 Discord ID（系統注入）

    Returns:
        str: 包含 exit code、stdout 與 stderr 的執行摘要
    """
    # 🔒 權限防火牆
    if LEADER_ID and caller_id != LEADER_ID:
        return "存取拒絕：run_terminal 僅限園區管理員。"

    # 安全限制
    timeout_sec = min(int(timeout_sec), 120)

    # 危險指令黑名單（雙重保險）
    _BLACKLIST = [
        "rm -rf /", "mkfs", ":(){:|:&};:", "dd if=",
        "shutdown", "reboot", "halt", "poweroff",
    ]
    for danger in _BLACKLIST:
        if danger in command:
            return f"⛔ 指令包含危險關鍵字「{danger}」，已拒絕執行。"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        exit_code = result.returncode

        output_lines = [f"📟 指令：{command}", f"🚪 Exit Code：{exit_code}"]

        if stdout:
            # 限制輸出長度避免 Discord 訊息超過 2000 字
            preview = stdout[:1200] + ("…（截斷）" if len(stdout) > 1200 else "")
            output_lines.append(f"📤 stdout：\n{preview}")
        if stderr:
            preview = stderr[:400] + ("…（截斷）" if len(stderr) > 400 else "")
            output_lines.append(f"⚠️ stderr：\n{preview}")

        return "\n".join(output_lines)

    except subprocess.TimeoutExpired:
        return f"⏰ 指令超時（{timeout_sec} 秒）：{command}"
    except Exception as e:
        return f"❌ 指令執行失敗：{e}"


# ==================== 核心公開介面 ====================

def get_gemini_tools_spec() -> List[Dict]:
    """
    自動生成 Gemini Function Calling 所需的工具清單 JSON。

    只要在此文件用 @register_tool 新增函數，
    Gemini 就能自動探索並呼叫新工具，無需修改 AI.py。

    Returns:
        list: Gemini API `tools` 字段所需的格式，例如：
            [{"functionDeclarations": [...]}]
    """
    return [{
        "functionDeclarations": [v["spec"] for v in _TOOL_REGISTRY.values()]
    }]


def dispatch_tool(tool_name: str, args: Dict, caller_id: Optional[int] = None) -> str:
    """
    工具分發器：根據名稱執行對應工具函數，並注入 caller_id。

    此函數由 AI.py 的工具分發邏輯呼叫，
    不應由外部直接使用（請透過 AI.py 的 on_message 流程觸發）。

    Args:
        tool_name (str):  Gemini functionCall.name
        args (dict):      Gemini functionCall.args（由 Gemini 填寫的参數）
        caller_id (int):  執行指令的 Discord 用戶 ID（由 Cog 傳入）

    Returns:
        str: 工具執行結果字串
    """
    if tool_name not in _TOOL_REGISTRY:
        return f"系統錯誤：未知工具 '{tool_name}'，請聯繫管理員。"

    func = _TOOL_REGISTRY[tool_name]["func"]
    try:
        return str(func(**args, caller_id=caller_id))
    except TypeError:
        # Fallback：舊版函數不接受 caller_id 關鍵字參數
        try:
            return str(func(**args))
        except Exception as e:
            return f"工具 '{tool_name}' 執行失敗：{e}"
    except Exception as e:
        return f"工具 '{tool_name}' 執行失敗：{e}"


def list_tools() -> List[str]:
    """回傳所有已登記的工具名稱清單。"""
    return list(_TOOL_REGISTRY.keys())


# ==================== 獨立測試模式 ====================

if __name__ == "__main__":
    print("=" * 50)
    print("  KK園區 Agent Tools 獨立測試")
    print("=" * 50)

    print("\n📦 已登記的工具：")
    for name in _TOOL_REGISTRY:
        desc = _TOOL_REGISTRY[name]["spec"]["description"][:40]
        print(f"  ✓ {name:<35} — {desc}…")

    print("\n🔧 Gemini Tools Spec（前 300 字元）：")
    spec_json = json.dumps(get_gemini_tools_spec(), ensure_ascii=False, indent=2)
    print(spec_json[:300], "…")

    print("\n🤖 測試 get_bot_status：")
    print(dispatch_tool("get_bot_status", {}, caller_id=None))

    print("\n🏆 測試 get_top_kkcoin_leaderboard (top_n=3)：")
    print(dispatch_tool("get_top_kkcoin_leaderboard", {"top_n": 3}, caller_id=None))

    print("\n🔒 測試 trigger_git_push（無權限）：")
    print(dispatch_tool("trigger_git_push", {"commit_message": "test"}, caller_id=99999))

    print("\n✅ 測試完成")
