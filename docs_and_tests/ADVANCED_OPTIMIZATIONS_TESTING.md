# 🧪 進階優化實戰指南

## 測試場景與預期行為

### 場景 1: 代碼相關提問（動態 Token 調整）

```
用戶輸入: "幫我寫一個 Python 函數來計算斐波那契數列"

預期日誌输出:
═══════════════════════════════════════════════════════════
⏳ 嘗試使用 Gemini (模型: gemini-2.0-flash)...
🔧 檢測到代碼相關任務，maxOutputTokens 調整為 800
📨 Gemini generateContent 請求詳情:
   - 端點: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
   - 方式: POST generateContent（手動滑動窗口記憶）
   - System Instruction 字數: 150
   - Contents 項數: 1
   - Temperature: 0.7
   - maxOutputTokens: 800  ⭐ 注意: 800 而非 300
═══════════════════════════════════════════════════════════

回應長度: ~600-800 字符（完整代碼 + 解釋）
Token 消耗: ~850 tokens（比固定 300 時的多覆蓋率）
```

### 場景 2: 普通對話（簡潔回應提示）

```
用戶輸入: "最近天氣怎麼樣？"

預期日誌输出:
═══════════════════════════════════════════════════════════
⏳ 嘗試使用 Gemini (模型: gemini-2.0-flash)...
💬 檢測到普通對話，maxOutputTokens 設為 300（簡潔回應）
📨 Gemini generateContent 請求詳情:
   - 端點: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
   - 方式: POST generateContent（手動滑動窗口記憶）
   - System Instruction 字數: 198  ⭐ 包含簡潔提示
   - Contents 項數: 1
   - Temperature: 0.7
   - maxOutputTokens: 300
═══════════════════════════════════════════════════════════

回應長度: ~50-100 字符（簡潔回答）
Token 消耗: ~120 tokens（節省 60%）

System Instruction 包含:
"...你是一個有用的 Discord 機器人...
請在一句話內回覆，語言簡潔。"  ⭐ 自動添加
```

### 場景 3: 長期對話摘要注入（記憶摘要機制）

```
對話序列:
1️⃣ 用戶: "我叫 Alice，我想建立一個 Discord 機器人"
2️⃣ 助手: "很樂意幫助..."
3️⃣ 用戶: "機器人名稱叫做 MyBot"
4️⃣ 助手: "好的..."
5️⃣ 用戶: "我想加入歡迎消息功能"
6️⃣ 助手: "可以用 on_member_join..."
...
(重複直到第 11 條訊息)

第 11 條訊息添加時:
═══════════════════════════════════════════════════════════
ℹ️ 已為用戶 123456789 注入對話摘要
🧠 提取的摘要: Alice、Discord、MyBot、歡迎、機器人
═══════════════════════════════════════════════════════════

接下來的 API 呼叫:
───────────────────────────────────────────────────────
System Instruction 變為:
"你是一個有用的 Discord 機器人...

🧠 前文摘要 (記住這些重要信息): Alice、Discord、MyBot、歡迎、機器人"
───────────────────────────────────────────────────────

用戶第 12 條: "幫我調整歡迎消息的格式"
助手理解: "Alice 要調整 MyBot 的歡迎消息格式 ✅"
而非:    "誰要調整什麼？缺少上下文 ❌"
```

### 場景 4: API 冷却機制（429 處理）

```
時間序列: (都在同一個小時內，API 額度緊張)

T=0:00
用戶: "寫一個 Flask API"
Gemini API 返回 429 (配額超限)
日誌:
⚠️ Gemini 配額超限 (429)，設置 60 秒冷却
❄️ Gemini 仍在冷却中，跳過...
⏳ 嘗試使用 Groq...
✅ Groq 成功回應

T=0:30
用戶: "解釋前面代碼"
日誌:
❄️ Gemini 仍在冷却中 (30s 後恢復)，跳過...
⏳ 嘗試使用 Groq...
✅ Groq 成功回應 (第 2 次)

T=1:05
用戶: "改進該代碼"
日誌:
✅ Gemini 冷却時間已過，重新嘗試...
⏳ 嘗試使用 Gemini...
✅ Gemini 成功回應 (恢復正常)

統計:
- 第 1 次請求: Gemini (1.5s)
- 第 2 次請求: Groq (0.8s) ✅ 快速轉移，無延遲
- 第 3 次請求: Gemini (1.5s) ✅ 自動恢復
```

---

## 🔍 日誌檢查清單

