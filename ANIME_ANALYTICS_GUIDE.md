# 🎬 動畫數據分析系統 - 功能文檔

## 功能概述

本系統為動畫推送系統添加了完整的**數據分析和統計功能**，能夠追蹤每集的觀看人數、評分，並生成排行榜和統計報表。

---

## 📊 新增功能列表

### 1️⃣ **增強的 Embed 顯示** 

每個動畫通知現在包含更詳細的觀看數據：

```
📊 觀看數據
本集: 👥 12,345 觀看 | ⭐ 8.5 評分
本季均值: 👥 9,850 觀看 | ⭐ 8.3 評分  
本季統計: 12 集, 共 118,200 觀看
```

**技術亮點：**
- 實時展示本集的觀看人數（`popular` 字段）
- 自動計算本季所有集的平均觀看人數
- 顯示本季總觀看次數
- 展示本季平均評分趨勢

---

### 2️⃣ **完整的數據庫統計表**

#### `anime_statistics` 表（動畫層級統計）
```sql
CREATE TABLE anime_statistics (
    animeSn INTEGER PRIMARY KEY,
    anime_name TEXT,              -- 動畫名稱
    total_episodes INTEGER,       -- 本季集數
    avg_views REAL,               -- 平均觀看數
    avg_score REAL,               -- 平均評分
    total_views INTEGER,          -- 本季總觀看數
    last_updated TIMESTAMP
)
```

#### `episode_statistics` 表（每集統計）
```sql
CREATE TABLE episode_statistics (
    videoSn INTEGER PRIMARY KEY,
    animeSn INTEGER,              -- 動畫 ID
    episode_num TEXT,             -- 集數標識
    views INTEGER,                -- 觀看人數
    score REAL,                   -- 評分
    recorded_at TIMESTAMP         -- 記錄時間
)
```

**數據流：**
```
API 返回 (popular, score)
    ↓
記錄到 episode_statistics
    ↓
定期聚合到 anime_statistics
    ↓
在 embed 中展示平均數據
```

---

### 3️⃣ **新增斜線命令**

#### `/anime_ranking` - 觀看排行榜

```
🏆 本季動畫觀看排行榜
統計前 10 部動畫的數據

🥇 進擊的巨人 Season 4
   👥 總觀看: 145,320 | 平均: 12,110
   ⭐ 平均評分: 8.7 | 集數: 12

🥈 咒術迴戰 Season 2  
   👥 總觀看: 128,450 | 平均: 10,704
   ⭐ 平均評分: 8.5 | 集數: 12

🥉 進化之實
   👥 總觀看: 98,760 | 平均: 8,980
   ⭐ 平均評分: 8.2 | 集數: 11

#4 凪的新生活
...
```

**用途：**
- 快速了解本季最受歡迎的動畫
- 對比各部動畫的人氣度
- 追蹤評分趨勢

#### `/anime_stats [動畫名]` - 動畫統計分析

顯示特定動畫的詳細統計信息（開發中，目前導向到排行榜）

**計劃功能：**
- 集數 vs 觀看人數趨勢圖
- 評分變化指標
- 排名變化趨勢
- 發布週期分析

---

## 🔧 實現細節

### 數據收集機制

```python
async def fetch_anime_details_from_api(self, video_sn: int):
    # 1. 調用 API 获取 popular（觀看數）和 score（評分）
    popular = anime.get("popular", 0)
    score = anime.get("score", 0)
    
    # 2. 立即記錄到統計表
    self.db.record_episode_stats(
        video_sn=video_sn,
        anime_sn=anime_sn,
        episode_num=f"Ep. {ep_number}",
        views=popular,        # 👥 觀看人數
        score=score          # ⭐ 評分
    )
    
    # 3. 緩存詳細信息供 embed 使用
    self.db.cache_anime_details(...)
```

### 統計聚合邏輯

```python
def update_anime_statistics(self, anime_sn: int, anime_name: str):
    # SQL 聚合
    SELECT 
        COUNT(*) as total_episodes,      -- 本季集數
        AVG(views) as avg_views,         -- 平均觀看
        AVG(score) as avg_score,         -- 平均評分
        SUM(views) as total_views        -- 總觀看數
    FROM episode_statistics
    WHERE animeSn = ?
```

### Embed 中的實時計算

```python
# 在 generate_anime_embed() 中
anime_stats = self.db.get_anime_statistics(anime_sn)
if anime_stats:
    # 顯示本集 vs 本季平均
    stats_lines = [
        f"本集: 👥 {popular:,} 觀看 | ⭐ {score:.1f} 評分",
        f"本季均值: 👥 {avg_views:,.0f} 觀看 | ⭐ {avg_score:.1f} 評分"
    ]
```

---

## 📈 使用場景

### 1. **實時監控人氣趨勢**
- 每集發布後立即看到觀看人數
- 對比該動畫的平均水平
- 發現冷門和爆紅集數

### 2. **季度分析報告**
```
本季統計概況：
• 共上架 45 部動畫，352 集
• 平均觀看: 8,234 人/集
• 平均評分: 7.8 分
• 最受歡迎: 進擊的巨人 (145K 觀看)
• 黑馬動畫: 冷門但評分高的作品
```

### 3. **推薦系統基礎**
- 基於觀看數推薦熱門動畫
- 基於評分推薦高質量作品
- 基於趨勢推薦上升動畫

---

## 🚀 部署狀態

✅ **已實施的功能：**
- ✅ 統計數據庫結構（3 個新表）
- ✅ 觀看數據實時記錄
- ✅ Embed 中顯示平均數據
- ✅ `/anime_ranking` 排行榜命令
- ✅ `/anime_stats` 指令框架

⏳ **計劃中的功能：**
- 📊 趨勢圖表（使用 matplotlib/seaborn）
- 📈 周/月統計報告
- 🎯 個性化推薦列表
- 💾 數據導出功能（CSV/JSON）

---

## 🔍 SQL 查詢示例

### 查詢排行前 5 的動畫
```sql
SELECT anime_name, total_views, avg_views, avg_score
FROM anime_statistics
ORDER BY total_views DESC
LIMIT 5;
```

### 查詢某動畫的集數趨勢
```sql
SELECT episode_num, views, score
FROM episode_statistics
WHERE animeSn = ?
ORDER BY recorded_at;
```

### 本季最高評分動畫
```sql
SELECT anime_name, avg_score, total_episodes
FROM anime_statistics
WHERE avg_score > 8.0
ORDER BY avg_score DESC;
```

---

## 💡 未來擴展

### Phase 2: 可視化儀表板
- 集成 matplotlib 生成趨勢圖
- 實時更新的 Discord embed 圖表
- 每週統計報告

### Phase 3: 智能推薦
- 基於評分 + 觀看數的評分算法
- 個性化推薦引擎
- 發現冷門佳作

### Phase 4: 數據導出
- CSV 數據導出
- 季度總結報告生成
- 分析數據的可視化

---

## 📝 命令總結

| 命令 | 功能 | 狀態 |
|------|------|------|
| `/anime_ranking` | 查看觀看排行榜 | ✅ 完成 |
| `/anime_stats {name}` | 查詢動畫統計 | ⏳ 開發中 |
| `/anime_test` | 測試推送 | ✅ 完成 |
| `/anime_start` | 啟動任務 | ✅ 完成 |
| `/anime_status` | 查看系統狀態 | ✅ 完成 |

---

**最後更新：** 2026-04-12 09:01 UTC  
**提交 ID：** 2c1feb61
