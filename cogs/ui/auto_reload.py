"""
改進的自動重載監控 Cog
新增功能：
1. 檔案鎖定機制（防止多實例衝突）
2. Bot 名稱識別（只處理對應的 Bot）
3. 更完善的錯誤處理
"""

import os
import json
import asyncio
import fcntl  # Unix 檔案鎖定
from datetime import datetime
from pathlib import Path
import discord
from discord.ext import commands, tasks

class AutoReload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.git_dir = os.getenv("GIT_DIR", "/home/e193752468/kkgroup")
        self.trigger_file = os.path.join(self.git_dir, ".reload_trigger")
        self.lock_file = os.path.join(self.git_dir, ".reload_lock")
        self.sys_channel_id = int(os.getenv("DISCORD_SYS_CHANNEL_ID", 0))
        
        # 識別當前 Bot（從環境變數或主程式傳入）
        self.bot_name = getattr(bot, 'bot_name', 'Bot')
        self.bot_prefix = getattr(bot, 'bot_prefix', 'DISCORD')
        
        self.is_reloading = False
        
        # 啟動監控任務
        if not self.check_reload_trigger.is_running():
            self.check_reload_trigger.start()
    
    def cog_unload(self):
        """Cog 卸載時停止任務"""
        if self.check_reload_trigger.is_running():
            self.check_reload_trigger.cancel()
    
    def acquire_lock(self, timeout=5):
        """獲取檔案鎖（防止多個 Bot 同時處理）"""
        try:
            lock_fd = open(self.lock_file, 'w')
            
            # 嘗試獲取排他鎖（非阻塞）
            start_time = asyncio.get_event_loop().time()
            while True:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return lock_fd  # 成功獲取鎖
                except BlockingIOError:
                    # 鎖被其他程序持有
                    if asyncio.get_event_loop().time() - start_time > timeout:
                        lock_fd.close()
                        return None  # 超時
                    asyncio.sleep(0.1)  # 等待後重試
        except Exception as e:
            print(f"❌ 獲取鎖失敗: {e}")
            return None
    
    def release_lock(self, lock_fd):
        """釋放檔案鎖"""
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except Exception as e:
                print(f"⚠️ 釋放鎖失敗: {e}")
    
    @tasks.loop(seconds=10)
    async def check_reload_trigger(self):
        """每 10 秒檢查一次觸發檔案"""
        # 防止重複重載
        if self.is_reloading:
            return
        
        lock_fd = None
        try:
            # 檢查檔案是否存在
            if not os.path.exists(self.trigger_file):
                return
            
            # 嘗試獲取鎖（防止多實例衝突）
            lock_fd = self.acquire_lock(timeout=2)
            if not lock_fd:
                print(f"⏳ [{self.bot_name}] 無法獲取鎖，跳過此次檢查")
                return
            
            # 讀取觸發檔案
            with open(self.trigger_file, 'r', encoding='utf-8') as f:
                trigger_data = json.load(f)
            
            # 檢查是否已處理
            if trigger_data.get("processed", False):
                return
            
            # 檢查是否需要重載
            if not trigger_data.get("needs_reload", False):
                # 標記為已處理（即使不需要重載）
                trigger_data["processed"] = True
                trigger_data["processed_by"] = self.bot_name
                trigger_data["processed_at"] = datetime.now().isoformat()
                with open(self.trigger_file, 'w', encoding='utf-8') as f:
                    json.dump(trigger_data, f, indent=2)
                return
            
            # 檢查是否已被其他 Bot 處理（雙重檢查）
            processed_by = trigger_data.get("processed_by")
            if processed_by and processed_by != self.bot_name:
                print(f"ℹ️ [{self.bot_name}] 重載已由 {processed_by} 處理")
                return
            
            # 標記為正在處理（立即寫入，防止其他實例處理）
            trigger_data["processing"] = True
            trigger_data["processing_by"] = self.bot_name
            trigger_data["processing_at"] = datetime.now().isoformat()
            with open(self.trigger_file, 'w', encoding='utf-8') as f:
                json.dump(trigger_data, f, indent=2)
            
            self.is_reloading = True
            
            # 執行重載
            await self.perform_reload(trigger_data)
            
            # 標記為已處理
            trigger_data["processed"] = True
            trigger_data["processed_by"] = self.bot_name
            trigger_data["reload_time"] = datetime.now().isoformat()
            trigger_data["processing"] = False
            with open(self.trigger_file, 'w', encoding='utf-8') as f:
                json.dump(trigger_data, f, indent=2)
            
        except json.JSONDecodeError:
            print(f"⚠️ [{self.bot_name}] 觸發檔案格式錯誤")
        except Exception as e:
            print(f"❌ [{self.bot_name}] 檢查觸發檔案失敗: {e}")
        finally:
            self.is_reloading = False
            self.release_lock(lock_fd)
    
    @check_reload_trigger.before_loop
    async def before_check_reload_trigger(self):
        """等待 Bot 準備完成"""
        await self.bot.wait_until_ready()
        print(f"✅ [{self.bot_name}] 自動重載監控已啟動")
    
    async def perform_reload(self, trigger_data):
        """執行重載操作"""
        print("=" * 60)
        print(f"🔄 [{self.bot_name}] 自動重載於: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 取得系統頻道
        channel = None
        if self.sys_channel_id:
            try:
                channel = self.bot.get_channel(self.sys_channel_id)
                if not channel:
                    channel = await self.bot.fetch_channel(self.sys_channel_id)
            except Exception as e:
                print(f"⚠️ [{self.bot_name}] 無法取得系統頻道: {e}")
        
        # 發送重載開始通知
        reload_msg = None
        if channel:
            reload_start_embed = discord.Embed(
                title=f"🔄 {self.bot_name} Bot 自動重載",
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
                print(f"⚠️ [{self.bot_name}] 發送開始通知失敗: {e}")
        
        # 執行重載
        try:
            async with self.bot._reload_lock if hasattr(self.bot, '_reload_lock') else asyncio.Lock():
                extensions = list(self.bot.extensions.keys())
                reloaded, failed = [], []
                
                print(f"📦 [{self.bot_name}] 開始重載 {len(extensions)} 個擴展...")
                
                for ext in extensions:
                    try:
                        await self.bot.reload_extension(ext)
                        reloaded.append(ext)
                        print(f"  ✅ {ext}")
                    except Exception as e:
                        error_msg = str(e)[:100]
                        failed.append(f"{ext}: {error_msg}")
                        print(f"  ❌ {ext}: {error_msg}")
                
                # 同步指令
                print(f"⚡ [{self.bot_name}] 同步 Slash 指令...")
                try:
                    guild_id = os.getenv(f"{self.bot_prefix}_GUILD_ID")
                    guild = discord.Object(id=guild_id) if guild_id else None
                    synced = await self.bot.tree.sync(guild=guild) if guild else await self.bot.tree.sync()
                    print(f"✅ [{self.bot_name}] 同步完成: {len(synced)} 個指令")
                except Exception as e:
                    synced = []
                    error_msg = str(e)[:100]
                    failed.append(f"指令同步: {error_msg}")
                    print(f"❌ [{self.bot_name}] 同步失敗: {error_msg}")
        
        except Exception as e:
            print(f"❌ [{self.bot_name}] 重載失敗: {e}")
            reloaded, failed, synced = [], [str(e)], []
        
        print("=" * 60)
        print(f"✅ [{self.bot_name}] 自動重載完成")
        print(f"   成功: {len(reloaded)} | 失敗: {len(failed)} | 同步: {len(synced)}")
        print("=" * 60)
        
        # 更新通知
        if channel and reload_msg:
            try:
                result_embed = discord.Embed(
                    title=f"✅ {self.bot_name} Bot 重載完成",
                    color=discord.Color.green() if not failed else discord.Color.orange(),
                    timestamp=datetime.now()
                )
                
                result_embed.add_field(
                    name="📊 重載統計",
                    value=f"✅ 成功: `{len(reloaded)}`\n❌ 失敗: `{len(failed)}`\n⚡ 同步: `{len(synced)}`",
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
                
                result_embed.set_footer(text=f"{self.bot_name} Bot 自動重載系統")
                await reload_msg.edit(embed=result_embed)
                
            except Exception as e:
                print(f"⚠️ [{self.bot_name}] 更新結果通知失敗: {e}")

async def setup(bot):
    await bot.add_cog(AutoReload(bot))
