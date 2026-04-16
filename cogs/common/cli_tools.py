"""
CLI Tools Cog - 將 MCP 工具改為 Slash Command
==============================================

目的：減少 AI 系統提示的 token 消耗

原架構：agent_tools → AI Function Calling（導入大量工具描述）→ token 爆量
新架構：agent_tools → CLI Slash Command（用戶直接執行）→ 節省 token

用戶可以直接調用工具，無需 AI 中介。

示例：
    /kkcoin_balance user_id:12345
    /bot_status
    /vm_logs service:bot
"""

import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 導入工具庫（但不通過 AI Function Calling 使用）
try:
    import agent_tools
    _TOOLS_AVAILABLE = True
except ImportError:
    agent_tools = None
    _TOOLS_AVAILABLE = False
    logger.warning("⚠️ agent_tools 模組不可用，CLI Tools 功能受限")

LEADER_DISCORD_ID: int = int(os.getenv("LEADER_DISCORD_ID", "0"))


class CLITools(commands.Cog):
    """直接執行工具的 Slash Command Cog"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="kkcoin_balance",
        description="查詢 KK幣餘額"
    )
    @app_commands.describe(user_id="Discord 用戶 ID（留空查詢自己）")
    async def kkcoin_balance(self, interaction: discord.Interaction, user_id: Optional[str] = None):
        """直接查詢 KK幣，無需 AI 中介"""
        try:
            if not agent_tools:
                await interaction.response.send_message("❌ 工具系統不可用", ephemeral=True)
                return

            # 直接呼叫工具
            result = agent_tools.get_kkcoin_balance(
                user_id=user_id or "",
                caller_id=interaction.user.id
            )

            # 分割長消息（Discord 2000 字符限制）
            if len(str(result)) > 1900:
                chunks = [str(result)[i:i+1900] for i in range(0, len(str(result)), 1900)]
                await interaction.response.send_message(chunks[0])
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.response.send_message(str(result))

        except Exception as e:
            logger.error(f"CLI tool 執行失敗: {e}")
            await interaction.response.send_message(f"❌ 執行失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="user_stats",
        description="查詢用戶遊戲資料"
    )
    @app_commands.describe(user_id="Discord 用戶 ID（留空查詢自己）")
    async def user_stats(self, interaction: discord.Interaction, user_id: Optional[str] = None):
        """查詢完整遊戲資料"""
        try:
            if not agent_tools:
                await interaction.response.send_message("❌ 工具系統不可用", ephemeral=True)
                return

            result = agent_tools.get_user_stats(
                user_id=user_id or "",
                caller_id=interaction.user.id
            )

            if len(str(result)) > 1900:
                chunks = [str(result)[i:i+1900] for i in range(0, len(str(result)), 1900)]
                await interaction.response.send_message(chunks[0])
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.response.send_message(str(result))

        except Exception as e:
            logger.error(f"CLI tool 執行失敗: {e}")
            await interaction.response.send_message(f"❌ 執行失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="leaderboard",
        description="查詢 KK幣排行榜"
    )
    @app_commands.describe(top_n="前幾名（預設 10，最多 20）")
    async def leaderboard(self, interaction: discord.Interaction, top_n: Optional[int] = 10):
        """查詢排行榜"""
        try:
            if not agent_tools:
                await interaction.response.send_message("❌ 工具系統不可用", ephemeral=True)
                return

            result = agent_tools.get_top_kkcoin_leaderboard(
                top_n=top_n or 10,
                caller_id=interaction.user.id
            )

            if len(str(result)) > 1900:
                chunks = [str(result)[i:i+1900] for i in range(0, len(str(result)), 1900)]
                await interaction.response.send_message(chunks[0])
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.response.send_message(str(result))

        except Exception as e:
            logger.error(f"CLI tool 執行失敗: {e}")
            await interaction.response.send_message(f"❌ 執行失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="bot_status",
        description="查詢 Bot 運行狀態"
    )
    async def bot_status(self, interaction: discord.Interaction):
        """查詢系統狀態"""
        try:
            if not agent_tools:
                await interaction.response.send_message("❌ 工具系統不可用", ephemeral=True)
                return

            result = agent_tools.get_bot_status(caller_id=interaction.user.id)
            await interaction.response.send_message(str(result))

        except Exception as e:
            logger.error(f"CLI tool 執行失敗: {e}")
            await interaction.response.send_message(f"❌ 執行失敗: {e}", ephemeral=True)

    # ==================== 管理員專用工具 ====================

    @app_commands.command(
        name="vm_logs",
        description="【管理員】查詢 VM 日誌"
    )
    @app_commands.describe(
        service_name="服務名稱（bot/shopbot/uibot）",
        lines="日誌行數（預設 100）"
    )
    async def vm_logs(
        self,
        interaction: discord.Interaction,
        service_name: str = "bot",
        lines: Optional[int] = 100
    ):
        """查詢 VM journalctl 日誌（需要管理員權限）"""
        # 管理員檢查
        if interaction.user.id != LEADER_DISCORD_ID:
            await interaction.response.send_message("🔒 此命令僅限園區管理員", ephemeral=True)
            return

        try:
            await interaction.response.defer()
            
            # 直接執行 shell 命令查詢日誌（比通過 agent_tools 更快）
            import subprocess
            cmd = f'gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap --command "sudo journalctl -u {service_name}.service -n {lines} --no-pager" 2>&1'
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout or result.stderr
            
            # 分割長消息
            if len(output) > 1900:
                chunks = [output[i:i+1900] for i in range(0, len(output), 1900)]
                await interaction.followup.send(f"```\n{chunks[0]}\n```")
                for chunk in chunks[1:]:
                    await interaction.followup.send(f"```\n{chunk}\n```")
            else:
                await interaction.followup.send(f"```\n{output}\n```")

        except Exception as e:
            logger.error(f"VM logs 查詢失敗: {e}")
            await interaction.followup.send(f"❌ 查詢失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="git_push",
        description="【管理員】提交並推送代碼"
    )
    @app_commands.describe(commit_message="提交訊息")
    async def git_push(self, interaction: discord.Interaction, commit_message: str):
        """Git 提交（需要管理員權限）"""
        # 管理員檢查
        if interaction.user.id != LEADER_DISCORD_ID:
            await interaction.response.send_message("🔒 此命令僅限園區管理員", ephemeral=True)
            return

        try:
            if not agent_tools:
                await interaction.response.send_message("❌ 工具系統不可用", ephemeral=True)
                return

            result = agent_tools.trigger_git_push(
                commit_message=commit_message,
                caller_id=interaction.user.id
            )

            await interaction.response.send_message(f"✅ Git 操作完成：\n{result}")

        except Exception as e:
            logger.error(f"Git push 失敗: {e}")
            await interaction.response.send_message(f"❌ 操作失敗: {e}", ephemeral=True)

    @app_commands.command(
        name="operation_log",
        description="【管理員】查詢操作日誌"
    )
    @app_commands.describe(limit="查看最近幾筆（預設 10，最多 50）")
    async def operation_log(self, interaction: discord.Interaction, limit: Optional[int] = 10):
        """審計日誌（需要管理員權限）"""
        # 管理員檢查
        if interaction.user.id != LEADER_DISCORD_ID:
            await interaction.response.send_message("🔒 此命令僅限園區管理員", ephemeral=True)
            return

        try:
            if not agent_tools:
                await interaction.response.send_message("❌ 工具系統不可用", ephemeral=True)
                return

            result = agent_tools.get_operation_log(
                limit=limit or 10,
                caller_id=interaction.user.id
            )

            if len(str(result)) > 1900:
                chunks = [str(result)[i:i+1900] for i in range(0, len(str(result)), 1900)]
                await interaction.response.send_message(chunks[0])
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.response.send_message(str(result))

        except Exception as e:
            logger.error(f"操作日誌查詢失敗: {e}")
            await interaction.response.send_message(f"❌ 查詢失敗: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CLITools(bot))
    logger.info("✅ CLI Tools Cog 已載入（工具現在通過 Slash Command 執行）")
