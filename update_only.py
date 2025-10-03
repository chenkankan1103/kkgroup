"""
Git 更新與熱重載指令
放在 commands/admin_gitupdate.py
"""
import asyncio
import subprocess
import discord
from discord import app_commands
from discord.ext import commands

class AdminGitUpdate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="git_update", description="從 Git 拉取最新程式碼並重載")
    @app_commands.default_permissions(administrator=True)
    async def git_update(self, interaction: discord.Interaction):
        """執行 Git 更新並重載所有模組"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            # === 1. 拉取最新程式碼 ===
            pull_result = subprocess.run(
                ["git", "pull"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd="."
            )
            
            # === 2. 取得最新 commit 資訊 ===
            commit_info = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%h - %s (%an, %ar)"],
                capture_output=True,
                text=True
            )
            
            # === 3. 取得變更統計 ===
            stats_result = subprocess.run(
                ["git", "diff", "HEAD@{1}", "HEAD", "--stat"],
                capture_output=True,
                text=True
            )
            
            # === 4. 建立回報 Embed ===
            embed = discord.Embed(
                title="🔄 Bot 更新通知",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            # 判斷是否有更新
            already_updated = "Already up to date" in pull_result.stdout or "已經是最新" in pull_result.stdout
            
            if already_updated:
                embed.add_field(
                    name="📋 狀態",
                    value="✅ 已是最新版本，無需更新",
                    inline=False
                )
                embed.color = discord.Color.green()
            else:
                embed.add_field(
                    name="📋 狀態",
                    value="🔄 發現新提交，已拉取最新程式碼",
                    inline=False
                )
                
                # 顯示 commit 資訊
                if commit_info.stdout:
                    embed.add_field(
                        name="📝 最新提交",
                        value=f"```{commit_info.stdout}```",
                        inline=False
                    )
                
                # 顯示變更統計
                if stats_result.stdout and stats_result.stdout.strip():
                    stats_text = stats_result.stdout.strip()
                    # 限制長度
                    if len(stats_text) > 800:
                        lines = stats_text.split('\n')
                        stats_text = '\n'.join(lines[:15]) + "\n... (省略更多)"
                    
                    embed.add_field(
                        name="📊 變更統計",
                        value=f"```diff\n{stats_text}```",
                        inline=False
                    )
                
                # === 5. 重載所有擴展 ===
                await interaction.followup.send(embed=embed)
                
                # 執行重載
                reload_embed = discord.Embed(
                    title="🔄 正在重載模組...",
                    color=discord.Color.orange()
                )
                reload_msg = await interaction.channel.send(embed=reload_embed)
                
                async with self.bot._reload_lock if hasattr(self.bot, '_reload_lock') else asyncio.Lock():
                    extensions = list(self.bot.extensions.keys())
                    reloaded, failed = [], []
                    
                    for ext in extensions:
                        try:
                            await self.bot.reload_extension(ext)
                            reloaded.append(ext)
                        except Exception as e:
                            failed.append(f"{ext}: {str(e)[:50]}")
                    
                    # 同步指令（只同步一次）
                    try:
                        guild = discord.Object(id=interaction.guild_id) if interaction.guild_id else None
                        synced = await self.bot.tree.sync(guild=guild) if guild else await self.bot.tree.sync()
                    except Exception as e:
                        synced = []
                        failed.append(f"指令同步失敗: {str(e)[:50]}")
                
                # 更新重載結果
                reload_embed.title = "✅ 模組重載完成"
                reload_embed.color = discord.Color.green()
                reload_embed.add_field(
                    name="📊 重載統計",
                    value=f"✅ 成功: `{len(reloaded)}`\n❌ 失敗: `{len(failed)}`\n⚡ 同步: `{len(synced)}`",
                    inline=False
                )
                
                if reloaded:
                    reload_list = "\n".join([f"• {ext.split('.')[-1]}" for ext in reloaded[:10]])
                    if len(reloaded) > 10:
                        reload_list += f"\n... 及其他 {len(reloaded) - 10} 個"
                    reload_embed.add_field(
                        name="✅ 成功重載",
                        value=reload_list,
                        inline=False
                    )
                
                if failed:
                    fail_list = "\n".join([f"• {f}" for f in failed[:5]])
                    reload_embed.add_field(
                        name="❌ 失敗清單",
                        value=fail_list,
                        inline=False
                    )
                
                await reload_msg.edit(embed=reload_embed)
                return
            
            await interaction.followup.send(embed=embed)
            
        except subprocess.TimeoutExpired:
            error_embed = discord.Embed(
                title="❌ 更新失敗",
                description="Git 操作逾時（超過 30 秒）",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
        except subprocess.CalledProcessError as e:
            error_embed = discord.Embed(
                title="❌ Git 錯誤",
                description=f"```\n{e.stderr[:500]}```" if e.stderr else "未知錯誤",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ 更新失敗",
                description=f"```py\n{str(e)[:500]}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    @app_commands.command(name="git_status", description="檢查 Git 狀態")
    @app_commands.default_permissions(administrator=True)
    async def git_status(self, interaction: discord.Interaction):
        """檢查當前 Git 狀態"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 當前分支
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True
            )
            
            # 未提交的變更
            status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True
            )
            
            # 最後一次 commit
            last_commit = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%h - %s (%an, %ar)"],
                capture_output=True,
                text=True
            )
            
            # 遠端狀態
            remote_status = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..@{u}"],
                capture_output=True,
                text=True
            )
            
            embed = discord.Embed(
                title="📊 Git 狀態",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🌿 當前分支",
                value=f"`{branch.stdout.strip() or 'unknown'}`",
                inline=True
            )
            
            behind_commits = remote_status.stdout.strip()
            if behind_commits and behind_commits.isdigit() and int(behind_commits) > 0:
                embed.add_field(
                    name="⚠️ 遠端狀態",
                    value=f"落後 `{behind_commits}` 個提交",
                    inline=True
                )
            else:
                embed.add_field(
                    name="✅ 遠端狀態",
                    value="已是最新",
                    inline=True
                )
            
            if last_commit.stdout:
                embed.add_field(
                    name="📝 最後提交",
                    value=f"```{last_commit.stdout}```",
                    inline=False
                )
            
            if status.stdout.strip():
                status_text = status.stdout.strip()
                if len(status_text) > 500:
                    status_text = status_text[:500] + "..."
                embed.add_field(
                    name="📋 未提交變更",
                    value=f"```\n{status_text}```",
                    inline=False
                )
            else:
                embed.add_field(
                    name="✅ 工作目錄",
                    value="乾淨（無未提交變更）",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 檢查失敗: {e}", ephemeral=True)
    
    @app_commands.command(name="reload_cog", description="重載指定的 Cog")
    @app_commands.default_permissions(administrator=True)
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        """重載單一 Cog"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            async with self.bot._reload_lock if hasattr(self.bot, '_reload_lock') else asyncio.Lock():
                await self.bot.reload_extension(cog_name)
                
                # 同步指令
                guild = discord.Object(id=interaction.guild_id) if interaction.guild_id else None
                synced = await self.bot.tree.sync(guild=guild) if guild else await self.bot.tree.sync()
            
            embed = discord.Embed(
                title="✅ 重載成功",
                description=f"已重載: `{cog_name}`\n同步了 `{len(synced)}` 個指令",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ 重載失敗",
                description=f"```py\n{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AdminGitUpdate(bot))
