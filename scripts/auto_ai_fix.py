#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動 AI 修復腳本
由 GitHub Actions 觸發，執行 AI 分析和修復代碼生成
"""

import os
import asyncio
import json
import subprocess
from datetime import datetime
import pytz

async def analyze_and_fix(event_data, nvidia_api_key, discord_webhook):
    """AI 分析和生成修復代碼"""
    try:
        import sys
        workspace_path = os.getenv('GITHUB_WORKSPACE', '.')
        sys.path.insert(0, workspace_path)
        from utils.google_ai import GoogleAIClient
        from utils.nvidia_ai import NVIDIAAIClient
        
        client = NVIDIAAIClient()
        print("✅ NVIDIA AI 客戶端初始化成功")
        
        # 獲取錯誤日誌
        payload = event_data.get('client_payload', {})
        error_logs = (
            payload.get('error_logs')
            or payload.get('error_data')
            or payload.get('log_text')
            or event_data.get('error_logs')
            or {}
        )
        if isinstance(error_logs, str):
            error_logs = {'log': error_logs}
        timestamp = payload.get('timestamp') or event_data.get('timestamp') or datetime.now().isoformat()
        severity = payload.get('severity') or event_data.get('severity') or 'medium'
        
        # 構建分析提示
        analysis_prompt = f"""你是KKGroup Discord Bot系統的AI除錯和修復專家。
        
        系統環境：
        - GCP VM: e2-micro (1GB RAM + 4GB swap)
        - 三個Bot服務: bot.service, shopbot.service, uibot.service
        - 技術棧: Python 3.11 + Discord.py + systemd
        
        錯誤日誌：
        {json.dumps(error_logs, ensure_ascii=False, indent=2)}
        
        時間：{timestamp}
        緊急程度：{severity}
        
        請分析並生成修復代碼：
        1. 根本原因分析
        2. 具體修復代碼（Python）
        3. 修復後的驗證方法
        4. 預防措施
        
        請以JSON格式回覆：
        {{
            "root_cause": "技術根本原因",
            "fix_code": "具體修復代碼",
            "verification": "驗證方法",
            "prevention": "預防措施",
            "file_path": "修復文件路徑"
        }}"""
        
        # 調用 NVIDIA AI
        messages = [
            {"role": "system", "content": "你是KKGroup Discord Bot系統的AI除錯和修復專家，請生成可執行的修復代碼。"},
            {"role": "user", "content": analysis_prompt}
        ]
        
        response = await client.call_api(
            messages, 
            model="deepseek-ai/deepseek-v4-pro", 
            max_tokens=2000
        )

        if not response:
            print("⚠️ NVIDIA 無回應，改用 Gemini 備援")
            response = await GoogleAIClient().call_api(
                messages,
                temperature=0.2,
                max_tokens=2000,
            )
        
        if response:
            try:
                result = json.loads(response)
                print("✅ AI 分析和修復代碼生成成功")
                return result
            except json.JSONDecodeError:
                print("⚠️ AI 回應不是有效JSON，嘗試提取修復代碼")
                return {
                    "root_cause": "AI 分析完成",
                    "fix_code": response,
                    "verification": "手動驗證修復效果",
                    "prevention": "定期檢查系統狀態",
                    "file_path": "fixes/auto_fix.py"
                }
        else:
            print("❌ NVIDIA AI 調用失敗")
            return None
            
    except ImportError as e:
        print(f"❌ NVIDIA AI 導入失敗: {e}")
        return None
    except Exception as e:
        print(f"❌ AI 分析過程發生錯誤: {e}")
        return None

async def create_fix_file(fix_data, timestamp, severity):
    """創建修復文件並提交"""
    if not fix_data:
        return False
    
    try:
        # 獲取修復代碼和文件路徑
        fix_code = fix_data.get('fix_code', '')
        file_path = fix_data.get('file_path', 'fixes/auto_fix.py')
        
        print(f"📝 創建修復文件: {file_path}")
        
        # 確保目錄存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 寫入修復代碼
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動生成的修復代碼
生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
AI 分析結果: {fix_data.get('root_cause', 'N/A')}
"""

