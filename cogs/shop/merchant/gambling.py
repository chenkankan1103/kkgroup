import random

from db_adapter import add_to_central_reserve

from .config import SLOT_MACHINE_CONFIG


async def process_slot_machine_bet(bet_amount: int) -> tuple:
    """
    處理拉霸機下注
    返回: (結果列表, 淨變化, 消息, 流入金庫的金額)

    金庫流入邏輯：
    - 玩家虧損 100% 流入金庫
    - 玩家盈利時，金庫不扣費
    """
    config = SLOT_MACHINE_CONFIG
    weights = config["weights"]
    multipliers = config["multipliers"]

    # 創建加權選擇池
    icon_pool = [icon for icon, weight in weights.items() for _ in range(weight)]
    result = [random.choice(icon_pool) for _ in range(3)]

    # 預設損失
    net_change = int(-bet_amount * 0.05)
    reserve_income = 0  # 金庫流入金額
    msg = ""

    # ========== 優先級1：三個相同 - 大獎 ==========
    if result[0] == result[1] == result[2]:
        if result[0] in multipliers:
            # 配置中的高倍數獎勵（💎⭐🔔🍋🍒）
            multiplier = multipliers[result[0]]
            net_change = int(bet_amount * (multiplier - 1))  # 淨收益 = (倍數-1)×下注
            win_amount = int(bet_amount * multiplier)  # 總獲得
            msg = f"🎉 {result[0]}{result[0]}{result[0]} 三連大獎！淨贏 {net_change} KKcoin（總獲得 {win_amount}）"
        else:
            # 其他三連（🍊🍉🍇）：1.5倍
            net_change = int(bet_amount * 0.5)  # 淨收益 50%
            win_amount = int(bet_amount * 1.5)
            msg = f"✨ {result[0]}{result[0]}{result[0]} 三連中獎！淨贏 {net_change} KKcoin（總獲得 {win_amount}）"

    # ========== 優先級2：恰好兩個相同 ==========
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        # 確定是哪兩個相同
        if result[0] == result[1]:
            pair_icon = result[0]
            third_icon = result[2]
        elif result[1] == result[2]:
            pair_icon = result[1]
            third_icon = result[0]
        else:  # result[0] == result[2]
            pair_icon = result[0]
            third_icon = result[1]

        # 計算返還與淨變化（確保一致性）
        returned = int(bet_amount * 0.98)
        net_change = returned - bet_amount
        loss_amount = bet_amount - returned
        msg = f"👍 {pair_icon}{pair_icon}+ 配對！返還 {returned} KKcoin（虧損 {loss_amount}）"

    # ========== 優先級3：單個星星（保本效果） ==========
    elif "⭐" in result and result.count("⭐") == 1:
        returned = int(bet_amount * 0.97)
        net_change = returned - bet_amount
        loss_amount = bet_amount - returned
        msg = f"⭐ 幸運星！返還 {returned} KKcoin（虧損 {loss_amount}）"

    # ========== 優先級4：沒有任何中獎 ==========
    else:
        # 正常虧損 8%（補償大獎的虧損）
        loss = int(bet_amount * 0.08)
        net_change = -loss
        msg = f"💸 遺憾沒中獎，損失 {loss} KKcoin。加油再試！"

    # ============================================================
    # 金庫流入機制：玩家虧損 100% 流入金庫
    # ============================================================
    if net_change < 0:  # 玩家虧損
        reserve_income = abs(net_change)
        # 異步添加到金庫
        try:
            add_to_central_reserve(reserve_income)
        except Exception as e:
            print(f"⚠️ 拉霸機金庫流入失敗: {e}")

    return result, net_change, msg, reserve_income
