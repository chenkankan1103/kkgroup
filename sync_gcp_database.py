#!/usr/bin/env python3
"""
從 GCP 複製已修復的資料庫到本地
使用 Google Cloud 認證
"""
import os
import shutil
import subprocess
import json
from pathlib import Path

# 檢查 google_credentials.json 是否存在
creds_path = Path('google_credentials.json')
if not creds_path.exists():
    print("❌ google_credentials.json 不存在")
    exit(1)

print("導入 Google Cloud 認證...")
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_path.absolute())

# 嘗試使用 gcloud 命令複製資料庫
gcp_user = 'e193752468'
gcp_host = '34.80.205.45'
gcp_db_path = '/home/e193752468/kkgroup/user_data.db'
local_db_path = Path('user_data.db')
local_db_backup = Path('user_data.db.local_backup')

print(f"\n備份本地資料庫...")
try:
    shutil.copy2(local_db_path, local_db_backup)
    print(f"✅ 本地資料庫已備份至: {local_db_backup}")
except Exception as e:
    print(f"⚠️ 備份失敗: {e}")

print(f"\n嘗試從 GCP 複製資料庫...")
print(f"來源: {gcp_user}@{gcp_host}:{gcp_db_path}")
print(f"目標: {local_db_path}")

try:
    # 使用 gcloud compute scp 命令
    cmd = [
        'gcloud', 'compute', 'scp',
        f'{gcp_user}@kkgroup-server:{gcp_db_path}',
        str(local_db_path),
        '--project=kk-group-440014',
        '--zone=asia-east1-b'
    ]
    
    print(f"\n執行命令: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ 資料庫複製成功")
        # 驗證資料庫
        if local_db_path.exists():
            size = local_db_path.stat().st_size
            print(f"資料庫大小: {size / 1024 / 1024:.2f} MB")
    else:
        print(f"❌ 複製失敗")
        print(f"stderr: {result.stderr}")
        print(f"stdout: {result.stdout}")
        
except Exception as e:
    print(f"❌ 執行失敗: {e}")
    print("\n嘗試替代方法...")
    
    # 替代方法：使用 sftp  
    try:
        import paramiko
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print(f"通過 SFTP 連接到 {gcp_host}...")
        ssh.connect(gcp_host, username=gcp_user)
        
        sftp = ssh.open_sftp()
        print(f"下載 {gcp_db_path}...")
        sftp.get(gcp_db_path, str(local_db_path))
        
        sftp.close()
        ssh.close()
        
        print("✅ 使用 SFTP 複製成功")
    except ImportError:
        print("❌ paramiko 未安裝，無法使用 SFTP")
    except Exception as e2:
        print(f"❌ SFTP 連接失敗: {e2}")
