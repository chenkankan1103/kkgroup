# 🌐 KKGroup 專案 GCP 出站流量深度分析

**提交日期**: 2026-04-11  
**分析範圍**: 整個專案中所有會產生出站流量的組件  
**目的**: 量化和優化 GCP 網路成本

---

## 📊 出站流量來源概覽

```
主要流量源：
┌─ Discord Bot Connections (持續)        ~70-80% 的流量
│  ├─ Discord WebSocket (gateway)  
│  ├─ API 調用 (embed 更新、訊息發送等)
│  └─ 檔案/圖片上傳
│
├─ 金融數據 API (定期)                  ~10-15% 的流量
│  ├─ yfinance (股票、加密貨幣、原物料)
│  ├─ QuickChart (圖表生成)
│  └─ 快取機制 (5 分鐘)
│
├─ Google Sheets 同步 (每日/每小時)      ~3-5% 的流量
│  ├─ gspread (讀寫 Google Sheets)
│  ├─ oauth2client (認證)
│  └─ 整表同步 (user_data 全量同步)
│
├─ AI API 調用 (按需)                   ~5-10% 的流量
│  ├─ Gemini (主要)
│  ├─ Groq (備用)
│  ├─ GitHub Models (備用)
│  └─ OpenAI 兼容格式請求
│
├─ 動畫追蹤 API (每日定時)              ~1-2% 的流量
│  ├─ Bahamut API (https://api.gamer.com.tw)
│  ├─ 動畫網頁爬蟲 (aiohttp)
│  └─ 每次 ~50-200KB
│
├─ Google Cloud 可視化 (已停用)         0% 的流量
│  ├─ google-cloud-monitoring (不再用)
│  ├─ google-cloud-billing (不再用)
│  └─ metrics_database (本地存儲)
│
└─ 其他 API 與隧道維護 (持續)           <1% 的流量
   ├─ Git 操作
   ├─ 健康檢查
   ├─ Cloudflare 隧道
   └─ OAuth 端點驗證
```

---

## 🎯 詳細流量分析

### 1️⃣ Discord Bot (最大流量來源)

**文件**: `bot.py`, `shopbot.py`, `uibot.py` + `commands/` 目錄

**流量特性**:
- **持續連接**: WebSocket 長連接到 Discord Gateway
- **訊息同步**: 定期發送 embed 到頻道更新市場數據
- **檔案上傳**: 股票圖表、使用者圖片

**關鍵操作**:
```python
# 持續發送市場更新 embed (stock_market.py)
await channel.edit(topic=...)  # 頭部更新
await message.edit(embed=updated_embed)  # Embed 更新
await channel.send(attach=chart_file)  # 圖表上傳

# 定期任務
@tasks.loop(minutes=30)  # stock_market.py L~1700
async def update_market_embed():
    # 更新所有市場訊息
```

**估計流量**:
```
WebSocket 連接: ~2-5 KB/分鐘 (心跳)
訊息發送:       ~30 KB/次 (含 embed 和圖表)
定時更新:       30分鐘一次 = ~1.4 MB/小時
日流量:         ~33 MB (市場更新) + WebSocket 連接開銷
```

---

### 2️⃣ 金融數據 API (yfinance)

**文件**: `utils/stock_api.py`, `shop_commands/stock_market.py`

**本質**:
```python
# 價格查詢 (L73-L111)
async def fetch_price(symbol: str) -> Optional[float]:
    def _fetch():
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")  # ← 調用 yfinance
        return float(data['Close'].iloc[-1])
    
    loop = asyncio.get_event_loop()
    price = await loop.run_in_executor(None, _fetch)

# 歷史數據 (L120+)
async def fetch_historical_data(symbol, period="3mo", interval="1d"):
    ticker = yf.Ticker(symbol)
    data = ticker.history(period=period, interval=interval)  # ← 抓多日期

# 圖表生成 (L185+)
async def fetch_chart(symbol, period="3mo", interval="1d"):
    data = await fetch_historical_data(symbol, period, interval)
    # 轉換為 QuickChart 圖表
    await create_quickchart_short_url(chart_config)
```

**流量估計**:
```
單次股票價格查詢:   ~10-50 KB
歷史數據 (3個月):   ~100-200 KB
圖表生成 (QuickChart): ~20 KB (URL 短連結)

高頻查詢時:
- 市場開市: 用戶頻繁查詢 (每次 30KB)
- 圖表生成: 每張圖 20KB + JSON 配置
- 快取命中率: 5 分鐘內相同商品不重複查詢

預估月流量:
- 50 個用戶, 每人每日查詢 5 次
- 5次 × 50用戶 × 30KB = 7.5 MB/天 ≈ 225 MB/月
```

