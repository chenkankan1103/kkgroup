import random
from .config import SLOT_MACHINE_CONFIG

async def process_slot_machine_bet(bet_amount: int) -> tuple:
    """
    處理拉霸機下注
    返回: (結果列表, 淨變化, 消息)
    """
    config = SLOT_MACHINE_CONFIG
    weights = config["weights"]
    multipliers = config["multipliers"]

    # 創建加權選擇池
    icon_pool = [icon for icon, weight in weights.items() for _ in range(weight)]
    result = [random.choice(icon_pool) for _ in range(3)]

    # 預設回收 80% 賭金（也就是淨損失 20%）
    net_change = int(-bet_amount * 0.2)
    msg = ""

    # 判斷三個相同
    if result[0] == result[1] == result[2]:
        if result[0] in multipliers:
            net_change = bet_amount * (multipliers[result[0]] - 1)
            msg = f"{result[0]}{result[0]}{result[0]} 三連！你贏得 {bet_amount * multipliers[result[0]]} KKcoin！"
        else:
            net_change = int(bet_amount * 0.5)
            msg = f"{result[0]}{result[0]}{result[0]} 小獎！你贏得 {int(bet_amount * 1.5)} KKcoin！"

    # 判斷兩個相同
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        net_change = int(-bet_amount * 0.1)  # 輸10%
        msg = f"兩個相同！回收 {int(bet_amount * 0.9)} KKcoin"

    # 判斷有且只有一顆星星
    elif "⭐" in result and result.count("⭐") == 1:
        net_change = int(-bet_amount * 0.05)  # 輸5%
        msg = f"一顆星星！回收 {int(bet_amount * 0.95)} KKcoin"

    else:
        # 幾乎不會到這裡，因為回收都設80%以上
        net_change = int(-bet_amount * 0.1)  # 最少回收90%
        msg = f"回收 90% 賭金，繼續加油！"

    return result, net_change, msg
