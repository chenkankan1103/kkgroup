#!/usr/bin/env python3
"""
Bot 狀態檢查和重啟工具 - 使用 SSH 鑰匙登入
"""
import subprocess
import time
import sys

GCP_USER = "e193752468"
GCP_IP = "35.206.126.157"
GCP_ALIAS = "gcp-kkgroup"  # 使用已配置的別名
SSH_KEY = r"C:\Users\88697\.ssh\google_compute_engine"

def run_ssh_command(cmd, timeout=20):
    """執行 SSH 命令"""
    try:
        # 優先使用別名，如果失敗則用 IP + 鑰匙
        full_cmd = f'ssh {GCP_ALIAS} "{cmd}"'
        print(f"  執行: {cmd}")
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "連接超時"
    except Exception as e:
        return -2, "", str(e)

def main():
    print("=" * 60)
    print("🤖 Discord Bot 狀態檢查 & 重啟工具")
    print("=" * 60)
    
    print(f"\n🔗 連接參數:")
    print(f"   用戶: {GCP_USER}")
    print(f"   IP: {GCP_IP}")
    print(f"   鑰匙: {SSH_KEY}")
    
    # 1. 連接測試
    print("\n1️⃣ 測試連接...")
    code, out, err = run_ssh_command("echo 'OK'", timeout=15)
    if code == 0:
        print("   ✅ 連接成功")
    else:
        print(f"   ❌ 連接失敗: {err}")
        return
    
    # 2. 檢查 Bot 進程
    print("\n2️⃣ 檢查 Bot 進程...")
    code, out, err = run_ssh_command("pgrep -f 'python.*bot.py' | wc -l", timeout=10)
    if code == 0:
        count = int(out) if out.isdigit() else 0
        print(f"   發現 {count} 個 Bot 進程")
        if count > 1:
            print(f"   ⚠️ 警告：進程數過多，可能有重複")
    else:
        print(f"   ⚠️ 檢查失敗")
    
    # 3. 檢查服務狀態
    print("\n3️⃣ 檢查 systemd 服務...")
    code, out, err = run_ssh_command("systemctl is-active bot.service", timeout=10)
    if code == 0:
        print(f"   服務狀態: {out}")
    
    # 4. 重啟 Bot
    print("\n4️⃣ 重啟 Bot 服務...")
    code, out, err = run_ssh_command("sudo systemctl restart bot.service", timeout=15)
    if code == 0 or "Failed" not in err:
        print("   ✅ 重啟命令已發送")
    else:
        print(f"   ⚠️ 重啟可能失敗: {err}")
    
    # 5. 等待
    print("\n5️⃣ 等待重啟完成...(5秒)")
    time.sleep(5)
    
    # 6. 驗證
    print("\n6️⃣ 驗證狀態...")
    code, out, err = run_ssh_command("pgrep -f 'python.*bot.py' | wc -l", timeout=10)
    if code == 0:
        count = int(out) if out.isdigit() else 0
        if count > 0:
            print(f"   ✅ Bot 已成功重啟！({count} 個進程)")
        else:
            print(f"   ❌ Bot 進程未啟動")
    
    # 7. 檢查 Discord 連線日誌
    print("\n7️⃣ 檢查最近的日誌...")
    code, out, err = run_ssh_command(
        "journalctl -u bot.service -n 5 --no-pager",
        timeout=10
    )
    if code == 0 and out:
        print("   最近的日誌:")
        for line in out.split('\n')[-5:]:
            if line.strip():
                print(f"   {line}")
    
    print("\n" + "=" * 60)
    print("✨ 檢查完成！")
    print("   🎮 機器人應該已在 Discord 上線")
    print("   ⏳ 如果看不到，請等待 30 秒再檢查")
    print("=" * 60)

if __name__ == "__main__":
    main()
