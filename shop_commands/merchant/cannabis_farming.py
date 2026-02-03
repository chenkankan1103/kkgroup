"""大麻種植系統 - 完整的種植管理"""
import aiosqlite
from datetime import datetime, timedelta
from .config import DB_PATH


# ==================== 大麻商品配置 ====================
CANNABIS_SHOP = {
    "種子": {
        "常規種": {
            "name": "常規種子",
            "price": 100,
            "emoji": "🌱",
            "growth_time": 3600,  # 1小時完全成熟
            "max_yield": 5,  # 最多產出 5 個
            "description": "標準大麻種子，成長快、產量穩定"
        },
        "優質種": {
            "name": "優質種子",
            "price": 200,
            "emoji": "🌿",
            "growth_time": 7200,  # 2小時完全成熟
            "max_yield": 10,
            "description": "優質大麻種子，成長較慢但產量高"
        },
        "黃金種": {
            "name": "黃金種子",
            "price": 500,
            "emoji": "👑",
            "growth_time": 10800,  # 3小時完全成熟
            "max_yield": 20,
            "description": "稀有黃金種子，需要耐心栽培但回報豐厚"
        }
    },
    "肥料": {
        "基礎肥料": {
            "name": "基礎肥料",
            "price": 50,
            "emoji": "🧂",
            "growth_boost": 0.1,  # 加速 10%
            "description": "基礎肥料，略微加速生長"
        },
        "進階肥料": {
            "name": "進階肥料",
            "price": 100,
            "emoji": "💊",
            "growth_boost": 0.2,  # 加速 20%
            "description": "進階肥料，顯著加速生長"
        },
        "超級肥料": {
            "name": "超級肥料",
            "price": 300,
            "emoji": "💉",
            "growth_boost": 0.5,  # 加速 50%
            "description": "超級肥料，大幅加速生長"
        }
    }
}

# 出售價格配置（收購價格為購買價的百分比）
CANNABIS_HARVEST_PRICES = {
    "常規種": 200,      # 每個 200 KKcoin（購買 100，賣 200，利潤倍增）
    "優質種": 500,      # 每個 500 KKcoin
    "黃金種": 1500      # 每個 1500 KKcoin
}


# ==================== 數據庫初始化 ====================
async def init_cannabis_tables():
    """初始化大麻種植相關表"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 種植記錄表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cannabis_plants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                seed_type TEXT NOT NULL,
                planted_at TIMESTAMP NOT NULL,
                matured_at TIMESTAMP NOT NULL,
                growth_progress REAL DEFAULT 0.0,
                fertilizer_applied INTEGER DEFAULT 0,
                status TEXT DEFAULT 'growing',
                harvested_amount INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 用戶庫存表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cannabis_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, item_type, item_name)
            )
        """)
        
        await db.commit()


# ==================== 庫存管理 ====================
async def add_inventory(user_id: int, item_type: str, item_name: str, quantity: int = 1):
    """增加庫存"""
    try:
        # 確保表存在
        await init_cannabis_tables()
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO cannabis_inventory (user_id, item_type, item_name, quantity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, item_type, item_name) 
                DO UPDATE SET quantity = quantity + ?
            """, (user_id, item_type, item_name, quantity, quantity))
            await db.commit()
    except Exception as e:
        print(f"❌ 添加庫存時出錯：{e}", file=__import__('sys').stderr)


async def remove_inventory(user_id: int, item_type: str, item_name: str, quantity: int = 1) -> bool:
    """移除庫存，若數量不足返回 False"""
    try:
        # 確保表存在
        await init_cannabis_tables()
        
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT quantity FROM cannabis_inventory WHERE user_id = ? AND item_type = ? AND item_name = ?",
                (user_id, item_type, item_name)
            ) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] < quantity:
                    return False
                
                if row[0] == quantity:
                    await db.execute(
                        "DELETE FROM cannabis_inventory WHERE user_id = ? AND item_type = ? AND item_name = ?",
                        (user_id, item_type, item_name)
                    )
                else:
                    await db.execute(
                        "UPDATE cannabis_inventory SET quantity = quantity - ? WHERE user_id = ? AND item_type = ? AND item_name = ?",
                        (quantity, user_id, item_type, item_name)
                    )
                
                await db.commit()
                return True
    except Exception as e:
        print(f"❌ 移除庫存時出錯：{e}", file=__import__('sys').stderr)
        return False


async def get_inventory(user_id: int) -> dict:
    """獲取用戶所有庫存"""
    try:
        # 確保表存在
        await init_cannabis_tables()
        
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT item_type, item_name, quantity FROM cannabis_inventory WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                
                inventory = {}
                for item_type, item_name, quantity in rows:
                    if item_type not in inventory:
                        inventory[item_type] = {}
                    inventory[item_type][item_name] = quantity
                
                return inventory
    except Exception as e:
        print(f"❌ 獲取庫存時出錯：{e}", file=__import__('sys').stderr)
        return {}


# ==================== 種植管理 ====================
async def plant_cannabis(user_id: int, guild_id: int, channel_id: int, seed_type: str) -> dict:
    """種植大麻"""
    async with aiosqlite.connect(DB_PATH) as db:
        seed_config = CANNABIS_SHOP["種子"][seed_type]
        now = datetime.now()
        matured_at = now + timedelta(seconds=seed_config["growth_time"])
        
        await db.execute("""
            INSERT INTO cannabis_plants 
            (user_id, guild_id, channel_id, seed_type, planted_at, matured_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, guild_id, channel_id, seed_type, now, matured_at))
        
        await db.commit()
        
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            plant_id = (await cursor.fetchone())[0]
        
        return {
            "id": plant_id,
            "seed_type": seed_type,
            "planted_at": now,
            "matured_at": matured_at,
            "growth_time": seed_config["growth_time"]
        }


