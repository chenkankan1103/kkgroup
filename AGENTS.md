# AGENTS.md — kkgroup 專案通用 Agent 指令

> **單一真實來源**：本檔案為所有 AI Agent（Claude Code, Codex, Copilot, Cursor, Windsurf 等）的統一入口。
> 完整詳細規範請參考 **`.github/copilot-instructions.md`**（與 `CLAUDE.md` 同步維護）。

---

## 🎯 專案一覽

| 項目 | 內容 |
|------|------|
| **專案** | kkgroup — Discord Bot 系統（三 Bot：bot, shopbot, uibot） |
| **部署** | GCP VM (us-central1-a) + systemd + GitHub Webhook 自動化 |
| **資料庫** | SQLite (`user_data.db`) + WAL 模式 + 向量庫 (`ruvector.db`) |
| **核心語言** | Python 3.11+ (discord.py 2.0, Flask, asyncio) |
| **知識庫** | `knowledge/_wiki/` (Obsidian 格式) + `graphify-out/` (知識圖譜) |

---

## 📖 必讀檔案（按優先級）

1. **`.github/copilot-instructions.md`** — 完整開發規範、技能調用、踩坑指南、AI 查詢工具
2. **`CLAUDE.md`** — 與上方同步，給 Claude Code 讀取
3. **`knowledge/_wiki/concepts/ai-fast-read.md`** — 一頁紙專案摘要、架構、高頻入口
4. **`scripts/commands_manager.py`** — 統一維運 CLI 入口

---

## ⚡ 核心規則速查

### Discord.py 2.0 必守
- ✅ `interaction.response.defer()` **必須是 callback 第一行 await**
- ✅ 所有後續回應用 `interaction.followup.send(..., ephemeral=True)`
- ✅ 永久視圖繼承 `PersistentViewBase` (`shared/utils/view_registry.py`)

### 資料庫操作
- ✅ 參數化查詢：`cursor.execute("SELECT ... WHERE id = ?", (user_id,))`
- ✅ WAL 模式 + `busy_timeout=30000`（多進程並發）
- ✅ 本地驗證 → `gcloud compute scp` 複製到 VM → `systemctl restart`

### 部署流程
- ✅ `git push` → Webhook 自動 `git pull` + 重啟三服務
- ✅ 複雜 SSH 指令用「上傳腳本 → 執行 → `&& rm /tmp/script.py`」

### 字型路徑（從 `cogs/common/` 出發）
- ✅ `../../fonts/NotoSansCJKtc-Regular.otf`（三層 `../`）
- ❌ `../fonts/`

---

## 🧹 臨時檔案管理（強制）

| 檔案類型 | 模式 | 處理 |
|----------|------|------|
| 檢查/測試/修復/除錯 | `check_*` `test_*` `fix_*` `debug_*` `simple_*` `crawl_*` `reset_*` | **用完即刪**（同對話結束前） |
| 正式測試 | `scripts/tests/*.py` | 經 Code Review 才留存 |

**違規後果**：下次對話開頭發現殘留 → 強制清理 → 浪費時間

---

## 🛠️ AI 專用查詢工具（優先用這些，別 grep 全專案）

```bash
# 架構級查詢
python scripts/query_graph.py stats
python scripts/query_graph.py community KKCoin
python scripts/query_graph.py callers <node_id>

# 符號級精確查詢
python scripts/lsp_query.py --file <path> symbols
python scripts/lsp_query.py --file <path> refs <symbol>
python scripts/lsp_query.py --file <path> def <symbol>
```

---

## 🎯 技能調用速查

| 使用者說... | 調用技能 |
|-------------|----------|
| "該用哪個技能？" | `ask-matt` |
| "幫我規劃功能" | `grill-with-docs` (有碼) / `grill-me` (無碼) |
| "太大裝不下" | `wayfinder` |
| "轉成 spec" | `to-spec` |
| "轉成 tickets" | `to-tickets` |
| "實作 spec" | `implement` |
| "審查變更" | `code-review` |
| "除錯 bug" | `diagnosing-bugs` |
| "改善架構" | `improve-codebase-architecture` |
| "強制極簡代碼" | `ponytail` |

---

## 📋 每次對話檢查清單

| # | 檢查項 |
|---|--------|
| 1 | 是否有 `check_*` `test_*` `fix_*` `debug_*` `simple_*` `crawl_*` `reset_*` 殘留？ |
| 2 | 臨時建立的 `.py`/`.json`/`.md` 是否已刪除？ |
| 3 | 是否誤留資料庫備份/空檔？ |
| 4 | 專案目錄 `__pycache__` 是否需清理？ |

---

## 🔗 相關連結

- **完整規範**：`.github/copilot-instructions.md` / `CLAUDE.md`
- **知識庫**：`knowledge/_wiki/`
- **知識圖譜**：`graphify-out/graph.json` (4570 節點、8512 邊、263 社群)
- **維運入口**：`python scripts/commands_manager.py <service> <action>`