# KKGroup 開發指南 (簡化版)

WHEN: KKGroup 開發、Discord bot、部署、webhook、資料庫、隧道、字型、紙娃娃

---

## 快速查詢

```
部署: git push → webhook 自動更新
重啟: sudo systemctl restart bot.service shopbot.service uibot.service
日誌: sudo journalctl -u bot.service -n 50
資料庫: 本地驗證 → gcloud compute scp → 重啟
字型: ../../fonts/ (三層 ../)
紙娃娃: 檢查→修復→驗證→部署→/admin_refresh_all_lockers
隧道: update_tunnel_url.py (不要手動改)
SSH: gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap
```

---

## 項目結構

```
kkgroup/
├── bots/ : bot.py, shopbot.py, uibot.py
├── cogs/ : common/, shop/, ui/
├── shared/ : db, utils, constants
├── game/ : api/, web/, system/, assets/
├── config/ : 配置、systemd
├── scheduled_tasks/ : cron
├── docs_and_tests/ : 測試代碼
└── fonts/ : NotoSansCJKtc-Regular.otf
```

規則:
- 測試/臨時代碼放 docs_and_tests/
- .env 不上傳 Git
- 敏感信息用環境變量

---

## 部署

### GitHub Webhook 自動化流程
1. **隧道 URL 監控** (auto_update_webhook.py, 每 5 分鐘)
   - 從 cloudflared 日誌提取當前 URL
   - 與舊 URL 比對，變化時自動更新
   - 更新 config.json + GitHub webhook 端點 + git push

2. **Push 事件觸發** (webhook.py)
   - GitHub push → cloudflared → kkgroup-api
   - webhook.py 驗證簽名 → git pull → 重啟 bots
   - 發送 Discord 通知

3. **Flask API**
   - kkgroup-api.service (port 5000)
   - 依賴: network-online.target, systemd-resolved.service
   - 編碼: PYTHONIOENCODING=utf-8, LANG=C.UTF-8

### Webhook 連不上的診斷
**現象**: 代碼 push 後 bot 沒有自動重啟
**原因**: 隧道 URL 變化，但 GitHub webhook 未同步
**解決**:
1. 手動檢查: `echo $GITHUB_TOKEN && cat config/config.json | grep url`
2. 手動觸發: `python3 scheduled_tasks/auto_update_webhook.py`
3. 查看日誌: `sudo tail -50 /var/log/webhook_auto_update.log`
4. 驗證 API: `curl https://[tunnel-url]/webhook/github -X GET`

---

## Discord 按鈕

用統一視圖系統 (shared.utils.embed_views, shared.utils.view_registry)
不要分散定義，改一個地方改所有

---

## Discord 指令

所有指令通過 CommandRegistry 集中管理 (cogs/discord_commands.py)

添加新指令:
1. 在 Cog 定義 @app_commands.command
2. 在 CommandRegistry 註冊
3. Cog 要有 setup() 函數

分類: UI/紙娃娃, Admin/系統, Shop/購物, Game/遊戲, Common/查詢

---

## 字型路徑

中文字型: kkgroup/fonts/NotoSansCJKtc-Regular.otf

正確: ../../fonts/NotoSansCJKtc-Regular.otf (三層 ../)
錯誤: ../fonts/ (只有一層 ../)

驗證:
__file__ → cogs/common/xxx.py
../ → cogs/
../ → kkgroup/ (根)
fonts/ → kkgroup/fonts/ ✓

---

## 資料庫 & VIP

規則:
- VM 為主，本地驗證後複製
- 改之前必備份
- 用 /grant_temporary_role 給 VIP（不要手動給）
- cleanup_expired_roles_loop() 每 5 分鐘自動清理過期

---

## VM 服務

3 個 Bot: bot, shopbot, uibot

SSH: gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

重啟: sudo systemctl restart bot.service shopbot.service uibot.service

日誌: sudo journalctl -u bot.service -n 50 --no-pager

Cron:
- 每 5 分: update_restart.py, sync_to_sheet.py
- 每週一 3AM: weekly_backup.py

---

## 安全

敏感信息全在 .env:
- Bot Token, API Key, 密碼
- .env 在 .gitignore 中
- 代碼中用 os.getenv("KEY")

洩漏立即撤銷並重設

---

## 遊戲系統

Web RPG 完成，統一在 game/

game/ 結構:
├── api/ : REST 端點
├── web/ : HTML 和靜態資源
├── system/ : 遊戲模組
└── assets/ : 資源

Flask 路由: HTML 路由定義在 404 handler 之前

---

## 10 個關鍵教訣 (簡要版)

1. Service 文件不上傳 Git，只在 VM 管理
2. 亂碼是系統問題，不是代碼問題 (檢查編碼和環境變量)
3. 必須在 VM 驗證，本地測試不夠
4. 環境變量要統一 (PYTHONIOENCODING=utf-8, TZ=Asia/Taipei)
5. Embed 按優先級設計，Breaking/Features 全顯示
6. 按日期分組優於按類型分組
7. 隧道 URL 變化 = webhook 斷連，用 update_tunnel_url.py
8. 盲目改代碼不如查 git 歷史找工作版本
9. MapleStory skin_id 必須在 items 列表中
10. 紙娃娃多樣性: 診斷→修復→驗證→部署→刷新 五步完整
11. **新用戶隨機造型**: 用 `paperdoll_manager.get_random()` 生成，遵循性別一致性，不要硬編碼

