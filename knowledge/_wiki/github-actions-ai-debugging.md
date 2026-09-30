# GitHub Actions AI 除錯系統

## 概述

KKGroup Discord Bot系統的AI驅動自動化除錯與修復系統，使用Gemini API作為核心AI引擎。

## 系統架構

### 🤖 AI監控流程

```
Bot錯誤發生 → LogMonitor 捕獲 → GitHub Actions觸發 → Gemini AI分析 → 自動修復 → VM重啟
```

### 🔧 核心組件

1. **LogMonitor 監控** (`cogs/common/log_monitor.py`)
   - 實時監控系統服務狀態
   - 捕獲OOM Killer、服務崩潰等錯誤
   - 自動執行基礎診斷指令

2. **GitHub Actions AI分析** (`.github/workflows/ai-debug-monitor.yml`)
   - 接收錯誤日誌
   - 使用Gemini 2.0 Flash進行深度分析
   - 生成修復代碼和解決方案

3. **自動修復機制**
   - AI生成修復代碼
   - 自動提交修復PR
   - VM自動重啟驗證

## API配置

### 🌟 Gemini API整合

```yaml
# GitHub Secrets
GEMINI_API_KEY: "<在 GitHub Secrets 設定，勿寫入文件>"
DISCORD_WEBHOOK_URL: "https://discord.com/api/webhooks/..."
```

### 📊 API使用策略

- **主要模型**: Gemini 2.0 Flash (快速響應)
- **備援模型**: Groq llama-3.3-70b (降級備用)
- **冷卻機制**: 429錯誤自動冷卻60秒
- **Token限制**: 單次分析最大1000 tokens

## 功能特性

### 🔍 智能錯誤分析

1. **根本原因識別**
   - OOM Killer觸發原因
   - 記憶體洩漏檢測
   - 依賴衝突分析
   - 配置錯誤診斷

2. **影響範圍評估**
   - 服務可用性影響
   - 用戶體驗評級
   - 數據完整性檢查
   - 系統穩定性評分

3. **自動修復生成**
   - 代碼修復建議
   - 配置優化方案
   - 預防措施建議
   - 監控改進建議

### 🚀 自動修復能力

#### **常見問題修復**
- **記憶體問題**: 自動調整swappiness、清理進程
- **依賴衝突**: 自動降級/升級套件版本
- **配置錯誤**: 自動修復.env配置
- **服務崩潰**: 自動重啟服務、清理日誌

#### **修復驗證流程**
1. AI生成修復代碼
2. 自動創建Feature Branch
3. 提交修復PR
4. VM自動拉取並重啟
5. 驗證修復效果

## 觸發條件

### 🔄 自動觸發

```yaml
on:
  push:
    branches: [ main, master ]  # 代碼推送時檢查
  workflow_dispatch:              # 手動觸發
  schedule:
    - cron: '0 */6 * * *'   # 每6小時檢查
```

### 📱 Discord通知系統

#### **通知等級**
- 🔴 **嚴重**: 服務完全中斷，需要立即處理
- 🟡 **警告**: 部分功能異常，建議檢查
- 🟢 **信息**: 正常維護信息，僅供參考

#### **通知內容**
- 錯誤摘要和根本原因
- AI分析結果和置信度
- 修復建議和實施步驟
- 預期修復時間

## 擴展性設計

### 🔌 API擴展機制

系統設計支援多AI提供商：

```python
# AI提供商配置（實際使用；與 cogs/common/AI.py 的降級鏈一致）
AI_PROVIDERS = {
    "gemini": {
        "api_key": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
        "endpoint": "https://generativelanguage.googleapis.com",
        "role": "主要分析模型"
    },
    "groq": {
        "api_key": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "role": "降級備援（純文字，無工具）"
    }
}
```

### 📈 未來擴展方向

1. **更多AI模型支援**
   - 依 `cogs/common/AI.py` 既有降級鏈擴充（NVIDIA / SambaNova 等）
   - 本地開源模型

2. **進階功能**
   - 時間旅行除錯
   - 預測性維護
   - 性能優化建議

3. **整合監控**
   - Grafana儀表板
   - Prometheus指標
   - Slack/Teams通知

## 使用指南

### 🛠️ 手動觸發除錯

```bash
# 通過GitHub網頁
1. 進入Actions頁面
2. 選擇"AI Debug Monitor"
3. 點擊"Run workflow"
4. 輸入觸發參數
```

### 📋 檢查清單

#### **部署前檢查**
- [ ] GitHub Secrets已配置
- [ ] Discord Webhook已設定
- [ ] Gemini API Key有效
- [ ] VM網路連線正常
- [ ] Bot服務運行中

#### **功能測試**
- [ ] 錯誤捕獲正常
- [ ] AI分析準確
- [ ] 修復代碼有效
- [ ] 通知及時發送
- [ ] 自動重啟成功

## 故障排除

### ⚠️ 常見問題

#### **API呼叫失敗**
```bash
# 檢查API Key
echo $GEMINI_API_KEY | cut -c1-10

# 測試API連線
curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"test"}]}]}'
```

#### **Discord通知失敗**
```bash
# 檢查Webhook URL
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content":"測試通知"}'
```

#### **VM重啟失敗**
```bash
# 檢查systemd服務
sudo systemctl status bot.service
sudo journalctl -u bot.service -n 20 --no-pager
```

## 最佳實踐

### 💡 效能優化

1. **API使用優化**
   - 合理設置請求頻率
   - 使用冷卻機制避免限制
   - 選擇適合的模型大小

2. **日誌管理**
   - 定期清理舊日誌
   - 使用結構化日誌格式
   - 設置日誌輪轉

3. **安全考量**
   - API Key定期輪換
   - 使用最小權限原則
   - 監控API使用量

## 相關文檔

- [Gemini API文檔](https://ai.google.dev/gemini-api)
- [LogMonitor 與 Auto AI Fix 流程總覽](concepts/log_monitor_pipeline.md)
- [開發工具和流程](concepts/development-tools-and-workflow.md)
- [部署和維運指南](concepts/deployment-and-operations.md)
