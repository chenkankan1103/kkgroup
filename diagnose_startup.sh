#!/bin/bash
# GCP Flask 啟動錯誤診斷

echo "🔍 診斷 gunicorn 啟動錯誤..."
echo "======================================"
echo ""

# 1. 檢查 Python 語法
echo "1️⃣ 檢查 sheet_sync_api.py 語法..."
python3 -m py_compile sheet_sync_api.py 2>&1
if [ $? -eq 0 ]; then
    echo "✅ 語法正確"
else
    echo "❌ 語法錯誤"
    exit 1
fi

echo ""

# 2. 測試直接導入
echo "2️⃣ 測試直接導入 sheet_sync_api..."
python3 << 'EOF'
import sys
import traceback

try:
    print("📥 導入 sheet_sync_manager...")
    from sheet_sync_manager import SheetSyncManager
    print("✅ sheet_sync_manager 導入成功")
    
    print("📥 導入 sheet_driven_db...")
    from sheet_driven_db import SheetDrivenDB
    print("✅ sheet_driven_db 導入成功")
    
    print("📥 導入 Flask...")
    from flask import Flask
    print("✅ Flask 導入成功")
    
    print("📥 導入 sheet_sync_api...")
    from sheet_sync_api import app
    print("✅ sheet_sync_api 導入成功")
    
    print("\n✅ 所有模塊導入成功！")
    print(f"   Flask 應用: {app}")
    
except ImportError as e:
    print(f"❌ 導入失敗: {e}")
    traceback.print_exc()
except Exception as e:
    print(f"❌ 其他錯誤: {e}")
    traceback.print_exc()
EOF

echo ""

# 3. 嘗試直接啟動 Flask（開發模式）
echo "3️⃣ 嘗試直接啟動 Flask（開發模式，5 秒後停止）..."
echo ""
timeout 5 python3 -c "
from sheet_sync_api import app
print('✅ Flask 啟動成功')
print('   測試連接...')
import requests
try:
    r = requests.get('http://localhost:5000/api/health', timeout=2)
    print(f'   GET /api/health: {r.status_code}')
except Exception as e:
    print(f'   連接失敗: {e}')
app.run(host='0.0.0.0', port=5000, debug=False)
" 2>&1 || true

echo ""
echo "4️⃣ 嘗試用 gunicorn 啟動（前景運行，5 秒後停止）..."
echo ""
if [ -f "venv/bin/gunicorn" ]; then
    echo "📍 gunicorn 路徑: $(which gunicorn || find . -name gunicorn)"
    timeout 5 venv/bin/gunicorn -w 1 -b 127.0.0.1:5000 --log-level=debug sheet_sync_api:app 2>&1 || true
else
    echo "⚠️ gunicorn 未找到在 venv/bin"
    which gunicorn && timeout 5 gunicorn -w 1 -b 127.0.0.1:5000 --log-level=debug sheet_sync_api:app 2>&1 || true
fi

echo ""
echo "======================================"
echo "診斷完成"
