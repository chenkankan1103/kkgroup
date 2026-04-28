# -*- coding: utf-8 -*-
"""
Paperdoll 代理服務
解決 Discord 無法加載 MapleStory API 圖片的問題
- Discord 請求圖片時沒有發送 User-Agent header → 403 Forbidden
- 我們充當中間人，轉發請求並添加 User-Agent header
- 無額外出站流量消耗（只是轉發），無下載/上傳浪費

使用方法：
1. 將 URL 從 https://maplestory.io/api/character/... 
   改為 http://localhost:8899/paperdoll/{base64_encoded_url}
2. 或使用新的簡化格式
"""

from flask import Flask, redirect, abort
from urllib.parse import quote, unquote
import base64
import requests
from functools import lru_cache
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MapleStory API 的 User-Agent
MAPLESTORY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

@lru_cache(maxsize=1000)
def get_paperdoll_image(url: str) -> bytes:
    """
    從 MapleStory API 獲取圖片
    帶有 User-Agent header，避免 403 Forbidden
    """
    try:
        headers = {
            'User-Agent': MAPLESTORY_USER_AGENT
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        if response.headers.get('content-type', '').startswith('image/'):
            return response.content
        else:
            logger.error(f"❌ 非圖片內容類型: {response.headers.get('content-type')}")
            return None
    except Exception as e:
        logger.error(f"❌ 獲取紙娃娃失敗: {e}")
        return None

@app.route('/paperdoll/<path:encoded_url>')
def paperdoll_redirect(encoded_url: str):
    """
    代理端點：接收編碼的 URL，轉發到 MapleStory API
    
    使用方法：
    1. 將完整的 MapleStory API URL 進行 base64 編碼
    2. 訪問 /paperdoll/{base64_encoded_url}
    3. 重定向或流式傳輸圖片給 Discord
    
    例：
    原始：https://maplestory.io/api/character/...
    編碼：POST /paperdoll/aHR0cHM6Ly9tYXBsZXN0b3J5Lmlv...
    """
    try:
        # 解碼 URL
        decoded_url = base64.b64decode(encoded_url).decode('utf-8')
        
        # 驗證 URL 來自 MapleStory API
        if not decoded_url.startswith('https://maplestory.io/'):
            logger.warning(f"⚠️ 拒絕非 MapleStory API 的 URL: {decoded_url[:50]}")
            abort(400, "只接受 MapleStory API 的 URL")
        
        logger.info(f"🔄 代理請求: {decoded_url[:80]}...")
        
        # 獲取圖片
        image_data = get_paperdoll_image(decoded_url)
        if not image_data:
            abort(503, "無法從 MapleStory API 獲取圖片")
        
        # 重定向到 Discord 可以直接加載的 CDN
        # 但實際上我們應該直接返回圖片內容
        # 這樣 Discord 可以以 image/gif 的形式加載
        from flask import Response
        return Response(image_data, mimetype='image/gif', cache_control='public, max-age=86400')
        
    except Exception as e:
        logger.error(f"❌ 代理錯誤: {e}")
        abort(500, f"代理錯誤: {str(e)[:100]}")

@app.route('/health')
def health():
    """健康檢查端點"""
    return {'status': 'ok'}, 200

if __name__ == '__main__':
    print("🎭 Paperdoll 代理服務啟動...")
    print("📍 聆聽 http://localhost:8899")
    print("✅ 當 Discord 加載紙娃娃時，請求會自動添加 User-Agent header")
    app.run(host='0.0.0.0', port=8899, debug=False)
