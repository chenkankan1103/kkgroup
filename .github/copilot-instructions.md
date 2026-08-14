# GitHub Copilot Instructions for kkgroup

This file contains instructions and skills that GitHub Copilot should follow when working in this repository.

## Project Overview

This is the kkgroup project - a Discord bot system with multiple services (bot, shopbot, uibot) deployed on GCP VM.

## Core Principles

- **Predictability over output** - The agent should take the same process every run, not produce the same output
- **Progressive disclosure** - Keep always-loaded context small; push detail behind context pointers
- **Single source of truth** - One authoritative place for each meaning
- **Leading words** - Use compact concepts from pretraining (tight, red, seam, fog of war, tracer bullets) to anchor behavior

## Engineering Skills (from Matt Pocock's skill set)

These skills are available for use. Invoke them by name when appropriate.

### Setup & Configuration

**`setup-matt-pocock-skills`** — Configure this repo for the engineering skills: set up issue tracker, triage labels, and domain doc layout. Run once before first use of other engineering skills.

### Planning & Architecture

**`ask-matt`** — Router skill. Ask which skill or flow fits your situation. A map over all user-invoked skills.

**`grill-with-docs`** — Relentless interview to sharpen a plan/design, which also creates docs (ADRs and glossary) as you go. Use when you have a codebase.

**`grill-me`** — Same relentless interview as grill-with-docs, but for when you have NO codebase. Stateless.

**`wayfinder`** — Plan a huge chunk of work (more than one agent session can hold) as a shared map of decision tickets on your issue tracker. Resolve them one at a time until the way is clear.

**`to-spec`** — Turn the current conversation into a spec and publish it to the issue tracker. No interview, just synthesis.

**`to-tickets`** — Break a plan, spec, or conversation into tracer-bullet tickets, each declaring its blocking edges.

### Implementation

**`implement`** — Build the work described by a spec or tickets. Use TDD at pre-agreed seams. Run typechecking regularly. End with code-review.

**`tdd`** — Test-driven development reference: what a good test is, where tests go (seams), anti-patterns, rules of the red→green loop.

**`prototype`** — Build a throwaway prototype to answer a design question: "does this logic feel right?" (logic branch) or "what should this look like?" (UI branch).

**`code-review`** — Two-axis review of diff since a fixed point: Standards (repo conventions + Fowler smell baseline) and Spec (matches originating issue/PRD). Runs in parallel sub-agents.

**`resolving-merge-conflicts`** — Resolve in-progress git merge/rebase conflicts. Preserve both intents, run automated checks, finish the merge.

### Codebase Health

**`improve-codebase-architecture`** — Scan for deepening opportunities (shallow → deep modules), present as visual HTML report, then grill through your pick.

**`codebase-design`** — Shared vocabulary for deep modules: module, interface, depth, seam, adapter, leverage, locality. Use this language when designing/restructuring.

**`diagnosing-bugs`** — Discipline for hard bugs: build a tight feedback loop → reproduce & minimise → hypothesise (3-5 ranked) → instrument → fix + regression test → cleanup + post-mortem. Hands off architectural recommendations to improve-codebase-architecture.

### Domain & Triage

**`domain-modeling`** — Actively build/sharpen the project's domain model: challenge terms, invent edge-case scenarios, write glossary (CONTEXT.md) and ADRs inline as decisions crystallise.

**`triage`** — Move issues/PRs through a state machine: categorise → verify → grill if needed → write agent-ready briefs. For issues you didn't create.

### Vocabulary (Model-Invoked References)

These run beneath other skills — reach for them directly when the **words** are the problem:

- **`domain-modeling`** — Sharpen domain terminology, resolve overloaded words, record ADRs
- **`codebase-design`** — Deep-module vocabulary for designing module shape

## Productivity Skills

**`handoff`** — Compact current conversation into a handoff document for another agent. Save to OS temp dir. Include "suggested skills" section.

**`teach`** — Teach the user a new skill/concept over multiple sessions using the current directory as stateful workspace. Creates lessons, reference docs, learning records.

**`writing-great-skills`** — Reference for writing/editing skills well: invocation modes, information hierarchy, when to split, pruning, leading words, failure modes.

**`grilling`** — The primitive interview skill used by grill-with-docs and grill-me. One question at a time, wait for answer, provide recommended answer, don't act until confirmed.

**`ponytail`** — Enforces a seven-rung decision ladder (YAGNI → reuse codebase → stdlib → native platform → installed deps → one-liner → minimal viable) to prevent over-engineering. Benchmarked: 54% less code, 20% cheaper, 27% faster, 100% safe.

