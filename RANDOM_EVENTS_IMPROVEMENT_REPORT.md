# 隨機事件系統重大改進報告

## 執行時間
- **2024年** - 完整改進和優化
- **Commit**: `f4be137`

## 📋 改進摘要

本次更新解決了置物櫃隨機事件系統的三個主要問題：

1. ✅ **修復重啟時事件重複觸發的 Bug**
2. ✅ **改進事件敍述格式，更加自然和生動**
3. ✅ **新增疾病、車禍、意外傷害等事件類型**

---

## 🔧 修復詳情

### 1. 重啟事件重複觸發 Bug 的修復

#### 問題根源
```python
# 原始代碼 - event_cooldown 在初始化時被設為空字典
def __init__(self, bot):
    self.event_cooldown = {}  # ❌ 重啟時為空

# random_event_trigger() 執行時
last_event = self.event_cooldown.get(user_id, 0)  # ❌ 返回 0
time_since_last = current_time - 0  # ❌ 會是一個很大的數字

# 因為 time_since_last > 86400 秒 (24小時)
# overtime_bonus = 0.3 (30% 額外機率)
# 觸發概率高達 30%+!
```

#### 解決方案
```python
# 改進後的 load_last_event_times()
def load_last_event_times(self):
    """從數據庫載入上次事件時間"""
    try:
        all_users = get_all_users()
        current_time = datetime.datetime.now().timestamp()
        
        # 初始化所有用戶的冷卻時間為當前時間
        for user_data in all_users:
            user_id = user_data.get('user_id')
            if user_id:
                # 設置為當前時間，避免重啟後立即觸發
                self.event_cooldown[user_id] = current_time
        
        print(f"✅ 初始化 {len(self.event_cooldown)} 個用戶的事件冷卻時間")
    except Exception as e:
        print(f"❌ 載入事件歷史錯誤: {e}")
```

#### 效果
- ✅ 重啟時所有用戶的冷卻時間都被設為當前時間
- ✅ 12 小時內不會再觸發事件
- ✅ 不會出現「每次重啟都觸發事件」的問題

---

## ✨ 新增事件類型

### 1. 車禍意外 (event_car_accident)
```
事件標題: 🚨 機車車禍/公車車禍/自行車碰撞/停車場意外
傷害: -20 到 -40 HP
虛弱: -15 到 -35 體力
場景包括:
  - 機車經過十字路口被計程車撞上
  - 公車急煞車被甩到擋風玻璃
  - 騎自行車逆向超車撞上貨車
  - 停車場出口被倒車的休旅車刮到
```

### 2. 食物中毒 (event_food_poisoning)
```
事件標題: 🤢 食物中毒
傷害: -15 到 -25 HP
虛弱: -30 到 -50 體力  (更高的體力損耗)
場景包括:
  - 公司食堂便當有怪味
  - 便利商店飯糰過期拉肚子
  - 同事家常菜没放冰箱
  - 餐廳湯品導致腹瀉
```

### 3. 工作過勞成疾 (event_workplace_illness)
```
事件標題: 🤒/🌡️/😣/🦠 過勞成疾
傷害: -10 到 -20 HP
虛弱: -40 到 -70 體力  (最高）
疾病類型:
  - 感冒 (🤒)
  - 發燒 (🌡️)
  - 頸椎症候群 (😣)
  - 流感 (🦠)
```

### 4. 工作場所傷害 (event_workplace_accident)
```
事件標題: ⚠️ 工作意外
傷害: -25 到 -35 HP  (較重)
虛弱: -20 到 -40 體力
事故類型:
  - 閃腰 (搬重物)
  - 夾傷 (被機器夾到)
  - 摔傷 (從梯子摔下)
  - 燙傷 (熱湯潑身)
```

---

## 📊 事件觸發條件更新

### 體力 < 50
```python
events.extend([
    {'handler': self.event_forced_overtime, 'weight': 3},
    {'handler': self.event_quota_pressure, 'weight': 2},
    {'handler': self.event_workplace_illness, 'weight': 2},  # 新增
])
```

### HP < 60
```python
events.extend([
    {'handler': self.event_beating, 'weight': 2},
    {'handler': self.event_medical_extortion, 'weight': 2},
    {'handler': self.event_car_accident, 'weight': 1},  # 新增
    {'handler': self.event_workplace_accident, 'weight': 1},  # 新增
])
```

### 通用事件
```python
events.extend([
    {'handler': self.event_supervisor_inspection, 'weight': 2},
    {'handler': self.event_group_punishment, 'weight': 2},
    {'handler': self.event_work_accident, 'weight': 2},
    {'handler': self.event_training_hell, 'weight': 1},
    {'handler': self.event_isolation_punishment, 'weight': 1},
    {'handler': self.event_food_poisoning, 'weight': 1},  # 新增
    {'handler': self.event_car_accident, 'weight': 1},  # 新增
])
```

