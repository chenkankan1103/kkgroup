"""
大麻系統統一適配器 - 自動將 JSON 欄位轉換為表操作
負責：
- cannabis_plants 和 cannabis_inventory 的 JSON 序列化/反序列化
- 所有數據庫操作都通過 SheetDrivenDB
- 支持異步操作包裝
"""

import json
import sqlite3
import asyncio
from datetime import datetime
from sheet_driven_db import SheetDrivenDB
from concurrent.futures import ThreadPoolExecutor

# 線程池用於同步 DB 操作的異步包裝
_executor = ThreadPoolExecutor(max_workers=4)

class CannabisFarmingAdapter:
    """大麻系統統一適配器"""
    
    def __init__(self, db_path: str = 'user_data.db'):
        self.db = SheetDrivenDB(db_path)
        self.db_path = db_path
    
    # ==================== 植物管理 ====================
    
    async def add_plant(self, user_id: int, plant_data: dict) -> bool:
        """添加植物到用戶的種植列表"""
        try:
            def _do_add():
                user = self.db.get_user(user_id)
                if not user:
                    return False
                
                # 解析現有植物列表
                plants_json = user.get('cannabis_plants', '[]')
                if isinstance(plants_json, str):
                    plants = json.loads(plants_json) if plants_json else []
                else:
                    plants = plants_json if isinstance(plants_json, list) else []
                
                # 添加新植物（自動生成 ID）
                if plants:
                    new_id = max([p.get('id', 0) for p in plants]) + 1
                else:
                    new_id = 1
                
                plant_data_copy = dict(plant_data)
                plant_data_copy['id'] = new_id
                plants.append(plant_data_copy)
                
                # 保存回數據庫
                return self.db.set_user_field(user_id, 'cannabis_plants', json.dumps(plants, ensure_ascii=False))
            
            return await asyncio.get_event_loop().run_in_executor(_executor, _do_add)
        except Exception as e:
            print(f"❌ 添加植物失敗: {e}")
            return False
    
    async def get_user_plants(self, user_id: int) -> list:
        """獲取用戶的所有植物"""
        try:
            def _do_get():
                user = self.db.get_user(user_id)
                if not user:
                    return []
                
                plants_json = user.get('cannabis_plants', '[]')
                if isinstance(plants_json, str):
                    return json.loads(plants_json) if plants_json else []
                return plants_json if isinstance(plants_json, list) else []
            
            return await asyncio.get_event_loop().run_in_executor(_executor, _do_get)
        except Exception as e:
            print(f"❌ 獲取植物失敗: {e}")
            return []
    
    async def update_plant(self, user_id: int, plant_id: int, updates: dict) -> bool:
        """更新特定植物的信息"""
        try:
            def _do_update():
                plants = self.db.get_user(user_id)
                if not plants:
                    return False
                
                plants_json = plants.get('cannabis_plants', '[]')
                if isinstance(plants_json, str):
                    plants_list = json.loads(plants_json) if plants_json else []
                else:
                    plants_list = plants_json if isinstance(plants_json, list) else []
                
                for plant in plants_list:
                    if plant.get('id') == plant_id:
                        plant.update(updates)
                        return self.db.set_user_field(user_id, 'cannabis_plants', json.dumps(plants_list, ensure_ascii=False))
                
                return False  # 植物未找到
            
            return await asyncio.get_event_loop().run_in_executor(_executor, _do_update)
        except Exception as e:
            print(f"❌ 更新植物失敗: {e}")
            return False
    
    async def remove_plant(self, user_id: int, plant_id: int) -> bool:
        """移除特定植物"""
        try:
            def _do_remove():
                user = self.db.get_user(user_id)
                if not user:
                    return False
                
                plants_json = user.get('cannabis_plants', '[]')
                if isinstance(plants_json, str):
                    plants = json.loads(plants_json) if plants_json else []
                else:
                    plants = plants_json if isinstance(plants_json, list) else []
                
                plants = [p for p in plants if p.get('id') != plant_id]
                return self.db.set_user_field(user_id, 'cannabis_plants', json.dumps(plants, ensure_ascii=False))
            
            return await asyncio.get_event_loop().run_in_executor(_executor, _do_remove)
        except Exception as e:
            print(f"❌ 移除植物失敗: {e}")
            return False
    
    # ==================== 庫存管理 ====================
    
    async def add_inventory(self, user_id: int, item_type: str, item_name: str, quantity: int = 1) -> bool:
        """增加庫存"""
        try:
            def _do_add():
                user = self.db.get_user(user_id)
                if not user:
                    return False
                
                # 解析現有庫存
                inventory_json = user.get('cannabis_inventory', '{}')
                if isinstance(inventory_json, str):
                    inventory = json.loads(inventory_json) if inventory_json else {}
                else:
                    inventory = inventory_json if isinstance(inventory_json, dict) else {}
                
                # 初始化類別
                if item_type not in inventory:
                    inventory[item_type] = {}
                
                # 添加或增加庫存
                if item_name not in inventory[item_type]:
                    inventory[item_type][item_name] = 0
                
                inventory[item_type][item_name] += quantity
                
                # 保存回數據庫
                return self.db.set_user_field(user_id, 'cannabis_inventory', json.dumps(inventory, ensure_ascii=False))
            
            return await asyncio.get_event_loop().run_in_executor(_executor, _do_add)
        except Exception as e:
            print(f"❌ 添加庫存失敗: {e}")
            return False
    
    async def remove_inventory(self, user_id: int, item_type: str, item_name: str, quantity: int = 1) -> bool:
        """移除庫存，數量不足返回 False"""
        try:
            def _do_remove():
                user = self.db.get_user(user_id)
                if not user:
                    return False
                
                # 解析現有庫存
                inventory_json = user.get('cannabis_inventory', '{}')
                if isinstance(inventory_json, str):
                    inventory = json.loads(inventory_json) if inventory_json else {}
                else:
                    inventory = inventory_json if isinstance(inventory_json, dict) else {}
                
                # 檢查庫存
                if item_type not in inventory or item_name not in inventory[item_type]:
                    return False
                
                current_qty = inventory[item_type][item_name]
                if current_qty < quantity:
                    return False
                
                # 移除或減少
                current_qty -= quantity
                if current_qty <= 0:
                    del inventory[item_type][item_name]
                    if not inventory[item_type]:
                        del inventory[item_type]
                else:
                    inventory[item_type][item_name] = current_qty
                
                # 保存回數據庫
                return self.db.set_user_field(user_id, 'cannabis_inventory', json.dumps(inventory, ensure_ascii=False))
            
            return await asyncio.get_event_loop().run_in_executor(_executor, _do_remove)
        except Exception as e:
            print(f"❌ 移除庫存失敗: {e}")
            return False
    
    async def get_inventory(self, user_id: int) -> dict:
        """獲取用戶完整庫存"""
        try:
            def _do_get():
                user = self.db.get_user(user_id)
                if not user:
                    return {}
                
                inventory_json = user.get('cannabis_inventory', '{}')
                if isinstance(inventory_json, str):
                    return json.loads(inventory_json) if inventory_json else {}
                return inventory_json if isinstance(inventory_json, dict) else {}
            
            return await asyncio.get_event_loop().run_in_executor(_executor, _do_get)
        except Exception as e:
            print(f"❌ 獲取庫存失敗: {e}")
            return {}
    
    # ==================== 批量操作 ====================
    
    async def get_all_user_plants(self) -> dict:
        """獲取所有用戶的植物（用於管理員命令）"""
        def _do_get_all():
            users = self.db.get_all_users()
            result = {}
            for user in users:
                plants_json = user.get('cannabis_plants', '[]')
                if isinstance(plants_json, str):
                    plants = json.loads(plants_json) if plants_json else []
                else:
                    plants = plants_json if isinstance(plants_json, list) else []
                
                if plants:
                    result[user.get('user_id')] = plants
            
            return result
        
        return await asyncio.get_event_loop().run_in_executor(_executor, _do_get_all)


# 創建全局實例
_adapter = None

def get_adapter() -> CannabisFarmingAdapter:
    """獲取適配器實例（單例）"""
    global _adapter
    if _adapter is None:
        _adapter = CannabisFarmingAdapter()
    return _adapter


# ==================== Discord Bot 集成 ====================
async def setup(bot):
    """
    Discord 應用程序空 setup 函數
    
    此模組不提供任何 Cog，只是提供工具函數。
    由於加載系統會自動檢測並加載所有 Python 模組，
    因此需要此函數以防止加載錯誤。
    """
    pass
