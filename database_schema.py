"""
改進的數據庫架構定義
支持動態欄位、自動類型推斷、未來的 PostgreSQL 遷移
"""

# ============================================================
# 欄位類型映射 - 智能推斷
# ============================================================

FIELD_TYPE_HINTS = {
    # 遊戲數值字段
    "user_id": "INTEGER PRIMARY KEY",
    "discord_id": "INTEGER",
    "level": "INTEGER",
    "xp": "INTEGER",
    "experience": "INTEGER",
    "exp": "INTEGER",
    "kkcoin": "INTEGER",
    "kcoin": "INTEGER",
    "coin": "INTEGER",
    "coins": "INTEGER",
    "gold": "INTEGER",
    "hp": "INTEGER",
    "health": "INTEGER",
    "stamina": "INTEGER",
    "energy": "INTEGER",
    "mana": "INTEGER",
    "mp": "INTEGER",
    "attack": "INTEGER",
    "defense": "INTEGER",
    "speed": "INTEGER",
    "luck": "INTEGER",
    "score": "INTEGER",
    "points": "INTEGER",
    "rank": "INTEGER",
    "wins": "INTEGER",
    "losses": "INTEGER",
    "draws": "INTEGER",
    "count": "INTEGER",
    "number": "INTEGER",
    
    # 玩家信息
    "nickname": "TEXT",
    "username": "TEXT",
    "name": "TEXT",
    "title": "TEXT",
    "role": "TEXT",
    "class": "TEXT",
    "profession": "TEXT",
    "job": "TEXT",
    "status": "TEXT",
    "state": "TEXT",
    "description": "TEXT",
    "bio": "TEXT",
    "notes": "TEXT",
    
    # 時間字段
    "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "created": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "updated": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "last_updated": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "last_seen": "TIMESTAMP",
    "joined_at": "TIMESTAMP",
    "registered_at": "TIMESTAMP",
    
    # 布爾值字段
    "active": "INTEGER",  # SQLite 用 0/1 表示 boolean
    "is_active": "INTEGER",
    "enabled": "INTEGER",
    "is_enabled": "INTEGER",
    "banned": "INTEGER",
    "is_banned": "INTEGER",
    "muted": "INTEGER",
    "is_muted": "INTEGER",
    "verified": "INTEGER",
    "is_verified": "INTEGER",
}

# ============================================================
# 類型推斷規則（優先級順序）
# ============================================================

def infer_column_type(header: str) -> str:
    """
    根據欄位名稱智能推斷欄位類型
    
    優先級：
    1. 精確匹配（在 FIELD_TYPE_HINTS 中）
    2. 包含關鍵字的規則
    3. 預設 TEXT
    """
    header_lower = header.lower()
    
    # 1. 精確匹配
    if header_lower in FIELD_TYPE_HINTS:
        return FIELD_TYPE_HINTS[header_lower]
    
    # 2. 包含關鍵字的規則
    
    # ID 相關
    if 'id' in header_lower or 'code' in header_lower:
        return 'INTEGER'
    
    # 數值相關
    if any(x in header_lower for x in [
        'coin', 'gold', 'money', 'price', 'cost', 'value',
        'level', 'exp', 'xp', 'experience',
        'hp', 'health', 'stamina', 'energy', 'mana', 'mp',
        'attack', 'defense', 'speed', 'luck',
        'count', 'number', 'amount', 'total', 'sum',
        'rank', 'wins', 'losses', 'draws', 'score', 'points'
    ]):
        return 'INTEGER'
    
    # 時間相關
    if any(x in header_lower for x in [
        'time', 'date', 'at', 'created', 'updated', 
        'joined', 'registered', 'last_'
    ]):
        return 'TIMESTAMP'
    
    # 布爾相關
    if any(x in header_lower for x in [
        'is_', 'has_', 'can_', 'active', 'enabled', 
        'banned', 'muted', 'verified', 'approved'
    ]):
        return 'INTEGER'  # SQLite 用 0/1 表示
    
    # 3. 預設
    return 'TEXT'


# ============================================================
# 數據庫初始化建議
# ============================================================

