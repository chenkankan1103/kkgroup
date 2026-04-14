"""
Locker Cache System
管理紙娃娃圖片快取，避免短時間內重複請求 MapleStory API
"""
import hashlib
import time
from typing import Optional, Dict, Tuple
from uicommands.utils.image_utils import build_maplestory_api_url


class LockerCache:
    """
    置物櫃快取管理器
    - paperdoll_image_cache: { paperdoll_hash → (image_url, timestamp) }
    - TTL: 預設 24 小時，可配置
    """
    
    def __init__(self, ttl_hours: int = 24):
        self.paperdoll_cache: Dict[str, Tuple[str, float]] = {}
        self.cache_ttl = ttl_hours * 3600  # 轉為秒
        self.hit_count = 0  # 快取命中次數
        self.miss_count = 0  # 快取未命中次數
    
    @staticmethod
    def build_paperdoll_hash(user_data: dict) -> str:
        """
        根據紙娃娃相關欄位產生 hash
        包括：face, hair, skin, 以及所有裝備欄位 (equip_*)
        """
        parts = []
        
        # 臉部、頭髮、膚色
        for key in ('face', 'hair', 'skin'):
            parts.append(str(user_data.get(key, '')))
        
        # 所有裝備欄位（假設存儲為 equip_0 到 equip_19）
        for i in range(20):
            equip_key = f'equip_{i}'
            parts.append(str(user_data.get(equip_key, '')))
        
        combined = ','.join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()
    
    async def get_paperdoll_image(
        self, 
        user_data: dict, 
        force_refresh: bool = False
    ) -> Optional[str]:
        """
        獲取紙娃娃圖片 URL
        
        邏輯：
        1. 計算當前 paperdoll_hash
        2. 若 force_refresh=False 且快取存在且未過期 → 回傳快取 URL
        3. 否則 → 呼叫 build_maplestory_api_url() 產生 MapleStory API URL
        4. 快取新 URL 並回傳
        
        Args:
            user_data: 使用者資料 dict
            force_refresh: 若 True，強制忽略快取並重新請求 API
        
        Returns:
            MapleStory API URL 或 None
        """
        current_hash = self.build_paperdoll_hash(user_data)
        now = time.time()
        
        # 快取查詢（跳過 force_refresh）
        if not force_refresh and current_hash in self.paperdoll_cache:
            cached_url, timestamp = self.paperdoll_cache[current_hash]
            if now - timestamp < self.cache_ttl:
                self.hit_count += 1
                print(f"✅ [LockerCache] 命中: hash={current_hash[:8]}... (age: {now - timestamp:.0f}s)")
                return cached_url
            else:
                # 快取過期
                del self.paperdoll_cache[current_hash]
        
        # 快取未命中或過期 → 生成新 URL
        self.miss_count += 1
        api_url = build_maplestory_api_url(user_data, animated=True)
        
        # 快取新 URL
        self.paperdoll_cache[current_hash] = (api_url, now)
        print(f"📝 [LockerCache] 新增: hash={current_hash[:8]}...")
        
        return api_url
    
    def invalidate_hash(self, paperdoll_hash: str) -> None:
        """
        手動清除指定 hash 的快取（若紙娃娃欄位在 DB 直接被改寫時使用）
        """
        if paperdoll_hash in self.paperdoll_cache:
            del self.paperdoll_cache[paperdoll_hash]
            print(f"🗑️ [LockerCache] 清除快取: hash={paperdoll_hash[:8]}...")
    
    def clear_all(self) -> None:
        """清除所有快取"""
        self.paperdoll_cache.clear()
        print(f"🗑️ [LockerCache] 清除所有快取 (命中: {self.hit_count}, 未命中: {self.miss_count})")
    
    def get_stats(self) -> dict:
        """取得快取統計資訊"""
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total > 0 else 0
        return {
            'cache_size': len(self.paperdoll_cache),
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'total_lookups': total,
            'hit_rate': hit_rate,
        }


# 全局快取實例
locker_cache = LockerCache(ttl_hours=24)