```bash
/ponytail full          # Enable standard enforcement
/ponytail-review        # Review changes for over-engineering
/ponytail-audit         # Full codebase audit
/ponytail-debt         # Show accumulated tech debt
/ponytail-gain         # Show code/tokens saved
/ponytail-help         # Show help
```

- **GitHub**: https://github.com/dietrichgebert/ponytail
- **Integrations**: 20+ agents (Claude Code, Codex, Copilot CLI, Cursor, Windsurf, etc.)

## Discord.py 2.0 Rules

- Use `discord.ext.commands.Bot` with `intents=discord.Intents.all()`
- Slash commands via `@bot.tree.command()` or `@app_commands.command()`
- Persistent views: inherit from `PersistentViewBase` in `shared/utils/view_registry.py`
- Button callbacks use `interaction.response.defer()` then `interaction.followup.send()`
- Ephemeral responses for user-specific feedback

### ⚡ Discord 互動 3 秒超時避坑（高頻踩坑！）

**核心問題**：Discord 要求按鈕/選單 callback 必須在 **3 秒內** 做出首次回應（defer 或 send），否則會顯示 "The application did not respond"。

**`defer()` 的作用**：告訴 Discord「收到請求，正在處理」，將超時延長到 **15 分鐘**。但 `defer()` 本身必須在 3 秒內被呼叫。

**正確模式**：

```python
async def _button_callback(self, interaction: discord.Interaction):
    # ✅ 第一步：立刻 defer()，什麼都別做
    await interaction.response.defer()

    # ✅ 第二步：慢慢處理（資料庫寫入、API 呼叫、KK幣獎勵等）
    self.tracker.record_vote(...)
    set_user_field(...)

    # ✅ 第三步：用 followup 回應用戶
    await interaction.followup.send("✅ 成功！", ephemeral=True)
```

**錯誤模式（會導致 3 秒超時）**：

```python
async def _button_callback(self, interaction: discord.Interaction):
    # ❌ 先做耗時操作（DB 寫入、API 呼叫...）
    self.tracker.record_vote(...)  # SQLite 可能鎖定等待
    set_user_field(...)

    # ❌ defer() 太晚，可能已超過 3 秒
    await interaction.response.defer()
```

**Modal 注意事項**：
- `send_modal()` 不需要 defer，但 Modal 本身也有 3 秒限制
- Modal 的 `on_submit` 中也需要在 3 秒內回應（defer 或 send_message）
- Modal 類別定義內的 `self` 是 Modal 實例，不是外部 View — 需用 `outer_self` 捕獲

**錯誤處理注意**：
- 如果已 defer 過，錯誤處理要用 `followup.send()` 而非 `response.send_message()`
- 檢查方式：`if interaction.response.is_done():` → 用 followup，否則用 response

**檢查清單**（寫 callback 時必查）：
| # | 檢查項 | ✅ |
|---|--------|-----|
| 1 | `defer()` 是 callback 的第一個 await？ | |
| 2 | 所有後續回應都用 `followup.send()`？ | |
| 3 | 錯誤處理有檢查 `is_done()` 再決定用哪個？ | |
| 4 | Modal 的 `on_submit` 也有在 3 秒內回應？ | |

## Async Best Practices

- Use `asyncio.gather()` for parallel operations
- Avoid `asyncio.sleep()` in hot paths
- Use `async with` for resource management
- Handle `asyncio.CancelledError` in long-running tasks

## Database (SQLite / user_data.db)

- Use parameterized queries: `cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`
- Connection pooling via `sqlite3.connect()` with `check_same_thread=False`
- Transactions: `conn.execute("BEGIN")` / `conn.commit()` / `conn.rollback()`

### ⚠️ 避免資料庫鎖定問題 (Database Lock Prevention)

**重要**：SQLite 在多進程並發存取時容易發生 `database is locked` 錯誤。請遵循以下最佳實踐：