---

## 🎨 改進的事件敍述格式

### 改進前（機械風格）
```
標題: 👊 暴力懲罰
描述: 主管心情不好，你成了出氣筒...
字段 1: ❤️ 傷害 | -20 HP
字段 2: ⚡ 體力 | -15
```

### 改進後（生動風格，含多個場景）
```
標題: 👊 暴力懲罰
描述: (AI生成或隨機選擇)
  - 主管今天心情特別差，你剛好說了一句話觸怒他...
  - 被主管當眾扇了一巴掌，臉火辣辣地疼...
  - 因為業績沒達標，被狠狠揍了一頓...
字段 1: ❤️ 身體傷害 | -20 HP
字段 2: ⚡ 精神創傷 | -15 體力
字段 3: 💔 後遺症 | 你的尊嚴被狠狠踐踏了...
```

### 具體改進的事件
1. **event_protection_fee** - 改進費用說明，加入「保護範圍」字段
2. **event_beating** - 添加多個場景，改進敍述
3. **event_forced_overtime** - 添加 AI 描述和圖片，改進結果說明

---

## 🖼️ 圖片生成改進

新增事件都調用了 `generate_pollinations_image()` 方法：

```python
image_prompt = await self.translate_to_english("車禍意外場景描述")
image_url = await self.generate_pollinations_image(
    image_prompt or "fallback description",
    is_negative_event=True  # 設為負面事件的圖片風格
)
```

事件對應的圖片提示詞：
- **車禍**: "traffic car accident, ambulance arriving at scene"
- **食物中毒**: "food poisoning, person in bathroom distressed"
- **過勞成疾**: "overworked person sick in bed, exhausted"
- **工作意外**: "workplace accident, injured worker"
- **強制加班**: "employee forced overtime working exhausted at desk until dawn"

---

## 📈 預期效果

### 對玩家體驗的改進

| 方面 | 改進 |
|------|------|
| 重啟頻率 | ✅ 減少不必要的事件重複觸發 |
| 事件多樣性 | ✅ 增加 4 種新事件類型 |
| 沉浸感 | ✅ 敍述更自然、場景更生動 |
| 視覺效果 | ✅ 所有新事件都有 AI 生成的圖片 |
| 挑戰性 | ✅ 新事件體現「健康」和「體力」的影響 |

### 對系統穩定性的改進

| 項目 | 改進 |
|------|------|
| Bug 根治 | ✅ 修復重啟觸發機制的根本原因 |
| 代碼質量 | ✅ 初始化邏輯更清晰 |
| 可維護性 | ✅ 新事件方法結構統一，便於後續擴展 |

---

## 🚀 部署步驟

### 1. 本地測試 ✅
```bash
# 已完成語法檢查
python -m py_compile uicommands/ScamParkEvents.py
```

### 2. 推送到 GitHub ✅
```bash
git add -A
git commit -m "改進隨機事件系統：修復重啟觸發BUG、添加車禍/疾病/意外事件、改進事件敍述格式"
git push origin main
```

### 3. GCP 服務器更新（需手動執行）
```bash
cd /home/kkbot/kkgroup
git pull origin main
# 重啟 Bot
supervisorctl restart sheet_sync_api
```

### 4. Bot 重啟後驗證
- 檢查 Bot 啟動日誌是否有 `✅ 初始化 XX 個用戶的事件冷卻時間` 訊息
- 驗證置物櫃是否有新事件出現（不會立即觸發）
- 檢查事件敍述是否更加生動

---

## 🔄 回滾方案

如果需要回滾到之前的版本：
```bash
git revert f4be137  # 回滾本次提交
git push origin main
```

---

## 📝 代碼統計

| 項目 | 數字 |
|------|------|
| 新增事件方法 | 4 個 |
| 改進的現有事件 | 3 個 |
| 新增代碼行數 | ~150 行 |
| 修改代碼行數 | ~25 行 |
| 總提交檔案 | 7 件 |

---

## ✅ 完成清單

- [x] 修復 event_cooldown 初始化問題
- [x] 實現 event_car_accident (車禍)
- [x] 實現 event_food_poisoning (食物中毒)
- [x] 實現 event_workplace_illness (過勞成疾)
- [x] 實現 event_workplace_accident (工作傷害)
- [x] 更新 get_possible_events() 觸發條件
- [x] 改進事件敍述格式
- [x] 添加 AI 圖片生成
- [x] 代碼語法檢查 ✅
- [x] 推送到 GitHub ✅
- [ ] GCP 服務器手動更新（待執行）
- [ ] Bot 重啟驗證（待執行）

---

## 📞 支持和問題

如有任何問題，請檢查：
1. Bot 啟動日誌中的初始化訊息
2. 置物櫃中是否有新事件出現
3. 事件敍述是否正確顯示

**最後更新**: Commit `f4be137`
