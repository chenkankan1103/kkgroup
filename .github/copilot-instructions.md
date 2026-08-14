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

### ��� Discord 互動 3 秒超時����（高������！）

**��心問題**：Discord 要求按���/選單 callback �����在 **3 秒內** ���出首次回應（defer 或 send），否則會��示 "The application did not respond"。

**`defer()` 的作用**：告�� Discord「收到��求，正在處理」，將超時延長到 **15 分鐘**。但 `defer()` 本身必��在 3 秒內被呼叫。

**正確模式**：

```python
async def _button_callback(self, interaction: discord.Interaction):
    # �� 第一步：立刻 defer()，什���都別做
    await interaction.response.defer()

    # �� 第二步：慢慢處理（資料庫��入、API ���叫、KK��獎��等）
    self.tracker.record_vote(...)
    set_user_field(...)

    # �� 第三步：用 followup 回應用��
    await interaction.followup.send("��� 成功！", ephemeral=True)
```

**����模式（會導致 3 秒超時）**：

```python
async def _button_callback(self, interaction: discord.Interaction):
    # ��� 先做��時操作（DB ��入、API ���叫...）
    self.tracker.record_vote(...)  # SQLite 可能��定等待
    set_user_field(...)

    # ��� defer() 太晚，可能已超過 3 秒
    await interaction.response.defer()
```

**Modal 注意事項**：
- `send_modal()` 不需要 defer，但 Modal 本身也有 3 秒限制
- Modal 的 `on_submit` 中也需要在 3 秒內回應（defer 或 send_message）
- Modal 類別定義內的 `self` 是 Modal 實例，不是外部 View — ���用 `outer_self` ���獲

**����處理注意**：
- 如果已 defer 過，����處理要用 `followup.send()` 而非 `response.send_message()`
- ���查方式：`if interaction.response.is_done():` → 用 followup，否則用 response

**��查清單**（�� callback 時必查）：
| # | ���查項 | �� |
|---|--------|-----|
| 1 | `defer()` 是 callback 的第一個 await？ | |
| 2 | 所有後續回應都用 `followup.send()`？ | |
| 3 | �����處理有��查 `is_done()` ���決定用哪個？ | |
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

### ������ ��免資料庫��定問題 (Database Lock Prevention)

**重要**：SQLite 在多進程並發存取時容易發生 `database is locked` �����。������以下最佳實��：

1. **��用 WAL ��式**：在資料庫連線建立時��用 WAL (Write-Ahead Logging) ��式
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   conn.execute("PRAGMA busy_timeout=30000")  # 30 秒等待超時
   conn.execute("PRAGMA synchronous=NORMAL")
   ```

2. **使用連線��/共用連線**：��免����開關連線，使用連線��或共用連線物件

3. **設定 busy_timeout**：設定足��的等待時間，��免短����定導致立即失敗
   ```python
   conn.execute("PRAGMA busy_timeout=30000")  # 30 秒
   ```

4. **��免長時間持有連線**：在 `with` 區��中��快完成操作並��放連線

5. **批次操作合��**：將多個��入操作合��為單一交易，減少��定時間

6. **使用 WAL ��式的優勢**：
   - ��取不��塞��入，��入不��塞��取
   - ��援多進程並發��取
   - ��少��定��突機率

**已知問題**：專案中有 5 ��進程同時存取同一 SQLite ��料庫 (bot, shopbot, uibot, unified_api, auto_self_heal)，已於 2026-07-24 修復並��用 WAL ��式解決。

## GCP VM Deployment

- SSH via IAP: `gcloud compute ssh <user>@<instance> --zone <zone> --tunnel-through-iap`
- Services: `bot.service`, `shopbot.service`, `uibot.service`
- Logs: `sudo journalctl -u <service> -n 100 --no-pager`
- Restart: `sudo systemctl restart <service>`

### ��� PowerShell ��號與 gcloud SSH ����（高������！）

**��心問題**：PowerShell 對單引號 `'`、��引號 `"`、管線 `|` 的處理與 bash 完全不同，gcloud SSH ���令��易因引號�����失敗。

