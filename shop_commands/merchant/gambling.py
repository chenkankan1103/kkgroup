import random
from .config import SLOT_MACHINE_CONFIG

async def process_slot_machine_bet(bet_amount: int) -> tuple:
    """
    處理拉霸機下注 - 99%期望值版本
    返回: (結果列表, 淨變化, 消息)
    """
    config = SLOT_MACHINE_CONFIG
    weights = config["weights"]
    multipliers = config["multipliers"]
    
    # 創建加權選擇池
    icon_pool = [icon for icon, weight in weights.items() for _ in range(weight)]
    result = [random.choice(icon_pool) for _ in range(3)]
    
    # 預設損失1% (99%期望值)
    net_change = int(-bet_amount * 0.01)
    msg = ""
    
    # 判斷三個相同 - 大獎
    if result[0] == result[1] == result[2]:
        if result[0] in multipliers:
            net_change = bet_amount * (multipliers[result[0]] - 1)
            msg = f"🎉 {result[0]}{result[0]}{result[0]} 三連大獎！你贏得 {bet_amount * multipliers[result[0]]} KKcoin！"
        else:
            # 其他三連獎勵 1.5倍
            net_change = int(bet_amount * 0.5)
            msg = f"✨ {result[0]}{result[0]}{result[0]} 小三連！你贏得 {int(bet_amount * 1.5)} KKcoin！"
    
    # 判斷兩個相同 - 中獎
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        # 兩個相同給予小額獎勵而不是虧損
        net_change = int(bet_amount * 0.1)  # 贏10%
        msg = f"👍 兩個相同！小獎勵 {int(bet_amount * 1.1)} KKcoin！"
    
    # 判斷有且只有一顆星星 - 保本
    elif "⭐" in result and result.count("⭐") == 1:
        net_change = 0  # 保本
        msg = f"⭐ 幸運星！保本回收 {bet_amount} KKcoin"
    
    # 沒有任何中獎條件 - 小虧損
    else:
        # 小虧損，但不會太多
        net_change = int(-bet_amount * 0.05)  # 輸5%
        msg = f"💸 這次沒中獎，損失 {int(bet_amount * 0.05)} KKcoin，再接再厲！"
    
    return result, net_change, msg
