# 🗄️ Flask API + SHEET 最優數據庫架構設計

**生成日期**: 2026年2月5日  
**目的**: 設計一個真正「以SHEET為主」、支持動態擴展的數據庫架構

---

## 📊 你的問題分析

### Q1: 哪種DB最適合？什麼格式最適合持續開發擴展？

### Q2: 使用Flask API是否能以SHEET為主，新增欄位自動檢測？

### Q3: 建立最適合的DB類型，避免格式對不上？

---

## ✅ 最佳方案對比

### 方案 A: SQLite + 動態Schema（現在的做法改進版）⭐ **推薦用於開發**

```
優點:
✅ 零配置、文件型數據庫
✅ 已在用，學習成本低
✅ 支持動態 ALTER TABLE 添加欄位
✅ 小型團隊/個人項目完美

缺點:
❌ 並發寫入有限制
❌ 無JSONB支持（只有TEXT）
❌ 架構變更困難（ALTER TABLE 速度慢）
```

**實施**:
```python
def ensure_db_schema(headers):
    # 自動檢測新欄位，用 ALTER TABLE 添加
    # 無需手動修改代碼
```

---

### 方案 B: PostgreSQL + JSONB（推薦用於生產）⭐⭐ **最佳靈活性**

```
優點:
✅ 完整的JSONB支持（原生JSON欄位）
✅ 高併發、企業級穩定
✅ 動態欄位 + 結構化欄位並存
✅ 全文搜索、複雜查詢
✅ GCP Cloud SQL 直接支持

缺點:
❌ 需要服務器部署
❌ 配置複雜
❌ 成本較高
```

**實施**:
```sql
-- 核心結構：既有固定欄位，也有靈活的 JSON 欄位
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    nickname VARCHAR(255),
    level INTEGER,
    xp INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- JSONB 欄位存儲動態欄位
    custom_data JSONB DEFAULT '{}'::jsonb
);

-- 插入示例
INSERT INTO users (user_id, nickname, level, xp, custom_data) 
VALUES (
    123456789, 
    '玩家名', 
    10, 
    1000,
    '{
        "kkcoin": 5000,
        "title": "新手",
        "hp": 100,
        "stamina": 50,
        "custom_field_1": "值",
        "custom_field_2": "值"
    }'::jsonb
);
```

---

### 方案 C: MongoDB（最靈活，但管理複雜）

```
優點:
✅ 完全無schema
✅ 最大靈活性

缺點:
❌ 數據重複、難以維護
❌ 查詢性能不如關係型
❌ 不適合嚴謹的遊戲數據
```

---

## 🎯 我的推薦：混合方案

### 開發階段（現在）- SQLite + 改進的動態Schema
- 保持現有的 SQLite 數據庫
- 改進自動欄位檢測邏輯
- 所有欄位一視同仁存儲

### 生產階段（未來）- PostgreSQL + JSONB + 動態Schema
- 核心欄位在表中
- 靈活欄位在 JSONB 中
- 最好的性能和靈活性

---

## 🚀 實現方案：「以SHEET為主」的動態系統

### 核心設計原則

```
1️⃣ 真理來源 (Source of Truth) = SHEET 的 Row 2（表頭）
2️⃣ 自動同步 = Flask API 自動檢測新欄位
3️⃣ 零代碼修改 = 無需改 Python 代碼添加新欄位
4️⃣ 格式對齊 = 自動 CREATE/ALTER，避免不匹配
```

### 系統架構

```
Google Sheets (表頭 = 欄位定義)
        ↓
Apps Script (提取表頭)
        ↓
Flask API /api/sync
        ↓
sheet_sync_manager.ensure_db_schema()
        ↓
SQLite: 自動 ALTER TABLE 添加欄位
        ↓
數據插入/更新
```

---

## 💾 適配當前SHEET的最優DB Schema

### 當前SHEET的欄位分析

根據你的系統，SHEET 應該包含：

```
Row 1: [分組, 分組, 分組, ...]          ← 分組標題
Row 2: [user_id, nickname, level, ...]   ← 表頭（欄位定義）
Row 3+: [數據...]                         ← 實際數據
```

