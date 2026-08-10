# KKGroup Knowledge Vault

這個資料夾是給 KKGroup 專案使用的本地知識庫入口。

它適合用 Obsidian 直接開啟，也可以單純當作一般 Markdown 文件夾使用。

目的不是把原始聊天紀錄全部堆進來，而是把已驗證、會反覆用到的維運知識整理成可查、可維護的頁面。

## 建議使用方式

1. 本機用 Obsidian 開啟這個 `knowledge/` 資料夾。
2. 新的原始資料先放進 `Inbox/`。
3. 經過整理後，再寫進 `_wiki/` 對應頁面。
4. 高價值的修復結果，補進 `_wiki/log.md` 與 `index.md`。

## 資料夾說明

- `Inbox/`: 暫存原始筆記、待整理想法、外部連結
- `_wiki/sources/`: 來源與事實頁
- `_wiki/concepts/`: 核心概念，例如部署流程、Webhook、服務管理
- `_wiki/entities/`: 具體系統或對象，例如 bot 服務、VM、commands manager
- `_wiki/questions/`: 已整理過的常見問題
- `_wiki/syntheses/`: 跨主題總結與決策記錄
- `_wiki/comparisons/`: 方案比較

## 本機與 VM 的分工

- 本機: 編輯、查閱、用 Obsidian 瀏覽
- VM: 不安裝 Obsidian，僅透過 Git 同步這份 Markdown 知識庫

這樣比較符合目前 GCP VM 是 headless Linux 的現況，也避免在伺服器上維護不必要的 GUI 軟體。

## 固定入口

- 開啟本機 vault: `./scripts/open-knowledge-vault.ps1`
- 同步 knowledge 到 VM: `./scripts/sync-knowledge-to-vm.ps1`
