#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GCP VM 诊断脚本 - 连接到 VM 并检查 Bot 状态
"""

import subprocess
import json
import sys

def run_gcloud(cmd):
    """运行 gcloud 命令并返回输出"""
    full_cmd = f'gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap --command "{cmd}"'
    print(f"\n📝 执行: {cmd}")
    print("-" * 70)
    
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        if result.stdout:
            print("✅ 输出：")
            print(result.stdout)
        
        if result.stderr:
            print("⚠️ 错误输出：")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ 命令成功 (exit code: 0)")
        else:
            print(f"❌ 命令失败 (exit code: {result.returncode})")
        
        return result.returncode, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        print("❌ 命令超时")
        return -1, "", "Timeout"
    except Exception as e:
        print(f"❌ 异常: {e}")
        return -1, "", str(e)

def main():
    print("=" * 70)
    print("🔍 GCP VM Bot 状态诊断")
    print("=" * 70)
    
    # 1. 检查实例状态
    print("\n1️⃣ 检查 VM 实例状态...")
    result = subprocess.run(
        'gcloud compute instances describe instance-20250501-142333 --zone us-central1-c --format="value(status)"',
        shell=True, capture_output=True, text=True
    )
    print(f"VM 状态: {result.stdout.strip()}")
    
    # 2. 检查 COMMANDS_DIR 配置
    print("\n2️⃣ 检查 COMMANDS_DIR 配置...")
    
    commands = [
        "cd /home/e193752468/kkgroup && grep 'COMMANDS_DIR' bots/bot.py",
        "cd /home/e193752468/kkgroup && grep 'COMMANDS_DIR' bots/shopbot.py",
        "cd /home/e193752468/kkgroup && grep 'COMMANDS_DIR' bots/uibot.py",
    ]
    
    for cmd in commands:
        run_gcloud(cmd)
    
    # 3. 检查服务状态
    print("\n3️⃣ 检查 Bot 服务状态...")
    
    services = ["bot.service", "shopbot.service", "uibot.service"]
    for svc in services:
        cmd = f"sudo systemctl is-active {svc}"
        rc, out, err = run_gcloud(cmd)
        print(f"   {svc}: {out.strip()}")
    
    # 4. 查看服务详细状态
    print("\n4️⃣ 检查服务详细状态...")
    for svc in services:
        cmd = f"sudo systemctl status {svc} --no-pager | head -15"
        run_gcloud(cmd)
    
    # 5. 查看最近日志
    print("\n5️⃣ 查看最近日志...")
    
    logs = [
        ("Bot Service", "sudo journalctl -u bot.service -n 20 --no-pager"),
        ("Shop Bot Service", "sudo journalctl -u shopbot.service -n 20 --no-pager"),
        ("UI Bot Service", "sudo journalctl -u uibot.service -n 20 --no-pager"),
    ]
    
    for name, cmd in logs:
        print(f"\n{name}:")
        run_gcloud(cmd)
    
    print("\n" + "=" * 70)
    print("✅ 诊断完成")
    print("=" * 70)

if __name__ == '__main__':
    main()