1. **啟用 WAL 模式**：在資料庫連線建立時啟用 WAL (Write-Ahead Logging) 模式
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   conn.execute("PRAGMA busy_timeout=30000")  # 30 秒等待超時
   conn.execute("PRAGMA synchronous=NORMAL")
   ```

2. **使用連線池/共用連線**：避免頻繁開關連線，使用連線池或共用連線物件

3. **設定 busy_timeout**：設定足夠的等待時間，避免短暫鎖定導致立即失敗
   ```python
   conn.execute("PRAGMA busy_timeout=30000")  # 30 秒
   ```

4. **避免長時間持有連線**：在 `with` 區塊中盡快完成操作並釋放連線

5. **批次操作合併**：將多個寫入操作合併為單一交易，減少鎖定時間

6. **使用 WAL 模式的優勢**：
   - 讀取不阻塞寫入，寫入不阻塞讀取
   - 支援多進程並發讀取
   - 減少鎖定衝突機率

**已知問題**：專案中有 5 個進程同時存取同一 SQLite 資料庫 (bot, shopbot, uibot, unified_api, auto_self_heal)，已於 2026-07-24 修復並啟用 WAL 模式解決。

## GCP VM Deployment

- SSH via IAP: `gcloud compute ssh <user>@<instance> --zone <zone> --tunnel-through-iap`
- Services: `bot.service`, `shopbot.service`, `uibot.service`
- Logs: `sudo journalctl -u <service> -n 100 --no-pager`
- Restart: `sudo systemctl restart <service>`

### ⚡ PowerShell 引號與 gcloud SSH 避坑（高頻踩坑！）

**核心問題**：PowerShell 對單引號 `'`、雙引號 `"`、管線 `|` 的處理與 bash 完全不同，gcloud SSH 命令極易因引號嵌套失敗。

**策略優先級**：
1. 先嘗試 PowerShell 簡化版：用 `echo "" | gcloud -q` 避免 SSH 互動提示
2. 如 2-3 次嘗試仍失敗 → 改用「上傳腳本 → 執行 → 清理」模式

**模式 A：簡單命令（PowerShell 直接執行）**
```powershell
# ✅ echo "" | 避免 SSH host key 互動提示
# ✅ gcloud -q 跳過所有確認
# ✅ --command 內用雙引號包覆，內部用單引號
echo "" | gcloud -q compute ssh user@instance --zone=zone --tunnel-through-iap --command "sudo journalctl -u bot.service -n 50 --no-pager | grep -iE 'error|fail'"
```

**模式 B：複雜命令（上傳腳本到 VM 執行，用完清理）**
```powershell
# 當命令含多層引號、awk/sed 等複雜語法時：
echo "" | gcloud -q compute scp local_script.py user@instance:/tmp/ --zone=zone --tunnel-through-iap
echo "" | gcloud -q compute ssh user@instance --zone=zone --tunnel-through-iap --command "cd /path && python3 /tmp/local_script.py && rm /tmp/local_script.py"
```

**PowerShell 引號規則速查**：
| 場景 | ✅ 正確寫法 | 說明 |
|------|------------|------|
| 命令含空格 | `--command="cmd arg1 arg2"` | 雙引號包覆整個命令 |
| 命令含 `$` | `--command 'echo $HOME'` | 單引號防止 PowerShell 展開變數 |
| 命令含 `\|` 管道 | `--command "cmd1 \| cmd2"` | 雙引號內管道正常傳遞 |
| 命令含雙引號 | `--command 'echo "hello"'` | 外層單引號，內層雙引號 |
| 多層嵌套 | **改用模式 B（腳本）** | 不要嘗試 3 層以上引號嵌套 |

**關鍵原則**：
- ✅ `echo "" | gcloud -q` 是避免 SSH 互動提示的標準前綴
- ✅ 命令簡單時用 PowerShell 直接執行
- ✅ 引號複雜時果斷改用「上傳腳本 → 執行 → 清理」
- ❌ 不要在 PowerShell 中嘗試超過 2 層引號嵌套
- ❌ 不要花超過 3 次嘗試在引號問題上
- ✅ **腳本用完後務必清理**：`&& rm /tmp/script.py`

## Git & Deployment Workflow

1. Commit & push to GitHub
2. On VM: `git pull`
3. `sudo systemctl restart <service>`
4. Verify logs: `sudo journalctl -u <service> -f`

## Local Pre-push / Pre-commit Checks (L1 + L2)

**Push 前必跑（本地驗證，避免 CI 失敗浪費時間）：**

```bash
# 完整檢查 (約 30-60 秒)
pytest tests/ -q --tb=line -x -m "not integration" && ruff check . && black --check .
```

**分項檢查：**

| 指令 | 用途 | 預估時間 |
|------|------|----------|
| `pytest tests/ -q -m "not integration"` | 只跑單元測試 (快) | ~10-20s |
| `pytest tests/ -q` | 跑所有測試 (含整合) | ~60s |
| `ruff check . --fix` | Lint + 自動修復 | ~5s |
| `black --check .` | 格式檢查 | ~5s |
| `pre-commit run --all-files` | 所有 pre-commit hooks | ~30s |

**Pre-commit Hook 安裝 (一次性)：**
```bash
pip install pre-commit
pre-commit install
# 之後每次 commit 自動跑檢查
```

**手動觸發所有 hooks：**
```bash
pre-commit run --all-files
```

**跳過 hooks (緊急時)：**
```bash
git commit --no-verify
```

## File Structure Conventions

