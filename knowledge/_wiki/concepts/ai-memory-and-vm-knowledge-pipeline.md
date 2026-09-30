# AI 記憶與 VM 知識更新流程

> ⚠️ **2026-09-30：這條管線的自動化部分已退役。** 中段的匯入腳本 `scheduled_tasks/refresh_knowledge_base.py` 從未掛上任何排程，已連同 `config/commands_registry.json` 的管理命令一併刪除。下方「目前能力」描述的是 `ai_memory.py` / `AI.py` 的讀取端，仍然有效；「自動刷新」已不存在。

## 目標

讓 KK 園區中控室 NPC 不只會聊天，而是真的能把 repo 與 VM 狀態持續寫進長期記憶。

## 原始設計的三個步驟

1. `scripts/scan_vm_state.py` — ✅ 仍存在
2. `scheduled_tasks/refresh_knowledge_base.py` — ❌ **已刪除（2026-09-30）**
3. `shared/db/ai_memory.py` + `cogs/common/AI.py` — ✅ 仍存在

步驟 2 缺席後，步驟 1 的產出沒有下游消費者：`scan_vm_state.py` 仍會寫出 `Inbox/vm-scan-latest.md`，但不會再被自動匯入知識庫。

## 資料流

原設計：

`VM / repo 現況`
-> `knowledge/_wiki/Inbox/vm-scan-latest.md`
-> `shared/db/ai_memory.py` 的 `knowledge_base`
-> `cogs/common/AI.py` 在回答時帶入相關知識

現在第二段（`Inbox` → `ai_memory.py`）沒有執行者，需手動完成。

## 主要檔案

- [scripts/scan_vm_state.py](../../../scripts/scan_vm_state.py)
  - 掃描目前主機平台、systemd 服務狀態、git 狀態、repo 熱區與可拓展建議
  - 產生 [knowledge/_wiki/Inbox/vm-scan-latest.md](../Inbox/vm-scan-latest.md)
  - ⚠️ 產出目前無自動消費者
- [shared/db/ai_memory.py](../../../shared/db/ai_memory.py)
  - 除了 topic/content/category，還會保存 `source_path`、`metadata_json`、`related_topics`
- [cogs/common/AI.py](../../../cogs/common/AI.py)
  - 回答時會把長期人格、相關知識與最近 VM 掃描一起送進 prompt

## 目前能力

- 中控室 NPC 可以讀到 wiki 摘要
- 可以讀到最近 VM 掃描摘要（若 `Inbox/vm-scan-latest.md` 有人更新）
- 可以把 Markdown 文件之間的連結轉成 related topics
- 可以把自己的人格設定保存到長期記憶

## 排程狀態

- ❌ **沒有任何排程。** 2026-09-30 實測 `crontab -l`、`/etc/cron.d`、systemd timer 皆查無知識庫刷新任務，repo 內也沒有任何 Python 呼叫端
- 歷史上曾以 `CRON_TZ=Asia/Taipei` + `0 18 * * *` 記載於 crontab，實測並不存在
- 要恢復自動刷新，需一併重建三件事：掃描 → 匯入 `ai_memory.py` → 掛排程。只把腳本放回來不會生效

## Discord Webhook 通知

- ❌ 已隨 `refresh_knowledge_base.py` 一併退役，目前沒有任何知識庫刷新通知
- 原本依序尋找的 `.env` 變數：`KNOWLEDGE_WEBHOOK_URL`、`DISCORD_WEBHOOK_URL`、`DISCORD_WEBHOOK`、`STARTUP_WEBHOOK_URL`
- VM 上的 `KNOWLEDGE_WEBHOOK_URL` 目前無消費者

## 互相關聯頁面

- [AI Fast Read](ai-fast-read.md)
- [Knowledge Maintenance Workflow](knowledge-maintenance-workflow.md)
- [Command Registry](../entities/command-registry.md)
- [Bot Services](../entities/bot-services.md)
- [VM 實際配置狀況](../entities/vm-actual-configuration.md)
