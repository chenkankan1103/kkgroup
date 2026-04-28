# -*- coding: utf-8 -*-
"""
強制刷新特定用戶的置物櫃
用法: python3 force_refresh_user_locker.py <user_id>
"""

import asyncio
import sqlite3
import sys
from pathlib import Path
import os

# 添加根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent))

import discord
from cogs.ui.utils.paperdoll_manager import build_api_url, validate
from cogs.ui.utils.locker_cache import locker_cache


async def force_refresh_locker(user_id: str):
    """強制刷新用戶的置物櫃"""
    print(f"\n🔄 開始強制刷新用戶 {user_id} 的置物櫃...\n")
    
    # 1. 獲取用戶數據
    db_path = Path(__file__).parent / "user_data.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        user_data = dict(row) if row else None
    finally:
        conn.close()
    
    if not user_data:
        print(f"❌ 找不到用戶 {user_id}")
        return False
    
    print(f"✅ 用戶已找到")
    
    # 2. 驗證紙娃娃數據
    if not validate(user_data):
        print(f"❌ 用戶紙娃娃數據不完整")
        return False
    
    print(f"✅ 紙娃娃數據完整")
    
    # 3. 生成 API URL
    try:
        url = build_api_url(user_data, pose='stand1')
        print(f"✅ 紙娃娃 API URL 已生成")
        if user_data.get('is_stunned') == 1:
            print(f"   ⚠️  暈倒狀態：pose 將自動轉換為 prone")
    except Exception as e:
        print(f"❌ 生成 URL 失敗: {e}")
        return False
    
    # 4. 清除緩存
    try:
        paperdoll_hash = locker_cache.build_paperdoll_hash(user_data)
        locker_cache.invalidate_hash(paperdoll_hash)
        print(f"✅ 紙娃娃緩存已清除")
    except Exception as e:
        print(f"⚠️  緩存清除失敗 (非致命): {e}")
    
    # 5. 連接 Discord Bot
    locker_msg_id = user_data.get('locker_message_id')
    thread_id = user_data.get('thread_id')
    
    if not locker_msg_id or not thread_id:
        print(f"❌ 置物櫃尚未建立（無訊息 ID 或線程 ID）")
        return False
    
    print(f"✅ 置物櫃訊息已找到 (ID: {locker_msg_id})")
    
    # 6. 初始化 Discord Bot
    try:
        token = os.getenv('DISCORD_TOKEN')
        if not token:
            print(f"❌ 環境變數 DISCORD_TOKEN 未設置")
            return False
        
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        client = discord.Client(intents=intents)
        
        async def on_ready():
            print(f"✅ Bot 已連接為 {client.user}")
            
            # 尋找置物櫃訊息
            try:
                # 遍歷所有 guild 尋找訊息
                found = False
                for guild in client.guilds:
                    try:
                        for channel in guild.text_channels:
                            try:
                                message = await channel.fetch_message(int(locker_msg_id))
                                if message:
                                    print(f"✅ 找到置物櫃訊息 (頻道: {channel.name})")
                                    print(f"✅ 已清除置物櫃緩存，訊息將在下次 Bot 重啟時自動刷新")
                                    print(f"\n💡 提示：")
                                    print(f"   - 紙娃娃 API URL 已更新")
                                    print(f"   - 緩存已清除")
                                    print(f"   - 用戶下次在 Discord 點擊「🔄 更新面板」時會顯示最新的紙娃娃")
                                    found = True
                                    break
                            except discord.NotFound:
                                pass
                            except Exception as e:
                                pass
                        
                        if found:
                            break
                    except Exception as e:
                        pass
                
                if not found:
                    print(f"⚠️  無法自動更新 embed（可能需要手動刷新）")
                    print(f"   用戶可在 Discord 中點擊「🔄 更新面板」按鈕")
            
            except Exception as e:
                print(f"⚠️  連接到 Discord 時出錯: {e}")
            
            finally:
                await client.close()
        
        client.event(on_ready)
        
        # 連接 Bot
        print(f"🔌 正在連接 Discord Bot...")
        await asyncio.wait_for(client.start(token), timeout=30)
        
    except asyncio.TimeoutError:
        print(f"⚠️  Bot 連接超時（可能網絡有延遲）")
        print(f"💡 緩存已清除，下次用戶刷新時會看到最新紙娃娃")
        return True
    except Exception as e:
        print(f"⚠️  Discord 連接失敗: {e}")
        print(f"💡 但緩存已清除，下次用戶刷新時會看到最新紙娃娃")
        return True
    
    print(f"\n✅ 置物櫃刷新完成！")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 force_refresh_user_locker.py <user_id>")
        print("範例: python3 force_refresh_user_locker.py 1430046213012590592")
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    try:
        success = asyncio.run(force_refresh_locker(user_id))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  操作已取消")
        sys.exit(1)
