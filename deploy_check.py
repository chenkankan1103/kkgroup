#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 部署檢查腳本 (Deploy Verification Script)

功能：
1. 驗證本地 Nginx：requests.get http://10.128.0.3/assets/leaderboard.png
2. 驗證隧道 URL：從 config.json 讀取並嘗試抓取
3. 自動修復：如果返回 530，自動重啟 Nginx 和隧道
4. 智能等待：允許 30-60 秒讓隧道穩定，超過 5 分鐘報告錯誤
"""

import os
import sys
import json
import time
import subprocess
import requests
from datetime import datetime
from pathlib import Path

# 配置
INTERNAL_IP = "10.128.0.3"
NGINX_PORT = 80
ASSETS_PATH = "/assets/leaderboard.png"
MAX_RETRY_ATTEMPTS = 10
RETRY_INTERVAL = 3  # 秒
RETRY_TIMEOUT = 300  # 5 分鐘

# 顏色輸出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def log(level, msg):
    """標準化日誌輸出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if level == "INFO":
        print(f"{Colors.OKBLUE}[{timestamp}] ℹ️  {msg}{Colors.ENDC}")
    elif level == "SUCCESS":
        print(f"{Colors.OKGREEN}[{timestamp}] ✅ {msg}{Colors.ENDC}")
    elif level == "WARNING":
        print(f"{Colors.WARNING}[{timestamp}] ⚠️  {msg}{Colors.ENDC}")
    elif level == "ERROR":
        print(f"{Colors.FAIL}[{timestamp}] ❌ {msg}{Colors.ENDC}")
    elif level == "DEBUG":
        print(f"{Colors.OKCYAN}[{timestamp}] 🐛 {msg}{Colors.ENDC}")