**策略優先級**：
1. 先��試 PowerShell 簡化版：用 `echo "" | gcloud -q` ��免 SSH 互動提示
2. 如 2-3 ����試仍失敗 → ��用「上����本 → ��行 → ��理」模式

**模式 A：簡單命令（PowerShell 直接��行）**
```powershell
# �� echo "" | ��免 SSH host key 互動提示
# �� gcloud -q ��過所有確認
# �� --command 內用��引號包��，內部用單引號
echo "" | gcloud -q compute ssh user@instance --zone=zone --tunnel-through-iap --command "sudo journalctl -u bot.service -n 50 --no-pager | grep -iE 'error|fail'"
```

**模式 B：複��命令（上����本到 VM ��行，用完清理）**
```powershell
# 當命令含多��引號、awk/sed 等複��語法時：
echo "" | gcloud -q compute scp local_script.py user@instance:/tmp/ --zone=zone --tunnel-through-iap
echo "" | gcloud -q compute ssh user@instance --zone=zone --tunnel-through-iap --command "cd /path && python3 /tmp/local_script.py && rm /tmp/local_script.py"
```

**PowerShell ��號規則速查**：
| 場景 | �� 正確��法 | ��明 |
|------|------------|------|
| ���令含空格 | `--command="cmd arg1 arg2"` | ��引號包��整個命令 |
| ���令含 `$` | `--command 'echo $HOME'` | ���引號防止 PowerShell ��開��數 |
| ���令含 `\|` 管道 | `--command "cmd1 \| cmd2"` | ��引號內管道正常���� |
| ���令含��引號 | `--command 'echo "hello"'` | 外��單引號，內����引號 |
| 多������� | **改用模式 B（��本）** | 不要��試 3 ��以上引號����� |

**關���原則**：
- �� `echo "" | gcloud -q` 是��免 SSH 互動提示的標準前��
- �� ���令簡單時用 PowerShell 直接��行
- �� ��號複��時果��改用「上����本 → ��行 → ��理」
- ��� 不要在 PowerShell 中��試超過 2 ��引號�����
- ��� 不要花超過 3 ����試在引號問題上
- �� **��本用完後務必清理**：`&& rm /tmp/script.py`

## Git & Deployment Workflow

1. Commit & push to GitHub
2. On VM: `git pull`
3. `sudo systemctl restart <service>`
4. Verify logs: `sudo journalctl -u <service> -f`

## Local Pre-push / Pre-commit Checks (L1 + L2)

**Push 前必��（本地����，��免 CI 失敗��費時間）：**

```bash
# 完整��查 (約 30-60 秒)
pytest tests/ -q --tb=line -x -m "not integration" && ruff check . && black --check .
```

**分項��查：**

| ��令 | 用途 | ��估時間 |
|------|------|----------|
| `pytest tests/ -q -m "not integration"` | 只��單元��試 (快) | ~10-20s |
| `pytest tests/ -q` | ��所有��試 (含整合) | ~60s |
| `ruff check . --fix` | Lint + 自動修復 | ~5s |
| `black --check .` | 格式��查 | ~5s |
| `pre-commit run --all-files` | 所有 pre-commit hooks | ~30s |

**Pre-commit Hook 安�� (一次性)：**
```bash
pip install pre-commit
pre-commit install
# 之後每次 commit 自動����查
```

**手動��發所有 hooks：**
```bash
pre-commit run --all-files
```

**跳過 hooks (��急時)：**
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

## KKGroup 專案實務知��庫

> **快速導��**：以下為 KKGroup 專案特有的部署、開發、維運規則。若需深入了解架構，��參考 `knowledge/_wiki/` 下的詳細文��。

### ��� ��心知��庫參考（優先������序）

