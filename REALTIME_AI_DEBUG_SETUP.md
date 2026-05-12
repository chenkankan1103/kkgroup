# 實時 AI 除錯系統設定指南

## 🚀 概述

已將原本只在 push 時觸發的 GitHub Actions AI 除錯系統，升級為**實時錯誤觸發**模式。當 Discord Bot 發生高緊急程度錯誤時，會立即觸發深度 AI 分析。

## 📋 系統架構

```
Bot 錯誤發生 → LogMonitor 實時檢測 → 本地 Gemini 快速分析
                                    ↓
                            判斷緊急程度（高/中/低）
                                    ↓
                            高緊急 → 觸發 GitHub Actions
                                    ↓
                        深度 AI 分析 → 修復代碼生成 → Discord 通知
```

## 🔧 設定步驟

### 1. .env 環境變數設定

在專案根目錄的 `.env` 檔案中新增：

```bash
# GitHub Token（用於觸發 repository_dispatch）
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# AI API 配置（原有）
AI_API_KEY=AIzaSyDlMU0Vjq9naAppLv_rtzRdpqJytF63FJc
AI_API_MODEL=gemini-2.0-flash

# Discord 通知（原有）
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# LogMonitor 通知頻道（原有）
LOG_CHANNEL_ID=1470272652429099125
```

### 2. GitHub Token 權限設定

1. 前往 [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. 點擊 "Generate new token (classic)"
3. 設定權限：
   - `repo:status` - 存取 repository status
   - `repo_deployment` - 存取 deployment status  
   - `public_repo` - 存取 public repositories
   - `workflow` - 觸發 GitHub Actions workflows

4. 複製生成的 token，加入到 `.env` 的 `GITHUB_TOKEN`

### 3. GitHub Secrets 設定

確保 GitHub Repository 的 Settings > Secrets 包含：

```
GEMINI_API_KEY = AIzaSyDlMU0Vjq9naAppLv_rtzRdpqJytF63FJc
DISCORD_WEBHOOK_URL = https://discord.com/api/webhooks/...
```

## 🎯 觸發條件

### 自動觸發（高緊急錯誤）

以下情況會自動觸發 GitHub Actions 深度分析：

- **緊急程度為 "高"** 的錯誤
- 包含關鍵字：`Traceback`、`Exception`、`CRITICAL`、`Fatal`
- 系統崩潰或未處理異常

### 不觸發的情況

- 緊急程度為 "中" 或 "低" 的錯誤
- 一般警告或資訊性訊息
- 已知的誤報模式（如 yfinance 資料缺失）

## 📊 運作流程

### 1. 實時監控（LogMonitor）

```python
# 持續監控系統日誌
journalctl -u bot.service -u shopbot.service -u uibot.service -f

# 錯誤模式匹配
ERROR|CRITICAL|Traceback|Exception|Fatal|Unhandled
```

### 2. 本地快速分析

```python
# 使用 Gemini 2.0 Flash 進行初步分析
ai_text = await llm.gemini(
    prompt="分析根本原因、建議修復、緊急程度",
    log_text=error_logs
)
```

### 3. 深度分析觸發

```python
# 判斷是否需要深度分析
if severity == "高" or "Traceback" in log_text:
    # 發送 repository_dispatch 到 GitHub
    await trigger_github_actions_analysis(log_text, ai_text)
```

### 4. GitHub Actions 深度分析

```yaml
# 接收實時錯誤請求
repository_dispatch:
  types: [error_analysis]

# 深度 AI 分析
- 根本原因技術細節
- 影響範圍評估  
- 具體修復代碼
- 預防措施建議
```

## 🔍 測試驗證

### 手動測試

```bash
# 1. 測試 LogMonitor
/logmonitor test

# 2. 手動觸發 GitHub Actions
# 進入 GitHub > Actions > AI Debug Monitor > Run workflow
```

### 驗證檢查清單

- [ ] `.env` 包含 `GITHUB_TOKEN`
- [ ] GitHub Secrets 設定正確
- [ ] LogMonitor 正常運行：`/logmonitor status`
- [ ] 測試錯誤能觸發深度分析
- [ ] Discord 接收到深度分析報告

## 📈 效能優化

### API 配額管理

- **本地分析**：使用較短的 prompt，節省配額
- **深度分析**：僅對高緊急錯誤觸發
- **冷卻機制**：同類錯誤 10 分鐘內只觸發一次

### 響應時間

- **本地分析**：5-15 秒
- **深度分析**：30-60 秒（包含 GitHub Actions 啟動時間）

## 🚨 故障排除

### 常見問題

#### 1. GitHub Actions 未觸發

```bash
# 檢查 GITHUB_TOKEN 權限
curl -H "Authorization: token $GITHUB_TOKEN" \
     -H "Accept: application/vnd.github.v3+json" \
     https://api.github.com/repos/chenkankan1103/kkgroup
```

#### 2. LogMonitor 無法發送 webhook

```bash
# 檢查網路連線
ping api.github.com

# 檢查 token 格式
echo $GITHUB_TOKEN | cut -c1-10
```

#### 3. 深度分析未發送到 Discord

- 檢查 `DISCORD_WEBHOOK_URL` 是否正確
- 確認 Gemini API 配額是否足夠
- 查看 GitHub Actions 執行日誌

## 📚 相關文檔

- [GitHub Actions AI 除錯系統](knowledge/_wiki/github-actions-ai-debugging.md)
- [LogMonitor 使用指南](cogs/common/log_monitor.py)
- [開發工作流程](knowledge/_wiki/concepts/development-workflow.md)

---

**最後更新**: 2026-05-12  
**維護者**: KKGroup 開發團隊  
**版本**: v2.0.0 - 實時觸發版本
