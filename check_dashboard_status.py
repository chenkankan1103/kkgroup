#!/usr/bin/env python3
"""
Dashboard Metrics 狀態檢查工具
- 檢查消息 ID 是否正確保存
- 驗證快取狀態
- 檢查最近的日誌輸出
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

def check_dashboard_status():
    """檢查儀表板狀態"""
    print("=" * 80)
    print("📊 Dashboard Metrics 狀態檢查")
    print("=" * 80)
    
    # 1. 檢查環境變數
    print("\n[1] 檢查環境變數...")
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        metrics_vars = [line for line in lines if 'METRICS' in line or 'DASHBOARD' in line]
        if metrics_vars:
            print("✅ 找到 Dashboard 相關環境變數:")
            for var in metrics_vars:
                print(f"   {var.strip()}")
        else:
            print("❌ 未找到 Dashboard 相關環境變數")
    else:
        print("❌ .env 檔案不存在")
    
    # 2. 檢查 message_ids storage
    print("\n[2] 檢查訊息 ID 存儲...")
    message_ids_file = "dashboard_message_ids.json"
    if os.path.exists(message_ids_file):
        try:
            with open(message_ids_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"✅ Dashboard 訊息 ID:")
            for key, value in data.items():
                print(f"   - {key}: {value}")
        except Exception as e:
            print(f"❌ 讀取失敗: {e}")
    else:
        print(f"❌ {message_ids_file} 不存在")
    
    # 3. 檢查日誌檔案
    print("\n[3] 檢查日誌檔案...")
    log_files = [
        "status_dashboard.log",
        "dashboard_logs.json",
        "update_task_errors.log"
    ]
    
    for log_file in log_files:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            print(f"✅ {log_file}: {size} bytes")
            
            # 顯示最後 5 行
            if log_file.endswith('.json'):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    print(f"   內容: {data}")
                except:
                    pass
            else:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    print(f"   最後 3 行:")
                    for line in lines[-3:]:
                        print(f"     {line.rstrip()}")
        else:
            print(f"⚠️ {log_file} 不存在")
    
    # 4. 檢查 metrics 快取
    print("\n[4] 檢查快取狀態...")
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from status_dashboard import metrics_cache, GCP_METRICS_ENABLED, GCP_METRICS_ONLY_BOT_RESPONSIBLE
        
        print(f"✅ GCP_METRICS_ENABLED: {GCP_METRICS_ENABLED}")
        print(f"✅ GCP_METRICS_ONLY_BOT_RESPONSIBLE: {GCP_METRICS_ONLY_BOT_RESPONSIBLE}")
        
        if metrics_cache.data:
            print(f"✅ 快取中有數據 (時間戳: {metrics_cache.timestamp})")
            print(f"   - 是否過期: {metrics_cache.is_stale()}")
        else:
            print("❌ 快取中沒有數據")
    except Exception as e:
        print(f"❌ 無法檢查快取: {e}")
    
    # 5. 檢查最近的錯誤
    print("\n[5] 檢查最近的錯誤...")
    if os.path.exists("update_task_errors.log"):
        with open("update_task_errors.log", 'r', encoding='utf-8') as f:
            errors = f.readlines()
        
        # 找出最近的 METRICS 錯誤
        recent_metrics_errors = [
            e for e in errors[-20:] if 'METRICS' in e
        ]
        
        if recent_metrics_errors:
            print(f"❌ 最近的 METRICS 錯誤:")
            for error in recent_metrics_errors[-5:]:
                print(f"   {error.rstrip()}")
        else:
            print("✅ 沒有最近的 METRICS 錯誤")
    
    # 6. 測試導入
    print("\n[6] 測試模組導入...")
    try:
        from gcp_metrics_monitor import GCPMetricsMonitor
        monitor = GCPMetricsMonitor(project_id="kkgroup")
        if monitor.available:
            print(f"✅ GCPMetricsMonitor 可用")
        else:
            print(f"❌ GCPMetricsMonitor 不可用 (認證失敗?)")
    except Exception as e:
        print(f"❌ 導入失敗: {e}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    check_dashboard_status()