部署後，檢查以下日誌輸出是否符合預期：

### ✅ 初始化日誌
```
2026-04-16 14:30:45 INFO: ✅ 初始化 2 個 API 配置: Gemini → Groq
```

### ✅ 動態 Token 檢測
```
[代碼任務]
🔧 檢測到代碼相關任務，maxOutputTokens 調整為 800

[聊天任務]
💬 檢測到普通對話，maxOutputTokens 設為 300（簡潔回應）
```

### ✅ 記憶摘要
```
🧠 已為用戶 123456789 注入對話摘要: 關鍵字1、關鍵字2、...
```

### ✅ API 冷却
```
[設置冷却]
⚠️ Gemini 配額超限 (429)，設置 60 秒冷却

[檢查冷却]
❄️ Gemini 仍在冷却中 (45s 後恢復)，跳過...

[冷却恢復]
✅ Gemini 冷却時間已過，重新嘗試...
```

---

## 💻 本地測試代碼

### 測試 1: 檢測任務類型

```python
# 在 Python REPL 中運行
from cogs.common.AI import AIResponse
from unittest.mock import MagicMock

# 創建 mock bot 對象
mock_bot = MagicMock()
ai_response = AIResponse(mock_bot)

# 測試代碼檢測
test_cases = [
    ("寫一個 Python 函數", "code"),
    ("這個代碼怎麼解釋", "code"),
    ("如何實現排序算法", "code"),
    ("最近天氣如何", "chat"),
    ("你好呀", "chat"),
    ("幫我找一下資料", "chat"),
    ("代碼有 bug，幫我看看", "code"),  # 邊界情況
]

for prompt, expected in test_cases:
    result = ai_response._detect_task_type(prompt)
    status = "✅" if result == expected else "❌"
    print(f"{status} '{prompt}' → {result} (期望: {expected})")
```

**預期輸出**:
```
✅ '寫一個 Python 函數' → code (期望: code)
✅ '這個代碼怎麼解釋' → code (期望: code)
✅ '如何實現排序算法' → code (期望: code)
✅ '最近天氣如何' → chat (期望: chat)
✅ '你好呀' → chat (期望: chat)
✅ '幫我找一下資料' → chat (期望: chat)
✅ '代碼有 bug，幫我看看' → code (期望: code)
```

### 測試 2: 摘要提取

```python
from cogs.common.AI import ContextManager

cm = ContextManager(max_history=5)

# 模擬舊訊息
old_messages = [
    {"role": "user", "parts": [{"text": "我叫 Alice，我想學 Python"}]},
    {"role": "user", "parts": [{"text": "建立一個 Discord 機器人"}]},
    {"role": "user", "parts": [{"text": "怎樣添加命令功能"}]},
]

summary = cm._extract_summary(old_messages)
print(f"提取的摘要: {summary}")
# 預期輸出: "Alice、Python、Discord、機器人、命令" 等關鍵字組合
```

### 測試 3: 冷却機制

```python
import time
from cogs.common.AI import AIResponse
from unittest.mock import MagicMock

mock_bot = MagicMock()
ai_response = AIResponse(mock_bot)

# 模擬設置冷却
api_name = "Gemini"
ai_response.api_cooldowns[api_name] = time.time() + 60

# 檢查冷却狀態
def is_in_cooldown(api_name):
    if api_name not in ai_response.api_cooldowns:
        return False, 0
    cooldown_until = ai_response.api_cooldowns[api_name]
    if time.time() < cooldown_until:
        remaining = int(cooldown_until - time.time())
        return True, remaining
    return False, 0

# 測試
in_cooldown, remaining = is_in_cooldown("Gemini")
print(f"✅ {api_name} 冷却狀態: {'是' if in_cooldown else '否'} (剩餘: {remaining}s)")

# 等待一秒
time.sleep(1)

in_cooldown, remaining = is_in_cooldown("Gemini")
print(f"✅ {api_name} 冷却狀態: {'是' if in_cooldown else '否'} (剩餘: {remaining}s)")
```

**預期輸出**:
```
✅ Gemini 冷却狀態: 是 (剩餘: 59s)
✅ Gemini 冷却狀態: 是 (剩餘: 58s)
```

---

## 📡 GCP 部署驗證腳本

將此腳本保存為 `verify_optimizations.sh`，在 GCP VM 上運行：

