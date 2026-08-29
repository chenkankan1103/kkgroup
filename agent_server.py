#!/usr/bin/env python3
"""
KK群組 - Agent Server (FastAPI)
================================
獨立運行的 Agent 執行服務，透過 HTTP API 接收任務。

特性：
- 非阻塞任務提交（立即回傳 task_id）
- 背景執行 Agent Loop
- 進度查詢（長輪詢 / 簡單輪詢）
- Webhook 回調完成通知
- 任務管理：列表、狀態、取消、暫停/恢復
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ─── 環境設定 ─────────────────────────────────────────────────────
os.environ.setdefault("CLAUDE_WORK_DIR", "/home/e193752468/kkgroup")
os.environ.setdefault(
    "AGENT_TASK_DB", "/home/e193752468/kkgroup/shared/db/data/agent_tasks.db"
)

# 記錄設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── 延遲導入（降低啟動記憶體） ──────────────────────────────────
_agent_module = None


def get_agent_module():
    global _agent_module
    if _agent_module is None:
        from shared.agent import (ClaudeCodeAgent, TaskStatus, create_task,
                                  get_task, get_task_stats, list_tasks,
                                  update_task)

        _agent_module = {
            "ClaudeCodeAgent": ClaudeCodeAgent,
            "create_task": create_task,
            "get_task": get_task,
            "list_tasks": list_tasks,
            "update_task": update_task,
            "get_task_stats": get_task_stats,
            "TaskStatus": TaskStatus,
        }
    return _agent_module


# ─── 全域狀態 ─────────────────────────────────────────────────────
_running_tasks: dict[str, "ClaudeCodeAgent"] = {}


# ─── Pydantic Models ──────────────────────────────────────────────
class TaskRequest(BaseModel):
    task_type: str = Field(default="code_agent", description="任務類型")
    payload: dict = Field(default_factory=dict, description="任務參數")
    callback_url: str | None = Field(None, description="完成後回調 URL")


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str = "Task accepted"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    task_type: str
    payload: dict
    result: Any | None = None
    error: str | None = None
    progress: str | None = None
    user_id: int | None = None
    channel_id: int | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None


class CancelRequest(BaseModel):
    force: bool = False


# ─── 背景任務執行器 ───────────────────────────────────────────────
async def run_agent_task(
    task_id: str,
    user_id: int,
    channel_id: int,
    instruction: str,
    callback_url: str | None,
):
    """背景執行 Agent 任務"""
    mod = get_agent_module()
    ClaudeCodeAgent = mod["ClaudeCodeAgent"]
    update_task = mod["update_task"]

    # 進度緩衝（供長輪詢讀取）
    progress_buffer: list[str] = []

    async def progress_callback(msg: str):
        progress_buffer.append(msg)
        # 即時更新資料庫（供輪詢 API 讀取）
        await update_task(task_id, progress=msg)

    agent = ClaudeCodeAgent(
        task_id=task_id,
        user_id=user_id,
        channel_id=channel_id,
        progress_callback=progress_callback,
    )
    _running_tasks[task_id] = agent

    try:
        result = await agent.run(instruction)
        await update_task(
            task_id,
            status=agent.status,
            result={"output": result} if not isinstance(result, dict) else result,
            completed_at=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.exception(f"Task {task_id} failed")
        await update_task(
            task_id,
            status="failed",
            error=str(e),
            completed_at=datetime.utcnow().isoformat(),
        )
        result = {"error": str(e)}
    finally:
        _running_tasks.pop(task_id, None)
        await agent.close()

    # Webhook 回調
    if callback_url:
        await _send_callback(callback_url, task_id, result)


async def _send_callback(url: str, task_id: str, result: Any):
    """發送 Webhook 回調（帶重試）"""
    import httpx

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    url,
                    json={
                        "task_id": task_id,
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            logger.info(f"Callback sent for {task_id}")
            return
        except Exception as e:
            logger.warning(f"Callback attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2**attempt)
    logger.error(f"Callback failed for {task_id} after 3 attempts")


# ─── FastAPI App ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Agent Server starting...")
    # 預熱：初始化資料庫
    get_agent_module()["create_task"]("warmup", "warmup", {})
    yield
    logger.info("🛑 Agent Server shutting down...")
    # 清理運行中任務
    for task_id, agent in _running_tasks.items():
        agent.cancel()
    await asyncio.sleep(1)


app = FastAPI(
    title="KKGroup Agent Server",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── API Routes ───────────────────────────────────────────────────


@app.post("/agent/task", response_model=TaskResponse)
async def submit_task(request: TaskRequest, background: BackgroundTasks):
    """提交新任務（非阻塞，立即回傳 task_id）"""
    task_id = str(uuid.uuid4())
    task_type = request.task_type

    # 從 payload 提取必要參數
    payload = request.payload
    instruction = payload.get("instruction") or payload.get("prompt") or ""
    user_id = payload.get("user_id", 0)
    channel_id = payload.get("channel_id", 0)

    if not instruction:
        raise HTTPException(400, "Missing 'instruction' or 'prompt' in payload")

    # 建立任務記錄
    await get_agent_module()["create_task"](
        task_id,
        task_type,
        {
            **payload,
            "instruction": instruction,
            "user_id": user_id,
            "channel_id": channel_id,
        },
    )

    # 背景執行
    background.add_task(
        run_agent_task, task_id, user_id, channel_id, instruction, request.callback_url
    )

    return TaskResponse(task_id=task_id, status="accepted")


@app.get("/agent/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """查詢任務狀態與結果"""
    task = await get_agent_module()["get_task"](task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return TaskStatusResponse(**task)


@app.get("/agent/task/{task_id}/progress")
async def get_task_progress(
    task_id: str, wait: bool = Query(False, description="長輪詢等待更新")
):
    """取得任務進度（支援長輪詢）"""
    task = await get_agent_module()["get_task"](task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if wait and task.get("status") in ("pending", "running", "paused"):
        # 簡單長輪詢：等待進度更新（最多 30 秒）
        for _ in range(30):
            await asyncio.sleep(1)
            fresh = await get_agent_module()["get_task"](task_id)
            if fresh and fresh.get("progress") != task.get("progress"):
                return {
                    "task_id": task_id,
                    "progress": fresh.get("progress"),
                    "status": fresh.get("status"),
                }
    return {
        "task_id": task_id,
        "progress": task.get("progress"),
        "status": task.get("status"),
    }


@app.post("/agent/task/{task_id}/cancel")
async def cancel_task(task_id: str, request: CancelRequest):
    """取消任務"""
    agent = _running_tasks.get(task_id)
    if not agent:
        task = await get_agent_module()["get_task"](task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        if task["status"] in ("completed", "failed", "cancelled"):
            return {
                "task_id": task_id,
                "status": task["status"],
                "message": "Task already finished",
            }
        await get_agent_module()["update_task"](task_id, status="cancelled")
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Task marked as cancelled",
        }

    if request.force:
        agent.cancel()
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Task force cancelled",
        }
    else:
        agent.pause()
        return {
            "task_id": task_id,
            "status": "paused",
            "message": "Task paused (use force=true to cancel)",
        }


@app.post("/agent/task/{task_id}/resume")
async def resume_task(task_id: str):
    """恢復暫停的任務"""
    agent = _running_tasks.get(task_id)
    if agent:
        agent.resume()
        return {"task_id": task_id, "status": "running", "message": "Task resumed"}

    task = await get_agent_module()["get_task"](task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["status"] != "paused":
        return {
            "task_id": task_id,
            "status": task["status"],
            "message": "Task not paused",
        }
    # 重新啟動背景任務（簡化：實際需重建 agent）
    return {
        "task_id": task_id,
        "status": "paused",
        "message": "Resume not implemented for paused tasks",
    }


@app.get("/agent/tasks")
async def list_tasks(status: str | None = None, limit: int = 50):
    """列出任務"""
    tasks = await get_agent_module()["list_tasks"](status, limit)
    return {"tasks": tasks, "count": len(tasks)}


@app.get("/agent/stats")
async def get_stats():
    """統計資訊"""
    stats = await get_agent_module()["get_task_stats"]()
    return {"stats": stats, "running_count": len(_running_tasks)}


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {
        "status": "healthy",
        "running_tasks": len(_running_tasks),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─── 啟動入口 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_SERVER_PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
