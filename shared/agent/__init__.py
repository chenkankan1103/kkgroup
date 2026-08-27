"""
KK群組 - Agent 核心套件
======================
統一匯出介面，供外部（Bot Adapter、FastAPI Server）使用。
"""

from .agent_core import (
    ClaudeCodeAgent,
    NvidiaNimClient,
    ToolExecutor,
    TaskStore,
    TaskStatus,
    ProgressCallback,
    TOOLS,
    SYSTEM_PROMPT,
)
from .tools import ToolImpl, create_tool_impl, secure_path
from .memory import (
    SQLiteTaskStore,
    get_task_store,
    create_task,
    update_task,
    get_task,
    list_tasks,
    delete_old_tasks,
    get_task_stats,
)

__all__ = [
    # Core
    "ClaudeCodeAgent",
    "NvidiaNimClient",
    "ToolExecutor",
    "TaskStore",
    "TaskStatus",
    "ProgressCallback",
    "TOOLS",
    "SYSTEM_PROMPT",
    # Tools
    "ToolImpl",
    "create_tool_impl",
    "secure_path",
    # Memory
    "SQLiteTaskStore",
    "get_task_store",
    "create_task",
    "update_task",
    "get_task",
    "list_tasks",
    "delete_old_tasks",
    "get_task_stats",
]