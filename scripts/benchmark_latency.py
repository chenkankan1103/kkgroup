#!/usr/bin/env python3
"""
Discord Bot Latency Benchmark
Standalone script, no external dependencies, measures on_message -> reply full path latency

Usage:
    python scripts/benchmark_latency.py --iterations 100 --warmup 10
"""

import argparse
import asyncio
import sys
import time
import statistics
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Required imports
import discord
from discord.ext import commands


async def run_benchmark(iterations: int = 100, warmup: int = 10, qps: float = 10.0):
    """Run latency benchmark test"""

    print(
        f"Starting benchmark: {iterations} iterations, {warmup} warmup, target {qps} QPS"
    )

    # 1. Initialize bot
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True

    class MockBot(commands.Bot):
        @property
        def user(self):
            mock_user = MagicMock()
            mock_user.id = 999999
            return mock_user

    bot = MockBot(command_prefix="!", intents=intents)

    # Load AI Cog
    from cogs.common.AI import AIResponse

    ai_cog = AIResponse(bot)
    await bot.add_cog(ai_cog)

    # Wait for initialization
    await asyncio.sleep(2)
    print("OK: Bot initialized")

    # Test message pool
    test_messages = [
        "@bot help me check KKcoin balance",
        "@bot search python asyncio tutorial",
        "@bot scrape https://example.com",
        "@bot how is my equipment",
        "@bot is bot status ok",
        "@bot hello admin",
        "@bot query leaderboard top 10",
        "@bot help me find discord.py docs",
        "@bot how is weather today",
        "@bot explain async/await",
    ]

    # Mock message factory
    def create_mock_message(content: str, user_id: int = 123456789):
        msg = MagicMock(spec=discord.Message)
        msg.author = MagicMock(spec=discord.User)
        msg.author.id = user_id
        msg.author.bot = False
        msg.content = content
        msg.clean_content = content

        # Simple mock for channel - avoid typing context manager issues
        channel = MagicMock(spec=discord.TextChannel)
        channel.typing = MagicMock()
        channel.typing.__aenter__ = AsyncMock(return_value=None)
        channel.typing.__aexit__ = AsyncMock(return_value=None)
        msg.channel = channel

        msg.reply = AsyncMock()
        msg.mentions = [MagicMock()]
        msg.mentions[0].id = 999999
        msg.guild = None
        return msg

    # 2. Warmup
    print(f"Warming up... ({warmup} iterations)")
    for i in range(warmup):
        msg = create_mock_message(test_messages[i % len(test_messages)])
        try:
            await bot.on_message(msg)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    print("OK: Warmup complete")

    # 3. Actual test
    print(f"Running benchmark... ({iterations} iterations)")
    latencies = []
    errors = 0
    interval = 1.0 / qps

    for i in range(iterations):
        msg = create_mock_message(
            test_messages[i % len(test_messages)],
            user_id=123456789 + (i % 20),  # Simulate 20 different users
        )

        start = time.perf_counter()
        try:
            await bot.on_message(msg)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)
        except Exception as e:
            errors += 1
            print(f"WARN: Iteration {i+1} error: {e}")

        if interval > 0:
            await asyncio.sleep(interval)

    # 4. Statistics
    if not latencies:
        print("ERROR: No successful test samples")
        return None

    latencies.sort()
    n = len(latencies)

    result = {
        "iterations": iterations,
        "successful": n,
        "errors": errors,
        "avg_ms": statistics.mean(latencies),
        "median_ms": statistics.median(latencies),
        "stdev_ms": statistics.stdev(latencies) if n > 1 else 0,
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "p50_ms": latencies[n // 2],
        "p75_ms": latencies[int(n * 0.75)],
        "p90_ms": latencies[int(n * 0.90)],
        "p95_ms": latencies[int(n * 0.95)],
        "p99_ms": latencies[int(n * 0.99)] if n > 100 else latencies[-1],
    }

    # 5. Output report
    print(f"\n{'='*50}")
    print("Latency Benchmark Report")
    print(f"{'='*50}")
    print(f"Total iterations:    {iterations}")
    print(f"Successful:          {n}")
    print(f"Errors:              {errors}")
    print(f"Success rate:        {n/iterations*100:.1f}%")
    print("\nLatency stats (ms):")
    print(f"  Average:           {result['avg_ms']:.1f}")
    print(f"  Median:            {result['median_ms']:.1f}")
    print(f"  StdDev:            {result['stdev_ms']:.1f}")
    print(f"  Min:               {result['min_ms']:.1f}")
    print(f"  Max:               {result['max_ms']:.1f}")
    print("\nPercentiles:")
    print(f"  P50:               {result['p50_ms']:.1f}")
    print(f"  P75:               {result['p75_ms']:.1f}")
    print(f"  P90:               {result['p90_ms']:.1f}")
    print(f"  P95:               {result['p95_ms']:.1f}")
    print(f"  P99:               {result['p99_ms']:.1f}")

    # 6. Grade
    p95 = result["p95_ms"]
    if p95 < 500:
        grade = "GREEN: Excellent (< 500ms)"
    elif p95 < 1000:
        grade = "YELLOW: Good (500-1000ms)"
    elif p95 < 2000:
        grade = "ORANGE: Average (1-2s)"
    else:
        grade = "RED: Needs optimization (> 2s)"
    print(f"\nOverall Grade: {grade} (based on P95)")

    return result


def main():
    parser = argparse.ArgumentParser(description="Discord Bot Latency Benchmark")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=100,
        help="Test iterations (default 100)",
    )
    parser.add_argument(
        "--warmup", "-w", type=int, default=10, help="Warmup iterations (default 10)"
    )
    parser.add_argument(
        "--qps", type=float, default=10.0, help="Target QPS (default 10)"
    )
    args = parser.parse_args()

    asyncio.run(
        run_benchmark(iterations=args.iterations, warmup=args.warmup, qps=args.qps)
    )


if __name__ == "__main__":
    main()
