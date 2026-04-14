#!/usr/bin/env python3
"""
🔐 KK 園區 Discord OAuth 系統健康檢查
驗證 OAuth 配置和後端端點
"""

import requests
import json
import os
from datetime import datetime
from urllib.parse import urljoin

# ========== 配置 ==========
TUNNEL_URL = "https://katrina-brief-fish-educators.trycloudflare.com"
API_BASE = urljoin(TUNNEL_URL, "/api/auth")

# 顏色輸出
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def log_header(msg: str):
    """打印標題"""
    print(f"\n{BLUE}{BOLD}{'='*60}{RESET}")
    print(f"{BLUE}{BOLD}✓ {msg}{RESET}")
    print(f"{BLUE}{BOLD}{'='*60}{RESET}\n")

def log_success(msg: str):
    """打印成功消息"""
    print(f"{GREEN}✅ {msg}{RESET}")

def log_error(msg: str):
    """打印錯誤消息"""
    print(f"{RED}❌ {msg}{RESET}")

def log_warning(msg: str):
    """打印警告消息"""
    print(f"{YELLOW}⚠️  {msg}{RESET}")

def log_info(msg: str):
    """打印信息"""
    print(f"{BLUE}ℹ️  {msg}{RESET}")

def check_env_config():
    """檢查 .env 配置"""
    log_header("環境配置檢查")
    
    required_vars = {
        'DISCORD_CLIENT_ID': 'Discord 應用 ID',
        'DISCORD_CLIENT_SECRET': 'Discord 應用密鑰',
        'DISCORD_REDIRECT_URI': 'OAuth 回調 URI',
        'SESSION_SECRET': '會話加密密鑰'
    }
    
    issues = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            log_error(f"缺少環境變數: {var} ({description})")
            issues.append(var)
        elif value.startswith('YOUR_') or value == 'placeholder':
            log_warning(f"{var} 仍為佔位符: {value}")
            issues.append(var)
        else:
            # 顯示部分值用於驗證
            if var == 'DISCORD_CLIENT_SECRET':
                display = f"{value[:10]}...***"
            else:
                display = value
            log_success(f"{var}: {display}")
    
    if not issues:
        log_success("所有環境變數配置完整！")
    else:
        log_error(f"發現 {len(issues)} 個問題需要修復")
    
    return len(issues) == 0