```bash
#!/bin/bash

echo "════════════════════════════════════════════════════════"
echo "🚀 進階優化驗證腳本"
echo "════════════════════════════════════════════════════════"

# 1. 檢查代碼是否已更新
echo ""
echo "[1️⃣] 檢查代碼變更..."
if grep -q "_detect_task_type" /home/user/kkgroup/cogs/common/AI.py; then
    echo "✅ 動態 Token 檢測方法已部署"
else
    echo "❌ 動態 Token 檢測方法未找到"
fi

if grep -q "summary_cache" /home/user/kkgroup/cogs/common/AI.py; then
    echo "✅ 記憶摘要機制已部署"
else
    echo "❌ 記憶摘要機制未找到"
fi

if grep -q "api_cooldowns" /home/user/kkgroup/cogs/common/AI.py; then
    echo "✅ API 冷却機制已部署"
else
    echo "❌ API 冷却機制未找到"
fi

# 2. 檢查服務狀態
echo ""
echo "[2️⃣] 檢查服務狀態..."
sudo systemctl status bot.service --no-pager | grep "Active"

# 3. 檢查最新日誌（前 20 行）
echo ""
echo "[3️⃣] 最新 20 行日誌..."
sudo journalctl -u bot.service -n 20 --no-pager | tail -10

# 4. 查看是否有優化日誌
echo ""
echo "[4️⃣] 尋找優化相關日誌..."
sudo journalctl -u bot.service --since "5 minutes ago" --no-pager | grep -E "🔧|💬|🧠|❄️" | head -10

echo ""
echo "════════════════════════════════════════════════════════"
echo "驗證完成！"
echo "════════════════════════════════════════════════════════"
```

### 運行驗證

```bash
# SSH 到 GCP VM
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

# 運行驗證腳本
bash verify_optimizations.sh

# 預期輸出
════════════════════════════════════════════════════════
🚀 進階優化驗證腳本
════════════════════════════════════════════════════════

[1️⃣] 檢查代碼變更...
✅ 動態 Token 檢測方法已部署
✅ 記憶摘要機制已部署
✅ API 冷却機制已部署

[2️⃣] 檢查服務狀態...
     Active: active (running) since Tue 2026-04-16 15:30:45 UTC

[3️⃣] 最新 20 行日誌...
⏳ 嘗試使用 Gemini (模型: gemini-2.0-flash)...
💬 檢測到普通對話，maxOutputTokens 設為 300（簡潔回應）

[4️⃣] 尋找優化相關日誌...
💬 檢測到普通對話，maxOutputTokens 設為 300（簡潔回應）
✅ 使用以下 API 成功回應

════════════════════════════════════════════════════════
驗證完成！
════════════════════════════════════════════════════════
```

---

## 🎯 關鍵成功指標 (KSI)

部署 24 小時後應監控的指標：

| KSI | 目標值 | 檢查方法 | 優先級 |
|----|-------|--------|-------|
| **平均回應時間** | < 1.5s | `journalctl` 日誌分析 | 🔴 高 |
| **Token 節省率** | > 25% | API 配額使用情況 | 🔴 高 |
| **長期對話質量** | > 80% 主觀評分 | 用戶反饋 | 🟡 中 |
| **API 故障轉移時間** | < 0.5s | 日誌中 Groq 響應時間 | 🟡 中 |
| **冷却機制有效率** | > 95% 無重試失敗 | 429 + 冷却設置日誌對比 | 🟢 低 |

---

## 🐛 常見問題排查

### Q: 為什麼日誌中沒有看到 🔧 標記？
**A**: 檢查 `_detect_task_type()` 中的關鍵字列表是否包含用戶提示詞中的詞。如果用戶用英文問「Write a Python function」，需要更新關鍵字為包含英文的版本。

### Q: 摘要注入後回應變慢了？
**A**: 摘要添加到 `system_instruction` 會增加約 50-100 tokens。如果摘要太長，可以調整 `_extract_summary()` 中的關鍵字數量限制（目前為 5）。

### Q: API 冷却時間太長，能改短嗎？
**A**: 可以在 `call_ai_api()` 中找到 `time.time() + 60`，改為 `time.time() + 30` 或其他時長。建議根據 API 提供商的文檔決定。

### Q: 為什麼有時候代碼類問題還是返回 300 tokens？
**A**: 檢查 `Groq` 回應時的 `max_tokens` 設置。Groq 的 OpenAI 兼容格式不自動同步動態檢測，可能需要額外邏輯。

---

**文檔版本**: 1.0.0  
**最後更新**: 2026-04-16  
**維護者**: GitHub Copilot
