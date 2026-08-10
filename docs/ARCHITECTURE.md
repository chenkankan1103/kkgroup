# AI Agent 可靠開發系統 - 架構設計文檔

## 1. 系統概覽

```
┌─────────────────────────────────────────────────────────────────┐
│                        用戶 / Discord                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   Gateway層     │  ← Discord Bot / Webhook / API
                    │  (接入/認證/限流) │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼───────┐    ┌───────▼───────┐    ┌───────▼───────┐
│  Agent 核心   │    │  排程/任務    │    │  知識/記憶    │
│  (推理/規劃)   │    │  (Cron/觸發)  │    │  (RAG/向量)   │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   工具執行層     │  ← Function Calling / MCP
                    │ (工具註冊/執行/審計)│
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼───────┐    ┌───────▼───────┐    ┌───────▼───────┐
│  資料存儲層    │    │  外部服務層    │    │  觀測/審計層   │
│ (PostgreSQL/  │    │ (API/爬蟲/    │    │ (Logging/     │
│  Redis/SQLite)│    │  LLM/MCP)     │    │  Metrics/Tracing)│
└───────────────┘    └───────────────┘    └───────────────┘
```

## 2. 模組邊界定義

### 2.1 核心模組

| 模組 | 職責 | 對外介面 | 依賴 |
|------|------|----------|------|
| `core/agent` | Agent 循環、推理、規劃 | `run(prompt) -> Response` | `tools`, `memory`, `llm` |
| `core/tools` | 工具註冊、執行、權限、審計 | `execute(name, args) -> Result` | `core/agent` |
| `core/memory` | 短期/長期記憶、向量檢索 | `store(key, value)`, `search(query)` | `db`, `embeddings` |
| `core/llm` | LLM 調用、重試、降級、成本控制 | `complete(messages) -> Response` | `openai`, `anthropic`, `local` |

### 2.2 業務模組

| 模組 | 職責 | 主要類/函數 |
|------|------|-------------|
| `cogs/ui/push_core` | 動漫推送核心邏輯 | `AnimePushCore.execute_push()` |
| `cogs/ui/schedule_tracker` | 排程追蹤 | `AnimeScheduleTracker.check_schedule()` |
| `cogs/ui/ranking_stats` | 排行榜統計 | `AnimeRankingStats.generate()` |
| `cogs/common/ai_tools` | AI 可調用工具箱 | `@register_tool` 裝飾器 |

### 2.3 基礎設施模組

| 模組 | 職責 | 關鍵文件 |
|------|------|----------|
| `infra/logging` | 結構化日誌、Trace、Metrics | `logger.py`, `tracer.py` |
| `infra/config` | 配置管理、環境變數、熱重載 | `settings.py` |
| `infra/db` | 數據庫連接、Session、遷移 | `database.py`, `models/` |
| `infra/errors` | 錯誤分類、重試策略、熔斷 | `exceptions.py`, `retry.py` |

## 3. 數據流設計

### 3.1 推送流程 (Push Flow)

```
用戶指令 / 排程觸發
       │
       ▼
┌──────────────────┐
│  Trace 開始       │  trace_id = uuid4()
│  Context 注入     │  guild_id, user_id, command
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  權限檢查         │  @require_leader / @require_permission
│  參數驗證         │  Pydantic Schema
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  核心業務邏輯      │  AnimePushCore.execute_push()
│  - 獲取新番數據    │  → fetch_new_anime()
│  - 去重檢查       │  → db.is_notified()
│  - 生成 Embed     │  → generate_embed()
│  - 發送 Discord   │  → channel.send()
│  - 記錄發送狀態   │  → db.save_message_info()
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Metrics 記錄     │  duration, success_count, error_count
│  Trace 結束       │
└──────────────────┘
```

### 3.2 Agent 工具調用流程

```
用戶訊息
    │
    ▼
┌──────────────────┐
│  LLM 判斷需調用工具  │  tool_calls = response.tool_calls
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  工具註冊表查找    │  tool = registry.get(name)
│  權限驗證         │  tool.check_permission(caller_id)
│  參數 Schema 驗證  │  tool.schema.validate(args)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  執行工具 (含重試)  │  result = await tool.execute(args)
│  記錄審計日誌      │  audit_log(action, args, result)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  結果注入 LLM 上下文 │  messages.append(ToolMessage(result))
│  繼續推理          │
└──────────────────┘
```

## 4. 契約定義 (Schema)

