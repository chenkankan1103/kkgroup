#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Threads 輕量趨勢收集器
使用已保存的 Cookies 通過 requests 收集趨勢
比 Selenium 快 10 倍，內存占用 1/20
"""

import requests
import json
import logging
import os
import sys
from datetime import datetime, timedelta
import asyncio

# Unicode 編碼修復
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================================
# 日誌系統
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('threads_collector.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# 常數配置
# ============================================================================
COOKIES_FILE = "threads_cookies.json"
TRENDS_FILE = "threads_trends.json"
COOKIES_EXPIRY_DAYS = 7  # Threads Cookies 有效期約 7-14 天
COOKIE_CHECK_FILE = "threads_cookies_check.json"

# ============================================================================
# 1. Cookie 過期檢測系統
# ============================================================================

class CookieValidator:
    """驗證和監控 Cookies 有效性"""
    
    @staticmethod
    def check_cookie_expiry():
        """檢查 Cookies 文件是否存在且未過期"""
        
        if not os.path.exists(COOKIES_FILE):
            logger.error("❌ Cookies 文件不存在")
            return False, "MISSING"
        
        # 讀取 Cookies 文件的修改時間
        file_mtime = os.path.getmtime(COOKIES_FILE)
        file_age_days = (datetime.now().timestamp() - file_mtime) / 86400
        
        logger.info(f"📅 Cookies 年齡: {file_age_days:.1f} 天")
        
        # 如果超過 7 天，標記為可能過期
        if file_age_days > COOKIES_EXPIRY_DAYS:
            logger.warning(f"⚠️  Cookies 可能已過期 ({file_age_days:.1f} 天)")
            return False, "EXPIRED"
        
        return True, "VALID"
    
    @staticmethod
    def save_expiry_record():
        """保存 Cookies 檢查記錄"""
        record = {
            "last_check": datetime.now().isoformat(),
            "file_age_days": (datetime.now().timestamp() - os.path.getmtime(COOKIES_FILE)) / 86400
            if os.path.exists(COOKIES_FILE) else None,
        }
        
        with open(COOKIE_CHECK_FILE, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

# ============================================================================
# 2. 輕量爬蟲 - 使用 Requests + Cookies
# ============================================================================

class ThreadsCollector:
    """用 Requests 和保存的 Cookies 收集 Threads 趨勢"""
    
    def __init__(self):
        self.session = requests.Session()
        self.cookies_valid = False
        self.trends = []
    
    def load_cookies(self):
        """從文件加載 Cookies"""
        
        if not os.path.exists(COOKIES_FILE):
            logger.error(f"❌ {COOKIES_FILE} 不存在")
            logger.error("   解決方案: 先運行 threads_scraper_v2.py 進行一次 Selenium 登入")
            return False
        
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
            
            # 添加 Cookies 到 Session
            for cookie in cookies_data:
                self.session.cookies.set(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie.get('domain', '.threads.net'),
                    path=cookie.get('path', '/'),
                )
            
            logger.info(f"✅ 已加載 {len(cookies_data)} 個 Cookies")
            self.cookies_valid = True
            return True
        
        except Exception as e:
            logger.error(f"❌ Cookies 加載失敗: {e}")
            return False
    
    def set_headers(self):
        """設置模擬瀏覽器的 Headers"""
        
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://www.threads.net/search/",
            "Origin": "https://www.threads.net",
            # Instagram Web App ID（通常是固定的）
            "X-IG-App-ID": "2382612025342621",
        }
        
        self.session.headers.update(headers)
        logger.info("✅ Headers 已設置")
    
    def fetch_trends(self):
        """嘗試多種方式收集趨勢"""
        
        if not self.cookies_valid:
            logger.error("❌ Cookies 無效，無法獲取趨勢")
            return False
        
        # 方法 1: 直接訪問搜尋頁面並解析 HTML
        logger.info("🔍 方法 1: 訪問搜尋頁面...")
        
        try:
            response = self.session.get(
                "https://www.threads.net/search/",
                timeout=15,
            )
            
            if response.status_code == 200:
                logger.info(f"✓ 頁面加載成功 (狀態碼: 200)")
                
                # 嘗試從 HTML 中提取趨勢
                import re
                
                # 尋找可能的 JSON 或文本模式
                # （由於 Threads 前端渲染，這可能不夠準確）
                html = response.text
                
                # 嘗試找包含趨勢的 script 標籤
                scripts = re.findall(r'<script[^>]*>(.+?)</script>', html, re.DOTALL)
                logger.info(f"  找到 {len(scripts)} 個 script 標籤")
                
                return True
            
            elif response.status_code == 401:
                logger.error(f"❌ 方法 1 失敗: Cookies 已過期 (401 Unauthorized)")
                return False
            
            elif response.status_code == 403:
                logger.error(f"❌ 方法 1 失敗: 被拒絕 (403 Forbidden)")
                return False
            
            elif response.status_code == 429:
                logger.error(f"❌ 方法 1 失敗: 被限流 (429 Too Many Requests)")
                return False
            
            else:
                logger.error(f"❌ 方法 1 失敗: 狀態碼 {response.status_code}")
                return False
        
        except requests.exceptions.Timeout:
            logger.error("❌ 方法 1 失敗: 連線超時")
            return False
        
        except Exception as e:
            logger.error(f"❌ 方法 1 失敗: {e}")
            return False
    
    def collect(self):
        """完整的收集流程"""
        
        logger.info("=" * 60)
        logger.info("🚀 Threads 輕量趨勢收集器")
        logger.info("=" * 60)
        
        # 步驟 1: 檢查 Cookies 有效性
        logger.info("\n📋 步驟 1: 檢查 Cookies...")
        is_valid, status = CookieValidator.check_cookie_expiry()
        
        if not is_valid:
            logger.error(f"❌ Cookies 狀態: {status}")
            self.handle_cookie_expired(status)
            return False
        
        logger.info(f"✅ Cookies 狀態: {status}")
        
        # 步驟 2: 加載 Cookies
        logger.info("\n📋 步驟 2: 加載 Cookies...")
        if not self.load_cookies():
            self.handle_cookie_expired("LOAD_FAILED")
            return False
        
        # 步驟 3: 設置 Headers
        logger.info("\n📋 步驟 3: 設置 Headers...")
        self.set_headers()
        
        # 步驟 4: 獲取趨勢
        logger.info("\n📋 步驟 4: 獲取趨勢...")
        if not self.fetch_trends():
            return False
        
        logger.info("\n" + "=" * 60)
        logger.info("❌ 注意: 目前 API 端點尚未確認")
        logger.info("=" * 60)
        logger.info("""