**快取現狀**:
```python
CACHE_DURATION_SECONDS = 300  # 5 分鐘快取 (L15)
_price_cache: Dict[str, Tuple[float, datetime]] = {}
_chart_cache: Dict[str, Tuple[str, datetime]] = {}
```

---

### 3️⃣ Google Sheets 同步

**文件**: `sync_to_sheet.py`, `sheet_sync_manager.py`, `sheet_driven_db.py`

**同步方式**:
```python
# 雙向同步
1. SHEET → DB (sync_sheet_to_db)  # gspread 讀取全表
2. DB → SHEET (export_sheet)      # gspread 寫入全表

def sync_sheet_to_db(headers, rows):
    for row in rows:  # ← 逐行解析和寫入 DB
        # 每行會調用一次 SQL INSERT/UPDATE
```

**流量特性**:
- **整表同步**: 每次同步讀取 Google Sheets 的全部資料
- **欄位自動檢測**: 動態適應 Sheet 表頭
- **OAuth 認證**: 每次請求需要 Bearer Token

**關鍵代碼片段**:
```python
# sync_to_sheet.py L40-60
class GameUserSync:
    def __init__(self, credentials_path, sheet_url, db_path):
        scope = ['https://www.googleapis.com/auth/spreadsheets']
        creds = ServiceAccountCredentials.from_json_keyfile_name(...)
        gc = gspread.authorize(creds)
        self.sheet = gc.open_by_url(sheet_url).sheet1

# sheet_sync_manager.py L55-80 - 整表同步
def sync_sheet_to_db(self, all_values):
    headers = self.get_sheet_headers(all_values)
    rows = self.get_sheet_data_rows(all_values)
    
    for row_values in rows:
        # 逐行插入/更新 DB
        self.db._sync_record_to_db(record, headers)
```

**流量估計**:
```
讀取完整 Google Sheet:
- 假設 100+ 用戶行 × 20+ 欄位
- 每次請求: ~50-100 KB (JSON 格式)

同步頻率 (假設):
- Crontab 觸發: 每日 1-4 次
- Apps Script 定時: 每小時 1 次 (估計)
- 臨機同步: 需要時調用 API

預估月流量:
- 每日 4 次同步 × 75 KB = 300 KB/天 ≈ 9 MB/月
- 加上反向同步 (DB → Sheet): ~9 MB/月
- 總計: ~18 MB/月
```

---

### 4️⃣ AI API 調用 (多備用方案)

**文件**: `commands/AI.py`, `prompt_function_calling.py`

**API 層級**:
```python
# AI.py L54-58
AI_API_KEY = os.getenv("AI_API_KEY")  # Gemini (主)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Groq (備)
GITHUB_MODELS_API_KEY = os.getenv("GITHUB_MODELS_API_KEY")  # GitHub Models (備)

# 優先級: Gemini → GitHub Models → Groq

# 每次調用結構
def _make_request(messages, model, api_key, api_url):
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "messages": messages,
        "model": model,
        "temperature": 0.7,
        "max_tokens": 1000+
    }
    # 發送 HTTP POST 請求
```

**流量特性**:
- **請求包含**: 完整對話歷史 + 系統提示 + 工具定義
- **回應包含**: 生成的文本
- **token 計算**: 會產生相應的計費

**估計流量**:
```
單次請求:
- 請求: 對話歷史 (每條 ~50-200B) + 系統提示 (500-1000B)
- 回應: 生成文本 (500-2000B)
- 平均: 1-3 KB/次調用

使用場景:
- AI 命令 (/ai_chat): 按需調用
- 工作系統故事生成: 每日檢查 (calls/day)
- 工作勸告: 偶爾調用

預估月流量:
- 50 用戶, 每周 2 次 AI 調用
- 50 × 8 次/月 × 2.5 KB = 1 MB/月 (保守估計)
```

**工具呼叫系統**:
```python
# prompt_function_calling.py
# 使用基於提示的工具呼叫 (不支援原生 function calling 的 API)
def build_system_prompt_with_tools(tools):
    # 在系統提示中教導模型輸出 <FUNCTION_CALL>...</FUNCTION_CALL>
    return system_prompt + tool_definitions

def extract_function_calls(response_text):
    # 解析 JSON function call 定義
    return [{"name": "...", "args": {...}}]
```

---

### 5️⃣ 動畫追蹤 API

**文件**: `commands/anime_tracker.py`

**API 端點**:
```python
# L52
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # 秒

# 方法 1: 獲取新動畫 (L371-415)
async def fetch_new_anime_from_api(self):
    async with aiohttp.ClientSession() as session:
        async with session.get(API_ENDPOINT, timeout=...) as resp:
            data = await resp.json()  # ← 完整 JSON 回應

# 方法 2: 網頁爬蟲 (L440-487)
async def fetch_anime_web_details(self, anime_sn):
    detail_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
    async with session.get(detail_url) as resp:
        html = await resp.text()  # ← 完整 HTML

# 方法 3: API 詳細資訊 (L485-548)
async def fetch_anime_details_from_api(self, video_sn):
    api_url = f"https://api.gamer.com.tw/mobile_app/anime/v3/video.php?sn={video_sn"
    data = await resp.json()
```

