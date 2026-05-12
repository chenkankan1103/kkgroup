# NVIDIA AI 集成指南

## 概述

NVIDIA AI 集成是 KKGroup Discord Bot 系統的核心 AI 分析組件，提供強大的錯誤分析和修復代碼生成能力。

## 系統架構

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   NVIDIA AI     │───▶│  Discord Bot    │───▶│  GitHub Actions │
│   Client        │    │   System       │    │   Integration   │
│                │    │                │    │                │
│ • API 調用     │    │ • 錯誤檢測     │    │ • 自動分析     │
│ • 模型選擇     │    │ • 日誌收集     │    │ • 修復生成     │
│ • 響應解析     │    │ • 狀態監控     │    │ • 自動提交     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 核心組件

### 1. NVIDIA AI Client (`utils/nvidia_ai.py`)

**功能特性**：
- 多模型支援（deepseek-v4-pro, nemotron-super, mistral-medium）
- OpenAI 相容介面
- 非同步 API 調用
- 錯誤分析和修復代碼生成
- JSON 響應解析

**模型配置**：
```python
self.models = {
    "deepseek-v4-pro": "deepseek-ai/deepseek-v4-pro",      # 最強編程模型
    "nemotron-super": "nvidia/nemotron-3-super-120b-a12b",  # NVIDIA 最強模型
    "mistral-medium": "mistralai/mistral-medium-3.5-128b",  # 平衡性能
    "deepseek-flash": "deepseek-ai/deepseek-v4-flash"        # 快速版本
}
```

**API 調用範例**：
```python
from utils.nvidia_ai import NVIDIAAIClient

client = NVIDIAAIClient()

# 錯誤分析
analysis = await client.analyze_error_logs(error_logs)

# 修復代碼生成
fix_code = await client.generate_fix_code(analysis)

# 直接 API 調用
response = await client.call_api(messages, model="deepseek-ai/deepseek-v4-pro")
```

### 2. GitHub Actions 集成

#### AI Debug Monitor (`.github/workflows/ai-debug-monitor.yml`)

**觸發方式**：
- 推送到 main/master 分支
- 手動觸發（workflow_dispatch）
- 定時執行（每天 3 點 + 每 6 小時）
- 實時錯誤分析（repository_dispatch）

**功能模式**：
- `auto`：自動檢測系統錯誤
- `force`：強制執行 AI 分析
- `test`：測試 NVIDIA API 連接

#### Auto AI Fix (`.github/workflows/auto-ai-fix.yml`)

**自動化流程**：
1. 接收 Auto Debug System 觸發
2. 調用 NVIDIA AI 分析
3. 生成修復代碼
4. 自動提交到 Git
5. 推送到遠端倉庫
6. 發送 Discord 通知

### 3. 自動 Debug System (`cogs/common/auto_debug_system.py`)

**監控功能**：
- 服務狀態檢查（bot.service, shopbot.service, uibot.service）
- 錯誤日誌分析
- GitHub Actions 觸發
- Discord 通知發送

**監控邏輯**：
```python
# 服務狀態檢查
for service in ["bot.service", "shopbot.service", "uibot.service"]:
    status = subprocess.run(['sudo', 'systemctl', 'is-active', service])
    if status in ["inactive", "failed"]:
        # 觸發錯誤處理

# 錯誤日誌分析
error_keywords = ["error", "exception", "failed", "traceback", "critical"]
error_count = sum(1 for keyword in error_keywords if keyword in logs)
if error_count >= 2:  # 1小時內2個以上錯誤
    # 觸發 GitHub Actions
```

## 模型選擇指南

### deepseek-v4-pro（推薦）

**優點**：
- 最強的編程和邏輯分析能力
- 深度理解複雜錯誤
- 生成高質量修復代碼
- 支援多種程式語言

**適用場景**：
- 複雜的系統錯誤
- 程式碼層面問題
- 邏輯錯誤和演算法問題

### nemotron-super

**優點**：
- NVIDIA 自家最強模型
- 綜合性能最佳
- 多領域知識豐富
- 穩定性和可靠性高

**適用場景**：
- 系統架構問題
- 跨領域複雜問題
- 需要綜合分析的場景

### mistral-medium

**優點**：
- 平衡性能和速度
- 響應速度快
- 成本效益高
- 適合即時分析

**適用場景**：
- 簡單錯誤快速分析
- 即時監控和響應
- 頻繁的小問題處理

## API 配置

### 環境變數設置

```bash
# NVIDIA API 配置
export NVIDIA_API_KEY="nvapi-your-key-here"
export NVIDIA_MODEL="deepseek-ai/deepseek-v4-pro"

# Discord 配置
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/your-webhook"

# GitHub 配置
export GITHUB_TOKEN="your-github-token"
```

### GitHub Secrets 配置

| Secret 名稱 | 描述 | 必需性 |
|-------------|--------|----------|
| `NVIDIA_API_KEY` | NVIDIA API 金鑰 | 必需 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL | 必需 |
| `GITHUB_TOKEN` | GitHub Personal Access Token | 必需 |
| `GCP_SA_KEY` | GCP Service Account Key | 可選 |

## 使用範例

### 1. 基本錯誤分析

```python
from utils.nvidia_ai import NVIDIAAIClient

async def analyze_error():
    client = NVIDIAAIClient()
    
    error_logs = """
    [ERROR] 2024-05-12 20:15:00 - Discord bot disconnected
    Traceback (most recent call last):
      File "/home/e193752468/kkgroup/bots/bot.py", line 150, in on_ready
        await tree.sync()
    discord.errors.HTTPException: 429 Too Many Requests
    """
    
    analysis = await client.analyze_error_logs(error_logs)
    print(f"分析結果: {analysis}")
```