```
cogs/
  common/     # Shared cog utilities
  shop/       # Shop-related cogs
  ui/         # UI-related cogs (persistent views)
config/
  commands_registry.json    # Command registry
  discord_commands_registry.json  # Discord slash commands
scripts/
  commands_manager.py       # Main CLI for bot management
shared/
  utils/
    view_registry.py        # PersistentViewBase
```

## Testing

- Unit tests in `tests/` (if exists)
- Integration tests via manual verification on staging
- Use `test_modules.py` for module validation

## Environment Variables

- `.env` is local only (not committed)
- Required: `DISCORD_TOKEN`, `DATABASE_URL`, `GCP_PROJECT_ID`
- Set on VM via systemd service EnvironmentFile

## Coding Style

- Type hints on all public functions
- Docstrings for classes and public methods (explain WHY not WHAT)
- Max line length: 100 chars
- Use `black` for formatting, `ruff` for linting

## Skill Invocation Patterns

When user says... | Invoke skill
--- | ---
"Which skill should I use?" | `ask-matt`
"Help me plan this feature" | `grill-with-docs` (has codebase) or `grill-me` (no codebase)
"This is too big for one session" | `wayfinder`
"Turn this into a spec" | `to-spec`
"Break this into tickets" | `to-tickets"
"Implement this spec" | `implement`
"Review my changes" | `code-review`
"Debug this bug" | `diagnosing-bugs`
"Improve the architecture" | `improve-codebase-architecture`
"Set up this repo for skills" | `setup-matt-pocock-skills`
"Teach me X" | `teach`
"Write a handoff" | `handoff`

## Context Hygiene

- Keep steps 1-3 (grill → spec → tickets) in ONE unbroken context window
- Don't compact until after `/to-tickets`
- If approaching smart zone limit (~120k tokens), `/handoff` and continue fresh
- Each `/implement` starts fresh from its ticket

## Persistent Views (Discord UI)

All Discord UI views MUST inherit from `PersistentViewBase`:
```python
from shared.utils.view_registry import PersistentViewBase

class MyView(PersistentViewBase):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None is automatic
```

## Command Registration

New slash commands must be registered in:
1. `config/discord_commands_registry.json` - for Discord API
2. `config/commands_registry.json` - for internal command manager

## Error Handling

- Log errors with context: `logger.error("Failed to X", extra={"user_id": uid, "error": str(e)})`
- User-facing errors: ephemeral followup with actionable message
- Never expose stack traces to users

---

*These instructions are derived from Matt Pocock's engineering skills (mattpocock/skills) adapted for VS Code + GitHub Copilot.*

---

## KKGroup 專案實務知識庫

> **快速導覽**：以下為 KKGroup 專案特有的部署、開發、維運規則。若需深入了解架構，請參考 `knowledge/_wiki/` 下的詳細文檔。

### 📚 核心知識庫參考（優先閱讀順序）

| 檔案路徑（AI 讀取用） | Obsidian 連結（人類用） | 用途 |
|----------------------|------------------------|------|
| `knowledge/_wiki/concepts/ai-fast-read.md` | `[[concepts/ai-fast-read]]` | 專案一句話摘要、分區、核心執行單位、資料層模型、高頻維運入口、最重要工作流、必記規則 |
| `knowledge/_wiki/entities/bot-services.md` | `[[entities/bot-services]]` | 三個 Bot 服務、systemd 操作、常用指令 |
| `knowledge/_wiki/entities/command-registry.md` | `[[entities/command-registry]]` | `scripts/commands_manager.py` 統一操作入口、registry 結構、診斷命令 |
| `knowledge/_wiki/concepts/webhook-and-tunnel.md` | `[[concepts/webhook-and-tunnel]]` | GitHub push → Cloudflare tunnel → Nginx → Flask → git pull → restart 流程、已知事實、檢查點 |
| `knowledge/_wiki/concepts/coding-rules-and-paths.md` | `[[concepts/coding-rules-and-paths]]` | 高頻編碼規則、路徑規則（字型三層 `../`）、Discord 指令規則 |
| `knowledge/_wiki/concepts/discord-bot-system.md` | `[[concepts/discord-bot-system]]` | 三 Bot 架構、Cogs 分類、按鈕視圖系統、Slash Commands、權限角色、訊息處理、事件處理 |
| `knowledge/_wiki/concepts/project-architecture.md` | `[[concepts/project-architecture]]` | 完整專案架構圖、資料流向、技術棧、安全、擴展性、效能優化、監控 |
| `knowledge/_wiki/concepts/deployment-and-operations.md` | `[[concepts/deployment-and-operations]]` | GCP VM 架構、systemd 服務配置、自動化部署、GitHub Webhook、網路隧道 |
| `knowledge/_wiki/concepts/kk-park-economy-system.md` | `[[concepts/kk-park-economy-system]]` | KK 幣經濟系統跨層關聯圖、核心代碼入口、查問題閱讀順序、功能對應檔案速查 |
| `knowledge/_wiki/concepts/ai-memory-and-vm-knowledge-pipeline.md` | `[[concepts/ai-memory-and-vm-knowledge-pipeline]]` | AI 記憶與 VM 知識更新流程、四步驟資料流、排程、Discord Webhook 通知 |
| `knowledge/_wiki/concepts/paperdoll-workflow.md` | `[[concepts/paperdoll-workflow]]` | `[[concepts/paperdoll-workflow]]` | 紙娃娃核心原則、修復流程 5 步驟、常見風險 |

> ⚠️ **注意**：專案根目錄**不存在** `CODING_RULES/` 資料夾。編碼規範請參考 `knowledge/_wiki/concepts/coding-rules-and-paths.md` 及上述相關概念文檔。

---

### 🚀 快速查詢指令

```bash
# 部署
git push → webhook 自動更新 ✅