def check_tunnel_connectivity():
    """檢查隧道連接"""
    log_header("隧道連接檢查")
    
    try:
        response = requests.get(f"{TUNNEL_URL}/api/auth/status", timeout=5)
        if response.status_code == 200:
            log_success(f"隧道可連接: {TUNNEL_URL}")
            data = response.json()
            log_info(f"系統狀態: {data.get('status', 'unknown')}")
            return True
        else:
            log_error(f"隧道回應異常: HTTP {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        log_error(f"隧道連接超時: {TUNNEL_URL}")
        return False
    except requests.exceptions.ConnectionError:
        log_error(f"無法連接隧道: {TUNNEL_URL}")
        log_warning("請確保 GCP VM 上的 Flask API 正在運行")
        return False
    except Exception as e:
        log_error(f"連接錯誤: {str(e)}")
        return False

def check_oauth_endpoints():
    """檢查 OAuth 端點"""
    log_header("OAuth 端點檢查")
    
    endpoints = {
        '/login': 'GET',
        '/verify': 'GET',
        '/user': 'GET',
        '/logout': 'POST',
        '/status': 'GET'
    }
    
    working = 0
    
    for endpoint, method in endpoints.items():
        url = urljoin(API_BASE, endpoint)
        try:
            if method == 'GET':
                response = requests.get(url, timeout=3)
            else:  # POST
                response = requests.post(url, timeout=3)
            
            if response.status_code in [200, 400, 401, 403]:
                # 200: 成功,  400/401/403: 預期回應
                log_success(f"{method} {endpoint}: HTTP {response.status_code}")
                working += 1
            else:
                log_error(f"{method} {endpoint}: HTTP {response.status_code} (異常)")
                
        except requests.exceptions.Timeout:
            log_error(f"{method} {endpoint}: 超時")
        except requests.exceptions.ConnectionError:
            log_error(f"{method} {endpoint}: 連接失敗")
        except Exception as e:
            log_error(f"{method} {endpoint}: {str(e)}")
    
    log_info(f"有效端點: {working}/{len(endpoints)}")
    return working == len(endpoints)

def check_oauth_url():
    """檢查 OAuth 登與 URL 生成"""
    log_header("OAuth URL 生成檢查")
    
    try:
        response = requests.get(f"{API_BASE}/login", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'oauth_url' in data:
                oauth_url = data['oauth_url']
                log_success("OAuth URL 成功生成！")
                log_info(f"URL 長度: {len(oauth_url)} 字符")
                
                # 驗證 URL 結構
                if 'discord.com' in oauth_url:
                    log_success("URL 指向 Discord OAuth 端點")
                else:
                    log_warning("URL 可能不指向 Discord")
                
                if 'client_id' in oauth_url:
                    log_success("URL 包含 client_id 參數")
                else:
                    log_error("URL 缺少 client_id 參數")
                
                if 'redirect_uri' in oauth_url:
                    log_success("URL 包含 redirect_uri 參數")
                else:
                    log_error("URL 缺少 redirect_uri 參數")
                
                return True
            else:
                log_error("回應缺少 oauth_url 字段")
                log_info(f"回應: {json.dumps(data, ensure_ascii=False, indent=2)}")
                return False
                
        else:
            log_error(f"API 回應異常: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log_error(f"OAuth URL 檢查失敗: {str(e)}")
        return False

def check_backend_files():
    """檢查後端文件"""
    log_header("後端文件檢查")
    
    files = {
        'blueprints/discord_auth.py': 'Discord OAuth Blueprint',
        'unified_api.py': '統一 API 伺服器',
        '.env': '環境配置文件'
    }
    
    all_exist = True
    
    for filepath, description in files.items():
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            log_success(f"{filepath} ({description}): {size} 字節")
        else:
            log_error(f"缺少文件: {filepath} ({description})")
            all_exist = False
    
    return all_exist

def check_frontend_integration():
    """檢查前端集成"""
    log_header("前端集成檢查")
    
    frontend_file = 'docs/index.html'
    
    if not os.path.exists(frontend_file):
        log_error(f"前端文件不存在: {frontend_file}")
        return False
    
    with open(frontend_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        'loginDiscord()': '登入函數',
        'verifyAuth()': '驗證函數',
        'logout()': '登出函數',
        'auth_token': 'Token 管理',
        '/api/auth/login': 'OAuth 端點調用',
        '/api/auth/verify': '驗證端點調用',
        '/api/auth/logout': '登出端點調用',
        'localStorage.setItem': 'Token 存儲',
        'localStorage.getItem': 'Token 讀取'
    }
    
    found = 0
    
    for check, description in checks.items():
        if check in content:
            log_success(f"✓ 已實現: {description}")
            found += 1
        else:
            log_warning(f"✗ 缺少: {description}")
    
    log_info(f"前端實現完成度: {found}/{len(checks)}")
    return found == len(checks)

def generate_report():
    """生成完整報告"""
    log_header("KK 園區 OAuth 系統健康檢查完成")
    
    checks = [
        ("✓ 環境配置", check_env_config()),
        ("✓ 隧道連接", check_tunnel_connectivity()),
        ("✓ 後端文件", check_backend_files()),
        ("✓ OAuth 端點", check_oauth_endpoints()),
        ("✓ OAuth URL", check_oauth_url()),
        ("✓ 前端集成", check_frontend_integration())
    ]
    
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}📊 檢查結果摘要{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}\n")
    
    passed = sum(1 for _, result in checks if result)
    total = len(checks)
    
    for check_name, result in checks:
        status = f"{GREEN}通過{RESET}" if result else f"{RED}失敗{RESET}"
        print(f"{check_name}: {status}")
    
    print(f"\n{BOLD}通過: {passed}/{total}{RESET}")
    
    if passed == total:
        log_success(f"\n🎉 OAuth 系統已就緒！可以開始測試 Web Portal")
        print(f"\n{BLUE}下一步:{RESET}")
        print(f"1. 在 GCP VM 上啟動 Flask API: python3 unified_api.py")
        print(f"2. 打開前端: https://chenkankan1103.github.io/kkgroup/")
        print(f"3. 點擊「登入 DC」按鈕開始 OAuth 流程")
    else:
        log_error(f"\n🔧 發現 {total - passed} 個需要修復的問題")
        print(f"\n{YELLOW}建議:{RESET}")
        print(f"1. 查看上方錯誤日誌")
        print(f"2. 參考 OAUTH_SETUP.md 獲取詳細指南")
        print(f"3. 確保所有環境變數已填入")

if __name__ == '__main__':
    print(f"\n{BOLD}{BLUE}🔐 KK 園區 Discord OAuth 系統健康檢查 v1.0{RESET}")
    print(f"{BLUE}檢查時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}\n")
    
    generate_report()
    
    print(f"\n{BLUE}{'='*60}{RESET}\n")
