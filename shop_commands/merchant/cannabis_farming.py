"""大麻種植系統 - 完整的種植管理"""
from datetime import datetime, timedelta
from .config import DB_PATH
from .cannabis_unified import get_adapter
from .cannabis_config import CANNABIS_SHOP, CANNABIS_HARVEST_PRICES
import json


# ==================== 數據庫初始化 ====================
async def init_cannabis_tables():
    """初始化大麻種植相關表 - 已廢棄（表已統一到 users 表中）"""
    # 此函數已于 2026-02-10 廢棄
    # 大麻系統現在使用 users 表中的 JSON 欄位:
    # - cannabis_plants: TEXT (JSON 陣列)
    # - cannabis_inventory: TEXT (JSON 物件)
    pass


# ==================== 庫存管理 ====================
async def add_inventory(user_id: int, item_type: str, item_name: str, quantity: int = 1):
    """增加庫存"""
    try:
        adapter = get_adapter()
        await adapter.add_inventory(user_id, item_type, item_name, quantity)
    except Exception as e:
        print(f"❌ 添加庫存時出錯：{e}", file=__import__('sys').stderr)


async def remove_inventory(user_id: int, item_type: str, item_name: str, quantity: int = 1) -> bool:
    """移除庫存，若數量不足返回 False"""
    try:
        adapter = get_adapter()
        return await adapter.remove_inventory(user_id, item_type, item_name, quantity)
    except Exception as e:
        print(f"❌ 移除庫存時出錯：{e}", file=__import__('sys').stderr)
        return False


async def get_inventory(user_id: int) -> dict:
    """獲取用戶所有庫存"""
    try:
        adapter = get_adapter()
        return await adapter.get_inventory(user_id)
    except Exception as e:
        print(f"❌ 獲取庫存時出錯：{e}", file=__import__('sys').stderr)
        return {}


# ==================== 種植管理 ====================
async def plant_cannabis(user_id: int, guild_id: int, channel_id: int, seed_type: str) -> dict:
    """種植大麻"""
    try:
        import random
        seed_config = CANNABIS_SHOP["種子"][seed_type]
        now = datetime.now()
        
        # 生長時間 ± 1 小時的隨機波動
        random_offset = random.randint(-3600, 3600)  # ±1小時
        actual_growth_time = seed_config["growth_time"] + random_offset
        matured_at = now + timedelta(seconds=actual_growth_time)
        
        adapter = get_adapter()
        
        # 創建植物記錄
        plant_data = {
            "user_id": user_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "seed_type": seed_type,
            "planted_at": now.isoformat(),
            "matured_at": matured_at.isoformat(),
            "growth_progress": 0.0,
            "fertilizer_applied": 0,
            "status": "growing",
            "harvested_amount": 0
        }
        
        await adapter.add_plant(user_id, plant_data)
        
        # 獲取生成的植物 ID（簡單起見，使用最大 ID）
        plants = await adapter.get_user_plants(user_id)
        plant_id = plants[-1].get('id') if plants else 0
        
        return {
            "id": plant_id,
            "seed_type": seed_type,
            "planted_at": now,
            "matured_at": matured_at,
            "growth_time": actual_growth_time
        }
    except Exception as e:
        print(f"❌ 種植失敗：{e}")
        return {"success": False, "reason": f"種植失敗：{e}"}


async def get_user_plants(user_id: int) -> list:
    """獲取用戶所有植物"""
    try:
        adapter = get_adapter()
        plants = await adapter.get_user_plants(user_id)
        
        result = []
        for plant in plants:
            try:
                # 計算當前成長進度
                now = datetime.now()
                planted_dt = datetime.fromisoformat(plant.get('planted_at', datetime.now().isoformat()))
                matured_dt = datetime.fromisoformat(plant.get('matured_at', datetime.now().isoformat()))
                
                status = plant.get('status', 'growing')
                if status == "harvested":
                    current_progress = 100.0
                else:
                    elapsed = (now - planted_dt).total_seconds()
                    total = (matured_dt - planted_dt).total_seconds()
                    current_progress = min(100.0, (elapsed / total) * 100 if total > 0 else 0)
                    
                    # 如果已經完全成熟但狀態還是growing，自動更新為harvested
                    if current_progress >= 100.0 and status != "harvested":
                        try:
                            await adapter.update_plant(user_id, plant.get('id'), {"status": "harvested"})
                            status = "harvested"
                        except Exception as update_error:
                            print(f"⚠️ 自動更新植物狀態失敗：{update_error}")
                
                result.append({
                    "id": plant.get('id'),
                    "seed_type": plant.get('seed_type'),
                    "planted_at": plant.get('planted_at'),
                    "matured_at": plant.get('matured_at'),
                    "progress": current_progress,
                    "fertilizer_applied": plant.get('fertilizer_applied', 0),
                    "status": status
                })
            except Exception as e:
                print(f"❌ 解析植物失敗：{e}")
        
        # 如果資料庫內植物超過 3 個，則保留最新 3 個（避免舊資料影響種植邏輯）
        if len(result) > 3:
            try:
                # 依照被種植時間排序，最近的保留
                sorted_plants = sorted(
                    result,
                    key=lambda p: datetime.fromisoformat(p.get('planted_at', datetime.now().isoformat())),
                    reverse=True
                )
                to_keep = sorted_plants[:3]
                to_remove = [p for p in result if p not in to_keep]

                for p in to_remove:
                    try:
                        await adapter.remove_plant(user_id, p.get('id'))
                    except Exception as remove_error:
                        print(f"⚠️ 無法刪除多餘植物：{remove_error}")

                result = to_keep
            except Exception as cleanup_error:
                print(f"⚠️ 清理超額植物失敗：{cleanup_error}")

        return result
    except Exception as e:
        print(f"❌ 獲取植物失敗：{e}")
        return []