### 推薦的DB Schema（SQLite）

```python
# 自動生成，無需手動定義
def create_flexible_schema(headers):
    """
    根據SHEET表頭動態創建DB表
    原則：
    - user_id: 整數，主鍵
    - nickname: 文字，玩家名
    - level, xp, kkcoin, hp, stamina: 整數（遊戲數值）
    - 其他: 文字（靈活存儲）
    - created_at, updated_at: 時間戳
    """
    
    columns = [
        "user_id INTEGER PRIMARY KEY",
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ]
    
    # 定義常見欄位的類型
    FIELD_TYPES = {
        "user_id": "INTEGER PRIMARY KEY",
        "nickname": "TEXT",
        "level": "INTEGER",
        "xp": "INTEGER",
        "kkcoin": "INTEGER",
        "hp": "INTEGER",
        "stamina": "INTEGER",
        "title": "TEXT",
        "role": "TEXT",
        # ... 其他已知欄位
    }
    
    # 遍歷表頭，自動添加欄位
    for header in headers:
        if header in ["user_id", "created_at", "updated_at"]:
            continue
        
        # 優先使用定義的類型，否則使用 TEXT
        col_type = FIELD_TYPES.get(header, "TEXT")
        columns.append(f'"{header}" {col_type}')
    
    sql = f"CREATE TABLE users ({', '.join(columns)})"
    return sql
```

### 生成的表結構示例

```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    nickname TEXT,
    level INTEGER,
    xp INTEGER,
    kkcoin INTEGER,
    hp INTEGER,
    stamina INTEGER,
    title TEXT,
    custom_field_1 TEXT,       -- 新增欄位自動添加
    custom_field_2 TEXT
)
```

---

## 🔧 如何實現「真正以SHEET為主」

### 步驟1：改進 sheet_sync_manager.py 的自動檢測

```python
class SheetSyncManager:
    # ... 現有代碼 ...
    
    def ensure_db_schema(self, headers):
        """
        ✨ 核心邏輯：自動檢測和創建/修改表
        
        工作流：
        1. 連接數據庫
        2. 檢查表是否存在
        3. 如果不存在，根據headers創建
        4. 如果存在，檢查是否有新欄位，用 ALTER TABLE 添加
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 檢查表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # 表不存在，根據表頭創建
                print("📝 表不存在，根據表頭創建...")
                self._create_table_from_headers(cursor, headers)
            else:
                # 表存在，檢查是否有新欄位
                print("✅ 表已存在，檢查新欄位...")
                self._migrate_schema(cursor, headers)
            
            conn.commit()
        finally:
            conn.close()
    
    def _create_table_from_headers(self, cursor, headers):
        """根據表頭智能創建表"""
        columns = [
            "user_id INTEGER PRIMARY KEY",
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ]
        
        for header in headers:
            if header in ["user_id", "created_at", "updated_at"]:
                continue
            
            # 智能判斷欄位類型
            col_type = self._infer_column_type(header)
            columns.append(f'"{header}" {col_type}')
        
        sql = f"CREATE TABLE users ({', '.join(columns)})"
        print(f"📝 SQL: {sql[:150]}...")
        cursor.execute(sql)
        print("✅ 表已根據表頭創建")
    
    def _infer_column_type(self, header):
        """
        智能判斷欄位類型
        
        規則：
        - 包含 'id' 的 → INTEGER
        - 包含 'coin', 'xp', 'level', 'hp', 'stamina' → INTEGER
        - 包含 'time', 'date' → TIMESTAMP
        - 其他 → TEXT
        """
        header_lower = header.lower()
        
        if 'id' in header_lower:
            return 'INTEGER'
        elif any(x in header_lower for x in ['coin', 'xp', 'level', 'hp', 'stamina', 'exp']):
            return 'INTEGER'
        elif any(x in header_lower for x in ['time', 'date', 'at']):
            return 'TIMESTAMP'
        else:
            return 'TEXT'
```

### 步驟2：改進 Flask API 的數據驗證

