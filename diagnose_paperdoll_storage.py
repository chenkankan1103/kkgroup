#!/usr/bin/env python3
"""
診斷 Discord 紙娃娃圖片存儲情況

用途：
- 檢查紙娃娃圖片存儲在哪個頻道
- 計算該頻道有多少條訊息
- 分析訊息時間分佈（何時開始累積）
- 檢查快取金鑰是否有效

在 GCP 上運行：
    python3 diagnose_paperdoll_storage.py
"""

import os
import asyncio
import discord
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path

# 加載環境變數
load_dotenv()

# 支持多個 token 名稱（優先級：DISCORD_TOKEN > UI_DISCORD_BOT_TOKEN > SHOP_DISCORD_BOT_TOKEN）
DISCORD_TOKEN = (os.getenv('DISCORD_TOKEN') or 
                 os.getenv('UI_DISCORD_BOT_TOKEN') or 
                 os.getenv('SHOP_DISCORD_BOT_TOKEN'))
FORUM_CHANNEL_ID = int(os.getenv('FORUM_CHANNEL_ID', '0'))
IMAGE_STORAGE_CHANNEL_ID = int(os.getenv('IMAGE_STORAGE_CHANNEL_ID', '0'))
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', '0'))

class DiagnosisBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.ready = False
    
    async def on_ready(self):
        self.ready = True
        print(f"✅ 已連接: {self.user}")
        await self.diagnose()
        await self.close()
    
    async def diagnose(self):
        """執行診斷"""
        print("\n" + "=" * 80)
        print("🔍 紙娃娃圖片存儲診斷")
        print("=" * 80)
        
        # 1️⃣ 檢查環境變數配置
        print("\n📋 環境變數配置：")
        print(f"  FORUM_CHANNEL_ID: {FORUM_CHANNEL_ID}")
        print(f"  IMAGE_STORAGE_CHANNEL_ID: {IMAGE_STORAGE_CHANNEL_ID}")
        print(f"  WELCOME_CHANNEL_ID: {WELCOME_CHANNEL_ID}")
        
        # 決定使用哪個頻道
        actual_storage_id = IMAGE_STORAGE_CHANNEL_ID or WELCOME_CHANNEL_ID
        print(f"  → 實際使用的存儲頻道 ID: {actual_storage_id}")
        
        # 2️⃣ 獲取頻道
        print("\n📀 頻道信息：")
        
        storage_channel = self.get_channel(actual_storage_id)
        if not storage_channel:
            print(f"  ❌ 找不到存儲頻道: {actual_storage_id}")
            return
        
        print(f"  ✅ 存儲頻道: {storage_channel.name} (ID: {storage_channel.id})")
        print(f"  📍 伺服器: {storage_channel.guild.name}")
        
        # 3️⃣ 掃描訊息
        print("\n🔎 掃描紙娃娃圖片訊息...")
        paperdoll_messages = []
        message_count = 0
        
        try:
            # 掃描最近 1000 條訊息
            async for message in storage_channel.history(limit=1000):
                message_count += 1
                
                # 檢查是否是紙娃娃圖片訊息
                if message.author == self.user:  # 機器人發送的訊息
                    if message.attachments:
                        # 檢查檔案名是否包含 "char_"
                        for attachment in message.attachments:
                            if 'char_' in attachment.filename or 'kkcoin_rank' not in attachment.filename:
                                paperdoll_messages.append({
                                    'id': message.id,
                                    'created_at': message.created_at,
                                    'attachment': attachment.filename,
                                    'size': attachment.size,
                                })
        
        except Exception as e:
            print(f"  ❌ 掃描失敗: {e}")
            return
        
        # 4️⃣ 統計結果
        print(f"\n📊 掃描結果：")
        print(f"  - 掃描訊息數: {message_count}")
        print(f"  - 紙娃娃圖片訊息: {len(paperdoll_messages)}")
        
        if paperdoll_messages:
            # 按時間排序
            paperdoll_messages.sort(key=lambda x: x['created_at'])
            
            oldest = paperdoll_messages[0]['created_at']
            newest = paperdoll_messages[-1]['created_at']
            
            print(f"  - 最早訊息: {oldest.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  - 最新訊息: {newest.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 計算總大小
            total_size = sum(msg['size'] for msg in paperdoll_messages)
            total_mb = total_size / (1024 * 1024)
            print(f"  - 總大小: {total_mb:.2f} MB")
            
            # 時間分佈分析
            print(f"\n📈 訊息時間分佈：")
            now = datetime.utcnow()
            
            time_buckets = {
                '最近 1 小時': 0,
                '最近 3 小時': 0,
                '最近 6 小時': 0,
                '最近 24 小時': 0,
                '超過 24 小時': 0,
            }
            
            for msg in paperdoll_messages:
                age = now - msg['created_at']
                if age < timedelta(hours=1):
                    time_buckets['最近 1 小時'] += 1
                elif age < timedelta(hours=3):
                    time_buckets['最近 3 小時'] += 1
                elif age < timedelta(hours=6):
                    time_buckets['最近 6 小時'] += 1
                elif age < timedelta(hours=24):
                    time_buckets['最近 24 小時'] += 1
                else:
                    time_buckets['超過 24 小時'] += 1
            
            for bucket, count in time_buckets.items():
                print(f"  {bucket}: {count} 條")
            
            # 5️⃣ 檢查快取鑰匙名稱
            print(f"\n🔑 快取鑰匙分析（前 10 條）：")
            for i, msg in enumerate(paperdoll_messages[:10], 1):
                filename = msg['attachment']
                created = msg['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                print(f"  {i}. {filename} ({created})")
            
            if len(paperdoll_messages) > 10:
                print(f"  ... 還有 {len(paperdoll_messages) - 10} 條訊息")
            
            # 6️⃣ 診斷建議
            print(f"\n💡 診斷建議：")
            if len(paperdoll_messages) > 100:
                print(f"  ⚠️ 警告：存儲頻道中有 {len(paperdoll_messages)} 條紙娃娃訊息")
                print(f"  建議清理舊訊息（超過 7 天以上）")
                
                # 計算舊訊息數
                old_cutoff = now - timedelta(days=7)
                old_count = sum(1 for msg in paperdoll_messages if msg['created_at'] < old_cutoff)
                print(f"  可安全清理的舊訊息: {old_count} 條")
            
            if time_buckets['最近 1 小時'] > 10:
                print(f"  ⚠️ 警告：最近 1 小時內上傳了 {time_buckets['最近 1 小時']} 條訊息")
                print(f"  可能表示有大量 API 調用或快取未命中")
            
            if not IMAGE_STORAGE_CHANNEL_ID:
                print(f"  ⚠️ 建議：設置 IMAGE_STORAGE_CHANNEL_ID 環境變數")
                print(f"  目前正使用歡迎頻道作為備用，請配置專用存儲頻道")
        
        else:
            print(f"  ✅ 存儲頻道中沒有紙娃娃圖片訊息")
        
        print("\n" + "=" * 80)

async def main():
    bot = DiagnosisBot()
    try:
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
