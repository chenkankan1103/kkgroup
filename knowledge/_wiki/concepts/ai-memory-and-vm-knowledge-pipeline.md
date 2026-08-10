# AI 記憶與 VM 知識更新流程

## 目標

讓 KK 園區中控室 NPC 不只會聊天，而是真的能把 repo 與 VM 狀態持續寫進長期記憶。

這條流程現在分成四個步驟：

1. `scripts/scan_vm_state.py`
2. `scripts/ingest_knowledge.py`
3. `scheduled_tasks/refresh_knowledge_base.py`
4. `shared/db/ai_memory.py` + `cogs/common/AI.py`

## 資料流

`VM / repo 現況`
-> `knowledge/_wiki/Inbox/vm-scan-latest.md`
-> `shared/db/ai_memory.py` 的 `knowledge_base`
-> `cogs/common/AI.py` 在回答時帶入相關知識

## 主要檔案

- [scripts/scan_vm_state.py](../../../scripts/scan_vm_state.py)
  - 掃描目前主機平台、systemd 服務狀態、git 狀態、repo 熱區與可拓展建議
  - 產生 [knowledge/_wiki/Inbox/vm-scan-latest.md](../Inbox/vm-scan-latest.md)
- [scripts/ingest_knowledge.py](../../../scripts/ingest_knowledge.py)
  - 掃描 `knowledge/_wiki` 下所有 Markdown
  - 解析標題、link、front matter、來源路徑
  - 寫入 `knowledge_base`，並建立 related topics
- [scheduled_tasks/refresh_knowledge_base.py](../../../scheduled_tasks/refresh_knowledge_base.py)
  - 每次執行時先掃描 VM，再重建知識資料
- [shared/db/ai_memory.py](../../../shared/db/ai_memory.py)
  - 現在除了 topic/content/category，還會保存 `source_path`、`metadata_json`、`related_topics`
- [cogs/common/AI.py](../../../cogs/common/AI.py)
  - 回答時會把長期人格、相關知識與最近 VM 掃描一起送進 prompt

## 目前能力

- 中控室 NPC 可以讀到 wiki 摘要
- 可以讀到最近 VM 掃描摘要
- 可以把 Markdown 文件之間的連結轉成 related topics
- 可以把自己的人格設定保存到長期記憶

## 建議排程

- 在 VM 本機用 cron 或 systemd timer，每 24 小時跑一次：
  - `python3 scheduled_tasks/refresh_knowledge_base.py`
- 目前 VM 已設定 cron：每天台灣時間 18:00 執行一次
  - `CRON_TZ=Asia/Taipei`
  - `0 18 * * * cd /home/e193752468/kkgroup && /home/e193752468/kkgroup/venv/bin/python3 scheduled_tasks/refresh_knowledge_base.py >> /home/e193752468/kkgroup/knowledge_refresh.log 2>&1`
- 另外可以在部署後手動補跑一次，讓知識庫立即反映最新 commit

## Discord Webhook 通知

- `scheduled_tasks/refresh_knowledge_base.py` 現在支援成功與失敗通知
- 會依序尋找以下 `.env` 變數：
  - `KNOWLEDGE_WEBHOOK_URL`
  - `DISCORD_WEBHOOK_URL`
  - `DISCORD_WEBHOOK`
  - `STARTUP_WEBHOOK_URL`
- 目前 VM 已配置 `KNOWLEDGE_WEBHOOK_URL`，每日 18:00 的知識庫刷新會嘗試發送 Discord 通知
- 若以上都沒設定，排程仍會執行，只是不發送 Discord 通知

## 互相關聯頁面

- [AI Fast Read](ai-fast-read.md)
- [Knowledge Maintenance Workflow](knowledge-maintenance-workflow.md)
- [Command Registry](../entities/command-registry.md)
- [Bot Services](../entities/bot-services.md)
- [VM 實際配置狀況](../entities/vm-actual-configuration.md)
