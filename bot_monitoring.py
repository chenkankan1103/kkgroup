#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord BOT 監控系統
功能：
1. 檢測重複進程（搶 TOKEN）
2. 檢測進程斷線（沒有重啟）
3. 檢測心跳問題（任務循環卡住）
4. 自動恢復機制
5. Discord 告警通知
"""

import os
import sys
import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
import re

# 顏色輸出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def log(level, message):
    """統一日誌輸出"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if level == 'INFO':
        color = Colors.BLUE
        symbol = 'ℹ️'
    elif level == 'SUCCESS':
        color = Colors.GREEN
        symbol = '✅'
    elif level == 'WARNING':
        color = Colors.YELLOW
        symbol = '⚠️'
    elif level == 'ERROR':
        color = Colors.RED
        symbol = '❌'
    elif level == 'DEBUG':
        color = Colors.CYAN
        symbol = '🔍'
    else:
        color = Colors.RESET
        symbol = '•'
    
    print(f"{color}[{timestamp}] {symbol} {message}{Colors.RESET}")
    
    # 同時寫入日誌文件
    log_dir = Path('/tmp/bot-monitoring')
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'monitoring.log'
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")


def run_command(cmd, remote=True):
    """執行命令（支持本機和 SSH 遠程）"""
    try:
        if remote and 'ssh' not in cmd:
            cmd = f'ssh gcp-work "{cmd}"'
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log('ERROR', f'命令超時: {cmd}')
        return 1, '', 'Timeout'
    except Exception as e:
        log('ERROR', f'執行命令失敗: {e}')
        return 1, '', str(e)