```python
@app.route('/api/sync', methods=['POST'])
def sync():
    """
    同步端點
    
    ✨ 改進：
    1. 自動確保DB schema與表頭匹配
    2. 無需手動修改代碼添加新欄位
    3. 自動發現和應用新欄位
    """
    data = request.get_json()
    headers = data.get('headers', [])
    rows = data.get('rows', [])
    
    try:
        # ✨ 關鍵：自動確保schema與表頭一致
        sync_manager.ensure_db_schema(headers)
        
        # 解析和插入記錄
        records = sync_manager.parse_records(headers, rows)
        updated, inserted, errors = sync_manager.insert_records(records)
        
        return jsonify({
            "status": "success",
            "message": f"同步完成",
            "stats": {
                "updated": updated,
                "inserted": inserted,
                "errors": errors
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
```

### 步驟3：Google Sheets 結構設計

```
SHEET 結構（推薦）：

Row 1: [玩家資料, 遊戲數據, , , 自定義欄位, ...]
       ↑ 分組標題（用於視覺組織）

Row 2: [user_id, nickname, level, xp, kkcoin, hp, stamina, title, custom_1, custom_2, ...]
       ↑ 表頭（欄位定義）
       ↑ 這一行就是 Python 代碼的欄位定義！

Row 3+: [123456789, 玩家名, 10, 1000, 5000, 100, 50, 新手, 值1, 值2, ...]
        ↑ 實際數據
```

---

## 🎁 立即可用的改進代碼

我將為你提供完整的升級版本，包括：

1. **改進的 sheet_sync_manager.py**
   - 自動類型推斷
   - 完全動態schema
   - 智能欄位檢測

2. **改進的 sheet_sync_api.py**
   - 自動schema同步端點
   - 欄位診斷端點
   - 更好的錯誤報告

3. **新的 database_schema.py**
   - 定義推薦的欄位類型映射
   - 支持未來的 PostgreSQL 遷移

4. **部署指南**
   - 如何無痛從 SQLite 遷移到 PostgreSQL

---

## 📈 擴展路線圖

### Phase 1: 現在（SQLite + 改進）
- 實現真正的動態schema
- SHEET = 唯一的欄位定義來源
- 無需修改代碼添加新欄位

### Phase 2: 3-6個月後（PostgreSQL 準備）
- 遷移到 PostgreSQL
- 核心欄位 + JSONB 混合存儲
- 性能優化

### Phase 3: 1年後（完全自動化）
- 多個遊戲服務器支持
- 自動備份和恢復
- 實時數據分析

---

## ❓ 常見問題

### Q: 如果SHEET中刪除了一個欄位，DB會自動刪除嗎？
```
A: 不會（這是故意的）
   原因：防止意外數據丟失
   做法：可以手動執行清理腳本或 Python 指令
```

### Q: 新增欄位後需要重啟Flask嗎？
```
A: 不需要
   原因：每次 sync 請求都會檢查 schema
   無需重啟，自動添加
```

### Q: 現有的 SQLite user_data.db 會被覆蓋嗎？
```
A: 不會
   改進代碼完全向後兼容
   可以直接替換而無需遷移
```

### Q: 性能會受影響嗎？
```
A: 幾乎沒有
   ALTER TABLE 只在新欄位出現時執行（極少）
   數據插入性能不變
```

---

## 🎯 下一步

你希望我：

1. **立即生成改進代碼**
   - 更新 sheet_sync_manager.py（自動類型推斷）
   - 更新 sheet_sync_api.py（自動schema檢查）
   - 新增 database_schema.py（欄位映射表）

2. **提供遷移腳本**
   - 從現有 SQLite 無痛遷移到 PostgreSQL

3. **創建測試數據**
   - 用你當前SHEET的實際欄位測試

4. **編寫運維指南**
   - 如何管理和擴展欄位

請告訴我你要先做哪一個！

---

## 📚 參考資源

- [SQLite Dynamic Schema](https://www.sqlite.org/pragma.html#pragma_table_info)
- [PostgreSQL JSONB Guide](https://www.postgresql.org/docs/current/datatype-json.html)
- [Flask-SQLAlchemy Dynamic Models](https://flask-sqlalchemy.palletsprojects.com/)

