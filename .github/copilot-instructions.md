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

## Discord.py 2.0 Rules

- Use `discord.ext.commands.Bot` with `intents=discord.Intents.all()`
- Slash commands via `@bot.tree.command()` or `@app_commands.command()`
- Persistent views: inherit from `PersistentViewBase` in `shared/utils/view_registry.py`
- Button callbacks use `interaction.response.defer()` then `interaction.followup.send()`
- Ephemeral responses for user-specific feedback

## Async Best Practices

- Use `asyncio.gather()` for parallel operations
- Avoid `asyncio.sleep()` in hot paths
- Use `async with` for resource management
- Handle `asyncio.CancelledError` in long-running tasks

## Database (SQLite / user_data.db)

- Use parameterized queries: `cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`
- Connection pooling via `sqlite3.connect()` with `check_same_thread=False`
- Transactions: `conn.execute("BEGIN")` / `conn.commit()` / `conn.rollback()`

## GCP VM Deployment

- SSH via IAP: `gcloud compute ssh <user>@<instance> --zone <zone> --tunnel-through-iap`
- Services: `bot.service`, `shopbot.service`, `uibot.service`
- Logs: `sudo journalctl -u <service> -n 100 --no-pager`
- Restart: `sudo systemctl restart <service>`

## Git & Deployment Workflow

1. Commit & push to GitHub
2. On VM: `git pull`
3. `sudo systemctl restart <service>`
4. Verify logs: `sudo journalctl -u <service> -f`

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