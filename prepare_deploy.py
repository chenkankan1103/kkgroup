#!/usr/bin/env python3
"""
在本地準備編碼檔案，然後上傳到 GCP
"""
import base64
import subprocess
import os

def main():
    files = [
        ('commands/kkcoin_visualizer_v2.py', 'kkcoin_visualizer_v2.py'),
        ('commands/kcoin.py', 'kcoin.py'),
    ]
    
    temp_dir = os.environ.get('TEMP', '/tmp')
    
    print("=" * 60)
    print("🔧 本地檔案編碼")
    print("=" * 60)
    
    for local_path, filename in files:
        if not os.path.exists(local_path):
            print(f"❌ 找不到: {local_path}")
            continue
        
        # 讀取檔案
        with open(local_path, 'rb') as f:
            data = f.read()
        
        # 編碼成 base64
        encoded = base64.b64encode(data).decode('utf-8')
        
        # 保存編碼檔案
        temp_file = os.path.join(temp_dir, f"{filename}.b64")
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(encoded)
        
        print(f"✅ {filename}")
        print(f"   原始大小: {len(data)} 字節")
        print(f"   編碼大小: {len(encoded)} 字符")
        print(f"   臨時檔案: {temp_file}")
        print()
    
    print("=" * 60)
    print("📤 上傳到 GCP /tmp")
    print("=" * 60)
    
    for local_path, filename in files:
        temp_file = os.path.join(temp_dir, f"{filename}.b64")
        if not os.path.exists(temp_file):
            continue
        
        cmd = f'scp "{temp_file}" kankan@35.206.126.157:/tmp/'
        print(f"上傳 {filename}...")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ {filename} 已上傳")
        else:
            print(f"❌ 上傳失敗: {result.stderr}")
        print()
    
    print("=" * 60)
    print("🔄 遠程解碼並部署")
    print("=" * 60)
    
    # 準備遠程部署命令
    deploy_cmd = """ssh gcp-kkgroup << 'DEPLOYSSH'
cd /tmp

# 解碼 kkcoin_visualizer_v2.py
echo "解碼 kkcoin_visualizer_v2.py..."
if [ -f kkcoin_visualizer_v2.py.b64 ]; then
    base64 -d kkcoin_visualizer_v2.py.b64 > /tmp/decoded1.py
    sudo cp /tmp/decoded1.py /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py
    sudo chown e193752468:e193752468 /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py
    rm /tmp/decoded1.py kkcoin_visualizer_v2.py.b64
    echo "✅ kkcoin_visualizer_v2.py 部署完成"
fi

# 解碼 kcoin.py
echo "解碼 kcoin.py..."
if [ -f kcoin.py.b64 ]; then
    base64 -d kcoin.py.b64 > /tmp/decoded2.py
    sudo cp /tmp/decoded2.py /home/e193752468/kkgroup/commands/kcoin.py
    sudo chown e193752468:e193752468 /home/e193752468/kkgroup/commands/kcoin.py
    rm /tmp/decoded2.py kcoin.py.b64
    echo "✅ kcoin.py 部署完成"
fi

echo ""
echo "驗證檔案:"
ls -lh /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py
ls -lh /home/e193752468/kkgroup/commands/kcoin.py
DEPLOYSSH
"""
    
    print(result.stdout if result.returncode == 0 else "執行遠程部署命令...")
    result = subprocess.run(deploy_cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    print("=" * 60)
    print("✅ 部署完成!")
    print("=" * 60)
    print("下一步: 重啟 Bot")
    print("  ssh gcp-kkgroup \"sudo systemctl restart bot\"")
    print("=" * 60)

if __name__ == "__main__":
    main()
