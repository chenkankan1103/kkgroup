#!/usr/bin/env python3
"""
Bot 效能分析腳本
用途：測量啟動時間、記憶體基線、模擬負載下的 CPU/記憶體分佈

使用方式：
    # 本地測試（需安裝 scalene, py-spy, memory-profiler）
    pip install scalene py-spy memory-profiler
    python scripts/profile_bot.py --mode scalene --duration 30
    python scripts/profile_bot.py --mode pyspy --duration 30
    python scripts/profile_bot.py --mode memory --duration 60
"""

import argparse
import asyncio
import sys
import time
import subprocess
from pathlib import Path

# 將專案根目錄加入路徑
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def simulate_load(bot, duration_sec: int, qps: float = 2.0):
    """模擬 Discord 訊息負載"""
    import discord
    from unittest.mock import AsyncMock, MagicMock

    test_messages = [
        "@bot 幫我查 KK幣餘額",
        "@bot 搜尋 python asyncio 教學",
        "@bot 爬取 https://example.com",
        "@bot 我的配裝怎麼樣",
        "@bot bot 狀態正常嗎",
        "@bot 你好 干部",
        "@bot 查詢排行榜前 10 名",
        "@bot 幫我找 discord.py 文檔",
    ]

    interval = 1.0 / qps
    end_time = time.time() + duration_sec
    msg_count = 0

    print(f"🚀 開始模擬負載：{qps} QPS，持續 {duration_sec} 秒")

    while time.time() < end_time:
        # 建立模擬訊息
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.User)
        mock_message.author.id = 123456789 + (msg_count % 10)
        mock_message.author.bot = False
        mock_message.content = test_messages[msg_count % len(test_messages)]
        mock_message.clean_content = mock_message.content
        mock_message.channel = MagicMock(spec=discord.TextChannel)
        mock_message.channel.typing = MagicMock(return_value=AsyncMock().__aenter__)
        mock_message.reply = AsyncMock()
        mock_message.mentions = [MagicMock()]
        mock_message.mentions[0].id = bot.user.id if hasattr(bot, "user") else 999999
        mock_message.guild = None

        # 觸發 on_message
        try:
            await bot.on_message(mock_message)
            msg_count += 1
        except Exception as e:
            print(f"⚠️ 訊息處理錯誤: {e}")

        await asyncio.sleep(interval)

    print(f"✅ 負載模擬完成：共發送 {msg_count} 條訊息")
    return msg_count


async def run_bot_with_profiling(mode: str, duration: int):
    """啟動 bot 並進行分析"""

    # 1. 先測量啟動時間
    print("📦 測量啟動時間...")
    start = time.time()

    from cogs.common.AI import AIResponse

    # 建立最小化的 bot 實例
    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True

    test_bot = commands.Bot(command_prefix="!", intents=intents)
    test_bot.user = MagicMock()
    test_bot.user.id = 999999

    # 載入 AI Cog
    ai_cog = AIResponse(test_bot)
    await test_bot.add_cog(ai_cog)

    startup_time = time.time() - start
    print(f"✅ 啟動耗時：{startup_time:.2f} 秒")

    # 2. 等待系統穩定
    await asyncio.sleep(2)

    # 3. 執行負載測試
    msg_count = await simulate_load(test_bot, duration, qps=2.0)

    # 4. 記錄結果
    result = {
        "startup_time_sec": startup_time,
        "load_duration_sec": duration,
        "messages_processed": msg_count,
        "avg_qps": msg_count / duration,
    }

    return result