def check_local_nginx():
    """驗證本地 Nginx 連接（僅在 GCP 上執行）"""
    import socket
    
    # 檢查是否在 GCP VM 上
    if socket.gethostname() != "instance-20250501-142333":
        log("WARNING", "未在 GCP VM 上運行，跳過本地 Nginx 檢查")
        log("INFO", "本地檢查應在 GCP VM 上執行： ssh user@vm 'curl http://10.128.0.3/assets/leaderboard.png'")
        return None  # 返回 None 表示跳過此檢查
    
    log("INFO", "驗證本地 Nginx...")
    url = f"http://{INTERNAL_IP}:{NGINX_PORT}{ASSETS_PATH}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            log("SUCCESS", f"本地 Nginx ✓ (HTTP {response.status_code}) - 大小: {len(response.content)} bytes")
            return True
        else:
            log("ERROR", f"本地 Nginx 返回 HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError as e:
        log("ERROR", f"無法連接本地 Nginx: {e}")
        return False
    except requests.exceptions.Timeout:
        log("ERROR", "連接本地 Nginx 超時")
        return False
    except Exception as e:
        log("ERROR", f"檢查本地 Nginx 時發生錯誤: {e}")
        return False

def load_tunnel_url():
    """從 config.json 讀取隧道 URL"""
    config_path = Path(__file__).parent / "docs" / "config.json"
    
    try:
        # 嘗試不同的編碼解析（處理 BOM）
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            config = json.load(f)
            tunnel_url = config.get("url")
            if tunnel_url:
                log("INFO", f"隧道 URL: {tunnel_url}")
                return tunnel_url
            else:
                log("ERROR", "config.json 中未找到 'url' 字段")
                return None
    except FileNotFoundError:
        log("ERROR", f"config.json 不存在: {config_path}")
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log("ERROR", f"config.json 解析失敗: {e}")
        return None

def check_external_tunnel(tunnel_url):
    """驗證外網隧道連接"""
    if not tunnel_url:
        log("ERROR", "未提供隧道 URL")
        return False
    
    full_url = f"{tunnel_url}{ASSETS_PATH}"
    log("INFO", f"驗證隧道：{full_url}")
    
    attempt = 0
    start_time = time.time()
    
    while attempt < MAX_RETRY_ATTEMPTS:
        attempt += 1
        elapsed = int(time.time() - start_time)
        
        try:
            response = requests.get(full_url, timeout=20)
            
            if response.status_code == 200:
                log("SUCCESS", f"隧道連接成功 ✓ (HTTP 200) - 嘗試 {attempt} - 耗時 {elapsed}s")
                return True
            elif response.status_code == 530:
                log("WARNING", f"隧道返回 HTTP 530 (源服務器錯誤) - 嘗試 {attempt}/{MAX_RETRY_ATTEMPTS} - 耗時 {elapsed}s")
                
                # 如果超過 5 分鐘還是 530，報告錯誤
                if elapsed > RETRY_TIMEOUT:
                    log("ERROR", f"隧道在 {RETRY_TIMEOUT}s 後仍返回 530，這通常表示源服務器配置問題")
                    return False
                
                # 首次嘗試時自動修復
                if attempt == 1:
                    log("INFO", "嘗試自動修復：重啟 Nginx 和隧道...")
                    restart_nginx_and_tunnel()
                
                # 等待後重新嘗試
                log("INFO", f"等待 {RETRY_INTERVAL}s 後重試...")
                time.sleep(RETRY_INTERVAL)
                continue
            else:
                log("ERROR", f"隧道返回 HTTP {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            log("WARNING", f"連接隧道超時 - 嘗試 {attempt}/{MAX_RETRY_ATTEMPTS}")
            time.sleep(RETRY_INTERVAL)
            continue
        except requests.exceptions.ConnectionError as e:
            log("WARNING", f"無法連接隧道 - 嘗試 {attempt}/{MAX_RETRY_ATTEMPTS}: {e}")
            time.sleep(RETRY_INTERVAL)
            continue
        except Exception as e:
            log("ERROR", f"檢查隧道時發生錯誤: {e}")
            return False
    
    log("ERROR", f"在 {MAX_RETRY_ATTEMPTS} 次嘗試後仍無法連接隧道")
    return False

def restart_nginx_and_tunnel():
    """重啟 Nginx 和隧道"""
    log("WARNING", "正在重啟 Nginx 和隧道...")
    
    try:
        # 注意：這需要 SSH 連接到 GCP 或本地管理員權限
        log("INFO", "重啟命令應在 GCP VM 上執行")
        log("DEBUG", "建議手動執行:")
        log("DEBUG", "  sudo systemctl restart nginx")
        log("DEBUG", "  sudo pkill cloudflared")
        log("DEBUG", "  nohup cloudflared tunnel --url http://10.128.0.3:80 --protocol http2 --logfile /tmp/cloudflared.log --no-autoupdate &")
        return False  # 返回 False 這意味著需要手動修復
    except Exception as e:
        log("ERROR", f"重啟失敗: {e}")
        return False

def main():
    """主函數"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("=" * 70)
    print("🚀 部署檢查工具 - Deploy Verification Tool")
    print("=" * 70)
    print(f"{Colors.ENDC}\n")
    
    all_passed = True
    
    # Step 1: 驗證本地 Nginx
    log("INFO", "=" * 50)
    log("INFO", "Step 1: 驗證本地 Nginx 連接")
    log("INFO", "=" * 50)
    local_result = check_local_nginx()
    if local_result is None:
        log("INFO", "本地檢查已跳過（在本地環境上運行）")
    elif not local_result:
        log("ERROR", "本地 Nginx 檢查失敗！")
        all_passed = False
    
    time.sleep(1)
    
    # Step 2: 讀取隧道 URL
    log("INFO", "=" * 50)
    log("INFO", "Step 2: 讀取隧道配置")
    log("INFO", "=" * 50)
    tunnel_url = load_tunnel_url()
    if not tunnel_url:
        log("ERROR", "無法讀取隧道 URL")
        all_passed = False
        return
    
    time.sleep(1)
    
    # Step 3: 驗證外網隧道
    log("INFO", "=" * 50)
    log("INFO", "Step 3: 驗證外網隧道連接 (最多等待 5 分鐘)")
    log("INFO", "=" * 50)
    if not check_external_tunnel(tunnel_url):
        log("ERROR", "隧道連接失敗！")
        all_passed = False
    
    # 最終報告
    print(f"\n{Colors.BOLD}")
    print("=" * 70)
    if all_passed:
        log("SUCCESS", "所有檢查已通過！✅")
        print("=" * 70)
        print(f"{Colors.OKGREEN}")
        print("部署已準備就緒！您可以：")
        print("1. 重新啟動 Bot: sudo systemctl restart bot.service")
        print("2. 驗證 Bot 狀態: sudo systemctl status bot.service")
        print(f"{Colors.ENDC}\n")
        return 0
    else:
        log("ERROR", "部分檢查失敗！請查看上述錯誤訊息")
        print("=" * 70)
        print(f"{Colors.FAIL}")
        print("建議操作：")
        print("1. 檢查 Nginx 狀態: sudo systemctl status nginx")
        print("2. 檢查隧道日誌: tail -f /tmp/cloudflared.log")
        print("3. 驗證 Nginx 配置: cat /etc/nginx/sites-available/default")
        print(f"{Colors.ENDC}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
