# .codex/instructions.md — Codex 專用指令

> **單一真實來源**：完整詳細規範請參考 **`.github/copilot-instructions.md`**（與 `CLAUDE.md`、`AGENTS.md` 同步維護）。

---

## 🎯 快速啟動

```bash
# 1. 讀取完整規範
cat .github/copilot-instructions.md

# 2. 專案一頁紙摘要
cat knowledge/_wiki/concepts/ai-fast-read.md

# 3. 統一維運入口
python scripts/commands_manager.py --help
```

---

## ⚡ 核心規則（必守）

### Discord.py 2.0
- `interaction.response.defer()` **必須是 callback 第一行 await**
- 後續回應用 `interaction.followup.send(..., ephemeral=True)`
- 永久視圖繼承 `PersistentViewBase` (`shared/utils/view_registry.py`)

### 資料庫
- 參數化查詢 + WAL 模式 + `busy_timeout=30000`
- 本地驗證 → `gcloud compute scp` 複製到 VM → `systemctl restart`

### 部署
- `git push` → Webhook 自動更新
- 複雜 SSH：上傳腳本 → 執行 → `&& rm /tmp/script.py`

### 字型路徑
- ✅ `../../fonts/NotoSansCJKtc-Regular.otf`（從 `cogs/common/`）

---

## 🧹 臨時檔案管理（強制）

| 模式 | 處理 |
|------|------|
| `check_*` `test_*` `fix_*` `debug_*` `simple_*` `crawl_*` `reset_*` | **用完即刪**（同對話結束前） |
| 正式測試 | 僅 `scripts/tests/`，經 Code Review |

---

## 🛠️ 查詢工具（優先用這些）

```bash
# 架構級
python scripts/query_graph.py community KKCoin
python scripts/query_graph.py callers <node_id>

# 符號級
python scripts/lsp_query.py --file <path> refs <symbol>
python scripts/lsp_query.py --file <path> def <symbol>
```

---

## 📋 對話檢查清單

- [ ] 無 `check_*` `test_*` `fix_*` `debug_*` `simple_*` `crawl_*` `reset_*` 殘留
- [ ] 臨時檔案已刪除
- [ ] 無多餘資料庫備份
- [ ] 專案 `__pycache__` 已清理

---

## 🔗 關鍵連結

- 完整規範：`.github/copilot-instructions.md`
- 知識庫：`knowledge/_wiki/`
- 知識圖譜：`graphify-out/graph.json`
- 維運 CLI：`scripts/commands_manager.py`