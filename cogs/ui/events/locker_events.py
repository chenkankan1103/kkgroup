"""
置物櫃事件定義
事件驅動系統：當使用者資料變更時，觸發特定事件，由監聽器根據事件類型進行局部 embed 更新
"""
from typing import Set, Optional
from datetime import datetime


class LockerEvent:
    """置物櫃更新事件基類"""
    
    def __init__(self, user_id: int, changed_fields: Set[str], timestamp: Optional[datetime] = None):
        """
        Args:
            user_id: Discord 使用者 ID
            changed_fields: 改變欄位集合，例如 {'kkcoins', 'hp'} 或 {'*'} 表示全部
            timestamp: 事件發生時間
        """
        self.user_id = user_id
        self.changed_fields = changed_fields
        self.timestamp = timestamp or datetime.now()
        self.event_type = self.__class__.__name__
    
    def __repr__(self):
        return f"<{self.event_type} user_id={self.user_id} fields={self.changed_fields}>"


class EquipmentChangedEvent(LockerEvent):
    """
    裝備更新事件
    觸發：紙娃娃重新請求 MapleStory.io API + 更新 appearance embed
    """
    pass


class CurrencyChangedEvent(LockerEvent):
    """
    KK幣/經驗值更新事件
    觸發：只更新 summary embed 的文字欄位（不請求 API）
    """
    pass


class HealthChangedEvent(LockerEvent):
    """
    血量/體力更新事件
    觸發：只更新 summary embed 的進度條（不請求 API）
    """
    pass


class InventoryChangedEvent(LockerEvent):
    """
    物品欄更新事件
    觸發：更新 summary embed 的物品欄資訊（不請求 API）
    """
    pass


class FullRefreshEvent(LockerEvent):
    """
    完整刷新事件（管理員指令或強制同步）
    事件：changed_fields={'*'} 表示所有欄位重新計算、API 圖片重新請求、兩個 embed 完整更新
    """
    pass


class SyncRequestedEvent(LockerEvent):
    """
    同步請求事件（來自定期背景任務或手動 /refresh）
    事件：檢查資料庫是否有變更，有則觸發對應的更新事件
    """
    pass
