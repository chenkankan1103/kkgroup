#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Threads 趨勢爬蟲 - 精確提取版本
直接提取搜尋頁面中的趨勢標題
"""

import sys
import io
# 修復 Windows PowerShell Unicode 編碼問題
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import json
import time
import os
import re
import random
import logging
from datetime import datetime

# ============================================================================
# 1. 設置日誌系統 - 用於監控和異常告警
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('threads_scraper.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# 2. 輪換 User-Agent - 混淆身份，降低反爬蟲檢測
# ============================================================================
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0',
]

def get_random_user_agent():
    """隨機選擇 User-Agent"""
    return random.choice(USER_AGENTS)

# ============================================================================
# 3. 配置 Edge 瀏覽器
# ============================================================================
edge_options = Options()

# 檢測環境：GCP VM 上無瀏覽器，需要啟用 headless 模式
IS_HEADLESS = os.environ.get('HEADLESS', 'false').lower() == 'true'
if IS_HEADLESS:
    logger.info("🖥️ Headless 模式啟用（無 GUI 環境）")
    edge_options.add_argument("--headless=new")
else:
    logger.info("🖥️ GUI 模式啟用（本機測試）")
    edge_options.add_argument("--start-maximized")

edge_options.add_argument("--disable-blink-features=AutomationControlled")
edge_options.add_argument(f"user-agent={get_random_user_agent()}")
edge_options.add_argument("--no-sandbox")
edge_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Edge(options=edge_options)
wait = WebDriverWait(driver, 15)

print("=" * 60)
print("Threads 趨勢爬蟲 - 精確提取版本")
print("=" * 60)

# ============================================================================
# 4. 自動重試登入 - 應對 Cookie 失效
# ============================================================================
def login_to_threads(max_retries=3):
    """自動登入並保存 Cookie，支持重試"""
    cookies_file = "threads_cookies.json"
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔐 登入嘗試 {attempt + 1}/{max_retries}")
            
            # 1. 嘗試使用已保存的 Cookie
            if os.path.exists(cookies_file):
                logger.info("✅ 使用保存的登入狀態")
                driver.get("https://www.threads.com")
                
                # 添加隨機延遲 - 防止檢測
                wait_time = random.uniform(2, 4)
                time.sleep(wait_time)
                
                with open(cookies_file, 'r') as f:
                    cookies = json.load(f)
                
                for cookie in cookies:
                    try:
                        driver.add_cookie(cookie)
                    except Exception as cookie_err:
                        logger.warning(f"⚠️ Cookie 添加失敗: {cookie.get('name', 'unknown')}")
                        pass
                
                # 刷新頁面以驗證 Cookie
                driver.refresh()
                
                # 添加隨機延遲
                wait_time = random.uniform(2, 3)
                time.sleep(wait_time)
                
                # 驗證是否已登入（檢查是否包含用戶特定的 UI 元素）
                try:
                    driver.find_element(By.XPATH, "//a[contains(@href, '/profile')]")
                    logger.info("✅ 登入狀態驗證成功")
                    return True
                except:
                    logger.warning("⚠️ Cookie 已過期，需要重新登入")
                    os.remove(cookies_file)
            
            # 2. 首次登入 - 等待用戶在瀏覽器中手動登入
            else:
                logger.info("📌 Cookies 不存在，等待首次登入...")
                
                # 檢查是否在 Headless 模式（VM 環境）
                if IS_HEADLESS:
                    logger.error("❌ Headless 模式下無法進行首次登入。請先在本地環境中運行爬蟲以生成 cookies。")
                    raise Exception("Headless 環境下缺少有效的 cookies 文件")
                
                # GUI 模式：訪問 Threads 並等待用戶登入
                driver.get("https://www.threads.com")
                logger.info("⏳ 等待用戶在瀏覽器中登入... (120 秒超時)")
                
                # 等待用戶登入（120 秒 - 給足夠時間）
                try:
                    wait_time = 0
                    max_wait = 120  # 增加到 120 秒
                    check_interval = 3
                    
                    while wait_time < max_wait:
                        time.sleep(check_interval)
                        wait_time += check_interval
                        
                        try:
                            # 方法 1: 檢查 URL 是否變化（從登入頁面進入主頁）
                            current_url = driver.current_url
                            if 'threads.com' in current_url and 'login' not in current_url.lower():
                                logger.info(f"✅ 登入成功！(URL 變化: {current_url[:50]}...)")
                                
                                # 等待 3 秒讓頁面穩定
                                time.sleep(3)
                                
                                # 保存 cookies
                                with open(cookies_file, 'w') as f:
                                    json.dump(driver.get_cookies(), f, indent=2)
                                logger.info("💾 登入狀態已保存")
                                return True
                        except:
                            pass
                        
                        # 每 20 秒提示一次
                        if wait_time % 20 == 0:
                            logger.info(f"⏳ 還在等待... ({wait_time}/{max_wait} 秒)")
                    
                    # 超時
                    logger.error("❌ 等待登入超時（120 秒）")
                    logger.error(f"最後 URL: {driver.current_url}")
                    
                    # 嘗試一次性保存（萬一已登入但檢測失敗）
                    try:
                        cookies = driver.get_cookies()
                        if len(cookies) > 5:  # 如果有很多 cookies，可能已登入
                            logger.warning("⚠️ 檢測到 Cookies，雖然 URL 檢查失敗，仍然嘗試保存")
                            with open(cookies_file, 'w') as f:
                                json.dump(cookies, f, indent=2)
                            logger.info("💾 Cookies 已保存（基於 Cookie 數量判斷）")
                            return True
                    except:
                        pass
                    
                    raise Exception("首次登入超時，請在瀏覽器中登入 Threads")
                
                except Exception as e:
                    raise Exception(f"首次登入失敗: {str(e)}")
            
            # 此時應該已經返回或拋出異常
        
        except Exception as e:
            logger.error(f"❌ 登入失敗（嘗試 {attempt + 1}）: {e}")
            if attempt < max_retries - 1:
                wait_time = random.uniform(3, 5)
                logger.info(f"⏳ 等待 {wait_time:.1f} 秒後重試...")
                time.sleep(wait_time)
            else:
                return False
    
    return False

# ============================================================================
# 主程式入口
# ============================================================================

try:
    # ============================================================================
    # 1. 登入與 Cookie 管理
    # ============================================================================
    if not login_to_threads():
        raise Exception("❌ 無法登入 Threads，請檢查帳號或網絡連接")
    
    # ============================================================================
    # 2. 訪問搜尋頁面
    # ============================================================================
    print("\n🔍 訪問搜尋頁面...")
    driver.get("https://www.threads.com/search/")
    
    # 添加隨機延遲 - 防止檢測
    wait_time = random.uniform(3, 5)
    logger.info(f"⏳ 隨機延遲 {wait_time:.1f} 秒，等待頁面加載...")
    time.sleep(wait_time)
    
    # ============================================================================
    # 3. 提取趨勢
    # ============================================================================
    
    # 使用 Selenium 直接從 JavaScript 加載的 DOM 中提取
    trends = []
    
    # 方法 1: 查找所有可點擊元素，過濾出趨勢
    clickable_elements = driver.find_elements(By.CSS_SELECTOR, "a, [role='button'], [onclick]")
    
    print(f"\n找到 {len(clickable_elements)} 個可點擊元素")
    
    # ============================================================================
    # 4. 異常告警 - 監控反爬蟲檢測信號
    # ============================================================================
    if len(clickable_elements) < 20:
        logger.warning(f"🚨 異常告警：可點擊元素過少 ({len(clickable_elements)}) - 可能被反爬蟲檢測或頁面加載不完全")
        # 不中斷執行，繼續嘗試提取
    
    # 排除的 UI 文本（包括具體的 UI 描述）
    excluded_patterns = ['為你推薦', '新串文', '搜尋', '通知', '動態', '個人檔案', 
                        '洞察報告', '已儲存', '編輯', '追蹤', '登出', '登入',
                        '附帶原始貼文', '大家討論', '精選最新', '篩選取消']
    
    # 提取趨勢
    for idx, elem in enumerate(clickable_elements):
        try:
            text = elem.text.strip()
            
            if not text or len(text) < 3:
                continue
            
            # 跳過 UI 元素
            if any(pattern in text for pattern in excluded_patterns):
                continue
            
            # 只關心包含中文的元素（趨勢通常是中文）
            if not any('\u4e00' <= c <= '\u9fff' for c in text):
                continue
            
            # 只取第一行作為趨勢標題（忽略詳細描述和計數）
            first_line = text.split('\n')[0].strip()
            
            # 再次檢查是否有效
            if not first_line or len(first_line) < 3 or len(first_line) > 150:
                continue
            
            if first_line not in [t['trend'] for t in trends]:
                print(f"  找到趨勢 {len(trends)+1}: {first_line[:60]}")
                trends.append({"trend": first_line, "platform": "threads"})
                
                if len(trends) >= 5:
                    break
        except Exception as e:
            pass
    
    # 如果用 Selenium 方法沒找到足夠的趨勢，嘗試 BeautifulSoup + regex
    if len(trends) < 5:
        print("\n📊 使用 BeautifulSoup 備用方法...")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        all_text = soup.get_text()
        
        # 分割成行並尋找合理長度的中文文本
        lines = [line.strip() for line in all_text.split('\n') if line.strip()]
        
        for line in lines:
            if (5 < len(line) < 150 and
                any('\u4e00' <= c <= '\u9fff' for c in line) and
                not any(pattern in line for pattern in excluded_patterns) and
                line not in [t['trend'] for t in trends]):
                
                print(f"  找到趨勢 {len(trends)+1}: {line[:60]}")
                trends.append({"trend": line, "platform": "threads"})
                
                if len(trends) >= 5:
                    break
    
    # 顯示結果
    if trends:
        print("\n" + "=" * 60)
        print("📊 提取的趨勢：")
        print("=" * 60)
        for idx, trend in enumerate(trends, 1):
            print(f"{idx}. {trend['trend'][:80]}")
        
        # 保存為 JSON
        with open('threads_trends.json', 'w', encoding='utf-8') as f:
            json.dump(trends, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 已保存 {len(trends)} 個趨勢到 threads_trends.json")
    else:
        logger.error("❌ 未找到任何趨勢 - 可能被反爬蟲檢測 (HTTP 429/403)")
        logger.error("🚨 可能的原因：")
        logger.error("   1. IP 被限流 (HTTP 429) - 請增加訪問間隔")
        logger.error("   2. 帳號被禁用 (HTTP 403) - 請嘗試其他帳號")
        logger.error("   3. 頁面加載失敗 - 請檢查網絡連接")

except Exception as e:
    logger.error(f"❌ 錯誤: {e}")
    
    # ============================================================================
    # 4. 異常分類與建議
    # ============================================================================
    import traceback
    error_trace = traceback.format_exc()
    
    if "429" in str(e):
        logger.error("🚨 HTTP 429 - 被限流")
        logger.error("建議：增加 wait_time 範圍，從 random.uniform(3, 5) 改為 random.uniform(5, 10)")
    elif "403" in str(e):
        logger.error("🚨 HTTP 403 - 帳號被禁用或 IP 被封禁")
        logger.error("建議：更換帳號或使用代理 IP")
    elif "timeout" in str(e).lower():
        logger.error("🚨 頁面加載超時")
        logger.error("建議：增加 WebDriverWait 超時時間，從 15 秒改為 30 秒")
    
    logger.debug(f"詳細堆棧：\n{error_trace}")
    print(f"\n詳細堆棧信息：\n{error_trace}")

finally:
    logger.info("🔌 關閉瀏覽器...")
    driver.quit()
    logger.info("✅ 爬蟲完成")