SQLITE_SCHEMA_TEMPLATE = """
-- SQLite 推薦 schema（自動生成）
-- 這個表會根據 SHEET 的表頭自動創建和修改

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- 以下欄位自動根據 SHEET 添加
    -- nickname TEXT,
    -- level INTEGER,
    -- xp INTEGER,
    -- kkcoin INTEGER,
    -- ... 其他欄位
);

-- 自動更新時間戳的觸發器
CREATE TRIGGER IF NOT EXISTS update_users_timestamp 
AFTER UPDATE ON users
BEGIN
    UPDATE users SET updated_at = CURRENT_TIMESTAMP 
    WHERE user_id = NEW.user_id;
END;
"""

# ============================================================
# PostgreSQL JSONB 方案（未來用）
# ============================================================

POSTGRESQL_SCHEMA_TEMPLATE = """
-- PostgreSQL 推薦 schema（生產環境）
-- 結合固定欄位 + 靈活的 JSONB

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    
    -- 核心玩家信息
    nickname VARCHAR(255),
    level INTEGER,
    xp INTEGER,
    
    -- 遊戲數據
    kkcoin INTEGER DEFAULT 0,
    hp INTEGER DEFAULT 100,
    stamina INTEGER DEFAULT 50,
    
    -- 元數據
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 靈活的 JSONB 欄位（存儲動態數據）
    custom_data JSONB DEFAULT '{}'::jsonb,
    
    -- 索引
    CONSTRAINT valid_user_id CHECK (user_id > 0)
);

-- 自動更新時間戳
CREATE OR REPLACE FUNCTION update_users_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_timestamp
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_users_timestamp();

-- JSONB 字段索引（加速查詢）
CREATE INDEX idx_users_custom_data ON users USING GIN (custom_data);
"""

# ============================================================
# 遷移策略
# ============================================================

class MigrationStrategy:
    """
    支持 SQLite → PostgreSQL 的遷移
    """
    
    SQLALCHEMY_URLS = {
        "sqlite": "sqlite:///user_data.db",
        "postgresql": "postgresql://user:password@localhost/kkgroup",
    }
    
    @staticmethod
    def generate_sqlalchemy_models(headers: list):
        """
        根據表頭生成 SQLAlchemy ORM 模型
        
        這樣可以無痛支持 SQLite 和 PostgreSQL 切換
        """
        return f"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 自動生成的欄位
{chr(10).join([f'    {header} = db.Column({infer_column_type(header)})'
               for header in headers if header not in ['user_id', 'created_at', 'updated_at']])}
    
    def to_dict(self):
        return {{
            'user_id': self.user_id,
{chr(10).join([f"            '{header}': self.{header}," for header in headers if header not in ['user_id']])}
        }}
"""


# ============================================================
# 推薦的欄位定義示例（基於你的遊戲）
# ============================================================

RECOMMENDED_SHEET_HEADERS = [
    "user_id",           # Discord user ID
    "nickname",          # 玩家名
    "level",             # 等級
    "xp",                # 經驗值
    "kkcoin",            # 貨幣
    "hp",                # 血量
    "stamina",           # 耐力
    "title",             # 頭銜
    "role",              # 職位/身份
    "status",            # 狀態（online/offline/dnd）
    "joined_at",         # 加入時間
    "last_seen",         # 上次見面時間
    # 可以繼續添加更多欄位...
]

# 基於上述表頭的推薦 SHEET 結構：
RECOMMENDED_SHEET_STRUCTURE = """
Row 1: [玩家資料, 遊戲數據, 遊戲數據, 遊戲數據, , , , , , , , ]
Row 2: [user_id, nickname, level, xp, kkcoin, hp, stamina, title, role, status, joined_at, last_seen]
Row 3: [123456789, 玩家A, 10, 1000, 5000, 100, 50, 新手, 玩家, online, 2024-01-01, 2024-01-15]
Row 4: [987654321, 玩家B, 15, 2500, 8000, 120, 60, 騎士, 管理員, online, 2024-01-02, 2024-01-15]
"""