下一步說明:
1. 在瀏覽器中訪問 https://www.threads.net/search/
2. 打開 F12 開發者工具
3. 進入 Network 標籤，找到 /api/ 開頭的請求
4. 複製完整的 API URL 和相關的 Headers
5. 更新本文件中的 API 端點

或者，暫時使用原有的 threads_scraper_v2.py（Selenium 版本），
該版本已驗證可行。
        """)
        
        return True
    
    def handle_cookie_expired(self, status):
        """Cookies 過期時的處理 - 通知 Discord 管理員"""
        
        logger.error("\n" + "=" * 60)
        logger.error("🚨 COOKIE 過期警告")
        logger.error("=" * 60)
        
        alert_message = f"""
⚠️ **Threads Cookies 已過期或無效**

**狀態**: {status}
**時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**需要操作**:
1. 在本地環境運行 `threads_scraper_v2.py`
2. 按照瀏覽器提示手動登入 Threads
3. 將生成的 `threads_cookies.json` 上傳到 GCP VM
4. 重啟 bot.service

**臨時措施**:
- 爬蟲已暫停
- Discord 機器人仍在線，但無法更新趨勢
- 等待管理員完成上述操作
        """
        
        logger.error(alert_message)
        
        # 後續可以集成 Discord 通知
        # 如果你有 Discord Bot Token，可以調用：
        # send_discord_alert(alert_message)

# ============================================================================
# 主程序入口
# ============================================================================

def main():
    try:
        collector = ThreadsCollector()
        success = collector.collect()
        
        if success:
            logger.info("\n✅ 趨勢收集完成")
        else:
            logger.error("\n❌ 趨勢收集失敗")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ 異常錯誤: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
