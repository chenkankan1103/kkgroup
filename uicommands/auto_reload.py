"""
自動重載監控 Cog
放在 commands/auto_reload.py

功能：
1. 監控 .reload_trigger 檔案
2. 自動執行熱重載（避免重複）
3. 發送重載結果通知
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
import discord
from discord.ext import commands, tasks

class AutoReload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.git_dir = os.getenv("GIT_DIR", "/home/e193752468/kkgroup")
        self.trigger_file = os.path.join(self.git_dir, ".reload_trigger")
        self.sys_channel_id = int(os.getenv("DISCORD_SYS_CHANNEL_ID", 0))
        self.last_check_time = None
        self.is_reloading = False  # 防止重複重載
        
        # 啟動監控任務
        if not self.check_reload_trigger.is_running():
            self.check_reload_trigger.start()
    
    def cog_unload(self):
        """Cog 卸載時停止任務"""
        if self.check_reload_trigger.is_running():
            self.check_reload_trigger.cancel()
    
    @tasks.loop(seconds=10)
    async def check_reload_trigger(self):
        """每 10 秒檢查一次觸發檔案"""
        try:
            # 檢查檔案是否存在
            if not os.path.exists(self.trigger_file):
                return
            
            # 讀取觸發檔案
            with open(self.trigger_file, 'r', encoding='utf-8') as f:
                trigger_data = json.load(f)
            
            # 檢查是否已處理
            if trigger_data.get("processed", False):
                return
            
            # 檢查是否需要重載
            if not trigger_data.get("needs_reload", False):
                # 標記為已處理
                trigger_data["processed"] = True
                with open(self.trigger_file, 'w', encoding='utf-8') as f:
                    json.dump(trigger_data, f, indent=2)
                return
            
            # 防止重複重載
            if self.is_reloading:
                print("⏳ 正在重載中，跳過此次觸發")
                return
            
            self.is_reloading = True
            
            # 執行重載
            await self.perform_reload(trigger_data)
            
            # 標記為已處理
            trigger_data["processed"] = True
            trigger_data["reload_time"] = datetime.now().isoformat()
            with open(self.trigger_file, 'w', encoding='utf-8') as f:
                json.dump(trigger_data, f, indent=2)
            
        except json.JSONDecodeError:
            print(f"⚠️ 觸發檔案格式錯誤，已忽略")
        except Exception as e:
            print(f"❌ 檢查觸發檔案時發生錯誤: {e}")
        finally:
            self.is_reloading = False
    
    @check_reload_trigger.before_loop
    async def before_check_reload_trigger(self):
        """等待 Bot 準備完成"""
        await self.bot.wait_until_ready()
        print("✅ 自動重載監控已啟動")
    
    async def perform_reload(self, trigger_data):
        """執行重載操作"""
        print("=" * 60)
        print(f"🔄 自動重載觸發於: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 取得系統頻道
        channel = None
        if self.sys_channel_id:
            try:
                channel = self.bot.get_channel(self.sys_channel_id)
                if not channel:
                    channel = await self.bot.fetch_channel(self.sys_channel_id)
            except Exception as e:
                print(f"⚠️ 無法取得系統頻道: {e}")
        
        # 發送重載開始通知
        reload_start_embed = None
        reload_msg = None
        if channel:
            reload_start_embed = discord.Embed(
                title="🔄 自動重載開始",
                description="偵測到程式碼更新，正在執行熱重載...",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            py_files = trigger_data.get("py_files", [])
            if py_files:
                files_text = "\n".join([f"• {f}" for f in py_files[:10]])
                if len(py_files) > 10:
                    files_text += f"\n... 還有 {len(py_files) - 10} 個檔案"
                reload_start_embed.add_field(
                    name="📂 變更的 Python 檔案",
                    value=f"```\n{files_text}\n```",
                    inline=False
                )
            
            try:
                reload_msg = await channel.send(embed=reload_start_embed)
            except Exception as e:
                print(f"⚠️ 發送開始通知失敗: {e}")
        
        # 執行重載
        try:
            # 使用鎖防止並發重載
            async with self.bot._reload_lock if hasattr(self.bot, '_reload_lock') else asyncio.Lock():
                extensions = list(self.bot.extensions.keys())
                reloaded, failed = [], []
                
                print(f"📦 開始重載 {len(extensions)} 個擴展...")
                
                for ext in extensions:
                    try:
                        await self.bot.reload_extension(ext)
                        reloaded.append(ext)
                        print(f"  ✅ {ext}")
                    except Exception as e:
                        error_msg = str(e)[:100]
                        failed.append(f"{ext}: {error_msg}")
                        print(f"  ❌ {ext}: {error_msg}")
                
                # 同步指令（只同步一次）
                print("⚡ 同步 Slash 指令...")
                try:
                    guild_id = os.getenv("DISCORD_GUILD_ID")
                    guild = discord.Object(id=guild_id) if guild_id else None
                    synced = await self.bot.tree.sync(guild=guild) if guild else await self.bot.tree.sync()
                    print(f"✅ 同步完成: {len(synced)} 個指令")
                except Exception as e:
                    synced = []
                    error_msg = str(e)[:100]
                    failed.append(f"指令同步: {error_msg}")
                    print(f"❌ 同步失敗: {error_msg}")
        
        except Exception as e:
            print(f"❌ 重載過程發生錯誤: {e}")
            reloaded, failed, synced = [], [str(e)], []
        
        print("=" * 60)
        print(f"✅ 自動重載完成")
        print(f"   成功: {len(reloaded)} | 失敗: {len(failed)} | 同步: {len(synced)}")
        print("=" * 60)
        
        # 更新通知
        if channel and reload_msg:
            try:
                # 建立結果 Embed
                result_embed = discord.Embed(
                    title="✅ 自動重載完成",
                    color=discord.Color.green() if not failed else discord.Color.orange(),
                    timestamp=datetime.now()
                )
                
                result_embed.add_field(
                    name="📊 重載統計",
                    value=f"✅ 成功: `{len(reloaded)}`\n❌ 失敗: `{len(failed)}`\n⚡ 同步: `{len(synced)}`",
                    inline=False
                )
                
                if reloaded:
                    reload_list = "\n".join([f"• {ext.split('.')[-1]}" for ext in reloaded[:10]])
                    if len(reloaded) > 10:
                        reload_list += f"\n... 及其他 {len(reloaded) - 10} 個"
                    result_embed.add_field(
                        name="✅ 成功重載",
                        value=reload_list,
                        inline=False
                    )
                
                if failed:
                    fail_list = "\n".join([f"• {f[:80]}" for f in failed[:5]])
                    if len(failed) > 5:
                        fail_list += f"\n... 及其他 {len(failed) - 5} 個"
                    result_embed.add_field(
                        name="❌ 失敗清單",
                        value=f"```\n{fail_list}\n```",
                        inline=False
                    )
                
                result_embed.set_footer(text="自動重載系統")
                
                await reload_msg.edit(embed=result_embed)
                
            except Exception as e:
                print(f"⚠️ 更新結果通知失敗: {e}")
        elif channel:
            # 如果沒有開始訊息，直接發送結果
            try:
                result_embed = discord.Embed(
                    title="✅ 自動重載完成",
                    description=f"成功: `{len(reloaded)}` | 失敗: `{len(failed)}` | 同步: `{len(synced)}`",
                    color=discord.Color.green() if not failed else discord.Color.orange(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=result_embed)
            except Exception as e:
                print(f"⚠️ 發送結果通知失敗: {e}")

async def setup(bot):
    await bot.add_cog(AutoReload(bot))
