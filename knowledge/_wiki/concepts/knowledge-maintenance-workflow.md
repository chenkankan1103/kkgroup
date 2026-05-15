# Knowledge Maintenance Workflow

## 日常流程

1. 新資訊先放進 `Inbox/`
2. 經驗證後，整理到 `_wiki/` 對應主題頁
3. 若是新的來源文件，先補 `sources/` 來源頁
4. 更新 `index.md` 與 `log.md`
5. 若該資訊來自 VM 或 repo 全域掃描，同步執行 `scheduled_tasks/refresh_knowledge_base.py`

## 什麼值得進 wiki

- 會重複用到的部署步驟
- 容易忘的路徑規則
- 已驗證過的故障判斷方式
- 服務與指令的固定入口
- 每日 VM 掃描後可重用的系統快照

## 什麼不要直接寫進 wiki

- 尚未驗證的猜測
- 臨時聊天片段
- 沒有來源或無法重現的結論

## 每次修復後最少要補的內容

- 影響範圍
- 根因
- 驗證方式
- 若下次再發生，第一個檢查點是什麼
- 是否需要補進 `AI 記憶與 VM 知識更新流程`

## 建議節奏

- 每次完成一個修復就補 `log.md`
- 每週一次整理 `Inbox/`
- 每次新增高頻命令就同步更新 registry 與 wiki
- 每次更新掃描腳本或知識匯入邏輯後，手動跑一次 `scheduled_tasks/refresh_knowledge_base.py`

## 補鏈原則

- 新增主題頁時，至少要掛到一個總覽頁，例如 [KK 園區系統地圖](kk-park-system-map.md)
- 若是維護或除錯主題，要補到 [開發工具和流程](development-tools-and-workflow.md) 或 [部署和維運指南](deployment-and-operations.md)
- 若是 AI / VM 掃描 / 長期記憶主題，要補到 [AI 記憶與 VM 知識更新流程](ai-memory-and-vm-knowledge-pipeline.md)
- 定期檢查 [Knowledge Link Audit](knowledge-link-audit.md)，避免產生孤島頁

## 頁面模板

一般知識頁預設採用這個收尾格式：

1. 正文主題區塊
2. 必要時加入快速入口或功能索引
3. 最後固定用 `## 相關文檔`

例外頁面只有兩種：

- [knowledge/_wiki/index.md](../index.md)：總索引頁
- [knowledge/_wiki/log.md](../log.md)：演進紀錄頁