# 重啟服務
sudo systemctl restart bot.service shopbot.service uibot.service

# 查看日誌
sudo journalctl -u bot.service -n 50 --no-pager

# 資料庫操作
本地驗證 → gcloud compute scp 複製到 VM → 重啟服務

# 字型路徑（從 cogs/common/ 出發）
../../fonts/NotoSansCJKtc-Regular.otf  # 正確：三層 ../
../fonts/                              # 錯誤：只有一層 ../

# 紙娃娃完整流程
檢查 → 修復 → 驗證 → 部署 → /admin_refresh_all_lockers

# GCP VM SSH (IAP)
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

# 統一維運入口
python scripts/commands_manager.py <service> <action>
```

---

### 🏗️ 專案結構速覽

```
kkgroup/
├── bots/           # bot.py, shopbot.py, uibot.py
├── cogs/
│   ├── common/     # 共用功能、KK幣、AI、工作功能
│   ├── shop/       # 商店、商家、大麻種植、醫院商家
│   └── ui/         # UI 互動、置物櫃、動漫追蹤、活動
├── shared/
│   ├── db/         # db_adapter.py, sheet_driven_db.py, ai_memory.py
│   └── utils/      # embed_views.py, view_registry.py, fortress_system.py
├── web/
│   ├── api/        # Flask API、blueprints
│   ├── portal/     # 前端 HTML、RPG 遊戲
│   └── activities/ # 活動系統
├── config/
│   ├── commands_registry.json
│   ├── discord_commands_registry.json
│   ├── services/   # systemd service 檔（僅 VM 管理，不上傳 Git）
│   └── scripts/
├── scheduled_tasks/ # cron 任務
├── scripts/        # commands_manager.py、掃描腳本等
├── fonts/          # NotoSansCJKtc-Regular.otf
├── game/           # Web RPG 系統
└── knowledge/      # 知識庫
```

---

### 🔧 核心開發規範

#### Discord.py 2.0
- 使用 `discord.ext.commands.Bot` 搭配 `intents=discord.Intents.all()`
- Slash Commands：`@bot.tree.command()` 或 `@app_commands.command()`
- **永久視圖必須繼承 `PersistentViewBase`**（`shared/utils/view_registry.py`）
- 按鈕回調：`interaction.response.defer()` → `interaction.followup.send()`
- 用戶專用回饋使用 `ephemeral=True`

#### 非同步最佳實踐
- 平行操作用 `asyncio.gather()`
- 熱路徑避免 `asyncio.sleep()`
- 資源管理用 `async with`
- 長期任務處理 `asyncio.CancelledError`

#### 資料庫
- 參數化查詢：`cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`
- 連線池：`sqlite3.connect(check_same_thread=False)`
- 交易：`BEGIN` / `commit()` / `rollback()`

#### 環境變數
- `.env` 僅本地使用，**不提交 Git**
- 必要變數：`DISCORD_TOKEN`、`DATABASE_URL`、`GCP_PROJECT_ID`
- VM 上透過 systemd `EnvironmentFile` 設定

#### 程式碼風格
- 公開函數必須有型別提示
- 類別與公開方法需有 docstring（**解釋 WHY，不只是 WHAT**）
- 行寬上限 100 字元
- 格式化用 `black`，檢查用 `ruff`

---

### 📦 部署與維運流程

#### GitHub Webhook 自動化（主流程）
1. **Push 事件觸發** (`web/blueprints/webhook.py`)
   - GitHub push → Cloudflare tunnel → kkgroup-api (Flask)
   - 驗證簽名 → `git pull` → 重啟三個 Bot 服務
   - 發送 Discord 通知

2. **Flask API 服務** (`kkgroup-api.service`, port 5000)
   - 依賴：`network-online.target`, `systemd-resolved.service`
   - 編碼環境變數：`PYTHONIOENCODING=utf-8`, `LANG=C.UTF-8`

3. **Webhook 狀態**：✅ **完全正常運作**
   - GitHub UI 可能顯示 "We couldn't deliver this payload"
   - 原因：隧道無法完整回傳 HTTP 200 給 GitHub
   - **不影響實際功能**，只影響 UI 記錄

4. **驗證 Webhook 運作**：
   - Flask 日誌：`sudo journalctl -u kkgroup-api.service | grep webhook`
   - Bot 重啟：`sudo systemctl status bot.service | grep Active`
   - GitHub 交付記錄：GitHub > Webhooks > Deliveries

#### VM 服務管理
- 三服務：`bot.service`、`shopbot.service`、`uibot.service`
- **必須啟用開機自啟**：`sudo systemctl enable bot.service shopbot.service uibot.service`
- 建議重啟策略：
  ```ini
  Restart=on-failure
  RestartSec=10
  StartLimitBurst=10
  StartLimitIntervalSec=600
  ```
- e2-micro 記憶體有限，**務必加 swap**：
  ```bash
  sudo fallocate -l 1G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

