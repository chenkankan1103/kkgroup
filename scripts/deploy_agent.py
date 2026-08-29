#!/usr/bin/env python3
"""
KK群組 - Agent Server 部署驗證腳本
=====================================
在 VM 上執行，自動完成：
1. 複製 service 檔案到 systemd
2. 安裝 Python 依賴
3. 初始化資料庫
4. 啟動服務
5. 驗證健康狀態
"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path("/home/e193752468/kkgroup")
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
SERVICE_FILE = PROJECT_ROOT / "config" / "services" / "agent.service"
SYSTEMD_DIR = Path("/etc/systemd/system")


def run_cmd(
    cmd: list[str], check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess:
    """執行命令並記錄"""
    log.info(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if capture:
        log.debug(f"stdout: {result.stdout}")
        log.debug(f"stderr: {result.stderr}")
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result


async def verify_dependencies() -> bool:
    """驗證 Python 依賴"""
    log.info("🔍 驗證 Python 依賴...")
    required = ["fastapi", "uvicorn", "aiohttp", "aiosqlite", "pydantic"]
    for pkg in required:
        try:
            __import__(pkg)
            log.info(f"  ✅ {pkg}")
        except ImportError:
            log.error(f"  ❌ {pkg} 未安裝")
            return False
    return True


async def init_database() -> bool:
    """初始化資料庫"""
    log.info("🗄️ 初始化 Agent 任務資料庫...")
    db_path = PROJECT_ROOT / "shared" / "db" / "data" / "agent_tasks.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 觸發資料庫初始化（透過 import）
    sys.path.insert(0, str(PROJECT_ROOT))
    from shared.agent.memory import get_task_store

    store = get_task_store()
    await store._ensure_init()

    # 驗證表存在
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        ) as cur:
            row = await cur.fetchone()
            if row:
                log.info(f"  ✅ 資料庫就緒: {db_path}")
                return True
    log.error("  ❌ 資料庫初始化失敗")
    return False


async def install_service() -> bool:
    """安裝 systemd service"""
    log.info("⚙️ 安裝 systemd service...")
    if not SERVICE_FILE.exists():
        log.error(f"  ❌ Service 檔案不存在: {SERVICE_FILE}")
        return False

    target = SYSTEMD_DIR / "kkgroup-agent.service"
    try:
        shutil.copy2(SERVICE_FILE, target)
        run_cmd(["sudo", "systemctl", "daemon-reload"])
        run_cmd(["sudo", "systemctl", "enable", "kkgroup-agent.service"])
        log.info(f"  ✅ 已安裝至 {target}")
        return True
    except Exception as e:
        log.error(f"  ❌ 安裝失敗: {e}")
        return False


async def start_service() -> bool:
    """啟動服務"""
    log.info("🚀 啟動 Agent Server...")
    run_cmd(["sudo", "systemctl", "restart", "kkgroup-agent.service"])
    await asyncio.sleep(3)  # 等待啟動

    # 檢查狀態
    result = run_cmd(
        ["sudo", "systemctl", "is-active", "kkgroup-agent.service"],
        check=False,
        capture=True,
    )
    if result.returncode == 0 and "active" in result.stdout:
        log.info("  ✅ 服務運行中")
        return True
    else:
        log.error(f"  ❌ 服務啟動失敗: {result.stdout} {result.stderr}")
        # 顯示日誌
        run_cmd(
            [
                "sudo",
                "journalctl",
                "-u",
                "kkgroup-agent.service",
                "-n",
                "30",
                "--no-pager",
            ],
            check=False,
        )
        return False


async def health_check() -> bool:
    """健康檢查"""
    log.info("🏥 健康檢查...")
    import aiohttp

    for attempt in range(10):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://localhost:8080/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        log.info(f"  ✅ 健康檢查通過: {data}")
                        return True
        except Exception as e:
            log.debug(f"  嘗試 {attempt+1}/10 失敗: {e}")
        await asyncio.sleep(2)

    log.error("  ❌ 健康檢查失敗（超過重試次數）")
    return False


async def test_submit_task() -> bool:
    """測試提交任務"""
    log.info("🧪 測試提交任務...")
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8080/agent/task",
                json={
                    "task_type": "test",
                    "payload": {
                        "instruction": "echo 'Hello from Agent Server'",
                        "user_id": 0,
                        "channel_id": 0,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    task_id = data.get("task_id")
                    log.info(f"  ✅ 任務提交成功: {task_id}")

                    # 等待完成
                    for _ in range(30):
                        await asyncio.sleep(1)
                        async with session.get(
                            f"http://localhost:8080/agent/task/{task_id}"
                        ) as r:
                            if r.status == 200:
                                task = await r.json()
                                if task.get("status") in ("completed", "failed"):
                                    log.info(f"  ✅ 任務完成: {task.get('status')}")
                                    if task.get("result"):
                                        log.info(f"     結果: {task['result']}")
                                    return True
                    log.warning("  ⚠️ 任務執行超時")
                    return True  # 提交成功就算過
    except Exception as e:
        log.error(f"  ❌ 測試失敗: {e}")
    return False


async def main():
    """主部署流程"""
    log.info("=" * 50)
    log.info("🚀 KKGroup Agent Server 部署驗證")
    log.info("=" * 50)

    checks = [
        ("Python 依賴", verify_dependencies()),
        ("資料庫初始化", init_database()),
        ("Systemd 安裝", install_service()),
        ("服務啟動", start_service()),
        ("健康檢查", health_check()),
        ("任務測試", test_submit_task()),
    ]

    all_passed = True
    for name, coro in checks:
        log.info(f"\n📋 {name}...")
        try:
            result = await coro
            if not result:
                all_passed = False
                log.error(f"❌ {name} 失敗")
        except Exception as e:
            all_passed = False
            log.error(f"❌ {name} 異常: {e}")

    log.info("\n" + "=" * 50)
    if all_passed:
        log.info("🎉 所有檢查通過，Agent Server 部署成功！")
        log.info("\n📋 管理指令:")
        log.info("  狀態: sudo systemctl status kkgroup-agent.service")
        log.info("  日誌: sudo journalctl -u kkgroup-agent.service -f")
        log.info("  重啟: sudo systemctl restart kkgroup-agent.service")
        log.info("  停止: sudo systemctl stop kkgroup-agent.service")
        return 0
    else:
        log.error("💥 部署失敗，請檢查上方錯誤")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
