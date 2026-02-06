#!/usr/bin/env python3
"""
簡化版紙娃娃診斷工具 - 直接指定token和頻道ID
在GCP上使用：python3 diagnose_paperdoll_simple.py <token> <channel_id>
"""

import asyncio
import discord
from datetime import datetime, timedelta
import sys

class SimpleBot(discord.Client):
    def __init__(self, token, channel_id):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.token = token
        self.channel_id = channel_id
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
        
        try:
            channel = self.get_channel(self.channel_id)
            if not channel:
                print(f"❌ 無法找到頻道 (ID: {self.channel_id})")
                return
            
            print(f"\n📍 頻道信息：")
            print(f"   名稱: {channel.name}")
            print(f"   ID: {channel.id}")
            print(f"   類型: {channel.type}")
            
            # 掃描訊息
            print(f"\n📊 掃描訊息中...")
            paperdoll_count = 0
            total_count = 0
            time_buckets = {
                "1h": 0,
                "3h": 0, 
                "6h": 0,
                "24h": 0,
                "older": 0
            }
            
            oldest_msg_time = None
            newest_msg_time = None
            total_size = 0
            
            now = datetime.utcnow()
            hour_1 = now - timedelta(hours=1)
            hour_3 = now - timedelta(hours=3)
            hour_6 = now - timedelta(hours=6)
            hour_24 = now - timedelta(hours=24)
            
            async for message in channel.history(limit=1000):
                total_count += 1
                
                # 統計時間分佈
                if message.created_at > hour_1:
                    time_buckets["1h"] += 1
                elif message.created_at > hour_3:
                    time_buckets["3h"] += 1
                elif message.created_at > hour_6:
                    time_buckets["6h"] += 1
                elif message.created_at > hour_24:
                    time_buckets["24h"] += 1
                else:
                    time_buckets["older"] += 1
                
                # 檢查附件
                for attachment in message.attachments:
                    if 'char_' in attachment.filename or attachment.filename.endswith('.png'):
                        paperdoll_count += 1
                        total_size += attachment.size / (1024 * 1024)  # MB
                
                if not oldest_msg_time or message.created_at < oldest_msg_time:
                    oldest_msg_time = message.created_at
                if not newest_msg_time or message.created_at > newest_msg_time:
                    newest_msg_time = message.created_at
            
            # 輸出結果
            print(f"\n📈 統計結果：")
            print(f"   總訊息數: {total_count}")
            print(f"   紙娃娃圖片數: {paperdoll_count}")
            print(f"   圖片總大小: {total_size:.2f} MB")
            
            if paperdoll_count > 0:
                avg_storage = total_size / paperdoll_count
                print(f"   平均單張大小: {avg_storage:.2f} MB")
            
            print(f"\n⏰ 時間分佈：")
            print(f"   過去1小時: {time_buckets['1h']} 條")
            print(f"   1-3小時前: {time_buckets['3h']} 條")
            print(f"   3-6小時前: {time_buckets['6h']} 條")
            print(f"   6-24小時前: {time_buckets['24h']} 條")
            print(f"   超過24小時: {time_buckets['older']} 條")
            
            if oldest_msg_time:
                print(f"\n📅 消息時間範圍：")
                print(f"   最舊: {oldest_msg_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                print(f"   最新: {newest_msg_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                time_diff = newest_msg_time - oldest_msg_time
                print(f"   跨度: {time_diff.days}天 {time_diff.seconds // 3600}小時")
            
            # 診斷結論
            print(f"\n🔍 診斷結論：")
            if paperdoll_count == 0:
                print(f"   ⚠️  此頻道中沒有找到紙娃娃圖片")
            elif time_buckets["1h"] > 20:
                print(f"   ⚠️  過去1小時有很多上傳 ({time_buckets['1h']} 條)")
                print(f"       可能有持續的API請求問題")
            elif paperdoll_count > 500:
                print(f"   ⚠️  紙娃娃圖片較多 ({paperdoll_count} 條)")
                print(f"       可能需要定期清理舊圖片")
            else:
                print(f"   ✅ 紙娃娃存儲狀態正常")
                print(f"       {paperdoll_count} 張圖片已保存")
                print(f"       存儲大小: {total_size:.2f} MB")
            
        except Exception as e:
            print(f"❌ 診斷出錯: {e}")
            import traceback
            traceback.print_exc()

async def main():
    # 從命令行參數獲取token和channel ID
    if len(sys.argv) < 3:
        print("用法: python3 diagnose_paperdoll_simple.py <token> <channel_id>")
        print("例子: python3 diagnose_paperdoll_simple.py 'YOUR_TOKEN' 1275688788806467635")
        sys.exit(1)
    
    token = sys.argv[1]
    try:
        channel_id = int(sys.argv[2])
    except ValueError:
        print(f"錯誤: channel_id 必須是整數，收到: {sys.argv[2]}")
        sys.exit(1)
    
    bot = SimpleBot(token, channel_id)
    try:
        await bot.start(token)
    except Exception as e:
        print(f"❌ 無法連接到Discord: {e}")

if __name__ == "__main__":
    asyncio.run(main())
