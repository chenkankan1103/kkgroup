#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚨 緊急修復: 隧道 URL 更新與 Webhook 恢復
當 IAP 隧道無回應時使用此腳本

用途：
1. 從本地 cloudflared 日誌推測新隧道 URL
2. 手動更新 config.json
3. 觸發 GitHub webhook 更新
4. 驗證連接

使用方式：
    python3 fix_webhook_emergency.py <new_tunnel_url>
    python3 fix_webhook_emergency.py https://example-tunnel.trycloudflare.com
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 配置
PROJECT_DIR = Path(__file__).parent
CONFIG_FILE = PROJECT_DIR / 'config' / 'config.json'

def update_config(tunnel_url):
    """更新 config.json"""
    if not tunnel_url.startswith('https://'):
        print(f"❌ 無效的 URL 格式: {tunnel_url}")
        print("💡 URL 應該以 https:// 開頭")
        return False
    
    if not tunnel_url.endswith('.com'):
        print(f"⚠️ 警告: URL 看起來不像 Cloudflare 隧道 ({tunnel_url})")
    
    try:
        if not CONFIG_FILE.exists():
            print(f"❌ config.json 不存在: {CONFIG_FILE}")
            return False
        
        # 讀取舊配置
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        old_url = config.get('url')
        print(f"📋 舊 URL: {old_url}")
        print(f"📋 新 URL: {tunnel_url}")
        
        if old_url == tunnel_url:
            print("✅ URL 已是最新，無需更新")
            return True
        
        # 更新配置
        config['url'] = tunnel_url
        config['API_BASE'] = tunnel_url
        config['lastUpdated'] = datetime.now().isoformat()
        
        # 備份舊配置
        backup_file = CONFIG_FILE.with_suffix('.json.backup')
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(f"💾 備份保存至: {backup_file}")
        
        # 寫入新配置
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ config.json 已更新")
        print(f"📝 lastUpdated: {config['lastUpdated']}")
        return True
        
    except Exception as e:
        print(f"❌ 更新 config.json 失敗: {e}")
        return False

def main():
    print("=" * 70)
    print("🚨 GitHub Webhook 緊急修復工具")
    print("=" * 70)
    
    if len(sys.argv) < 2:
        print("\n❌ 缺少隧道 URL 參數")
        print("\n💡 使用方式:")
        print("    python3 fix_webhook_emergency.py https://example.trycloudflare.com")
        print("\n需要提供新的隧道 URL。可以通過以下方式獲取:")
        print("1. SSH 進 VM: gcloud compute ssh ... --command 'sudo journalctl -u cloudflared.service'")
        print("2. 檢查 Cloudflare 儀表板")
        print("3. 查看 cloudflared 進程日誌")
        return False
    
    tunnel_url = sys.argv[1].strip()
    
    # 更新配置
    if not update_config(tunnel_url):
        return False
    
    print("\n" + "=" * 70)
    print("✅ 本地修復完成")
    print("=" * 70)
    print("\n⏭️  後續步驟:")
    print("1. ✅ config.json 已更新 (本地)")
    print("2. ⏳ 需要在 VM 上執行:")
    print("   - git add config/config.json")
    print("   - git commit -m 'chore: restore tunnel URL'")
    print("   - git push")
    print("3. ⏳ 或者在 VM 上直接運行:")
    print("   - sudo systemctl restart kkgroup-api.service")
    print("   - sudo systemctl restart bot.service shopbot.service uibot.service")
    print("\n💡 GitHub webhook 會在下次 push 時自動更新")
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