async def get_user_plants(user_id: int) -> list:
    """獲取用戶所有植物"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, seed_type, planted_at, matured_at, growth_progress, fertilizer_applied, status FROM cannabis_plants WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
            plants = []
            for row in rows:
                plant_id, seed_type, planted_at, matured_at, progress, fertilizer, status = row
                
                # 計算當前成長進度
                now = datetime.now()
                planted_dt = datetime.fromisoformat(planted_at)
                matured_dt = datetime.fromisoformat(matured_at)
                
                if status == "harvested":
                    current_progress = 100.0
                else:
                    elapsed = (now - planted_dt).total_seconds()
                    total = (matured_dt - planted_dt).total_seconds()
                    current_progress = min(100.0, (elapsed / total) * 100 if total > 0 else 0)
                
                plants.append({
                    "id": plant_id,
                    "seed_type": seed_type,
                    "planted_at": planted_at,
                    "matured_at": matured_at,
                    "progress": current_progress,
                    "fertilizer_applied": fertilizer,
                    "status": status
                })
            
            return plants


async def apply_fertilizer(plant_id: int, fertilizer_type: str) -> bool:
    """對植物施肥"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT matured_at, status FROM cannabis_plants WHERE id = ?",
            (plant_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            
            matured_at, status = row
            if status != "growing":
                return False
            
            # 施肥加速成熟時間
            fertilizer_config = CANNABIS_SHOP["肥料"][fertilizer_type]
            boost = fertilizer_config["growth_boost"]
            
            matured_dt = datetime.fromisoformat(matured_at)
            now = datetime.now()
            remaining = (matured_dt - now).total_seconds()
            new_remaining = remaining * (1 - boost)
            new_matured_at = now + timedelta(seconds=max(0, new_remaining))
            
            await db.execute(
                "UPDATE cannabis_plants SET matured_at = ?, fertilizer_applied = fertilizer_applied + 1 WHERE id = ?",
                (new_matured_at, plant_id)
            )
            await db.commit()
            return True


async def harvest_plant(plant_id: int) -> dict:
    """收割植物"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, seed_type, matured_at FROM cannabis_plants WHERE id = ?",
            (plant_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"success": False, "reason": "植物不存在"}
            
            user_id, seed_type, matured_at = row
            
            # 檢查是否成熟
            now = datetime.now()
            matured_dt = datetime.fromisoformat(matured_at)
            if now < matured_dt:
                remaining_secs = (matured_dt - now).total_seconds()
                return {
                    "success": False, 
                    "reason": f"植物未成熟，還需 {remaining_secs:.0f} 秒"
                }
            
            # 隨機產出數量 (50%-100%)
            import random
            seed_config = CANNABIS_SHOP["種子"][seed_type]
            max_yield = seed_config["max_yield"]
            yield_amount = random.randint(int(max_yield * 0.5), max_yield)
            
            # 更新植物狀態並增加庫存
            await db.execute(
                "UPDATE cannabis_plants SET status = 'harvested', harvested_amount = ? WHERE id = ?",
                (yield_amount, plant_id)
            )
            
            # 添加到庫存
            await add_inventory(user_id, "大麻", seed_type, yield_amount)
            
            await db.commit()
            
            return {
                "success": True,
                "user_id": user_id,
                "seed_type": seed_type,
                "yield_amount": yield_amount,
                "sell_price": CANNABIS_HARVEST_PRICES[seed_type] * yield_amount
            }


async def sell_cannabis(user_id: int, seed_type: str, quantity: int) -> dict:
    """出售大麻"""
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