async def apply_fertilizer(user_id: int, plant_id: int, fertilizer_type: str) -> bool:
    """對植物施肥"""
    try:
        adapter = get_adapter()

        # 獲取用戶的植物
        plants = await adapter.get_user_plants(user_id)

        # 找到指定的植物
        plant = None
        for p in plants:
            if p.get('id') == plant_id:
                plant = p
                break

        if not plant:
            return False

        # 檢查植物狀態
        if plant.get('status') != 'growing':
            return False

        # 計算施肥效果
        fertilizer_config = CANNABIS_SHOP["肥料"][fertilizer_type]
        boost = fertilizer_config["growth_boost"]

        matured_at = datetime.fromisoformat(plant.get('matured_at', datetime.now().isoformat()))
        now = datetime.now()
        remaining = (matured_at - now).total_seconds()
        new_remaining = remaining * (1 - boost)
        new_matured_at = now + timedelta(seconds=max(0, new_remaining))

        # 更新施肥計數
        updates = {
            "matured_at": new_matured_at.isoformat(),
            "fertilizer_applied": plant.get('fertilizer_applied', 0) + 1
        }

        return await adapter.update_plant(user_id, plant_id, updates)

    except Exception as e:
        print(f"❌ 施肥失敗：{e}")
        return False


async def harvest_plant(user_id: int, plant_id: int) -> dict:
    """收割植物"""
    try:
        adapter = get_adapter()
        
        # 獲取用戶的植物
        plants = await adapter.get_user_plants(user_id)
        
        # 找到指定的植物
        plant = None
        for p in plants:
            if p.get('id') == plant_id:
                plant = p
                break
        
        if not plant:
            return {"success": False, "reason": "植物不存在或不屬於你"}
        
        seed_type = plant.get('seed_type')
        matured_at = plant.get('matured_at')
        
        # 檢查是否已經收割過（從列表中移除的植物）
        # 注意：這裡我們不檢查狀態，因為get_user_plants會自動更新成熟植物的狀態
        
        # 檢查是否成熟
        now = datetime.now()
        matured_dt = datetime.fromisoformat(matured_at)
        if now < matured_dt:
            remaining_secs = (matured_dt - now).total_seconds()
            return {
                "success": False, 
                "reason": f"植物未成熟，還需 {remaining_secs:.0f} 秒"
            }
        
        # 隨機產出數量 - 基於種子等級的指數分布
        import random
        seed_config = CANNABIS_SHOP["種子"][seed_type]
        max_yield = seed_config["max_yield"]
        
        # 實現指數/加權分布：常規種易高產、優質種中等、黃金種多集中低產
        if seed_type == "常規種":
            # 常規種：加權均勻（偏向高值）
            weights = list(range(1, max_yield + 1))  # 1到max_yield，越大機率越高
            yield_amount = random.choices(range(1, max_yield + 1), weights=weights, k=1)[0]
        elif seed_type == "優質種":
            # 優質種：指數衰減，平均值中等
            yield_amount = min(max_yield, max(1, int(random.expovariate(0.20))))
        else:  # 黃金種
            # 黃金種：陡峭指數衰減，常見 1-5 顆
            yield_amount = min(max_yield, max(1, int(random.expovariate(0.25))))
        
        # 收割成功 - 從數據庫中移除植物
        await adapter.remove_plant(user_id, plant_id)
        
        # 添加到庫存
        await adapter.add_inventory(user_id, "大麻", seed_type, yield_amount)
        
        return {
            "success": True,
            "user_id": user_id,
            "seed_type": seed_type,
            "yield_amount": yield_amount,
            "sell_price": CANNABIS_HARVEST_PRICES[seed_type] * yield_amount
        }
    except Exception as e:
        print(f"❌ 收割失敗：{e}")
        return {"success": False, "reason": f"收割失敗：{e}"}


async def sell_cannabis(user_id: int, seed_type: str, quantity: int) -> dict:
    """出售大麻"""
    try:
        # 檢查庫存
        if not await remove_inventory(user_id, "大麻", seed_type, quantity):
            return {"success": False, "reason": "大麻數量不足"}
        
        # 計算收入
        unit_price = CANNABIS_HARVEST_PRICES[seed_type]
        total_price = unit_price * quantity
        
        return {
            "success": True,
            "seed_type": seed_type,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price
        }
    except Exception as e:
        print(f"❌ 出售失敗：{e}")
        return {"success": False, "reason": f"出售失敗：{e}"}
