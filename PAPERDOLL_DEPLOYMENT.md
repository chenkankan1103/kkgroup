# 紙娃娃系統部署指南

## 本地測試流程

### 步驟1：準備資料
- `twms_fashion_db.json` – 已整理的33653筆物品資料（TWMS 256版本）
- 此文件應位於 `c:\Users\88697\Desktop\kkgroup\` 目錄

### 步驟2：本地測試setup
1. 確保Python環境已配置
2. 安裝依賴（如需要）：`pip install discord.py aiohttp`
3. 在Discord啟用測試伺服器，設定機器人權限

### 步驟3：測試紙娃娃系統
1. 在Discord中執行 `/shopping` 指令
2. 按下"探索"按鈕
3. 找到"👗 進入衣帽間"按鈕
4. 測試分頁、選擇物品、預覽、購買流程

### 注意事項
- 本地測試資料庫路徑：`./test_paperdoll.db`
- 此資料庫為測試用，**不會上傳到GIT**
- 確保items表已成功載入（如無物品分類，檢查資料庫連接）

## GCP部署流程

### 步驟1：上傳代碼到GIT
測試OK後，執行：
```bash
git add .
git commit -m "Add paperdoll system with paperdoll views and database integration"
git push origin main
```

### 步驟2：GCP自動更新
- GCP會自動從GIT拉取最新代碼
- 機器人會自動重啟並加載新代碼

### 步驟3：SSH連接GCP並執行資料整合
1. 連接GCP SSH：
   ```bash
   ssh <your-gcp-instance>
   ```

2. 進入機器人目錄：
   ```bash
   cd /path/to/kkgroup
   ```

3. 執行資料整合腳本：
   ```bash
   python create_items_table.py --gcp-db-path /path/to/gcp/database.db --json-file twms_fashion_db.json
   ```
   - 替換 `/path/to/gcp/database.db` 為GCP上的實際資料庫路徑
   - 此腳本會在資料庫中創建 `items` 表並插入33653筆物品資料

4. 驗證整合成功：
   ```bash
   sqlite3 /path/to/gcp/database.db "SELECT COUNT(*) FROM items;"
   ```
   - 應返回 33653

### 步驟4：確認機器人運行
- 機器人已加載最新代碼和資料
- 在Discord執行 `/shopping` 並測試"進入衣帽間"功能

## 文件說明

### shop.py
- `ButtonInteraction` – 主Cog，管理資料庫連接、分類和物品查詢
- `DressingRoomView` – 衣帽間分類選擇（含分頁）
- `EditView` – 物品選擇編輯頁（含分頁）
- `PreviewView` – 物品預覽和購買按鈕
- `ConfirmView` – 購買確認頁面

### create_items_table.py
- 用於GCP SSH執行的資料整合腳本
- 接受命令行參數 `--gcp-db-path` 和 `--json-file`
- 創建items表並從JSON插入資料

### twms_fashion_db.json
- 包含ID、名稱、分類、地區、版本和API URL
- 大小約6MB（33653筆記錄）
- **不上傳GIT**，僅在GCP上保留

## 常見問題

### Q：本地資料庫和GCP資料庫如何區分？
A：本地測試使用 `./test_paperdoll.db`，GCP運行時 `shop.py` 中的 `db_path` 應指向GCP資料庫。上傳GIT前務必檢查路徑配置。

### Q：items表創建失敗怎麼辦？
A：檢查以下項：
- GCP資料庫路徑是否正確
- 文件權限是否允許讀寫
- JSON文件是否存在且格式正確
- 執行 `python create_items_table.py --help` 查看完整選項

### Q：購買物品時提示"KK幣不足"？
A：確保測試帳號在資料庫中有足夠KK幣（預設價格5000）。

## 後續優化建議

1. **快取優化** – 可在首次啟動時預載入categories和items到記憶體
2. **分頁改進** – 實現更智能的分頁算法，支持動態項目數
3. **物品搜索** – 添加搜索功能以快速找到特定物品
4. **交易歷史** – 記錄玩家購買交易
5. **限制銷售** – 實現物品限售or特惠活動

---
**最後更新：2026年2月15日**
