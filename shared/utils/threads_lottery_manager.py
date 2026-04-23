# -*- coding: utf-8 -*-
"""
Threads 趨勢樂透管理系統
- 管理用戶投注記錄
- 執行對獎邏輯
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

log = logging.getLogger("threads_lottery")

# 資料儲存路徑
LOTTERY_DATA_FILE = "data/threads_lottery_bets.json"
os.makedirs("data", exist_ok=True)


class ThreadsLotteryManager:
    """Threads 趨勢樂透管理器"""
    
    def __init__(self):
        self.data_file = LOTTERY_DATA_FILE
        self.bets = self.load_bets()
    
    def load_bets(self) -> Dict:
        """加載投注記錄"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_bets(self):
        """保存投注記錄"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.bets, f, ensure_ascii=False, indent=2)
    
    def create_bet(self, user_id: int, trends: List[str], selected_indices: List[int], 
                   custom_keyword: str = "") -> str:
        """
        創建新投注
        
        Args:
            user_id: Discord 用戶 ID
            trends: 5 個趨勢列表
            selected_indices: 用戶選中的索引（1,2,3）
            custom_keyword: 自訂關鍵字
        
        Returns:
            投注 ID
        """
        bet_id = f"{user_id}_{int(datetime.now().timestamp())}"
        
        bet_data = {
            "bet_id": bet_id,
            "user_id": user_id,
            "trends": trends,
            "selected_indices": selected_indices,  # 按順序的索引，如 [0, 2, 4]
            "custom_keyword": custom_keyword,
            "created_at": datetime.now().isoformat(),
            "drawing_time": (datetime.now() + timedelta(hours=4)).isoformat(),
            "status": "pending",  # pending, completed, won, lost
            "result": None
        }
        
        self.bets[bet_id] = bet_data
        self.save_bets()
        
        log.info(f"[Lottery] 用戶 {user_id} 創建投注: {bet_id}")
        return bet_id
    
    def get_user_pending_bets(self, user_id: int) -> List[Dict]:
        """獲取用戶待獎的投注"""
        return [bet for bet in self.bets.values() 
                if bet["user_id"] == user_id and bet["status"] == "pending"]
    
    def check_and_settle_bet(self, bet_id: str, current_trends: List[str]) -> Dict:
        """
        對獎投注
        
        Args:
            bet_id: 投注 ID
            current_trends: 當前（4 小時後）的趨勢列表，按排名順序
        
        Returns:
            對獎結果
        """
        if bet_id not in self.bets:
            return {"success": False, "error": "找不到投注"}
        
        bet = self.bets[bet_id]
        if bet["status"] != "pending":
            return {"success": False, "error": "投注已結算"}
        
        # 1. 檢查時間
        drawing_time = datetime.fromisoformat(bet["drawing_time"])
        if datetime.now() < drawing_time:
            return {"success": False, "error": "還未到兌獎時間"}
        
        # 2. 檢查選中趨勢是否在前 3 名
        selected_trends = [bet["trends"][i] for i in bet["selected_indices"]]
        trends_in_top3 = all(trend in current_trends[:3] for trend in selected_trends)
        
        # 3. 檢查自訂關鍵字
        custom_hit = False
        if bet["custom_keyword"]:
            custom_hit = any(bet["custom_keyword"] in trend for trend in current_trends)
        
        # 4. 判斷獲獎情況
        if trends_in_top3 and custom_hit:
            result = "大獎"  # 全中
        elif trends_in_top3:
            result = "中獎"  # 選中趨勢全中
        elif custom_hit:
            result = "補獎"  # 自訂關鍵字中獎
        else:
            result = "未中"
        
        # 5. 更新投注狀態
        bet["status"] = "completed"
        bet["result"] = {
            "current_trends": current_trends,
            "selected_trends": selected_trends,
            "trends_in_top3": trends_in_top3,
            "custom_keyword": bet["custom_keyword"],
            "custom_hit": custom_hit,
            "award": result,
            "settled_at": datetime.now().isoformat()
        }
        
        self.save_bets()
        
        log.info(f"[Lottery] 投注 {bet_id} 已結算: {result}")
        return {"success": True, "result": result, "details": bet["result"]}
    
    def get_bet_info(self, bet_id: str) -> Optional[Dict]:
        """獲取投注詳情"""
        return self.bets.get(bet_id)
    
    def format_bet_display(self, bet: Dict) -> str:
        """格式化顯示投注內容"""
        lines = []
        lines.append(f"**投注 ID**: `{bet['bet_id'][:20]}...`")
        lines.append(f"**已選趨勢**: ")
        for idx in bet["selected_indices"]:
            lines.append(f"  {idx+1}. {bet['trends'][idx]}")
        
        if bet["custom_keyword"]:
            lines.append(f"**自訂關鍵字**: `{bet['custom_keyword']}`")
        
        lines.append(f"**狀態**: {bet['status']}")
        lines.append(f"**兌獎時間**: <t:{int(datetime.fromisoformat(bet['drawing_time']).timestamp())}:f>")
        
        if bet["result"]:
            result = bet["result"]
            lines.append(f"**結果**: 🎉 {result['award']}")
            lines.append(f"**前三名**: {', '.join(result['current_trends'][:3])}")
        
        return "\n".join(lines)


# 全局實例
_manager = None

def get_manager() -> ThreadsLotteryManager:
    """獲取投注管理器實例"""
    global _manager
    if _manager is None:
        _manager = ThreadsLotteryManager()
    return _manager