| ���案路��（AI ��取用） | Obsidian 連結（人類用） | 用途 |
|----------------------|------------------------|------|
| `knowledge/_wiki/concepts/ai-fast-read.md` | `[[concepts/ai-fast-read]]` | 專案一句話摘要、分區、��心��行單位、資料��模型、高��維運入口、最重要工作流、必記規則 |
| `knowledge/_wiki/entities/bot-services.md` | `[[entities/bot-services]]` | 三個 Bot 服務、systemd ���作、常用指令 |
| `knowledge/_wiki/entities/command-registry.md` | `[[entities/command-registry]]` | `scripts/commands_manager.py` 統一操作入口、registry 結構、����命令 |
| `knowledge/_wiki/concepts/webhook-and-tunnel.md` | `[[concepts/webhook-and-tunnel]]` | GitHub push → Cloudflare tunnel → Nginx → Flask → git pull → restart ��程、已知事實、��查點 |
| `knowledge/_wiki/concepts/coding-rules-and-paths.md` | `[[concepts/coding-rules-and-paths]]` | 高��編��規則、路��規則（字型三�� `../`）、Discord ��令規則 |
| `knowledge/_wiki/concepts/discord-bot-system.md` | `[[concepts/discord-bot-system]]` | 三 Bot ��構、Cogs 分類、按���視��系統、Slash Commands、權限角色、��息處理、事件處理 |
| `knowledge/_wiki/concepts/project-architecture.md` | `[[concepts/project-architecture]]` | 完整專案架構��、資料流向、技術��、安全、��展性、效能優化、監控 |
| `knowledge/_wiki/concepts/deployment-and-operations.md` | `[[concepts/deployment-and-operations]]` | GCP VM ��構、systemd 服務配置、自動化部署、GitHub Webhook、網路��道 |
| `knowledge/_wiki/concepts/kk-park-economy-system.md` | `[[concepts/kk-park-economy-system]]` | KK ��經濟系統����關聯��、��心代��入口、查問題������序、功能對應��案速查 |
| `knowledge/_wiki/concepts/ai-memory-and-vm-knowledge-pipeline.md` | `[[concepts/ai-memory-and-vm-knowledge-pipeline]]` | AI 記��與 VM 知��更新流程、四步��資料流、排程、Discord Webhook 通知 |
| `knowledge/_wiki/concepts/paperdoll-workflow.md` | `[[concepts/paperdoll-workflow]]` | ��������心原則、修復流程 5 步��、常見風�� |

> ������ **注意**：專案根目錄**不存在** `CODING_RULES/` ��料��。編��規����參考 `knowledge/_wiki/concepts/coding-rules-and-paths.md` 及上述相關概念文��。

---

### ��� ���速查��指令

```bash
# 部署
git push → webhook 自動更新 ��

# 重��服務
sudo systemctl restart bot.service shopbot.service uibot.service

# ��看日誌
sudo journalctl -u bot.service -n 50 --no-pager

# ��料庫操作
本地���� → gcloud compute scp ���製到 VM → 重��服務

# 字型路��（從 cogs/common/ 出發）
../../fonts/NotoSansCJKtc-Regular.otf  # 正確：三�� ../
../fonts/                              # �����：只有一�� ../

# ������完整流程
��查 → 修復 → ����� → 部署 → /admin_refresh_all_lockers

# GCP VM SSH (IAP)
gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap

# 統一維運入口
python scripts/commands_manager.py <service> <action>
```

---

### ������ 專案結構速��

```
kkgroup/
├── bots/           # bot.py, shopbot.py, uibot.py
├── cogs/
│   ├── common/     # 共用功能、KK��、AI、工作功能
│   ├── shop/       # ��店、商家、大麻種��、��院商家
│   └── ui/         # UI 互動、置物���、動��追���、活動
├── shared/
│   ├── db/         # db_adapter.py, sheet_driven_db.py, ai_memory.py
│   └── utils/      # embed_views.py, view_registry.py, fortress_system.py
├── web/
│   ├── api/        # Flask API、blueprints
│   ├── portal/     # 前端 HTML、RPG 遊��
│   └── activities/ # ���動系統
├── config/
│   ├── commands_registry.json
│   ├── discord_commands_registry.json
│   ├── services/   # systemd service ���（�� VM 管理，不上�� Git）
│   └── scripts/
├── scheduled_tasks/ # cron 任務
├── scripts/        # commands_manager.py、������本等
├── fonts/          # NotoSansCJKtc-Regular.otf
├── game/           # Web RPG 系統
��── knowledge/      # 知��庫
```