#### Cron 排程任務
- 每 5 分鐘：`update_restart.py`、`sync_to_sheet.py`
- 每週三、六 14:00：`refresh_all_lockers_cron.py`
- 每週一 03:00：`weekly_backup.py`
- 知識庫刷新：每天 18:00（台灣時間）執行 `refresh_knowledge_base.py`

---

### 🎮 紙娃娃系統核心規則

#### 新用戶隨機造型
```python
# ✅ 正確：使用 paperdoll_manager.get_random()
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

#### 用戶選擇性別時
```python
# ✅ 保持性別，生成符合該性別的隨機造型
selected_gender = select.values[0]  # 'male' 或 'female'
appearance = paperdoll_manager.get_random(preserve_gender=selected_gender)
await self.cog.update_user_data(user_id, appearance)
```

#### 核心原則
- ✅ 必須使用 `paperdoll_manager.get_random()` 生成隨機造型
- ✅ 來源必須是 `twms_fashion_db.json` 中的有效物品 ID
- ✅ 性別一致性：男性選自 `face_male/hair_male` 等，女性選自 `face_female/hair_female` 等
- ❌ **不要在 welcome_message.py 硬編碼造型值**（如 `'face': 20005`）
- ✅ 所有 API URL 透過 `paperdoll_manager.build_api_url()` 建構

#### 修復流程（完整 5 步）
1. **診斷** - 檢查 fashion DB 和部件 ID 有效性
2. **修復** - 更新 `twms_fashion_db.json` 或代碼邏輯
3. **驗證** - 本地測試確保生成的造型有效
4. **部署** - Git push 觸發 webhook 重啟 Bot
5. **刷新** - 執行 `/admin_refresh_all_lockers` 更新所有用戶紙娃娃

---

### 💰 KK 園區經濟系統（跨層共享機制）

核心貨幣 `kkcoin` 行為分散在：
- `cogs/common/kcoin.py` - 查詢、排行榜、中央儲備金
- `cogs/shop/shop.py` - 購物、拉霸、裝備購買
- `cogs/shop/cannabis_cog.py` - 種植循環
- `cogs/shop/merchant/` - 多商家交易流程
- `cogs/ui/anime_tracker.py` - UI 互動獎勵
- `shared/utils/fortress_system.py` - 活動成本與獎勵
- `shared/db/db_adapter.py` - `get_user_kkcoin()`、`update_user_kkcoin()` 向後相容入口
- `shared/db/sheet_driven_db.py` - kkcoin 為玩家主資料欄位之一

**查問題閱讀順序**：
1. 使用者說數字不對 → `kcoin.py` → `db_adapter.py` → 觸發功能檔
2. 功能沒扣款/發獎 → 對應 Cog/View → 是否呼叫 `update_user_kkcoin()` / `set_user_field()` → 有無重複防護
3. 找不到指令 → `config/discord_commands_registry.json` → 對應 `file` 欄位 → 進 Cog

---

### 🔐 安全與資料庫原則

- 敏感資訊全在 `.env`：Bot Token、API Key、密碼
- `.env` 在 `.gitignore` 中
- 代碼中用 `os.getenv("KEY")`
- **洩漏立即撤銷並重設**
- **VM 為主，本地驗證後複製**
- **改資料庫前必備份**
- VIP 角色用 `/grant_temporary_role` 給予（不要手動給）
- `cleanup_expired_roles_loop()` 每 5 分鐘自動清理過期角色

---

### ⚠️ 常見踩坑避雷

| 層級 | ❌ 不要做 | ✅ 正確做法 |
|------|-----------|-------------|
| 代碼 | 硬編碼敏感資訊 | 用環境變數 |
| 代碼 | 分散定義按鈕 | 用統一視圖系統 |
| 代碼 | 盲目改代碼 | 先查 git 歷史找工作版本 |
| 代碼 | 忽視字型路徑層級 | 從 `cogs/common/` 用 `../../fonts/` |
| 部署 | 手動改隧道 URL | 讓 webhook 自動處理 |
| 部署 | 頻繁重啟 Flask | 只在必要時重啟 |
| 部署 | 只在本地測試 | **必須在 VM 驗證** |
| 部署 | 上傳 service 檔到 Git | service 檔僅在 VM 管理 |
| 資料庫 | 直接改 VM 資料庫 | 本地驗證 → 複製 → 重啟 |
| 資料庫 | 忘記備份 | 改前必備份 |
| 資料庫 | 只改部分部位 | 完整更新 |
| 資料庫 | 用單一值替換所有預設 | 用 `paperdoll_manager.get_random()` |

---

### ❓ 常見問題快速回答

| 問題 | 回答 |
|------|------|
| 代碼多久生效？ | webhook 自動觸發，push 後幾秒內 |
| 可以直接改資料庫嗎？ | 不建議，本地驗證 → 複製 → 重啟 |
| 為什麼用統一按鈕系統？ | 改一個地方改所有 |
| 紙娃娃修復後看不到效果？ | 1) `/admin_refresh_all_lockers` 2) 資料庫有無複製到 VM 3) 服務有無重啟 |
| 動畫推播重複/沒推到？ | 2026-04-29 已修復 - 用資料庫追蹤已檢查時刻，防重啟重複推送，修正時間計算邏輯 |

---

### 🔗 相關技能調用模式

| 使用者說... | 調用技能 |
|-------------|----------|
| "該用哪個技能？" | `ask-matt` |
| "幫我規劃這個功能" | `grill-with-docs` (有代碼庫) 或 `grill-me` (無代碼庫) |
| "這太大了，一個 session 做不完" | `wayfinder` |
| "轉成 spec" | `to-spec` |
| "拆成 tickets" | `to-tickets` |
| "實作這個 spec" | `implement` |
| "審查我的變更" | `code-review` |
| "除錯這個 bug" | `diagnosing-bugs` |
| "改善架構" | `improve-codebase-architecture` |
| "設定 repo 給 skills 用" | `setup-matt-pocock-skills` |
| "教我 X" | `teach` |
| "寫一份 handoff" | `handoff` |
| "強制極簡代碼" | `ponytail` |
| "檢查過度設計" | `ponytail-review` |

---

### 🧹 Context Hygiene（上下文衛生）

- 步驟 1-3（grill → spec → tickets）在**同一個未中斷的 context window** 完成
- 不要在 `/to-tickets` 前 compact
- 接近 token 限制 (~120k) 時，用 `/handoff` 產出文件後重新開始
- 每個 `/implement` 從其 ticket 重新開始

## graphify — 專案知識圖譜（優先使用！）

> `graphify-out/` 是預先建立的專案知識圖譜，包含 **4,100 個節點、8,301 條邊、258 個社群**。
> 遇到架構問題時，**優先搜尋 graph.json**，不要盲目 grep 整個專案。

### 使用方式（GitHub Copilot 可執行）

| 問題類型 | 做法 | 工具 |
|----------|------|------|
| 「某功能在哪個檔案？」 | 在 `graphify-out/graph.json` 中搜尋節點 `label` | `grep_search` |
| 「A 和 B 的關聯？」 | 在 `graph.json` 中找兩個節點，追蹤它們的邊（edges） | `grep_search` + `read_file` |
| 「這個概念涉及哪些檔案？」 | 搜尋 `graph.json` 中同一個 `community_name` 的所有節點 | `grep_search` |
| 「專案整體架構？」 | 讀 `graphify-out/GRAPH_REPORT.md` 的 Community Hubs 列表 | `read_file` |

### 觸發條件

當使用者問以下問題時，**優先查 graphify 而非 grep 原始碼**：
- "這個功能在哪裡？" / "where is…"
- "A 和 B 有什麼關係？" / "how does X relate to Y"
- "有哪些檔案用到這個？" / "what depends on…"
- "解釋一下架構" / "explain the architecture"
- 任何需要理解檔案/類別之間關聯的問題

### 圖譜結構說明

`graph.json` 中每個節點包含：
- `id` — 唯一識別碼（如 `cogs_ui_anime_tracker`）
- `label` — 人類可讀名稱（如 `AnimeTracker`、`anime_tracker.py`）
- `source_file` — 原始碼路徑
- `community` / `community_name` — 所屬社群（如 `KKCoin`、`PersistentViewBase`）
- `file_type` — `"code"` 表示程式碼節點

邊（edges）記錄節點之間的引用、繼承、呼叫等關係。

### 維護

當專案結構有重大變更時，提醒使用者執行 `/graphify` 重建圖譜。

## gstack Skill Routing (auto-trigger)

gstack 是一個虛擬工程團隊（CEO review → Engineering review → QA → Ship pipeline）。當對話內容匹配時會**自動觸發**，不需要打 `/` 指令。

| 使用者說... | 自動調用的 Skill |
|------------|-----------------|
| 腦力激盪、產品點子、專案想法 | `office-hours` |
| 策略、範圍、優先級、行銷 | `plan-ceo-review` |
| 架構、技術棧選擇 | `plan-eng-review` |
| 設計系統、設計審查 | `design-consultation` 或 `plan-design-review` |
| 完整審查流程（Plan → Review → Ship）| `autoplan` |
| Bug、錯誤、壞掉了 | `investigate` |
| QA、測試、檢查行為 | `qa` 或 `qa-only` |
| Code review、diff 檢查 | `review` |
| 視覺調整、CSS、樣式 | `design-review` |
| 部署、發 PR、上線 | `ship` 或 `land-and-deploy` |
| 儲存當前進度 | `context-save` |
| 恢復先前上下文 | `context-restore` |
| 撰寫 backlog-ready spec/issue | `spec` |


---

## AI 專用查��工具（新增）

本專案提供三個工具�� AI Agent ���速理解代��庫，無需����大量原始��：

### 1. scripts/query_graph.py — Graphify 知������查��
`ash
python scripts/query_graph.py stats                    # ����統計
python scripts/query_graph.py hubs                     # ��心社群排行
python scripts/query_graph.py community KKCoin         # ��社群所有節點
python scripts/query_graph.py search update_user_kkcoin # 關���字�����
python scripts/query_graph.py callers <node_id>        # ��呼叫者（反向��）
python scripts/query_graph.py callees <node_id>        # ��被呼叫者（正向��）
python scripts/query_graph.py impact cogs/shop/shop.py # 影響����分��
python scripts/query_graph.py node <node_id>           # 節點詳細資��
`
- **資料來源**：graphify-out/graph.json (4570 節點、8512 ��、263 社群)
- **優勢**：架構級、離線、多語言、社群/依��關係、影響分��
- **自動更新**：.github/workflows/graphify-update.yml ��次 push main 自動重建

### 2. scripts/lsp_query.py — Pylance LSP 封��查��
`ash
python scripts/lsp_query.py --file <路��> symbols      # 列出��案所有符號
python scripts/lsp_query.py --file <路��> refs <符號>      # ��引用
python scripts/lsp_query.py --file <路��> def <符號>       # ��定義
python scripts/lsp_query.py --file <路��> hierarchy <符號> # ���叫��級
python scripts/lsp_query.py --file <路��> diagnostics      # �����/警告
python scripts/lsp_query.py --file <路��> type <符號>      # ���別推導
python scripts/lsp_query.py --file <路��> hover <符號>     # Hover ����
`
- **資料來源**：Pylance LSP (VS Code 內建 Python Extension)
- **優勢**：符號級、即時、精確、型別/重構/定義跳��
- **MCP ��合**：可直接呼叫 mcp_pylance_mcp_s_pylanceLSP

### 3. .github/workflows/graphify-update.yml — Graphify 自動更新
- **��發**：push 到 main、PR merged、手動��發、每日 03:00 UTC
- **行為**：比對 uilt_at_commit，過期才重建，自動 commit 回 repo
- **權限**：contents: write 可推送更新

### 兩者互補關係

| ����需求 | 用 Graphify | 用 LSP |
|----------|-------------|--------|
| 「KK��系統包含哪些��案？」 | community KKCoin | 無 |
| 「誰呼叫了 update_user_kkcoin？」 | callers (��態����) |
efs (精確引用) |
| 「改 shop.py 會��哪��？」 | impact (按社群影響) | 無 |
| 「這個��數的型別��名？」 | 無 | 	ype |
| 「專案架構��心是什���？」 | hubs | 無 |
| 「這個類別有哪些方法？」 | 部分 | symbols |

**Graphify** = ��構級、離線、多語言、社群/依��關係
**LSP** = 符號級、即時、精確、型別/重構/定義跳��
