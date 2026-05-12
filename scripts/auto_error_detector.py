#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動錯誤檢測器
監控系統日誌，檢測特定錯誤並自動觸發 GitHub Actions 修復
"""

import os
import asyncio
import aiohttp
import json
import subprocess
from datetime import datetime, timedelta
import re

class AutoErrorDetector:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo_owner = "chenkankan1103"
        self.repo_name = "kkgroup"
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.last_error_time = {}
        self.error_patterns = {
            "name_self_error": r"name\s*['\"]\s*self\s*['\"]\s*is\s*not\s*defined",
            "syntax_error": r"SyntaxError",
            "import_error": r"ImportError",
            "attribute_error": r"AttributeError"
        }
        
    async def check_system_logs(self):
        """檢查系統日誌中的錯誤"""
        errors_found = []
        
        # 檢查 Discord Bot 日誌
        try:
            # 獲取最近的系統日誌
            log_files = [
                "/var/log/syslog",
                "/var/log/kern.log",
                "/home/e193752468/.local/share/logs/discord_bot.log"
            ]
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    print(f"🔍 檢查日誌文件: {log_file}")
                    
                    # 讀取最近的日誌內容
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()[-1000:]  # 只讀取最後1000行
                            
                        for line in lines:
                            # 檢查各種錯誤模式
                            for error_name, pattern in self.error_patterns.items():
                                if re.search(pattern, line, re.IGNORECASE):
                                    timestamp = self.extract_timestamp(line)
                                    
                                    # 檢查是否需要觸發（避免重複觸發）
                                    if self.should_trigger_error(error_name, timestamp):
                                        errors_found.append({
                                            "type": error_name,
                                            "message": line.strip(),
                                            "timestamp": timestamp,
                                            "file": log_file
                                        })
                                        
                    except Exception as e:
                        print(f"❌ 讀取日誌文件失敗 {log_file}: {e}")
                        
        except Exception as e:
            print(f"❌ 檢查系統日誌失敗: {e}")
            
        return errors_found
    
    def extract_timestamp(self, log_line):
        """從日誌行中提取時間戳"""
        # 嘗試匹配常見的時間戳格式
        timestamp_patterns = [
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',  # YYYY-MM-DD HH:MM:SS
            r'(\w{3}\s+\d{2}\s+\d{2}:\d{2}:\d{2})',   # Mon DD HH:MM:SS
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})',  # MM/DD/YYYY HH:MM:SS
        ]
        
        for pattern in timestamp_patterns:
            match = re.search(pattern, log_line)
            if match:
                return match.group(1)
        
        return datetime.now().isoformat()
    
    def should_trigger_error(self, error_type, timestamp):
        """判斷是否應該觸發錯誤處理"""
        # 檢查冷卻時間（避免重複觸發）
        if error_type in self.last_error_time:
            last_time = self.last_error_time[error_type]
            current_time = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
            
            # 如果同一類型錯誤在 10 分鐘內已經觸發過，則跳過
            if current_time - last_time < timedelta(minutes=10):
                return False
        
        # 更新最後觸發時間
        self.last_error_time[error_type] = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        return True
    
    async def trigger_github_action(self, error_data):
        """觸發 GitHub Actions 進行自動修復"""
        try:
            # 準備觸發數據
            payload = {
                "error_type": "name_self_error_fix",
                "timestamp": datetime.now().isoformat(),
                "severity": "high",
                "error_data": error_data,
                "source": "auto_error_detector"
            }
            
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json"
            }
            
            # 觸發 repository_dispatch 事件
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/dispatches"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 204:
                        print("✅ 成功觸發 GitHub Actions 自動修復")
                        return True
                    else:
                        error_text = await response.text()
                        print(f"❌ 觸發 GitHub Actions 失敗: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            print(f"❌ 觸發 GitHub Actions 時發生異常: {e}")
            return False
    
    async def send_discord_notification(self, error_data):
        """發送 Discord 通知"""
        if not self.webhook_url:
            return
        
        try:
            webhook_data = {
                "content": f"🚨 **自動錯誤檢測**",
                "embeds": [{
                    "title": "檢測到系統錯誤",
                    "description": f"已自動觸發 GitHub Actions 進行修復",
                    "color": 0xFF0000,
                    "fields": [
                        {"name": "🔍 錯誤類型", "value": error_data.get("type", "未知"), "inline": True},
                        {"name": "📁 錯誤文件", "value": error_data.get("file", "未知"), "inline": True},
                        {"name": "⏰ 檢測時間", "value": error_data.get("timestamp", datetime.now().isoformat()), "inline": True},
                        {"name": "🤖 處理狀態", "value": "已觸發自動修復", "inline": True}
                    ]
                }]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=webhook_data) as response:
                    if response.status == 204:
                        print("✅ Discord 通知發送成功")
                    else:
                        print(f"❌ Discord 通知發送失敗: {response.status}")
                        
        except Exception as e:
            print(f"❌ 發送 Discord 通知失敗: {e}")
    
    async def monitor_loop(self):
        """監控循環"""
        print("🚀 自動錯誤檢測器啟動")
        
        while True:
            try:
                print("🔍 開始檢查系統日誌...")
                
                # 檢查系統日誌
                errors = await self.check_system_logs()
                
                if errors:
                    print(f"🚨 檢測到 {len(errors)} 個錯誤")
                    
                    for error in errors:
                        print(f"🔍 錯誤詳情: {error}")
                        
                        # 發送 Discord 通知
                        await self.send_discord_notification(error)
                        
                        # 觸發 GitHub Actions 修復
                        await self.trigger_github_action(error)
                        
                        # 等待一段時間避免重複觸發
                        await asyncio.sleep(30)
                else:
                    print("✅ 未檢測到錯誤")
                
                # 等待下次檢查（每 2 分鐘檢查一次）
                await asyncio.sleep(120)
                
            except Exception as e:
                print(f"❌ 監控循環發生異常: {e}")
                await asyncio.sleep(30)  # 異常時等待 30 秒後重試

async def main():
    """主函數"""
    print("🚀 啟動自動錯誤檢測器")
    
    # 檢查環境變數
    required_vars = ["GITHUB_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ 缺少必要環境變數: {', '.join(missing_vars)}")
        print("請設置以下環境變數:")
        for var in missing_vars:
            print(f"  export {var}=your_token_here")
        return
    
    # 啟動監控系統
    detector = AutoErrorDetector()
    await detector.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())