---

### ��� ��心開發規��

#### Discord.py 2.0
- 使用 `discord.ext.commands.Bot` ���配 `intents=discord.Intents.all()`
- Slash Commands：`@bot.tree.command()` 或 `@app_commands.command()`
- **永久視��必����承 `PersistentViewBase`**（`shared/utils/view_registry.py`）
- �����回調：`interaction.response.defer()` → `interaction.followup.send()`
- 用��專用回��使用 `ephemeral=True`

#### 非同步最佳實��
- 平行操作用 `asyncio.gather()`
- 熱路����免 `asyncio.sleep()`
- ��源管理用 `async with`
- 長期任務處理 `asyncio.CancelledError`

#### ��料庫
- 參數化查��：`cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`
- 連線��：`sqlite3.connect(check_same_thread=False)`
- 交易：`BEGIN` / `commit()` / `rollback()`

#### 環境��數
- `.env` ���本地使用，**不提交 Git**
- ���要��數：`DISCORD_TOKEN`、`DATABASE_URL`、`GCP_PROJECT_ID`
- VM 上透過 systemd `EnvironmentFile` 設定

#### 程式��風格
- 公開��數必��有型別提示
- 類別與公開方法需有 docstring（**解�� WHY，不只是 WHAT**）
- 行��上限 100 字元
- 格式化用 `black`，��查用 `ruff`

---

### ��� 部署與維運流程

#### GitHub Webhook 自動化（主流程）
1. **Push 事件��發** (`web/blueprints/webhook.py`)
   - GitHub push → Cloudflare tunnel → kkgroup-api (Flask)
   - �������名 → `git pull` → 重��三個 Bot 服務
   - 發送 Discord 通知

2. **Flask API 服務** (`kkgroup-api.service`, port 5000)
   - 依��：`network-online.target`, `systemd-resolved.service`
   - 編��環境��數：`PYTHONIOENCODING=utf-8`, `LANG=C.UTF-8`

3. **Webhook ��態**：��� **完全正常運作**
   - GitHub UI 可能��示 "We couldn't deliver this payload"
   - 原因：��道無法完整回�� HTTP 200 給 GitHub
   - **不影響實際功能**，只影響 UI 記錄

4. **���� Webhook 運作**：
   - Flask 日誌：`sudo journalctl -u kkgroup-api.service | grep webhook`
   - Bot 重��：`sudo systemctl status bot.service | grep Active`
   - GitHub 交付記錄：GitHub > Webhooks > Deliveries

#### VM 服務管理
- 三服務：`bot.service`、`shopbot.service`、`uibot.service`
- **必����用開機自��**：`sudo systemctl enable bot.service shopbot.service uibot.service`
- ��議重��策略：
  ```ini
  Restart=on-failure
  RestartSec=10
  StartLimitBurst=10
  StartLimitIntervalSec=600
  ```