---

## 紙娃娃系統

### 新用戶加入時的隨機造型邏輯
在 `welcome_message.py` 的 `create_user_data()` 方法中：
```python
# ✅ 正確做法：調用 get_random() 生成隨機造型
random_appearance = paperdoll_manager.get_random()
user_data = {
    'face': int(random_appearance['face']),
    'hair': int(random_appearance['hair']),
    'skin': int(random_appearance['skin']),
    'top': int(random_appearance['top']),
    'bottom': int(random_appearance['bottom']),
    'shoes': int(random_appearance['shoes']),
    'gender': random_appearance['gender'],
    # ...其他欄位
}
```

### 用戶選擇性別時的隨機造型
在 `PersistentWelcomeView.gender_select()` 中：
```python
# ✅ 保持性別不變，生成符合該性別的隨機造型
selected_gender = select.values[0]  # 'male' 或 'female'
appearance = paperdoll_manager.get_random(preserve_gender=selected_gender)
await self.cog.update_user_data(user_id, appearance)
```

### 核心規則
- ✅ 必須使用 `paperdoll_manager.get_random()` 生成隨機造型
- ✅ 來源必須是 `twms_fashion_db.json` 中的有效物品 ID
- ✅ 性別一致性：男性選自 `face_male/hair_male` 等，女性選自 `face_female/hair_female` 等
- ✅ **不要在 welcome_message.py 硬編碼造型值**（例如 `'face': 20005`）
- ✅ 所有 API URL 透過 `paperdoll_manager.build_api_url()` 建構，自動添加代理層

### 紙娃娃修復流程（完整 5 步）
1. **診斷** - 檢查 fashion DB 和部件 ID 有效性
2. **修復** - 更新 twms_fashion_db.json 或代碼邏輯
3. **驗證** - 本地測試確保生成的造型有效
4. **部署** - Git push 觸發 webhook 重啟 Bot
5. **刷新** - 執行 `/admin_refresh_all_lockers` 更新所有用戶紙娃娃

---

## 踩坑避免

代碼層:
- 不要硬編碼敏感信息
- 不要分散按鈕定義
- 不要盲目改代碼（查歷史版本）
- 不要忽視字型路徑計算

部署層:
- 不要手動改隧道 URL
- 不要頻繁重啟 Flask
- 不要只在本地測試
- 不要上傳 service 文件

資料庫層:
- 不要直接改 VM 資料庫
- 不要忘記備份
- 不要只改部分部位
- 不要用單一值替換所有預設

---

## 常見問題

Q: 代碼多久生效?
A: webhook 自動觸發，push 後幾秒內

Q: 可以直接改資料庫嗎?
A: 不建議，本地驗證→複製→重啟

Q: 為什麼用統一按鈕系統?
A: 改一個地方改所有

Q: Cloudflare 沒有 URL?
A: 等 30-40 秒再查

Q: 紙娃娃修復後看不到效果?
A: 1) /admin_refresh_all_lockers
   2) 資料庫有沒複製到 VM
   3) 服務有沒重啟
   4) config.json 隧道 URL 過期

Q: 動畫推播重複推送或沒推到?
A: 2026-04-29 已修復 - 使用數據庫追蹤已檢查時刻
   - 創建 anime_check_history 表記錄每日檢查
   - 防止 Bot 重啟導致重複推送
   - 修復時間計算邏輯，使用完整 datetime 而非字符串
   - 正確處理日期邊界和午夜情況（不再晚一小時）
   - Commits: eae0f664, c4cf5618, bda137f7

Q: VS Code 任務卡住或失敗?
A: 2026-04-29 已修復 GCP SSH 任務 - 使用 bash -c 包裝
   - 任務: 📋 GCP 系列、🔍 日誌、🔧 診斷
   - PowerShell 無法執行 grep/tail，改用 bash -c
   - .vscode/tasks.json 已更新

Q: 新用戶加入還是用舊版造型？
A: 2026-05-01 已修復 - 新用戶隨機造型邏輯
   - 修改 `create_user_data()` 調用 `paperdoll_manager.get_random()`
   - 新用戶加入時自動獲得隨機男/女造型各占 50%
   - 用戶選擇性別後再生成符合該性別的隨機造型
   - Commit: 47b30914
   - 重點: 不要硬編碼造型值，遵循紙娃娃系統邏輯

Q: 語音頻道無人後五分鐘不會自動刪除？
A: 2026-05-01 已修復 - 語音頻道自動刪除倒數計時
   - 問題: 修改提交後 VM 沒有同步最新代碼，需要手動 git reset
   - 解決步驟:
     1. SSH 連 VM: `gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap`
     2. 進目錄: `cd /home/e193752468/kkgroup`
     3. 強制同步: `git reset --hard origin/main`
     4. 重啟: `sudo systemctl restart bot.service`
   - 驗證: 無人語音頻道會在 5 分鐘後自動刪除，日誌中出現:
     - `🕐 房間 {id} 無人，5 分鐘後將自動刪除`
     - `🗑️ 執行刪除...` / `✅ 成功刪除無人頻道 {id}`
   - Commit: 7614c5ec (添加詳細日誌、return 語句、異常處理)
   - Cog 載入確認: `[ScamHub] cog initialized` 且 `✅ loaded cogs.common.fraud_voice`

---

最後更新: 2026-05-01
