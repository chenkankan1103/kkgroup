#!/usr/bin/env python3
"""
部署檔案到 GCP 的幫助腳本
"""
import subprocess
import base64
import os

def deploy_file(local_path, remote_path):
    """通過 SSH 部署檔案到 GCP"""
    # 確保本地檔案存在
    if not os.path.exists(local_path):
        print(f"❌ 本地檔案不存在: {local_path}")
        return False
    
    # 讀取檔案內容
    with open(local_path, 'rb') as f:
        file_content = f.read()
    
    # 編碼為 base64
    encoded = base64.b64encode(file_content).decode('utf-8')
    
    # 寫入本地臨時編碼文件
    temp_encoded = f"/tmp/encoded_{os.path.basename(local_path)}.b64"
    with open(temp_encoded, 'w') as f:
        f.write(encoded)
    
    print(f"部署中: {local_path} -> {remote_path}")
    
    # 第一步：上傳 base64 編碼檔案
    upload_cmd = f'scp "{temp_encoded}" kankan@35.206.126.157:/tmp/'
    print(f"  📤 上傳編碼檔案...")
    result = subprocess.run(upload_cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        # 如果 SCP 失敗，嘗試通過 SSH 管道傳輸
        print(f"  ⚠️  SCP 上傳失敗，嘗試替代方法...")
        with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # 用 Python 直接複製
        cmd = f"""ssh gcp-kkgroup 'python3 -c "
import base64
data = {repr(encoded)}
with open('/tmp/temp_decoded', 'wb') as f:
    f.write(base64.b64decode(data))
"' && ssh gcp-kkgroup "sudo cp /tmp/temp_decoded {remote_path} && sudo chown e193752468:e193752468 {remote_path} && rm /tmp/temp_decoded"
"""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    else:
        # 第二步：在遠程解碼並複製
        b64_file = os.path.basename(temp_encoded)
        decode_cmd = f"""ssh gcp-kkgroup "base64 -d /tmp/{b64_file} > /tmp/decoded_file && sudo cp /tmp/decoded_file {remote_path} && sudo chown e193752468:e193752468 {remote_path} && rm /tmp/{b64_file} /tmp/decoded_file"
"""
        result = subprocess.run(decode_cmd, shell=True, capture_output=True, text=True)
    
    # 清理本地臨時檔案
    try:
        os.remove(temp_encoded)
    except:
        pass
    
    if result.returncode == 0:
        print(f"✅ {remote_path} 部署成功")
        # 驗證
        verify_cmd = f'ssh gcp-kkgroup "ls -lh {remote_path}"'
        verify = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)
        print(verify.stdout)
        return True
    else:
        print(f"❌ 部署失敗: {result.stderr}")
        return False

if __name__ == "__main__":
    files_to_deploy = [
        ('commands/kkcoin_visualizer_v2.py', '/home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py'),
        ('commands/kcoin.py', '/home/e193752468/kkgroup/commands/kcoin.py'),
    ]
    
    print("=" * 60)
    print("🚀 開始部署到 GCP")
    print("=" * 60)
    
    success_count = 0
    for local, remote in files_to_deploy:
        if deploy_file(local, remote):
            success_count += 1
        print()
    
    print("=" * 60)
    print(f"✅ 部署完成: {success_count}/{len(files_to_deploy)} 個檔案成功")
    print("=" * 60)