{fix_code}

# 驗證方法
# {fix_data.get('verification', '手動驗證修復效果')}

# 預防措施
# {fix_data.get('prevention', '定期檢查系統狀態')}
''')
        
        # 配置 Git
        subprocess.run(['git', 'config', 'user.name', 'AI Auto Fix Bot'], check=True)
        subprocess.run(['git', 'config', 'user.email', 'ai-fix@kkgroup.local'], check=True)
        
        # 添加文件到 Git
        subprocess.run(['git', 'add', file_path], check=True)

        staged_changes = subprocess.run(['git', 'diff', '--cached', '--quiet'], check=False)
        if staged_changes.returncode == 0:
            print(f"ℹ️ 修復文件 {file_path} 沒有實際差異，跳過 commit/push")
            return True
        
        # 提交修復
        commit_message = f"""fix: AI 自動修復 - {fix_data.get('root_cause', '未知錯誤')}

🤖 由 NVIDIA deepseek-v4-pro 自動生成修復代碼
📊 錯誤時間: {timestamp}
🚨 緊急程度: {severity}
🔧 修復文件: {file_path}
"""
        
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        
        # 推送到遠端
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
        
        print(f"✅ 修復代碼已提交並推送到: {file_path}")
        return True
        
    except Exception as e:
        print(f"❌ 創建修復文件失敗: {e}")
        return False

async def send_discord_notification(fix_data, success, discord_webhook):
    """發送 Discord 通知"""
    if not discord_webhook:
        return
    
    color = 0x00FF00 if success else 0xFF0000
    status = "✅ 修復成功" if success else "❌ 修復失敗"
    
    webhook_data = {
        "content": f"🤖 **AI 自動修復** - {status}",
        "embeds": [{
            "title": "🔧 自動修復報告",
            "description": f"根據錯誤分析生成的修復代碼",
            "color": color,
            "fields": [
                {"name": "🤖 AI引擎", "value": "NVIDIA deepseek-v4-pro", "inline": True},
                {"name": "⏰ 修復時間", "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "inline": True},
                {"name": "📁 修復文件", "value": fix_data.get('file_path', 'N/A'), "inline": True},
                {"name": "🔍 根本原因", "value": fix_data.get('root_cause', 'N/A')[:100], "inline": False}
            ]
        }]
    }
    
    try:
        import requests
        response = requests.post(discord_webhook, json=webhook_data)
        if response.status_code == 204:
            print("✅ Discord 通知發送成功")
        else:
            print(f"❌ Discord 通知發送失敗: {response.status_code}")
    except Exception as e:
        print(f"❌ 發送 Discord 通知失敗: {e}")

async def main():
    """主執行流程"""
    print("🚀 開始 AI 自動修復流程")
    
    # 獲取環境變數
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    discord_webhook = os.getenv("DISCORD_WEBHOOK")
    
    # 獲取觸發數據
    event_data_str = os.getenv("GITHUB_EVENT_DATA", "{}")
    event_data = json.loads(event_data_str)
    
    print(f"📊 事件數據: {event_data}")
    
    # AI 分析和生成修復代碼
    fix_data = await analyze_and_fix(event_data, nvidia_api_key, discord_webhook)
    
    if fix_data:
        # 獲取錯誤信息
        payload = event_data.get('client_payload', {})
        timestamp = payload.get('timestamp', datetime.now().isoformat())
        severity = payload.get('severity', 'medium')
        
        # 創建修復文件並提交
        success = await create_fix_file(fix_data, timestamp, severity)
        
        # 發送通知
        await send_discord_notification(fix_data, success, discord_webhook)
    else:
        print("❌ 無法生成修復代碼")

if __name__ == "__main__":
    asyncio.run(main())