### 4.1 工具調用契約

```python
# 每個工具必須定義
TOOL_CONTRACT = {
    "name": "fetch_anime_data",
    "description": "從 API 獲取動漫資訊",
    "parameters": {
        "type": "object",
        "properties": {
            "anime_id": {"type": "integer", "description": "動漫 ID"},
            "include_episodes": {"type": "boolean", "default": False}
        },
        "required": ["anime_id"]
    },
    "returns": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "episodes": {"type": "array", "items": {"type": "object"}},
            "status": {"type": "string", "enum": ["airing", "finished", "upcoming"]}
        }
    },
    "permissions": ["user", "admin"],
    "idempotent": True,
    "timeout_seconds": 30,
    "retry_policy": {"max_attempts": 3, "backoff": "exponential"}
}
```

### 4.2 數據庫模型契約

```python
# 核心表結構定義
MODEL_CONTRACTS = {
    "anime_notifications": {
        "columns": {
            "id": "BIGSERIAL PRIMARY KEY",
            "guild_id": "BIGINT NOT NULL",
            "channel_id": "BIGINT NOT NULL",
            "anime_sn": "INTEGER NOT NULL",
            "episode_sn": "INTEGER",
            "message_id": "BIGINT",
            "status": "VARCHAR(20) DEFAULT 'pending'",  # pending/sent/failed
            "created_at": "TIMESTAMP DEFAULT NOW()",
            "sent_at": "TIMESTAMP"
        },
        "indexes": ["guild_id", "anime_sn", "status"]
    }
}
```

## 5. 觀測性設計

### 5.1 Trace 結構

```
Trace (trace_id: uuid)
├── Span: agent.think (推理)
│   ├── Event: llm.request
│   ├── Event: llm.response
│   └── Event: tool.decision
├── Span: tool.execute (工具執行)
│   ├── Event: tool.start
│   ├── Event: db.query
│   ├── Event: api.call
│   └── Event: tool.end
└── Span: agent.respond (回應生成)
    ├── Event: llm.request
    └── Event: response.sent
```

### 5.2 關鍵 Metrics

| Metric | Type | Labels | 用途 |
|--------|------|--------|------|
| `agent_request_duration_ms` | Histogram | agent, operation | 性能監控 |
| `tool_execution_duration_ms` | Histogram | tool, status | 工具性能 |
| `tool_call_total` | Counter | tool, status | 調用統計 |
| `db_query_duration_ms` | Histogram | query_type | DB 性能 |
| `llm_token_usage` | Counter | model, type (prompt/completion) | 成本控制 |
| `error_total` | Counter | error_type, module | 錯誤告警 |

## 6. 部署架構

```
┌─────────────┐     ┌─────────────┐
│   Discord   │     │    Web      │
│   Gateway   │     │   Dashboard │
└──────┬──────┘     └──────┬──────┘
       │                   │
       ▼                   ▼
┌─────────────────────────────────┐
│          Load Balancer           │  (Nginx / Cloud Run)
└──────────────┬──────────────────┘
               │
     ┌─────────┼─────────┐
     ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│ Bot #1 │ │ Bot #2 │ │ Bot #N │  (水平擴展，共享 Redis/DB)
└────────┘ └────────┘ └────────┘
     │         │         │
     └─────────┼─────────┘
               ▼
      ┌────────────────┐
      │  PostgreSQL    │  ← 主數據庫
      │  (Primary)     │
      └────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌─────────────┐   ┌─────────────┐
│   Redis     │   │  Vector DB  │
│  (Cache/    │   │  (Memory/   │
│   PubSub)   │   │   RAG)      │
└─────────────┘   └─────────────┘
```

## 7. 擴展點設計

### 7.1 新增工具流程

1. 在 `cogs/common/ai_tools/` 創建 `new_tool.py`
2. 使用 `@register_tool` 裝飾器定義 Schema 和權限
3. 實現 `async def execute(args, context) -> ToolResult`
4. 添加單元測試 `tests/unit/tools/test_new_tool.py`
5. 重啟 Bot 自動發現

### 7.2 新增 Agent 能力

1. 定義 Prompt Template (`prompts/agent_name.md`)
2. 配置工具白名單 (`config/agent_tools.yaml`)
3. 實現專用 Handler (`core/agent/handlers/agent_name.py`)
4. 註冊到 Agent Factory

---

**版本**: 1.0.0
**最後更新**: 2026-07-15
**負責人**: Architecture Team
