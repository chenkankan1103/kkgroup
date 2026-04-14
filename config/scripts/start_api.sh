#!/bin/bash
# 啟動 KKCoin Unified API

cd /home/e193752468/kkgroup
# 載入 .env 環境變數（確保 Discord OAuth 等配置可用）
if [ -f "/home/e193752468/.env" ]; then
  set -a
  source /home/e193752468/.env
  set +a
fi

export PYTHONUNBUFFERED=1
export FLASK_DEBUG=False
export API_HOST=127.0.0.1
export API_PORT=5000

/usr/bin/python3 /home/e193752468/kkgroup/unified_api.py