### 2. 修復代碼生成

```python
async def generate_fix():
    client = NVIDIAAIClient()
    
    analysis_result = {
        "root_cause": "Discord API 速率限制",
        "impact": "Bot 無法正常運行",
        "fix_steps": ["實現速率限制", "添加重試機制"],
        "prevention": ["監控 API 使用量", "實現快取機制"]
    }
    
    fix_code = await client.generate_fix_code(analysis_result)
    print(f"修復代碼: {fix_code}")
```

### 3. GitHub Actions 中的使用

```yaml
- name: AI 分析
  env:
    NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}
  run: |
    python3 << 'EOF'
    from utils.nvidia_ai import NVIDIAAIClient
    
    client = NVIDIAAIClient()
    response = await client.call_api(messages, model="deepseek-ai/deepseek-v4-pro")
    print(f"AI 分析結果: {response}")
    EOF
```

## 效能優化

### API 調用優化

```python
# 使用適當的 max_tokens
response = await client.call_api(
    messages, 
    max_tokens=1500,  # 分析用
    temperature=0.3     # 較低溫度，更確定性
)

# 錯誤處理和重試
max_retries = 3
for attempt in range(max_retries):
    try:
        response = await client.call_api(messages)
        break
    except Exception as e:
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)
```

### 模型選擇優化

```python
# 根據錯誤類型選擇模型
def select_model(error_type):
    if error_type == "complex_code":
        return "deepseek-ai/deepseek-v4-pro"
    elif error_type == "system_architecture":
        return "nvidia/nemotron-3-super-120b-a12b"
    else:
        return "mistralai/mistral-medium-3.5-128b"
```

## 故障排除

### 常見問題

#### 1. API 調用失敗

**症狀**：
```
❌ NVIDIA API 調用失敗: 401 Unauthorized
```

**解決方案**：
```python
# 檢查 API Key
if not client.api_key:
    print("❌ NVIDIA_API_KEY 未設置")

# 驗證 API Key
test_response = await client.call_api([{"role": "user", "content": "test"}])
```

#### 2. 模型載入失敗

**症狀**：
```
❌ NVIDIA AI 載入失敗: ImportError
```

**解決方案**：
```python
# 檢查 Python 路徑
import sys
print(f"Python 路徑: {sys.path}")

# 檢查模組是否存在
try:
    from utils.nvidia_ai import NVIDIAAIClient
    print("✅ 模組載入成功")
except ImportError as e:
    print(f"❌ 模組載入失敗: {e}")
```

#### 3. JSON 解析失敗

**症狀**：
```
❌ AI 回應不是有效JSON
```

**解決方案**：
```python
# 添加錯誤處理
try:
    result = json.loads(response)
except json.JSONDecodeError:
    print("⚠️ AI 回應不是有效JSON，使用原始回應")
    result = {"raw_analysis": response}
```

## 監控和日誌

### API 使用監控

```python
# 添加使用統計
import time
from datetime import datetime

class NVIDIAAIClient:
    def __init__(self):
        self.api_calls = 0
        self.last_call_time = None
    
    async def call_api(self, messages, **kwargs):
        self.api_calls += 1
        self.last_call_time = datetime.now()
        
        # API 調用邏輯
        response = await self._make_api_call(messages, **kwargs)
        
        # 記錄使用情況
        print(f"API 調用 #{self.api_calls} - 模型: {kwargs.get('model', 'default')}")
        return response
```

### 效能指標

```python
# 響應時間監控
import time

start_time = time.time()
response = await client.call_api(messages)
end_time = time.time()

response_time = end_time - start_time
print(f"API 響應時間: {response_time:.2f} 秒")

# 成功率監控
success_rate = successful_calls / total_calls * 100
print(f"API 成功率: {success_rate:.1f}%")
```

## 安全考量

### API 金鑰保護

1. **環境變數存儲**：避免硬編碼在代碼中
2. **GitHub Secrets**：使用 GitHub Secrets 管理敏感資訊
3. **權限最小化**：只給予必要的權限
4. **定期輪換**：定期更換 API 金鑰

### 請求限制

```python
# 實現速率限制
import asyncio
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_calls_per_minute=60):
        self.max_calls = max_calls_per_minute
        self.calls = []
    
    async def wait_if_needed(self):
        now = datetime.now()
        # 清理超過1分鐘的記錄
        self.calls = [call_time for call_time in self.calls if now - call_time < timedelta(minutes=1)]
        
        if len(self.calls) >= self.max_calls:
            sleep_time = 60 - (now - self.calls[0]).seconds
            await asyncio.sleep(sleep_time)
        
        self.calls.append(now)

# 使用速率限制
rate_limiter = RateLimiter()
await rate_limiter.wait_if_needed()
response = await client.call_api(messages)
```

## 相關文檔

- [自動 AI Debug 系統](automatic-ai-debug-system.md)
- [GitHub Actions 工作流程](../github-actions-workflows.md)
- [系統部署指南](../../deployment/system-deployment.md)
- [故障排除手冊](../troubleshooting/nvidia-ai-troubleshooting.md)

---

**更新時間**：2024-05-12  
**版本**：1.0.0  
**維護者**：NVIDIA AI Integration Team
