import os
import subprocess
import asyncio
from discord import app_commands, Interaction, Embed
from discord.ext import commands
import discord
from datetime import datetime

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
GIT_DIR = "/home/e193752468/kkgroup"

# 定義重啟順序：先關閉的放前面，主 Bot 放最後
SERVICES = [
    ("shopbot", "shopbot.service"),
    ("uibot", "uibot.service"),
    ("bot", "bot.service"),  # 主 Bot 最後重啟
]

class AdminBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    def restart_service(self, service_name: str):
        """使用 systemctl 重啟服務"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return True, f"✅ {service_name} 重啟成功"
            else:
                return False, f"❌ {service_name} 重啟失敗: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, f"⏱️ {service_name} 重啟超時"
        except Exception as e:
            return False, f"❌ {service_name} 重啟錯誤: {str(e)}"
    
    def stop_service(self, service_name: str):
        """停止服務"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return True, f"⏸️ {service_name} 已停止"
            else:
                return False, f"❌ {service_name} 停止失敗: {result.stderr}"
        except Exception as e:
            return False, f"❌ {service_name} 停止錯誤: {str(e)}"
    
    def start_service(self, service_name: str):
        """啟動服務"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "start", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return True, f"▶️ {service_name} 已啟動"
            else:
                return False, f"❌ {service_name} 啟動失敗: {result.stderr}"
        except Exception as e:
            return False, f"❌ {service_name} 啟動錯誤: {str(e)}"
    
    def get_service_status(self, service_name: str):
        """獲取服務狀態"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip()
        except:
            return "unknown"
    
    def check_git_updates(self):
        """檢查 Git 更新"""
        try:
            subprocess.run(["git", "fetch"], cwd=GIT_DIR, check=True, timeout=10)
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..origin/main"],
                cwd=GIT_DIR,
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            commits_behind = int(result.stdout.strip())
            return commits_behind > 0, commits_behind
        except Exception as e:
            return False, str(e)
    
    def get_git_update_details(self):
        """獲取更新詳情"""
        try:
            commits = subprocess.check_output([
                "git", "log", "HEAD..origin/main",
                "--pretty=format:• %s (%h)",
                "--max-count=5"
            ], cwd=GIT_DIR, timeout=5).decode("utf-8").strip()

            changed_files = subprocess.check_output([
                "git", "diff", "--name-only", "HEAD", "origin/main"
            ], cwd=GIT_DIR, timeout=5).decode("utf-8").strip()

            return {
                "commits": commits if commits else "沒有 commit 資訊",
                "files": changed_files.split("\n") if changed_files else []
            }
        except Exception as e:
            return {"commits": f"獲取失敗: {e}", "files": []}
    
    def pull_git_updates(self):
        """拉取 Git 更新"""
        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=GIT_DIR,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            return True, result.stdout
        except Exception as e:
            return False, str(e)
    
    @app_commands.command(name="update_and_restart", description="檢查更新、拉取代碼並依序重啟所有服務")
    async def update_and_restart(self, interaction: Interaction):
        """完整的更新和重啟流程（按順序重啟）"""
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        embed = Embed(title="🔄 更新與重啟流程", color=0xFFA500)
        embed.set_footer(text=f"執行者: {interaction.user.name}")
        embed.timestamp = datetime.now()
        
        # 1. 檢查更新
        embed.add_field(name="📡 檢查更新", value="檢查中...", inline=False)
        msg = await interaction.followup.send(embed=embed)
        
        has_update, commits_count = self.check_git_updates()
        
        if isinstance(commits_count, str):  # 錯誤訊息
            embed.set_field_at(0, name="📡 檢查更新", value=f"❌ 檢查失敗: {commits_count}", inline=False)
            await msg.edit(embed=embed)
            return
        
        if not has_update:
            embed.set_field_at(0, name="📡 檢查更新", value="✅ 已是最新版本，是否仍要重啟服務？", inline=False)
            embed.color = 0x00FF00
            await msg.edit(embed=embed)
            # 即使沒有更新，也繼續執行重啟流程
        else:
            embed.set_field_at(0, name="📡 檢查更新", value=f"✅ 發現 {commits_count} 個新提交", inline=False)
            
            # 2. 獲取更新詳情
            update_details = self.get_git_update_details()
            commit_text = update_details.get("commits", "")
            if len(commit_text) > 500:
                commit_text = commit_text[:500] + "..."
            embed.add_field(name="📝 更新內容", value=f"```\n{commit_text}\n```", inline=False)
            await msg.edit(embed=embed)
            
            # 3. 拉取更新
            field_index = len(embed.fields)
            embed.add_field(name="📥 拉取代碼", value="拉取中...", inline=False)
            await msg.edit(embed=embed)
            
            success, pull_result = self.pull_git_updates()
            if not success:
                embed.set_field_at(field_index, name="📥 拉取代碼", value=f"❌ 拉取失敗: {pull_result}", inline=False)
                embed.color = 0xFF0000
                await msg.edit(embed=embed)
                return
            
            embed.set_field_at(field_index, name="📥 拉取代碼", value="✅ 代碼已更新", inline=False)
            await msg.edit(embed=embed)
        
        # 4. 依序重啟所有服務（重要：先關閉其他，最後關閉主 Bot）
        field_index = len(embed.fields)
        embed.add_field(name="🔄 重啟服務", value="準備依序重啟...", inline=False)
        await msg.edit(embed=embed)
        
        restart_results = []
        
        # 先停止所有服務（從前到後）
        for name, service in SERVICES:
            success, message = self.stop_service(service)
            restart_results.append(f"⏸️ 停止 {name}: {'成功' if success else '失敗'}")
            embed.set_field_at(field_index, name="🔄 重啟服務", value="\n".join(restart_results), inline=False)
            await msg.edit(embed=embed)
            await asyncio.sleep(1)
        
        # 等待所有服務完全停止
        restart_results.append("⏳ 等待服務停止...")
        embed.set_field_at(field_index, name="🔄 重啟服務", value="\n".join(restart_results), inline=False)
        await msg.edit(embed=embed)
        await asyncio.sleep(3)
        
        # 按順序啟動服務（從前到後）
        for name, service in SERVICES:
            success, message = self.start_service(service)
            restart_results.append(f"▶️ 啟動 {name}: {'成功' if success else '失敗'}")
            embed.set_field_at(field_index, name="🔄 重啟服務", value="\n".join(restart_results), inline=False)
            await msg.edit(embed=embed)
            await asyncio.sleep(2)  # 給每個服務啟動時間
        
        # 5. 檢查服務狀態
        await asyncio.sleep(3)  # 等待服務完全啟動
        status_results = []
        all_active = True
        for name, service in SERVICES:
            status = self.get_service_status(service)
            emoji = "🟢" if status == "active" else "🔴"
            status_results.append(f"{emoji} {name}: {status}")
            if status != "active":
                all_active = False
        
        embed.add_field(name="📊 服務狀態", value="\n".join(status_results), inline=False)
        embed.color = 0x00FF00 if all_active else 0xFF0000
        
        await msg.edit(embed=embed)
    
    @app_commands.command(name="check_updates", description="僅檢查是否有 Git 更新")
    async def check_updates(self, interaction: Interaction):
        """僅檢查更新，不執行拉取"""
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        has_update, commits_count = self.check_git_updates()
        
        if isinstance(commits_count, str):  # 錯誤
            await interaction.followup.send(f"❌ 檢查失敗: {commits_count}")
            return
        
        if not has_update:
            await interaction.followup.send("✅ 目前已是最新版本")
            return
        
        # 獲取更新詳情
        update_details = self.get_git_update_details()
        
        embed = Embed(
            title="📦 發現新更新",
            description=f"有 {commits_count} 個新提交待更新",
            color=0xFFA500
        )
        
        commit_text = update_details.get("commits", "")
        if commit_text:
            if len(commit_text) > 1000:
                commit_text = commit_text[:1000] + "..."
            embed.add_field(name="📝 更新內容", value=f"```\n{commit_text}\n```", inline=False)
        
        files = update_details.get("files", [])
        if files:
            files_text = "\n".join([f"• {f}" for f in files[:10]])
            if len(files) > 10:
                files_text += f"\n... 還有 {len(files) - 10} 個檔案"
            embed.add_field(name="📂 變更檔案", value=files_text, inline=False)
        
        embed.add_field(
            name="💡 提示",
            value="使用 `/update_and_restart` 來更新並重啟服務",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="restart_all", description="依序重啟所有 bot 服務（不更新代碼）")
    async def restart_all(self, interaction: Interaction):
        """按順序重啟所有服務：先關閉其他 bot，最後關閉主 bot"""
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        embed = Embed(title="🔄 依序重啟所有服務", color=0xFFA500)
        msg = await interaction.followup.send(embed=embed)
        
        results = []
        
        # 第一階段：停止所有服務
        results.append("**階段 1: 停止服務**")
        for name, service in SERVICES:
            success, message = self.stop_service(service)
            results.append(message)
            embed.description = "\n".join(results)
            await msg.edit(embed=embed)
            await asyncio.sleep(1)
        
        # 等待
        results.append("\n⏳ 等待服務停止...")
        embed.description = "\n".join(results)
        await msg.edit(embed=embed)
        await asyncio.sleep(3)
        
        # 第二階段：啟動所有服務
        results.append("\n**階段 2: 啟動服務**")
        for name, service in SERVICES:
            success, message = self.start_service(service)
            results.append(message)
            embed.description = "\n".join(results)
            await msg.edit(embed=embed)
            await asyncio.sleep(2)
        
        # 檢查狀態
        await asyncio.sleep(3)
        results.append("\n**📊 最終狀態**")
        all_active = True
        for name, service in SERVICES:
            status = self.get_service_status(service)
            emoji = "🟢" if status == "active" else "🔴"
            results.append(f"{emoji} {name}: {status}")
            if status != "active":
                all_active = False
        
        embed.description = "\n".join(results)
        embed.color = 0x00FF00 if all_active else 0xFF0000
        await msg.edit(embed=embed)
    
    @app_commands.command(name="restart", description="重啟指定的 bot 服務")
    @app_commands.describe(service="選擇要重啟的服務")
    @app_commands.choices(service=[
        app_commands.Choice(name="ShopBot", value="shopbot.service"),
        app_commands.Choice(name="UIBot", value="uibot.service"),
        app_commands.Choice(name="Bot (主機器人)", value="bot.service"),
    ])
    async def restart(self, interaction: Interaction, service: str):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        success, message = self.restart_service(service)
        
        # 等待服務啟動
        await asyncio.sleep(2)
        status = self.get_service_status(service)
        status_emoji = "🟢" if status == "active" else "🔴"
        
        await interaction.followup.send(f"{message}\n{status_emoji} 狀態: {status}")
    
    @app_commands.command(name="status", description="查看所有 bot 服務狀態")
    async def status(self, interaction: Interaction):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ 你沒有權限使用此指令", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        results = []
        
        for name, service in SERVICES:
            status = self.get_service_status(service)
            emoji = "🟢" if status == "active" else "🔴"
            results.append(f"{emoji} {name}: {status}")
        
        embed = Embed(
            title="📊 服務狀態",
            description="\n".join(results),
            color=0x00FF00,
            timestamp=datetime.now()
        )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AdminBot(bot))
