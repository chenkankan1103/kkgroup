# Knowledge Link Audit

## 本次稽核目的

這份頁面用來記錄知識庫裡哪些頁面幾乎沒有被其他頁引用，避免 wiki 只剩資料夾樹狀，而沒有實際可導航的關聯。

## 稽核方式

- 掃描 `knowledge/_wiki/` 下所有 Markdown 頁
- 統計每個檔名被其他 Markdown 頁提及的次數
- 不把頁面引用自己算進去

## 補鏈前的孤島頁

以下頁面在本次補鏈前，沒有被其他知識頁提到：

- [開發工作流程](development-workflow.md)
- [Discord 訊息 ID 持久化實踐](discord-message-id-persistence.md)
- [LogMonitor 與 Auto AI Fix 流程總覽](log_monitor_pipeline.md)
- [GitHub Actions AI 除錯系統](../github-actions-ai-debugging.md)

## 補鏈前的弱連結頁

以下頁面在本次補鏈前，只有 1 次被其他頁提及：

- [AI Fast Read](ai-fast-read.md)
- [Knowledge Maintenance Workflow](knowledge-maintenance-workflow.md)
- [Paperdoll Workflow](paperdoll-workflow.md)
- [Operational Sources](../sources/operational-sources.md)
- [Design Reference Sources](../sources/design-reference-sources.md)

## 本次已做的補強

- 新增 [KK 園區系統地圖](kk-park-system-map.md) 作為跨主題導航頁
- 在 [knowledge/_wiki/index.md](../index.md) 補上原本未露出的主題頁入口
- 將訊息持久化、LogMonitor、GitHub Actions AI debug、開發工作流程掛回對應主題頁
- 將 [KK 園區經濟系統](kk-park-economy-system.md) 補成知識頁到程式碼入口的導覽頁

## 後續維護規則

新增一頁知識時，至少要做三件事：

1. 補進 [knowledge/_wiki/index.md](../index.md) 或對應主題頁
2. 在至少一個既有頁面的「相關文檔」中掛回去
3. 若該頁對應特定代碼，補程式碼入口連結

## 建議優先看哪些入口

- 總覽入口: [KK 園區系統地圖](kk-park-system-map.md)
- 低 token 入口: [AI Fast Read](ai-fast-read.md)
- 維護入口: [Knowledge Maintenance Workflow](knowledge-maintenance-workflow.md)
