# kkpark-map 視覺驗證管線（可重用步驟）

這個目錄是 `web/kkpark-map/` 的視覺驗收工具：以 headless Edge + CDP 跑一輪 DOM 數據面檢查，
零截圖優先，輸出可解析的 JSON 與 `BASELINE: PASS/FAIL`。

檔案：

- `kkpark_probe.py` — 管線本體（路徑全部由 `__file__` 推導，不需要改路徑設定）
- `probes.json` — 探針集（POI 之類的新功能落地時只改這裡，不用重組環境）
- `RUNBOOK.md` — 這份步驟與踩坑清單

執行期產物（瀏覽器 profile、截圖）落在系統 temp，不污染 repo。

## 管線做什麼

靜態 server（自動挑 port）＋ headless Edge（唯一 profile）＋ CDP：

1. 啟 `about:blank` → 附加 CDP → `Page.addScriptToEvaluateOnNewDocument` 預置 localStorage
   （在頁面腳本跑之前寫入，avatar.js 啟動即讀得到）
2. `Page.navigate` 到 index.html → 點 `btnStartNew` 進遊戲 → 可選 `flyTo`
3. 逐支探針取 DOM 數據（可選 `until` 輪詢到條件成立再取樣）
4. 基準線判定：破圖 0、console 錯誤 0、非 favicon 的 404 0 → 印 `BASELINE: PASS/FAIL`
5. `finally` 收掉 Edge、關 server、刪 profile

## 三個 preset（localStorage 前置）

| preset | 用途 | 寫入 |
|---|---|---|
| `no_login` | 一般視覺驗證 | 教學已看 + 清存檔 + 移除登入態 |
| `login_doll` | **要驗主角紙娃娃** | 上面＋`kkpark_discord_id`＋`kkpark_map_avatar_cache_v1` 快取 |
| `tut_only` | 只跳教學 | 教學已看 + 清存檔 |

`login_doll` 的重點：預置快取命中後 `fetchPaperdoll` 直接回物件，**不打正式 API**
（未知 ID 走 API 會 404），所以不依賴 VM 資料庫狀態，也不受 5 分鐘負快取影響。
走正式 API 才需要真實存在於 VM 資料庫的 Discord ID（5-25 位數）。

## 常用指令

```bash
# 一般一輪（無登入）
python scripts/tests/kkpark_map_probe/kkpark_probe.py --preset no_login --fly 22.62,120.30,16

# 驗主角造型
python scripts/tests/kkpark_map_probe/kkpark_probe.py --preset login_doll --fly 22.62,120.30,16

# 指定別的探針集
python scripts/tests/kkpark_map_probe/kkpark_probe.py --probes scripts/tests/kkpark_map_probe/probes_poi.json

# 真的要看畫面才截圖（每輪最多 1-2 張、純地圖、無對話框）
python scripts/tests/kkpark_map_probe/kkpark_probe.py --shot "%TEMP%\kkpark_shot\out.png"
python scripts/tests/kkpark_map_probe/kkpark_probe.py --shot "%TEMP%\kkpark_shot\crop.png" --clip-selector ".mk-poi" --scale 4
```

## 探針格式（加在 probes.json 的 checks 陣列）

```json
{
  "name": "poi_count",
  "expr": "document.querySelectorAll('.mk-poi').length",
  "until": "document.querySelectorAll('.mk-poi').length > 0",
  "timeout": 20
}
```

- `expr`：回傳值；回傳物件請用 `JSON.stringify({...})` 包起來
- `until`：先輪詢到成立再取樣（給圖片載入、需要時間的渲染用）
- `timeout`：輪詢上限秒數

## 踩坑（已踩過，別重來）

1. **不要重用 Chromium profile**：舊行程會抓走新 profile（profile 鎖轉交），
   你會接到上一輪殘留的頁面狀態，資料全錯。每次用唯一 profile（管線已自動處理）
2. **不要用固定 port**：可能撞到殘留行程。管線自動挑 port
3. **`--headless --screenshot` 在 load 事件就拍**，等不到圖磚與動畫 → 改用本管線
4. **Windows console 是 cp950**：腳本開頭要 `sys.stdout.reconfigure(encoding='utf-8')`，
   否則印 emoji 會 UnicodeEncodeError 崩掉
5. **崩掉的腳本會留下孤兒 Edge 行程**（finally 沒跑到）→ 下次用新 port/profile
6. **favicon.ico 404 是正常的**：用 Network domain 抓 404 URL 再排除 favicon，
   不要只看 console 文字（文字不含 URL）

## 環境事實

- 紙娃娃 CDN：`https://maplestory.io/api/character/...`（tail=0 靜態 / animated 動畫）
- 正式造型 API：`https://kkgroup2026.duckdns.org/api/game/user/<id>/paperdoll`（未知 ID 404）
- 圖磚：Esri（Leaflet 1.9.4 via cdnjs）
- 總部座標：HQ = (22.62, 120.30)；遊戲預設視角 zoom 8（TW.center 23.75, 120.9）