**流量特性**:
- **JSON API**: 每次 ~20-50 KB
- **網頁爬蟲**: 每次 ~100-200 KB (完整 HTML)
- **定時檢查**: 每日定時更新

**流量估計**:
```
每日檢查:
- 一次 API 調用: ~30 KB
- 若有新動畫, 爬蟲 5 個詳細頁: 5 × 150 KB = 750 KB

預估月流量:
- 每日 1 次定期檢查: 30 KB × 30天 = 900 KB
- 新動畫爬蟲 (假設周 2-3 次): 750 KB × 8 = 6 MB
- 用戶查詢 (每周模糊查詢): ~5-10 個查詢 × 30KB = 150KB/周
- 總計: ~7-8 MB/月
```

---

### 6️⃣ Google Cloud 可視化 (已停用)

**文件**: `gcp_metrics_monitor.py`, `metrics_data_collector.py`

**狀態**: ❌ **已停用** (不再產生流量)

```python
# gcp_metrics_monitor.py L4-6
"""此模組已簡化為最小存根，不再進行以下操作：
  • 監控網路出站流量
  • 監控成本/計費
  • 生成圖表
"""

# metrics_data_collector.py L55
# 原本會查詢 google-cloud-monitoring API，現已禁用
GOOGLE_CLOUD_AVAILABLE = False
```

**流量歷史**:
- 之前: 每 6 小時查詢一次 GCP Monitoring API (~100-200 KB/次)
- 現在: 0 KB (已禁用)

---

## 📈 月度流量估計總結

```
┌─ Discord WebSocket + API        ~40 MB/月 (保守估計)
├─ yfinance + QuickChart          ~225 MB/月
├─ Google Sheets 同步             ~18 MB/月
├─ AI API 調用                    ~2-5 MB/月
├─ 動畫追蹤                       ~8 MB/月
└─ 其他 (OAuth, 備份, Git 等)    ~5 MB/月
  ─────────────────────────────────────
  總計: ~300-350 MB/月
```

---

## 💡 優化建議

### 高優先級 (快速降低成本)

1. **yfinance 快取優化**
   ```
   現在: 5 分鐘快取
   改善:
   - 使用 redis 或記憶體快取
   - 9.5 小時外盤交易時段提高快取
   - 預期節省: 20-30%
   ```

3. **Google Sheets 同步優化**
   ```
   現在: 每次同步都讀全表
   改善:
   - 只同步變更的行 (使用 timestamp)
   - 降低同步頻率到每日 2 次
   - 預期節省: 50%
   ```

### 中優先級

2. **Discord embed 優化**
   - 使用 GitHub Pages 或 CDN 託管圖表靜態資源
   - 預期節省: 10-15%

5. **AI API 使用者成本控制**
   - 監控用戶 token 使用
   - 有配額限制或升級通知

---

## 🔧 診斷和測試工具

### 已存在的檢查代碼

| 工具 | 位置 | 功能 |
|-----|------|------|
| **OAuth 健康檢查** | [`oauth_health_check.py`](#) | 驗證 OAuth 端點和隧道連接 |
| **隧道診斷** | [`diagnose_tunnel.py`](#) | 快速診斷 Nginx 和隧道 404 問題 |
| **用戶驗證** | [`verify_user_id.py`](#) | 檢查用戶 ID 和資料庫 |
| **排行榜驗證** | [`verify_kkcoin.py`](#) | 驗證 KK幣 計算正確性 |
| **API 驗證** | [`verify_tools.py`, `verify_new_api_key.py`](#) | 驗證 API 密鑰和工具 |
| **週備份測試** | [`weekly_backup.py`](#) | 完整備份至本機和 Sheets |
| **歡迎流程測試** | [`test_welcome_resilience.py`](#) | 驗證新成員加入容限 |
| **資料庫檢查** | [`inspect_db.py`](#) | 檢查和修復資料庫 |

### 建議添加的監控工具

```python
# 1. 實時網路流量監控 (GCP 側)
# 使用: gcloud compute instances describe <instance> --format="get(networkInterfaces[])"
# 或使用 Stackdriver Monitoring API

# 2. API 呼叫計數統計
# 記錄每個出站 API 的調用次數和流量

# 3. 定期流量報告生成
# 比對實際通過和預估，找異常
```

---

## 🎯 行動清單

- [ ] 檢查 yfinance 快取策略
- [ ] 優化 Google Sheets 同步頻率

---

**最後更新**: 2026-04-11  
**負責人**: 系統監控  
**下次審查**: 2026-05-11
