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
                        
                        # 每 20 秒提示一次
                        if wait_time % 20 == 0:
                            logger.info(f"⏳ 還在等待... ({wait_time}/{max_wait} 秒)")
                            
                            # 嘗試自動點擊中間的登入按鈕
                            try:
                                # 尋找登入按鈕
                                login_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), '登入')]|//button[contains(text(), '登錄')]|//a[contains(text(), '登入')]")
                                
                                if login_buttons:
                                    logger.info("🔘 找到登入按鈕，自動點擊...")
                                    # 點擊第一個登入按鈕
                                    driver.execute_script("arguments[0].scrollIntoView(true);", login_buttons[0])
                                    time.sleep(1)
                                    login_buttons[0].click()
                                    logger.info("✅ 已點擊登入按鈕")
                                    time.sleep(2)  # 等待頁面反應
                            except:
                                pass
                        
                        try:
                            # 檢查是否已登入（URL 變化）
                            current_url = driver.current_url
                            if 'threads.com' in current_url and 'login' not in current_url.lower() and '/threads.com' in current_url:
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
    # 2. 訪問搜尋頁面（有趨勢列表）
    # ============================================================================
    print("\n🔍 訪問搜尋頁面...")
    driver.get("https://www.threads.com/search")
    
    # 添加隨機延遲 - 防止檢測
    wait_time = random.uniform(3, 5)
    logger.info(f"⏳ 隨機延遲 {wait_time:.1f} 秒，等待頁面加載...")
    time.sleep(wait_time)
    
    # ============================================================================
    # 3. 提取趨勢 - 改進方案
    # ============================================================================
    
    print("\n🔍 開始提取趨勢（多方法組合）...")
    trends = []
    
    # 步驟 1: 模擬用戶操作 - 滾動頁面讓 JS 加載更多內容
    print("📜 模擬滾動操作，觸發動態加載...")
    for scroll_step in range(3):
        driver.execute_script("window.scrollBy(0, 500);")
        time.sleep(random.uniform(1, 2))
    
    # 回到頁面頂部
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)
    
    # 步驟 2: 等待頁面穩定（讓所有 JS 執行完成）
    print("⏳ 等待頁面穩定...")
    for i in range(5):
        try:
            driver.find_elements(By.TAG_NAME, "button")  # 等待至少有按鈕
            break
        except:
            time.sleep(1)
    
    # 步驟 3: 智能提取趨勢
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # 定義排除的關鍵字
    excluded_keywords = [
        '使用', 'Instagram', '帳號', '繼續', '登入', '服務條款',
        '隱私政策', 'Cookie', '政策', '回報問題', '編輯', '追蹤',
        '按鈕', '連結', '點擊', '搜尋', '通知', '動態', '個人檔案',
        '首頁', '訊息', '書籤', '設定', '更多', '分享', '評論',
        'Threads', 'Meta', 'Facebook', '廣告', '推薦', '為你推薦',
        '精選', '熱門', '最新', '活動', '活躍', '用戶', '追蹤者'
    ]
    
    # 定義趨勢的特徵
    def is_likely_trend(text):
        """判斷文本是否看起來像趨勢"""
        if not text or len(text) < 2 or len(text) > 100:
            return False
        
        # 排除關鍵字
        if any(kw in text for kw in excluded_keywords):
            return False
        
        # 排除互動數統計文本
        interaction_keywords = ['讚', '轉發', '回覆', '分享', '人喜歡', '人回覆', '人轉發', 
                               '人分享', '秒前', '分鐘前', '小時前', '天前']
        if any(kw in text for kw in interaction_keywords):
            return False
        
        # 排除長的幫助文本
        if len(text) > 30:
            return False
        
        # 必須包含中文
        if not any('\u4e00' <= c <= '\u9fff' for c in text):
            return False
        
        # 不能是單個字
        if len(text) == 1:
            return False
        
        # 排除純數字或過多數字
        digit_ratio = sum(1 for c in text if c.isdigit()) / len(text)
        if digit_ratio > 0.3:  # 超過 30% 數字
            return False
        
        return True
    
    # 方法 1: 從所有文本節點提取
    print("\n📍 方法 1: 文本節點掃描...")
    text_nodes = []
    for elem in soup.find_all(text=True):
        text = elem.strip()
        if is_likely_trend(text):
            text_nodes.append(text)
    
    print(f"   找到 {len(text_nodes)} 個候選文本")
    
    # 方法 2: 從特定容器提取
    print("\n📍 方法 2: 容器分析...")
    
    containers = [
        soup.find_all('button'),
        soup.find_all('a'),
        soup.find_all('span'),
        soup.find_all('div', {'role': 'button'}),
    ]
    
    for container_list in containers:
        for container in container_list:
            text = container.get_text().strip()
            if is_likely_trend(text):
                text_nodes.append(text)
    
    # 去重
    unique_trends = list(set(text_nodes))
    print(f"   找到 {len(unique_trends)} 個唯一候選詞彙")
    
    # 方法 3: 排序並選擇最可能的趨勢
    print("\n📍 方法 3: 趨勢評分...")
    
    def score_trend(text):
        """給趨勢評分（看起來越像趨勢分數越高）"""
        score = 0
        
        # 長度在 4-25 字最好（趨勢通常不會太長）
        if 4 <= len(text) <= 25:
            score += 10
        elif len(text) < 4:
            score -= 10
        
        # 包含數字的通常是熱度或排名
        if any(c.isdigit() for c in text):
            score += 3
        
        # 常見話題符號
        if '#' in text or '@' in text:
            score += 5
        
        # 常見詞尾（通常趨勢會以這些結尾）
        if any(text.endswith(end) for end in ['?', '！', '!', '嗎', '了', '中', '過', '著', '熱', '榜', '排']):
            score += 2
        
        # 避免互動數
        if any(word in text for word in ['讚', '轉發', '回覆', '分享']):
            score -= 100
        
        return score
    
    scored_trends = [(t, score_trend(t)) for t in unique_trends]
    scored_trends.sort(key=lambda x: x[1], reverse=True)
    
    print("   📊 排名前 10 的候選趨勢:")
    for i, (trend, score) in enumerate(scored_trends[:10], 1):
        print(f"      {i}. [{score}分] {trend}")
    
    # 方法 4: 最終篩選
    print("\n📍 方法 4: 最終篩選...")
    final_trends = []
    
    for trend, score in scored_trends:
        # 至少要 2 分才算趨勢
        if score >= 2 and len(final_trends) < 5:
            # 再次檢查不是 UI 元素
            if not any(ui in trend for ui in ['使用', '登入', '帳號', '服務', '條款', '隱私', '回報']):
                final_trends.append({"trend": trend, "platform": "threads"})
                print(f"  ✅ 確認趨勢 {len(final_trends)}: {trend}")
    
    # 如果還是找不到，用文本節點作為備用
    if len(final_trends) < 5:
        print("\n⚠️  備用方案：使用文本節點...")
        for trend in text_nodes[:5]:
            if trend not in [t['trend'] for t in final_trends]:
                final_trends.append({"trend": trend, "platform": "threads"})
                print(f"  ✅ 備用趨勢 {len(final_trends)}: {trend}")
    
    trends = final_trends
    
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
