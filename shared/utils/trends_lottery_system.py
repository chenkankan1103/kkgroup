# -*- coding: utf-8 -*-
"""
趨勢樂透遊戲系統 - 投注、開獎、獎金管理

遊戲規則：
1. 玩家投注 10 數位美金
2. 預測下一次趨勢更新（4小時後）的前三名
3. 開獎時：
   - 中 1 個：返回本金 ($10 USD)
   - 中 2 個：獲得 10 倍 ($100 USD)
   - 中 3 個：獲得 10 倍 ($100 USD) + 平分中央獎池
4. 投注款項加入中央獎池
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class Bet:
    """投注記錄"""
    user_id: int
    prediction: List[str]  # 預測的前3名趨勢 ["trend1", "trend2", "trend3"]
    amount: float  # 投注金額 (10 USD)
    timestamp: str  # 投注時間 ISO format
    round_id: str  # 開獎輪次 ID
    result: Optional[str] = None  # 開獎結果 "miss" / "1match" / "2match" / "3match"
    payout: float = 0.0  # 獲得的獎金
    
    def to_dict(self) -> Dict:
        """轉換為字典"""
        return asdict(self)


class TrendsLotterySystem:
    """趨勢樂透遊戲系統"""
    
    BET_AMOUNT = 10.0  # 投注金額：10 USD
    USD_PAYOUT_1MATCH = 10.0  # 中1個：10 USD（退本金）
    USD_PAYOUT_2MATCH = 100.0  # 中2個：100 USD
    USD_PAYOUT_3MATCH = 100.0  # 中3個：100 USD + 獎池
    
    def __init__(self, db_adapter):
        """
        初始化樂透系統
        
        Args:
            db_adapter: 數據庫適配層 (from db_adapter import ...)
                       需要實現以下方法：
                       - get_user_field(user_id, field, default)
                       - set_user_field(user_id, field, value)
                       - add_user_field(user_id, field, value)
                       - get_all_users()
        """
        if db_adapter is None:
            raise ValueError("DB adapter 不能為 None")
        self.db = db_adapter
    
    def _initialize_db(self):
        """初始化數據庫表（如果不存在）"""
        try:
            # 這裡假設 db_adapter 已經有創建表的功能
            # 實際實現需要根據你的 DB 系統
            logger.info("✅ 樂透系統 DB 初始化")
        except Exception as e:
            logger.error(f"❌ 樂透系統 DB 初始化失敗: {e}")
    
    async def place_bet(
        self,
        user_id: int,
        prediction: List[str],
        round_id: str
    ) -> Tuple[bool, str]:
        """
        玩家投注
        
        Args:
            user_id: 玩家 ID
            prediction: 預測的前3名趨勢 ["trend1", "trend2", "trend3"]
            round_id: 開獎輪次 ID (如 "2024-04-22-12")
        
        Returns:
            (成功/失敗, 消息)
        """
        # 檢查預測有效性
        if not prediction or len(prediction) != 3:
            return False, "❌ 必須預測 3 個趨勢"
        
        if len(set(prediction)) != 3:
            return False, "❌ 不能重複選擇同一個趨勢"
        
        # 檢查玩家餘額
        user_digital_usd = self.db.get_user_field(user_id, "digital_usd", default=0.0)
        
        try:
            user_digital_usd = float(user_digital_usd)
        except (ValueError, TypeError):
            user_digital_usd = 0.0
        
        if user_digital_usd < self.BET_AMOUNT:
            return False, f"❌ 數位美金不足 (需要 {self.BET_AMOUNT} USD，你有 {user_digital_usd} USD)"
        
        # 扣除投注金額
        new_balance = user_digital_usd - self.BET_AMOUNT
        self.db.set_user_field(user_id, "digital_usd", new_balance)
        
        # 投注額加入中央獎池
        await self._add_to_jackpot(self.BET_AMOUNT, round_id)
        
        # 記錄投注
        bet = Bet(
            user_id=user_id,
            prediction=prediction,
            amount=self.BET_AMOUNT,
            timestamp=datetime.now().isoformat(),
            round_id=round_id
        )
        
        # 保存投注記錄（使用 JSON 格式存儲在用戶字段）
        bets_json = self.db.get_user_field(user_id, "lottery_bets", default="[]")
        
        try:
            bets_list = json.loads(bets_json)
        except (json.JSONDecodeError, TypeError):
            bets_list = []
        
        bets_list.append(bet.to_dict())
        self.db.set_user_field(user_id, "lottery_bets", json.dumps(bets_list))
        
        logger.info(f"✅ 玩家 {user_id} 投注成功：{prediction}")
        return True, f"✅ 投注成功！\n預測：{', '.join(prediction)}\n投注額：{self.BET_AMOUNT} USD"
    
    async def draw_lottery(
        self,
        round_id: str,
        actual_top3: List[str]
    ) -> Dict:
        """
        開獎並結算
        
        Args:
            round_id: 開獎輪次 ID
            actual_top3: 實際的前3名趨勢 ["trend1", "trend2", "trend3"]
        
        Returns:
            開獎結果 {
                "round_id": "...",
                "top3": ["trend1", "trend2", "trend3"],
                "results": [
                    {
                        "user_id": 123,
                        "prediction": [...],
                        "matches": 2,
                        "payout": 100,
                        "payout_type": "kkcoin"
                    },
                    ...
                ],
                "jackpot": 1000.0,
                "timestamp": "..."
            }
        """
        if len(actual_top3) != 3 or len(set(actual_top3)) != 3:
            logger.error("❌ 開獎數據無效")
            return {}
        
        jackpot = await self._get_jackpot(round_id)
        results = []
        three_match_winners = []
        
        # 獲取本輪的所有投注
        all_bets = await self._get_round_bets(round_id)
        
        for bet_dict in all_bets:
            bet = Bet(**bet_dict)
            
            # 計算匹配數
            matches = sum(1 for pred in bet.prediction if pred in actual_top3)
            
            payout = 0.0
            payout_type = None
            
            if matches == 1:
                # 中1個：返回本金
                payout = self.USD_PAYOUT_1MATCH
                payout_type = "digital_usd"
            elif matches == 2:
                # 中2個：10倍 ($100 USD)
                payout = self.USD_PAYOUT_2MATCH
                payout_type = "digital_usd"
            elif matches == 3:
                # 中3個：記錄，後續獲得 $100 + 平分獎池
                three_match_winners.append(bet.user_id)
                payout = self.USD_PAYOUT_3MATCH  # 先給 $100
                payout_type = "digital_usd_plus_jackpot"
            
            # 發放獎金
            if payout_type == "digital_usd" or payout_type == "digital_usd_plus_jackpot":
                current = self.db.get_user_field(bet.user_id, "digital_usd", default=0.0)
                try:
                    current = float(current)
                except (ValueError, TypeError):
                    current = 0.0
                self.db.set_user_field(bet.user_id, "digital_usd", current + payout)
            
            # 更新投注記錄
            bet.result = f"{matches}match"
            bet.payout = payout
            
            results.append({
                "user_id": bet.user_id,
                "prediction": bet.prediction,
                "matches": matches,
                "payout": payout,
                "payout_type": payout_type
            })
        
        # 處理3個全中的玩家 - 平分獎池
        if three_match_winners and jackpot > 0:
            share_amount = jackpot / len(three_match_winners)
            for winner_id in three_match_winners:
                # 已經在上面給了 $100，這裡只需加獎池份額
                current = self.db.get_user_field(winner_id, "digital_usd", default=0.0)
                try:
                    current = float(current)
                except (ValueError, TypeError):
                    current = 0.0
                self.db.set_user_field(winner_id, "digital_usd", current + share_amount)
        
        # 清空獎池
        await self._clear_jackpot(round_id)
        
        # 返回開獎結果
        draw_result = {
            "round_id": round_id,
            "top3": actual_top3,
            "results": results,
            "jackpot": jackpot,
            "jackpot_winners": len(three_match_winners),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"✅ 開獎完成：{round_id}，獎池：{jackpot} USD")
        return draw_result
    
    async def _add_to_jackpot(self, amount: float, round_id: str) -> bool:
        """將金額加入獎池"""
        try:
            jackpot_key = f"lottery_jackpot_{round_id}"
            current = self.db.get_user_field("LOTTERY_SYSTEM", jackpot_key, default=0.0)
            
            try:
                current = float(current)
            except (ValueError, TypeError):
                current = 0.0
            
            new_jackpot = current + amount
            self.db.set_user_field("LOTTERY_SYSTEM", jackpot_key, new_jackpot)
            
            return True
        except Exception as e:
            logger.error(f"❌ 獎池更新失敗: {e}")
            return False
    
    async def _get_jackpot(self, round_id: str) -> float:
        """獲取獎池金額"""
        try:
            jackpot_key = f"lottery_jackpot_{round_id}"
            jackpot = self.db.get_user_field("LOTTERY_SYSTEM", jackpot_key, default=0.0)
            
            try:
                return float(jackpot)
            except (ValueError, TypeError):
                return 0.0
        except Exception as e:
            logger.error(f"❌ 獎池查詢失敗: {e}")
            return 0.0
    
    async def _clear_jackpot(self, round_id: str) -> bool:
        """清空獎池（開獎後）"""
        try:
            jackpot_key = f"lottery_jackpot_{round_id}"
            self.db.set_user_field("LOTTERY_SYSTEM", jackpot_key, 0.0)
            return True
        except Exception as e:
            logger.error(f"❌ 獎池清空失敗: {e}")
            return False
    
    async def _get_round_bets(self, round_id: str) -> List[Dict]:
        """獲取本輪的所有投注"""
        # 這是一個簡化實現，實際上可能需要更複雜的查詢
        # 這裡假設所有投注記錄都存儲在用戶字段中
        all_bets = []
        
        try:
            # 遍歷所有用戶
            all_users = self.db.get_all_users()
            
            for user_data in all_users:
                user_id = user_data.get("user_id")
                # 確保 user_id 是整數
                if isinstance(user_id, str):
                    try:
                        user_id = int(user_id)
                    except (ValueError, TypeError):
                        continue
                bets_json = user_data.get("lottery_bets", "[]")
                
                try:
                    bets_list = json.loads(bets_json)
                    for bet in bets_list:
                        if bet.get("round_id") == round_id:
                            all_bets.append(bet)
                except (json.JSONDecodeError, TypeError):
                    continue
            
            return all_bets
        except Exception as e:
            logger.error(f"❌ 投注查詢失敗: {e}")
            return []
    
    async def get_user_bets(self, user_id: int, round_id: Optional[str] = None) -> List[Dict]:
        """獲取玩家投注記錄"""
        try:
            bets_json = self.db.get_user_field(user_id, "lottery_bets", default="[]")
            
            try:
                all_bets = json.loads(bets_json)
            except (json.JSONDecodeError, TypeError):
                return []
            
            if round_id:
                return [b for b in all_bets if b.get("round_id") == round_id]
            
            return all_bets
        except Exception as e:
            logger.error(f"❌ 玩家投注查詢失敗: {e}")
            return []
    
    async def get_jackpot_info(self, round_id: str) -> Dict:
        """獲取獎池信息"""
        jackpot = await self._get_jackpot(round_id)
        all_bets = await self._get_round_bets(round_id)
        
        return {
            "round_id": round_id,
            "jackpot": jackpot,
            "total_bets": len(all_bets),
            "total_wagered": len(all_bets) * self.BET_AMOUNT
        }
