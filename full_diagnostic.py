#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete diagnostic and deployment script
檢查本地代碼、提交到 GitHub、然後在 VM 上部署
"""
import os
import subprocess
import sys
import time

def run_command(cmd, description=""):
    """執行命令並返回結果"""
    print(f"\n{'='*60}")
    print(f"📝 {description or cmd}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=r'c:\Users\88697\Desktop\kkgroup',
            timeout=30
        )
        output = result.stdout + result.stderr
        print(f"✅ 命令返回碼: {result.returncode}")
        if output.strip():
            print(f"📋 輸出:\n{output[:2000]}")  # 最多2000個字符
        return result.returncode, output
    except Exception as e:
        print(f"❌ 命令執行失敗: {e}")
        return -1, str(e)

def main():
    print("=" * 60)
    print("🚀 完整診斷與部署流程")
    print("=" * 60)
    
    # Step 1: 驗證本地代碼
    print("\n【Step 1】驗證本地代碼修改")
    rc, _ = run_command(
        r"grep -n 'COMMANDS_DIR = \"cogs' bots/bot.py bots/shopbot.py bots/uibot.py",
        "檢查三個 bot 的 COMMANDS_DIR"
    )
    
    # Step 2: 檢查 git 狀態
    print("\n【Step 2】檢查 Git 狀態")
    run_command("git status --short", "顯示修改的文件")
    
    # Step 3: 檢查是否已提交
    print("\n【Step 3】檢查最新 commit")
    run_command("git log --oneline -5", "顯示最新 5 個 commits")
    
    # Step 4: 驗證本地修改是否正確
    print("\n【Step 4】驗證關鍵修改內容")
    bot_rc, _ = run_command(
        r"python -c \"import sys; sys.path.insert(0, '.'); from bots.bot import COMMANDS_DIR; print(f'bot.COMMANDS_DIR = {COMMANDS_DIR}')\"",
        "測試 bot.py 的 COMMANDS_DIR"
    )
    
    # Step 5: 在 VM 上執行診斷
    print("\n【Step 5】連接 GCP VM 進行遠程診斷")
    vm_commands = """
cd /home/e193752468/kkgroup
echo "=== Git Status ==="
git status
echo ""
echo "=== Current Branch ==="
git branch
echo ""
echo "=== Latest Commits ==="
git log --oneline -3
echo ""
echo "=== Check COMMANDS_DIR in remote ===" 
grep -n 'COMMANDS_DIR' bots/bot.py | head -1
echo ""
echo "=== Service Status ===" 
sudo systemctl is-active bot.service
sudo systemctl is-active shopbot.service
sudo systemctl is-active uibot.service
echo ""
echo "=== Recent Bot Logs ==="
sudo journalctl -u bot.service -n 5 --no-pager 2>/dev/null | head -5
"""
    
    # 將命令寫入 VM 上的臨時腳本
    remote_script_cmd = f'gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap --command "{vm_commands}"'
    run_command(remote_script_cmd, "在 VM 上執行診斷")
    
    print("\n" + "=" * 60)
    print("✅ 診斷完成！")
    print("=" * 60)
    print("""
下一步：
1. 如果本地代碼顯示 COMMANDS_DIR 正確，但 VM 上未更新，執行：
   git pull origin restructure-project-20260414
   
2. 重啟服務：
   sudo systemctl restart bot.service
   sudo systemctl restart shopbot.service
   sudo systemctl restart uibot.service
   
3. 檢查服務狀態：
   sudo systemctl status bot.service
""")

if __name__ == '__main__':
    main()