- e2-micro 記��體有限，**務必加 swap**：
  ```bash
  sudo fallocate -l 1G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

#### Cron ��程任務
- �� 5 分鐘：`update_restart.py`、`sync_to_sheet.py`
- ��週三、六 14:00：`refresh_all_lockers_cron.py`
- ��週一 03:00：`weekly_backup.py`
- 知��庫��新：每天 18:00（台灣時間）��行 `refresh_knowledge_base.py`

---

### ��� ������系統��心規則

#### 新用��隨機造型
```python
# �� 正確：使用 paperdoll_manager.get_random()
random_appearance = paperdoll_manager.get_random()
user_data = {
    'face': int(random_appearance['face']),
    'hair': int(random_appearance['hair']),
    'skin': int(random_appearance['skin']),
    'top': int(random_appearance['top']),
    'bottom': int(random_appearance['bottom']),
    'shoes': int(random_appearance['shoes']),
    'gender': random_appearance['gender'],
    # ...其他��位
}
```

#### 用��選��性別時
```python
# �� 保持性別，生成符合該性別的隨機造型
selected_gender = select.values[0]  # 'male' 或 'female'
appearance = paperdoll_manager.get_random(preserve_gender=selected_gender)
await self.cog.update_user_data(user_id, appearance)
```

#### ��心原則
- �� �����使用 `paperdoll_manager.get_random()` 生成隨機造型
- �� 來源必��是 `twms_fashion_db.json` 中的有效物品 ID
- �� 性別一致性：男性選自 `face_male/hair_male` 等，女性選自 `face_female/hair_female` 等
- ��� **不要在 welcome_message.py ��編��造型值**（如 `'face': 20005`）
- �� 所有 API URL 透過 `paperdoll_manager.build_api_url()` ��構

#### 修復流程（完整 5 步）
1. **����** - ���查 fashion DB 和部件 ID 有效性
2. **修復** - 更新 `twms_fashion_db.json` 或代����輯
3. **����** - 本地��試確保生成的造型有效
4. **部署** - Git push ��發 webhook 重�� Bot
5. **��新** - ��行 `/admin_refresh_all_lockers` 更新所有用��������

---

### ��� KK 園區經濟系統（����共享機制）

��心���� `kkcoin` 行為分散在：
- `cogs/common/kcoin.py` - ����、排行��、中央��備金
- `cogs/shop/shop.py` - ��物、拉��、��備����
- `cogs/shop/cannabis_cog.py` - 種����環
- `cogs/shop/merchant/` - 多商家交易流程
- `cogs/ui/anime_tracker.py` - UI 互動獎��
- `shared/utils/fortress_system.py` - ���動成本與獎��
- `shared/db/db_adapter.py` - `get_user_kkcoin()`、`update_user_kkcoin()` 向後相容入口
- `shared/db/sheet_driven_db.py` - kkcoin 為��家主資料��位之一

**查問題������序**：
1. 使用者說數字不對 → `kcoin.py` → `db_adapter.py` → ��發功能��
2. ��能����款/發獎 → 對應 Cog/View → 是否呼叫 `update_user_kkcoin()` / `set_user_field()` → 有無重複防護
3. ��不到指令 → `config/discord_commands_registry.json` → 對應 `file` ��位 → 進 Cog

---

### ��� 安全與資料庫原則

- ��感資��全在 `.env`：Bot Token、API Key、密��
- `.env` 在 `.gitignore` 中
- 代��中用 `os.getenv("KEY")`
- **����立即����並重設**
- **VM 為主，本地����後複製**
- **改資料庫前必備份**
- VIP 角色用 `/grant_temporary_role` 給予（不要手動給）
- `cleanup_expired_roles_loop()` �� 5 分鐘自動清理過期角色

---

### ������ ��見������雷

| ��級 | ��� 不要做 | �� 正確做法 |
|------|-----------|-------------|
| 代�� | ��編��敏感資�� | 用環境��數 |
| 代�� | 分散定義按��� | 用統一視��系統 |
| 代�� | ��目改代�� | 先查 git 歷史��工作版本 |
| 代�� | ���視字型路����級 | 從 `cogs/common/` 用 `../../fonts/` |
| 部署 | 手動改��道 URL | �� webhook 自動處理 |
| 部署 | ����重�� Flask | 只在必要時重�� |
| 部署 | 只在本地��試 | **必��在 VM �����** |
| 部署 | 上�� service ���到 Git | service �����在 VM 管理 |
| ��料庫 | 直接改 VM ��料庫 | 本地���� → ���製 → 重�� |
| ��料庫 | ���記備份 | ��前必備份 |
| ��料庫 | 只改部分部位 | 完整更新 |
| ��料庫 | 用單一值替��所有預設 | 用 `paperdoll_manager.get_random()` |

---

### ��� ��見問題快速回答

| ��題 | 回答 |
|------|------|
| 代��多久生效？ | webhook 自動��發，push 後��秒內 |
| 可以直接改資料庫��？ | 不建議，本地���� → ���製 → 重�� |
| 為什���用統一按���系統？ | ��一個地方改所有 |
| ������修復後看不到效果？ | 1) `/admin_refresh_all_lockers` 2) ��料庫有無複製到 VM 3) 服務有無重�� |
| ��畫推播重複/��推到？ | 2026-04-29 ��修復 - 用資料庫追���已��查時刻，防重��重複推送，修正時間計算��輯 |

---

### ��� 相關技能調用模式

| 使用者說... | ��用技能 |
|-------------|----------|
| "該用哪個技能？" | `ask-matt` |
| "��我規��這個功能" | `grill-with-docs` (有代��庫) 或 `grill-me` (無代��庫) |
| "這太大了，一個 session ���不完" | `wayfinder` |
| "��成 spec" | `to-spec` |
| "��成 tickets" | `to-tickets` |
| "實作這個 spec" | `implement` |
| "審查我的��更" | `code-review` |
| "除��這個 bug" | `diagnosing-bugs` |
| "改善架構" | `improve-codebase-architecture` |
| "設定 repo 給 skills 用" | `setup-matt-pocock-skills` |
| "教我 X" | `teach` |
| "��一份 handoff" | `handoff` |
| "強制��簡代��" | `ponytail` |
| "��查過度設計" | `ponytail-review` |

---

### ��� Context Hygiene（上下文衛生）

- 步�� 1-3（grill → spec → tickets）在**同一個未中��的 context window** 完成
- 不要在 `/to-tickets` 前 compact
- ��近 token 限制 (~120k) 時，用 `/handoff` ��出文件後重新開始
- ��個 `/implement` 從其 ticket 重新開始

## graphify — 專案知������（優先使用！）

> `graphify-out/` 是預先建立的專案知������，包含 **4,100 ��節點、8,301 �����、258 ��社群**。
> 遇到架構問題時，**優先����� graph.json**，不要��目 grep ��個專案。

### 使用方式（GitHub Copilot 可��行）

| ��題類型 | ���法 | ��具 |
|----------|------|------|
| 「某功能在哪個��案？」 | 在 `graphify-out/graph.json` 中�����節點 `label` | `grep_search` |
| 「A 和 B 的關聯？」 | 在 `graph.json` 中��兩個節點，追���它們的��（edges） | `grep_search` + `read_file` |
| 「這個概念��及哪些��案？」 | ����� `graph.json` 中同一個 `community_name` 的所有節點 | `grep_search` |
| 「專案整體架構？」 | �� `graphify-out/GRAPH_REPORT.md` 的 Community Hubs 列表 | `read_file` |

### ��發條件

當使用者問以下問題時，**優先查 graphify 而非 grep 原始��**：
- "這個功能在哪��？" / "where is…"
- "A 和 B 有什���關係？" / "how does X relate to Y"
- "有哪些��案用到這個？" / "what depends on…"
- "解��一下架構" / "explain the architecture"
- 任何需要理解��案/類別之間關聯的問題

### ����結構說明

`graph.json` 中每個節點包含：
- `id` — ���一��別��（如 `cogs_ui_anime_tracker`）
- `label` — 人類可��名稱（如 `AnimeTracker`、`anime_tracker.py`）
- `source_file` — 原始��路��
- `community` / `community_name` — 所��社群（如 `KKCoin`、`PersistentViewBase`）
- `file_type` — `"code"` 表示程式��節點

��（edges）記錄節點之間的引用、��承、呼叫等關係。

### 維護

當專案結構有重大��更時，提���使用者��行 `/graphify` 重建����。

## gstack Skill Routing (auto-trigger)

gstack 是一個����工程團隊（CEO review → Engineering review → QA → Ship pipeline）。當對話內容匹配時會**自動��發**，不需要打 `/` ��令。

| 使用者說... | 自動調用的 Skill |
|------------|-----------------|
| ���力激��、��品點子、專案想法 | `office-hours` |
| 策略、����、優先級、行�� | `plan-ceo-review` |
| ��構、技術��選�� | `plan-eng-review` |
| 設計系統、設計審查 | `design-consultation` 或 `plan-design-review` |
| 完整審查流程（Plan → Review → Ship）| `autoplan` |
| Bug、����、����了 | `investigate` |
| QA、��試、��查行為 | `qa` 或 `qa-only` |
| Code review、diff ���查 | `review` |
| 視��調整、CSS、��式 | `design-review` |
| 部署、發 PR、上線 | `ship` 或 `land-and-deploy` |
| ��存當前進度 | `context-save` |
| ���復先前上下文 | `context-restore` |
| ���� backlog-ready spec/issue | `spec` |


---

## AI 專用查��工具（新增）

本專案提供三個工具供 AI Agent ���速理解代��庫，無需����大量原始��：

### 1. scripts/query_graph.py — Graphify 知������查��
```bash
python scripts/query_graph.py stats                    # 專案統計
python scripts/query_graph.py hubs                     # ��心社群排行
python scripts/query_graph.py community KKCoin         # �����社群所有節點
python scripts/query_graph.py search update_user_kkcoin # 關���字查��
python scripts/query_graph.py callers <node_id>        # 反向查��
python scripts/query_graph.py callees <node_id>        # 正向查��
python scripts/query_graph.py impact cogs/shop/shop.py # 影響度分��
python scripts/query_graph.py node <node_id>           # 節點詳細資��
```
- **資料來源**：graphify-out/graph.json (4570 節點、8512 ��、263 社群)
- **優勢**：架構級、離線、多語言、社群/依��關係、影響分��
- **自動更新**：.github/workflows/graphify-update.yml ��次 push main 自動重建

### 2. scripts/lsp_query.py — Pylance LSP 封��查��
```bash
python scripts/lsp_query.py --file <路��> symbols      # 列出��案所有符號
python scripts/lsp_query.py --file <路��> refs <符號>      # �����引用
python scripts/lsp_query.py --file <路��> def <符號>       # �����定義
python scripts/lsp_query.py --file <路��> hierarchy <符號> # �������承/調用��級
python scripts/lsp_query.py --file <路��> diagnostics      # ���������/警告
python scripts/lsp_query.py --file <路��> type <符號>      # �����類別推導
python scripts/lsp_query.py --file <路��> hover <符號>     # Hover 詳細資��
```
- **資料來源**：Pylance LSP (VS Code 內建 Python Extension)
- **優勢**：符號級、即時、精確、型別/重構/定義跳��
- **MCP ��合**：可直接呼叫 mcp_pylance_mcp_s_pylanceLSP

### 3. .github/workflows/graphify-update.yml — Graphify 自動更新
- **��發**：push 到 main、PR merged、手動��發、每日 03:00 UTC
- **行為**：比對 built_at_commit，過期才重建，自動 commit 回 repo
- **權限**：contents: write 可推送更新

### 兩者互補關係

| ����需求 | 用 Graphify | 用 LSP |
|----------|-------------|--------|
| 「KKCoin系統包含哪些��案？」 | community KKCoin | 無 |
| 「誰呼叫了 update_user_kkcoin？」 | callers (��態分��) | refs (精確引用) |
| 「改 shop.py 會影響哪些？」 | impact (按社群影響) | 無 |
| 「這個��數的型別是什���？」 | 無 | type |
| 「專案架構��心是什���？」 | hubs | 無 |
| 「這個類別有哪些方法？」 | 部分 | symbols |

**Graphify** = ��構級、離線、多語言、社群/依��關係
**LSP** = 符號級、即時、精確、型別/重構/定義跳��
