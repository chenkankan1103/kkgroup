"""
KK群組 - 結構化日誌工具
========================
統一 JSON Lines 格式輸出，支援 journalctl 解析、Agent 掃描。

特性：
- JSON Lines 格式（每行一個獨立 JSON 物件）
- 自動注入 trace_id / span_id（支援分散式追蹤）
- 標準欄位：ts, level, event, service, trace_id, span_id
- 相容 Python logging 模組
- 零依賴、高效能
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

# ─── Context Variables（支援 async/多執行緒） ─────────────────────────
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id_var: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
_service_name_var: ContextVar[str] = ContextVar("service_name", default="kkgroup-bot")


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """設定或生成 trace_id"""
    if trace_id is None:
        trace_id = uuid.uuid4().hex[:16]
    _trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> Optional[str]:
    return _trace_id_var.get()


def set_span_id(span_id: Optional[str] = None) -> str:
    if span_id is None:
        span_id = uuid.uuid4().hex[:8]
    _span_id_var.set(span_id)
    return span_id


def get_span_id() -> Optional[str]:
    return _span_id_var.get()


def set_service_name(name: str):
    _service_name_var.set(name)


def get_service_name() -> str:
    return _service_name_var.get()


# ─── 結構化 Logger ──────────────────────────────────────────────────
class StructuredLogger:
    """
    結構化 Logger，輸出 JSON Lines 到 stdout/stderr。
    Systemd/journalctl 會自動捕獲。
    """

    def __init__(self, name: str, level: int = logging.INFO):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = False  # 不重複傳給 root logger

        # 確保只有一個 handler
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(message)s")
            )  # 只輸出 message（我們自己組 JSON）
            handler.setLevel(level)
            self.logger.addHandler(handler)

    def _log(self, level: str, event: str, **fields: Any) -> None:
        """核心記錄方法"""
        # 基礎欄位
        record: Dict[str, Any] = {
            "ts": self._utc_now(),
            "level": level,
            "event": event,
            "service": get_service_name(),
            "logger": self.name,
        }

        # Trace/Span ID
        trace_id = get_trace_id()
        span_id = get_span_id()
        if trace_id:
            record["trace_id"] = trace_id
        if span_id:
            record["span_id"] = span_id

        # 進程/執行緒資訊（除錯用）
        record["pid"] = os.getpid()
        record["thread"] = threading.current_thread().ident

        # 使用者自訂欄位
        record.update(fields)

        # 輸出 JSON Lines
        try:
            self.logger.info(
                json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            )
        except Exception as e:
            # 最後手段：避免日誌本身出錯導致程式崩潰
            fallback = {
                "ts": self._utc_now(),
                "level": "error",
                "event": "log_serialization_failed",
                "error": str(e),
                "original_event": event,
                "fields": {k: str(v) for k, v in fields.items()},
            }
            self.logger.info(json.dumps(fallback, ensure_ascii=False))

    def _utc_now(self) -> str:
        """ISO 8601 UTC 時間戳"""
        return (
            time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            + f".{int(time.time() * 1000000) % 1000000:06d}Z"
        )

    # 便利方法
    def debug(self, event: str, **fields):
        self._log("debug", event, **fields)

    def info(self, event: str, **fields):
        self._log("info", event, **fields)

    def warning(self, event: str, **fields):
        self._log("warning", event, **fields)

    def error(self, event: str, **fields):
        self._log("error", event, **fields)

    def exception(self, event: str, exc: Exception, **fields):
        """記錄例外（自動帶入型別與訊息）"""
        self._log(
            "error", event, exc_type=type(exc).__name__, exc_msg=str(exc), **fields
        )

    # 兼容 logging.Logger 介面
    def log(self, level: int, msg: str, *args, **kwargs):
        level_name = logging.getLevelName(level).lower()
        self._log(level_name, msg, **kwargs)

    def isEnabledFor(self, level: int) -> bool:
        return self.logger.isEnabledFor(level)


# ─── 工廠函數 ──────────────────────────────────────────────────────
_loggers: Dict[str, StructuredLogger] = {}


def get_structured_logger(name: str, level: int = logging.INFO) -> StructuredLogger:
    """取得或建立結構化 Logger（單例）"""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name, level)
    return _loggers[name]


# ─── 上下文管理器：自動管理 Trace/Span ──────────────────────────────
class TraceContext:
    """Context Manager：自動設定/清理 trace_id, span_id"""

    def __init__(
        self,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        service: Optional[str] = None,
    ):
        self.trace_id = trace_id
        self.span_id = span_id
        self.service = service
        self._old_trace = None
        self._old_span = None
        self._old_service = None

    def __enter__(self):
        self._old_trace = _trace_id_var.get()
        self._old_span = _span_id_var.get()
        self._old_service = _service_name_var.get()

        if self.trace_id is not None:
            set_trace_id(self.trace_id)
        if self.span_id is not None:
            set_span_id(self.span_id)
        if self.service is not None:
            set_service_name(self.service)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._old_trace is not None:
            _trace_id_var.set(self._old_trace)
        else:
            _trace_id_var.set(None)
        if self._old_span is not None:
            _span_id_var.set(self._old_span)
        else:
            _span_id_var.set(None)
        if self._old_service is not None:
            _service_name_var.set(self._old_service)


# ─── 裝飾器：自動帶入 trace_id ─────────────────────────────────────
def with_trace(func):
    """裝飾器：為函數調用自動生成 trace_id"""
    import functools

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        with TraceContext():
            return func(*args, **kwargs)

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        with TraceContext():
            return await func(*args, **kwargs)

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


# 需要 import asyncio
import asyncio


# ───Journalctl 查詢輔助 ────────────────────────────────────────────
def parse_journalctl_json(line: str) -> Optional[Dict]:
    """解析 journalctl -o json 的單行輸出"""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def extract_error_fingerprint(message: str, length: int = 80) -> str:
    """提取錯誤指紋（用於去重聚類）"""
    # 移除動態部分（數字、路徑、UUID、時間戳）
    import re

    fp = message
    fp = re.sub(r"\b\d+\b", "<NUM>", fp)
    fp = re.sub(r"/[^/\s]+(/\w+)*", "<PATH>", fp)
    fp = re.sub(r"[0-9a-f]{8,}", "<HASH>", fp)
    fp = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TIME>", fp)
    return fp[:length]


# ─── 測試 ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 設定服務名稱
    set_service_name("test-service")

    log = get_structured_logger("test")

    # 基本用法
    log.info("service_started", version="1.0.0", port=8080)
    log.warning("high_memory_usage", current_mb=450, limit_mb=512)

    # 帶 trace_id
    with TraceContext(trace_id="abc123", service="api"):
        log.info("request_received", method="POST", path="/agent/task")
        log.error(
            "processing_failed", exc_type="TimeoutError", exc_msg="Request timeout"
        )

    # Exception 記錄
    try:
        raise ValueError("測試錯誤")
    except Exception as e:
        log.exception("operation_failed", exc=e, user_id=12345)