def run_scalene(duration: int):
    """使用 Scalene 進行 CPU/記憶體分析"""
    print("🔬 啟動 Scalene 分析...")

    # 生成分析腳本
    profile_script = f"""
import asyncio
import sys
sys.path.insert(0, r\"{PROJECT_ROOT}\")
from scripts.profile_bot import run_bot_with_profiling

async def main():
    result = await run_bot_with_profiling("scalene", {duration})
    print(f"RESULT: {{result}}")

asyncio.run(main())
"""

    script_path = PROJECT_ROOT / "scripts" / "_temp_scalene_target.py"
    script_path.write_text(profile_script)

    try:
        # 執行 scalene
        cmd = [
            sys.executable,
            "-m",
            "scalene",
            "--cpu",
            "--memory",
            "--html",
            "--outfile",
            str(PROJECT_ROOT / "profiles" / f"scalene_report_{int(time.time())}.html"),
            str(script_path),
        ]

        print(f"執行指令: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, timeout=duration + 60)
        print(f"Scalene 完成，返回碼: {result.returncode}")

    finally:
        script_path.unlink(missing_ok=True)


def run_pyspy(duration: int):
    """使用 py-spy 產生火焰圖"""
    print("🔥 啟動 py-spy 火焰圖分析...")

    # 先在背景啟動 bot
    profile_script = f"""
import asyncio
import sys
sys.path.insert(0, r\"{PROJECT_ROOT}\")
from scripts.profile_bot import run_bot_with_profiling

async def main():
    result = await run_bot_with_profiling("pyspy", {duration})
    print(f"RESULT: {{result}}")

asyncio.run(main())
"""

    script_path = PROJECT_ROOT / "scripts" / "_temp_pyspy_target.py"
    script_path.write_text(profile_script)

    try:
        # 啟動目標進程
        proc = subprocess.Popen([sys.executable, str(script_path)], cwd=PROJECT_ROOT)

        # 給一點時間啟動
        time.sleep(2)

        # 執行 py-spy
        output_svg = PROJECT_ROOT / "profiles" / f"flamegraph_{int(time.time())}.svg"
        cmd = [
            "py-spy",
            "record",
            "-o",
            str(output_svg),
            "-p",
            str(proc.pid),
            "--duration",
            str(duration),
            "--rate",
            "100",
            "--native",  # 包含 C extension
        ]

        print(f"執行指令: {' '.join(cmd)}")
        result = subprocess.run(cmd, timeout=duration + 30)
        print(f"py-spy 完成，火焰圖輸出: {output_svg}")

        # 等待目標進程結束
        proc.wait(timeout=10)

    finally:
        script_path.unlink(missing_ok=True)
        if "proc" in locals() and proc.poll() is None:
            proc.terminate()


def run_memory_profile(duration: int):
    """使用 memory-profiler 記錄記憶體增長"""
    print("📊 啟動記憶體分析...")

    profile_script = f"""
import asyncio
import sys
sys.path.insert(0, r\"{PROJECT_ROOT}\")
from scripts.profile_bot import run_bot_with_profiling

@profile
async def main():
    result = await run_bot_with_profiling("memory", {duration})
    print(f"RESULT: {{result}}")

asyncio.run(main())
"""

    script_path = PROJECT_ROOT / "scripts" / "_temp_memory_target.py"
    script_path.write_text(profile_script)

    try:
        cmd = [sys.executable, "-m", "memory_profiler", str(script_path)]

        print(f"執行指令: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, cwd=PROJECT_ROOT, timeout=duration + 60, capture_output=True, text=True
        )

        # 輸出記憶體分析結果
        output_file = (
            PROJECT_ROOT / "profiles" / f"memory_profile_{int(time.time())}.txt"
        )
        output_file.write_text(result.stdout)
        print(f"記憶體分析完成，輸出: {output_file}")
        print(result.stdout[-2000:])  # 顯示最後 2000 字元

    finally:
        script_path.unlink(missing_ok=True)


async def simple_benchmark(duration: int):
    """簡單內建基準測試（無需外部工具）"""
    print("⏱️ 執行內建基準測試...")

    from cogs.common.AI import AIResponse
    import discord
    from discord.ext import commands
    from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True

    test_bot = commands.Bot(command_prefix="!", intents=intents)
    # Mock the user property since it's read-only in newer discord.py
    with patch.object(type(test_bot), "user", new_callable=PropertyMock) as mock_user:
        mock_user.return_value = MagicMock()
        mock_user.return_value.id = 999999

        ai_cog = AIResponse(test_bot)
        await test_bot.add_cog(ai_cog)

        await asyncio.sleep(1)

        # 測試案例
        test_cases = [
            "@bot 幫我查 KK幣餘額",
            "@bot 搜尋 python asyncio 教學",
            "@bot 爬取 https://example.com",
            "@bot 我的配裝怎麼樣",
            "@bot bot 狀態正常嗎",
            "@bot 你好 干部",
        ]

        latencies = []

        for i in range(min(30, duration * 2)):  # 根據 duration 調整測試次數
            msg = test_cases[i % len(test_cases)]

            mock_message = MagicMock(spec=discord.Message)
            mock_message.author = MagicMock(spec=discord.User)
            mock_message.author.id = 123456789
            mock_message.author.bot = False
            mock_message.content = msg
            mock_message.clean_content = msg
            mock_message.channel = MagicMock(spec=discord.TextChannel)
            mock_message.channel.typing = MagicMock(return_value=AsyncMock().__aenter__)
            mock_message.reply = AsyncMock()
            mock_message.mentions = [MagicMock()]
            mock_message.mentions[0].id = 999999
            mock_message.guild = None

            start = time.perf_counter()
            try:
                await test_bot.on_message(mock_message)
            except Exception:
                pass
            latency = (time.perf_counter() - start) * 1000  # ms
            latencies.append(latency)

            await asyncio.sleep(0.1)  # 10 QPS

        # 統計
        latencies.sort()
        n = len(latencies)
        p50 = latencies[n // 2]
        p95 = latencies[int(n * 0.95)]
        p99 = latencies[int(n * 0.99)]
        avg = sum(latencies) / n

        print("\n📈 延遲統計 (ms):")
        print(f"   平均: {avg:.1f}")
        print(f"   P50:  {p50:.1f}")
        print(f"   P95:  {p95:.1f}")
        print(f"   P99:  {p99:.1f}")
        print(f"   總請求: {n}")

        return {
            "avg_latency_ms": avg,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "total_requests": n,
        }


def main():
    parser = argparse.ArgumentParser(description="Bot 效能分析工具")
    parser.add_argument(
        "--mode",
        choices=["scalene", "pyspy", "memory", "benchmark"],
        default="benchmark",
        help="分析模式",
    )
    parser.add_argument("--duration", type=int, default=30, help="測試持續時間(秒)")
    args = parser.parse_args()

    # 確保輸出目錄存在
    (PROJECT_ROOT / "profiles").mkdir(exist_ok=True)

    if args.mode == "scalene":
        run_scalene(args.duration)
    elif args.mode == "pyspy":
        run_pyspy(args.duration)
    elif args.mode == "memory":
        run_memory_profile(args.duration)
    elif args.mode == "benchmark":
        asyncio.run(simple_benchmark(args.duration))


if __name__ == "__main__":
    main()
