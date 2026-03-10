# GCP Metrics 部署指南

## 🚀 快速部署（手動）

由於 PowerShell 無法很好地處理複雜的 gcloud SSH 命令，請按以下步驟手動部署：

### 步驟 1: SSH 到 VM
```powershell
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap
```

### 步驟 2: 重啟 Bot 服務
```bash
cd /home/e193752468/kkgroup
sudo systemctl restart bot.service
```

### 步驟 3: 驗證啟動日誌（重啟後 3-5 秒）
```bash
sudo journalctl -u bot.service -n 30 | grep -E "DASHBOARD|METRICS|initialize"
```

預期看到：
```
[DASHBOARD] bot 實例已註冊
[DASHBOARD] 正在為 bot 創建 GCP Metrics 任務...
[DASHBOARD] bot GCP Metrics 更新任務已啟動
✅ Metrics 監控已啟用（由 bot 負責）
```

### 步驟 4: 等待 5 分鐘
```bash
# 實時監控 metrics 任務
sudo journalctl -u bot.service -f | grep METRICS
```

預期看到（每 5 分鐘）：
```
[METRICS TASK] 開始更新 GCP Metrics（bot）
[METRICS TASK] 成功獲取 metrics 數據（X 數據點)
[METRICS TASK] metrics embed 已更新
```

### 步驟 5: 檢查 Discord Embed
您的 metrics embed 應該在 5 分鐘內更新。

---

## 🔍 故障排除

如果 embed 仍未更新：

### 檢查 1: 驗證代碼已部署
```bash
grep -n "metrics_cache" /home/e193752468/kkgroup/status_dashboard.py
```
應該輸出：第 722-723 行有 `class MetricsCache:`

### 檢查 2: 確認 GCP 認證
```bash
/home/e193752468/kkgroup/venv/bin/python3 << 'EOF'
from google.cloud import monitoring_v3
try:
    client = monitoring_v3.MetricServiceClient()
    print("✓ GCP 認證成功")
except Exception as e:
    print(f"✗ GCP 認證失敗: {e}")
EOF
```

### 檢查 3: 測試 Metrics Monitor
```bash
/home/e193752468/kkgroup/venv/bin/python3 << 'EOF'
import asyncio
from gcp_metrics_monitor import GCPMetricsMonitor

async def test():
    monitor = GCPMetricsMonitor(project_id="kkgroup")
    if monitor.available:
        print("✓ Monitor 可用")
        data = await monitor.get_network_egress_data(hours=6)
        print(f"✓ 獲取 {len(data)} 個數據點")
    else:
        print("✗ Monitor 不可用")

asyncio.run(test())
EOF
```

### 檢查 4: 查看完整錯誤日誌
```bash
sudo journalctl -u bot.service --since '30 minutes ago' | tail -100
```

---

## 📋 代碼驗收清單

新的 metrics 系統應該有以下特性：

- [x] **MetricsCache 類**：
  - 存儲 API 回應的快取
  - 10 分鐘 TTL
  - 位置：status_dashboard.py 第 722-732 行

- [x] **create_metrics_update_task() 函數**：
  - 為每種 bot 類型創建適當的任務
  - 只有 "bot" 類型實際執行更新
  - 其他類型是 NO-OP
  - 位置：status_dashboard.py 第 727-852 行

- [x] **initialize_dashboard() 更新**：
  - 现在创建并启动 metrics 任务
  - 位置：status_dashboard.py 第 1047-1068 行

- [x] **配置標誌**：
  - GCP_METRICS_ENABLED = True
  - GCP_METRICS_ONLY_BOT_RESPONSIBLE = "bot"
  - GCP_METRICS_UPDATE_INTERVAL_MINUTES = 5
  - 位置：status_dashboard.py 第 28-38 行

---

## 配置文件變更摘要

### status_dashboard.py
```python
# 行 28-38: 新の配置標誌
GCP_METRICS_ENABLED = True
GCP_METRICS_ONLY_BOT_RESPONSIBLE = "bot"
GCP_METRICS_UPDATE_INTERVAL_MINUTES = 5

# 行 457: 新の全域變數
metrics_tasks = {}

# 行 720-732: 新的快取類
class MetricsCache:
    def __init__(self):
        self.data = None
        self.timestamp = None
        self.ttl_seconds = 600
    
    def is_stale(self):
        ...

metrics_cache = MetricsCache()

# 行 727-852: 新の任務創建函數
async def create_metrics_update_task(bot_type_str: str):
    """為指定機器人創建 metrics 更新任務"""
    ...

# 行 1047-1068: initialize_dashboard() 的更新部分
if GCP_METRICS_ENABLED:
    metrics_task = await create_metrics_update_task(bot_type_str)
    metrics_tasks[bot_type_str] = metrics_task
    metrics_task.start()
```

---

## 性能考量

- **更新頻率**：每 5 分鐘（可調整 GCP_METRICS_UPDATE_INTERVAL_MINUTES）
- **API 超時**：10-15 秒
- **快取 TTL**：10 分鐘
- **線程執行**：matplotlib 圖表使用線程池避免事件循環阻塞

---

## 已知限制

1. ⚠️ 只有 "bot" 類型會執行真正的更新
   - shopbot 和 uibot 的任務是 NO-OP

2. ⚠️ 消息 ID 存儲在 .env 中
   - 如果找不到舊消息，會創建新的

3. ⚠️ 快取隔離
   - 緩存的數據不在進程間共享
   - 每個 bot 實例有自己的快取副本

---

## 提交信息

```
commit ce6b149: feat: implement bot-exclusive GCP metrics monitoring with caching
commit 50a261e: chore: reduce GCP metrics update interval to 5 minutes
```