class BotMonitor:
    def __init__(self):
        self.gcp_path = '/home/e193752468/kkgroup'
        self.bots = ['bot.py', 'shopbot.py', 'uibot.py']
        self.services = ['bot.service', 'shopbot.service', 'uibot.service']
        self.flask_service = 'flask-api.service'
        self.monitoring_enabled = True
        
    # ============ 進程檢查 ============
    
    def check_duplicate_processes(self):
        """檢查重複的 BOT 進程"""
        log('INFO', '🔍 檢查重複進程...')
        
        issues = []
        
        for bot in self.bots:
            # 查詢所有 bot 進程
            rc, stdout, _ = run_command(f'pgrep -f "python.*{bot}" | wc -l')
            
            if rc == 0:
                count = int(stdout.strip())
                if count > 1:
                    log('WARNING', f'偵測到 {count} 個 {bot} 進程（應該只有 1 個）')
                    
                    # 獲取詳細信息
                    rc, stdout, _ = run_command(f'ps aux | grep -E "python.*{bot}" | grep -v grep')
                    pids = []
                    
                    for line in stdout.strip().split('\n'):
                        if line:
                            parts = line.split()
                            pid = parts[1]
                            pids.append(pid)
                    
                    if len(pids) > 1:
                        log('ERROR', f'{bot}: 發現 {len(pids)} 個進程，PID: {pids}')
                        issues.append({
                            'bot': bot,
                            'type': 'duplicate',
                            'count': count,
                            'pids': pids
                        })
        
        return issues
    
    def kill_duplicate_processes(self):
        """殺死重複的進程"""
        issues = self.check_duplicate_processes()
        
        if not issues:
            log('SUCCESS', '✅ 沒有重複進程')
            return True
        
        log('WARNING', f'⚡ 發現 {len(issues)} 個重複進程問題')
        
        for issue in issues:
            bot = issue['bot']
            pids = issue['pids']
            
            if len(pids) > 1:
                # 保留第一個（通常是 systemd 啟動的），殺死其他的
                to_kill = pids[1:]
                
                for pid in to_kill:
                    rc, _, err = run_command(f'kill -9 {pid}')
                    if rc == 0:
                        log('SUCCESS', f'已殺死老舊的 {bot} (PID: {pid})')
                    else:
                        log('ERROR', f'殺死 {bot} (PID: {pid}) 失敗: {err}')
        
        return len(issues) == 0
    
    # ============ 服務檢查 ============
    
    def check_services_running(self):
        """檢查所有服務是否運行"""
        log('INFO', '📋 檢查服務狀態...')
        
        all_services = self.services + [self.flask_service]
        issues = []
        
        for service in all_services:
            rc, stdout, _ = run_command(f'systemctl is-active {service}')
            status = stdout.strip()
            
            if status != 'active':
                log('WARNING', f'❌ {service}: {status}')
                issues.append({'service': service, 'status': status})
            else:
                log('SUCCESS', f'✅ {service}: active')
        
        return issues
    
    # ============ 心跳檢查 ============
    
    def check_heartbeat(self):
        """檢查 BOT 心跳（最後日誌時間）"""
        log('INFO', '💓 檢查心跳...')
        
        issues = []
        
        # 檢查 bot.log 的最後修改時間
        rc, stdout, _ = run_command(f'stat -c %Y {self.gcp_path}/bot.log 2>/dev/null')
        
        if rc == 0 and stdout.strip():
            try:
                last_update_ts = int(stdout.strip())
                now_ts = int(time.time())
                diff_seconds = now_ts - last_update_ts
                diff_minutes = diff_seconds / 60
                
                # 如果距離現在超過 6 分鐘（防止 5 分鐘更新任務遲到），視為心跳問題
                HEARTBEAT_THRESHOLD = 360  # 6 分鐘
                
                if diff_seconds > HEARTBEAT_THRESHOLD:
                    log('WARNING', f'⚠️ Bot 心跳異常: 最後更新於 {diff_minutes:.1f} 分鐘前')
                    issues.append({
                        'type': 'heartbeat',
                        'last_update_minutes': diff_minutes
                    })
                else:
                    log('SUCCESS', f'💚 心跳正常 ({diff_minutes:.1f} 分鐘前)')
            
            except ValueError:
                log('ERROR', '無法解析時間戳')
        else:
            log('WARNING', 'bot.log 文件不存在或無法訪問')
        
        return issues
    
    def check_recent_logs(self):
        """檢查 systemd journal 中的最近錯誤"""
        log('INFO', '📝 檢查最近的日誌...')
        
        errors = []
        
        for service in self.services + [self.flask_service]:
            # 檢查過去 1 小時的錯誤日誌
            rc, stdout, _ = run_command(f'journalctl -u {service} --since "1 hour ago" | grep -i "error\\|exception\\|failed" | tail -10')
            
            if stdout.strip():
                log('WARNING', f'{service} 有錯誤日誌:')
                for line in stdout.strip().split('\n')[:5]:  # 只顯示前 5 行
                    log('ERROR', f'  {line}')
                errors.append({
                    'service': service,
                    'error_count': len(stdout.strip().split('\n'))
                })
        
        return errors
    
    # ============ Flask API 檢查 ============
    
    def check_flask_health(self):
        """檢查 Flask API 健康狀態"""
        log('INFO', '🔌 檢查 Flask API...')
        
        rc, stdout, stderr = run_command('curl -s -m 5 http://localhost:5000/api/health')
        
        if rc == 0 and stdout.strip():
            log('SUCCESS', '✅ Flask API 響應正常')
            return True
        else:
            log('WARNING', f'⚠️ Flask API 無響應 或超時')
            return False
    
    # ============ 自動恢復 ============
    
    def handle_duplicate_processes(self):
        """處理重複進程"""
        if not self.kill_duplicate_processes():
            log('WARNING', '重複進程處理中，等待 10 秒後重新檢查...')
            time.sleep(10)
            return self.kill_duplicate_processes()
        return True
    
    def restart_service(self, service):
        """重啟服務"""
        log('WARNING', f'⚡ 重啟服務: {service}')
        
        rc, _, err = run_command(f'systemctl restart {service}')
        if rc == 0:
            log('SUCCESS', f'✅ {service} 已重啟')
            time.sleep(5)  # 等待服務完全啟動
            return True
        else:
            log('ERROR', f'❌ 重啟 {service} 失敗: {err}')
            return False
    
    def restart_bot_ecosystem(self):
        """重啟整個 BOT 生態系統"""
        log('ERROR', '🔴 重啟整個 BOT 生態系統...')
        
        # 順序很重要：Flask API 先啟動，然後是 BOT
        run_command('systemctl restart flask-api.service')
        time.sleep(5)
        run_command('systemctl restart bot-ecosystem.target')
        time.sleep(5)
        
        log('INFO', '等待 15 秒讓服務完全啟動...')
        time.sleep(15)
    
    # ============ 告警通知 ============
    
    def send_discord_alert(self, title, description, severity='warning'):
        """發送 Discord 告警訊息"""
        # 這需要一個專用的事件或 webhook
        # TODO: 實現 Discord 告警
        log('INFO', f'📢 Discord 告警: {title}')
    
    # ============ 主監控循環 ============
    
    def run_full_check(self):
        """執行完整的監控檢查"""
        log('CYAN', '╔════════════════════════════════════════════════╗')
        log('CYAN', '║   Discord BOT 監控系統 - 完整檢查              ║')
        log('CYAN', f'║   {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                        ║')
        log('CYAN', '╚════════════════════════════════════════════════╝')
        print()
        
        all_issues = []
        
        # 1. 進程檢查
        print('=' * 50)
        duplicate_issues = self.check_duplicate_processes()
        if duplicate_issues:
            log('WARNING', f'發現 {len(duplicate_issues)} 個重複進程問題')
            self.handle_duplicate_processes()
            all_issues.extend(duplicate_issues)
        print()
        
        # 2. 服務檢查
        print('=' * 50)
        service_issues = self.check_services_running()
        if service_issues:
            log('ERROR', f'發現 {len(service_issues)} 個服務異常')
            # 嘗試重啟相關服務
            for issue in service_issues:
                self.restart_service(issue['service'])
            all_issues.extend(service_issues)
        print()
        
        # 3. Flask API 檢查
        print('=' * 50)
        if not self.check_flask_health():
            log('WARNING', '嘗試重啟 Flask API...')
            self.restart_service('flask-api.service')
            all_issues.append({'type': 'flask_health'})
        print()
        
        # 4. 心跳檢查
        print('=' * 50)
        heartbeat_issues = self.check_heartbeat()
        if heartbeat_issues:
            log('WARNING', '偵測到心跳問題')
            all_issues.extend(heartbeat_issues)
        print()
        
        # 5. 日誌檢查
        print('=' * 50)
        log_issues = self.check_recent_logs()
        if log_issues:
            log('WARNING', f'發現 {len(log_issues)} 個服務有錯誤日誌')
            all_issues.extend(log_issues)
        print()
        
        # 最終報告
        print('=' * 50)
        if not all_issues:
            log('SUCCESS', '🎉 所有檢查通過！系統狀態正常')
            print('=' * 50)
            return 0
        else:
            log('WARNING', f'⚠️ 發現 {len(all_issues)} 個問題')
            
            # 決定是否需要完整重啟
            critical_issues = [i for i in all_issues if i.get('type') in ['duplicate', 'flask_health']]
            if len(critical_issues) > 0 and len(critical_issues) >= 2:
                log('ERROR', '🔴 偵測到多個嚴重問題，執行完整重啟...')
                self.restart_bot_ecosystem()
            
            print('=' * 50)
            return 1
    
    def run_continuous(self, interval=300):
        """連續監控模式（間隔 interval 秒）"""
        log('INFO', f'🔄 啟動連續監控（每 {interval} 秒檢查一次）')
        log('INFO', '按 Ctrl+C 停止監控')
        
        try:
            while self.monitoring_enabled:
                self.run_full_check()
                print()
                log('INFO', f'下次檢查時間: {datetime.now() + timedelta(seconds=interval)}')
                time.sleep(interval)
        except KeyboardInterrupt:
            log('INFO', '監控已停止')


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Discord BOT 監控系統')
    parser.add_argument('--continuous', '-c', action='store_true', help='連續監控模式')
    parser.add_argument('--interval', '-i', type=int, default=300, help='檢查間隔（秒，預設 300）')
    parser.add_argument('--check-duplicates', action='store_true', help='只檢查重複進程')
    parser.add_argument('--check-health', action='store_true', help='只檢查 Flask 健康狀態')
    parser.add_argument('--check-heartbeat', action='store_true', help='只檢查心跳')
    
    args = parser.parse_args()
    
    monitor = BotMonitor()
    
    if args.check_duplicates:
        monitor.check_duplicate_processes()
    elif args.check_health:
        monitor.check_flask_health()
    elif args.check_heartbeat:
        monitor.check_heartbeat()
    elif args.continuous:
        monitor.run_continuous(interval=args.interval)
    else:
        return monitor.run_full_check()


if __name__ == '__main__':
    sys.exit(main())
