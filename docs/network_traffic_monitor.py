#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 GCP 出站流量監控工具包
測試和驗證所有出站流量源，估計月度成本

使用方式:
    python3 network_traffic_monitor.py --check-all      # 全面檢查
    python3 network_traffic_monitor.py --api discord    # 只檢查 Discord
    python3 network_traffic_monitor.py --estimate       # 流量預估
"""

import asyncio
import aiohttp
import time
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import subprocess

# 彩色輸出
class Color:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(msg):
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*70}{Color.END}")
    print(f"{Color.BOLD}{Color.CYAN}▶ {msg}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{'='*70}{Color.END}\n")

def print_success(msg):
    print(f"{Color.GREEN}✅ {msg}{Color.END}")

def print_error(msg):
    print(f"{Color.RED}❌ {msg}{Color.END}")

def print_warning(msg):
    print(f"{Color.YELLOW}⚠️  {msg}{Color.END}")

def print_info(msg):
    print(f"{Color.CYAN}ℹ️  {msg}{Color.END}")

@dataclass
class TrafficEstimate:
    """流量估計數據"""
    name: str                           # 名稱
    daily_mb: float                     # 每日 MB
    monthly_mb: float                   # 每月 MB
    description: str                    # 描述
    risk_level: str                     # 風險等級: low / medium / high
    
    def __str__(self):
        emoji_risk = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        return f"{emoji_risk[self.risk_level]} {self.name:20} | {self.daily_mb:8.2f} MB/日 | {self.monthly_mb:8.2f} MB/月"

class NetworkTrafficMonitor:
    """出站流量監控類"""
    
    def __init__(self):
        self.estimates: List[TrafficEstimate] = []
        self.start_time = datetime.now()
    
    # ========== Discord API 檢查 ==========
    async def check_discord(self) -> Optional[TrafficEstimate]:
        """檢查 Discord WebSocket 連接"""
        print_header("Discord API 檢查")
        
        try:
            # Discord 沒有公開檢查端點，但可以檢查隧道
            tunnel_url = os.getenv("TUNNEL_URL", "https://katrina-brief-fish-educators.trycloudflare.com")
            
            # 簡單 ping 測試
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{tunnel_url}/api/auth/status", timeout=5) as resp:
                    response_size = len(await resp.content.read())
                    print_success(f"隧道可達 (狀態: {resp.status})")
        except Exception as e:
            print_error(f"隧道檢查失敗: {e}")
            return None
        
        # Discord 流量估計
        daily_mb = 40  # 保守估計
        monthly_mb = daily_mb * 30
        
        estimate = TrafficEstimate(
            name="Discord Bot",
            daily_mb=daily_mb,
            monthly_mb=monthly_mb,
            description="WebSocket + embed 更新 + 圖表上傳",
            risk_level="medium"
        )
        
        print_info(f"WebSocket 連接: ~2-5 KB/分鐘")
        print_info(f"訊息發送: ~30 KB/次 (含 embed)")
        print_info(f"市場更新: 30分鐘一次")
        print(estimate)
        
        return estimate
    
    # ========== yfinance 檢查 ==========
    async def check_yfinance(self) -> Optional[TrafficEstimate]:
        """檢查 yfinance API 流量"""
        print_header("yfinance 流量檢查")
        
        try:
            import yfinance as yf
            
            # 測試單次查詢
            ticker = yf.Ticker("2330.TW")
            start_time = time.time()
            
            history = ticker.history(period="1d")
            elapsed = time.time() - start_time
            
            if history.empty:
                print_warning("未能獲取到資料")
                return None
            
            print_success(f"成功獲取台積電價格: {history['Close'].iloc[-1]:.2f} (耗時: {elapsed:.2f}秒)")
            
            # 估計區間查詢大小
            history_3m = ticker.history(period="3mo")
            if len(history_3m) > 0:
                print_info(f"3 個月歷史數據: {len(history_3m)} 筆")
                print_info(f"估計每次查詢: 100-200 KB")
        
        except ImportError:
            print_error("yfinance 未安裝")
            return None
        except Exception as e:
            print_error(f"yfinance 測試失敗: {e}")
            return None
        
        # 流量估計
        daily_queries = 5 * 50  # 50 個用戶，每人 5 次查詢/天
        kb_per_query = 75  # 平均 75 KB
        daily_mb = (daily_queries * kb_per_query) / 1024
        monthly_mb = daily_mb * 30
        
        estimate = TrafficEstimate(
            name="yfinance",
            daily_mb=daily_mb,
            monthly_mb=monthly_mb,
            description="股票、加密貨幣、原物料報價",
            risk_level="medium"
        )
        
        print(estimate)
        return estimate
    
    # ========== Google Sheets 檢查 ==========
    async def check_google_sheets(self) -> Optional[TrafficEstimate]:
        """檢查 Google Sheets 同步流量"""
        print_header("Google Sheets 同步檢查")
        
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            
            creds_path = "google_credentials.json"
            if not os.path.exists(creds_path):
                print_warning(f"找不到認證文件: {creds_path}")
                print_info("跳過實際連接測試，使用預估值")
            else:
                print_info("找到認證文件，可以進行實際測試")
                # 實際連接代碼（可選）
        
        except ImportError:
            print_warning("gspread 或 google.oauth2  未安裝")
        except Exception as e:
            print_error(f"Google Sheets 檢查失敗: {e}")
            return None
        
        # 流量估計
        # 整表同步: 100+ 用戶行 × 20+ 欄位
        kb_per_sync = 75  # 平均 75 KB
        daily_syncs = 4   # 每日 4 次同步
        daily_mb = (kb_per_sync * daily_syncs * 2) / 1024  # × 2 (往返)
        monthly_mb = daily_mb * 30
        
        estimate = TrafficEstimate(
            name="Google Sheets",
            daily_mb=daily_mb,
            monthly_mb=monthly_mb,
            description="User data 雙向同步",
            risk_level="low"
        )
        
        print_info(f"整表同步大小: ~75 KB")
        print_info(f"同步頻率: 每日 4 次 (08:00 12:00 16:00 20:00)")
        print_info(f"往返流量: ~600 KB/天")
        print(estimate)
        
        return estimate
    
    # ========== AI API 檢查 ==========
    async def check_ai_apis(self) -> Optional[TrafficEstimate]:
        """檢查 AI API 流量"""
        print_header("AI API 流量檢查")
        
        # 檢查環境變數
        has_gemini = bool(os.getenv("AI_API_KEY"))
        has_groq = bool(os.getenv("GROQ_API_KEY"))
        has_github = bool(os.getenv("GITHUB_MODELS_API_KEY"))
        
        apis_available = sum([has_gemini, has_groq, has_github])
        print_info(f"可用 API: {apis_available}/3")
        
        if has_gemini:
            print_success("✓ Gemini (主)")
        if has_github:
            print_success("✓ GitHub Models (備)")
        if has_groq:
            print_success("✓ Groq (備)")
        
        if apis_available == 0:
            print_warning("無 AI API 配置")
        
        # 流量估計
        # 每周使用場景: 命令 (2次) + 故事 (1次) ≈ 3次
        requests_per_week = 3
        kb_per_request = 2.5  # 平均 2.5 KB
        requests_per_month = requests_per_week * 4
        daily_mb = (requests_per_month * kb_per_request) / 1024 / 30
        monthly_mb = daily_mb * 30
        
        estimate = TrafficEstimate(
            name="AI APIs",
            daily_mb=daily_mb,
            monthly_mb=monthly_mb,
            description="Gemini + 備用 APIs",
            risk_level="low"
        )
        
        print_info(f"調用場景: AI 命令、工作故事、勸告")
        print_info(f"平均請求大小: 1-3 KB")
        print(estimate)
        
        return estimate
    
    # ========== 動畫 API 檢查 ==========
    async def check_anime_api(self) -> Optional[TrafficEstimate]:
        """檢查動畫追蹤 API 流量"""
        print_header("動畫追蹤 API 檢查")
        
        api_url = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.content.read()
                        response_size_kb = len(data) / 1024
                        print_success(f"API 可達 (回應大小: {response_size_kb:.1f} KB)")
                    else:
                        print_warning(f"API 回應異常: {resp.status}")
        except Exception as e:
            print_error(f"API 測試失敗: {e}")
            return None
        
        # 流量估計
        # 每日 1 次定期檢查 + 用戶查詢
        api_request_kb = 30
        html_request_kb = 150
        daily_api_requests = 1
        weekly_user_queries = 10
        daily_user_queries = weekly_user_queries / 7
        
        daily_mb = (api_request_kb * daily_api_requests + 
                   html_request_kb * daily_user_queries) / 1024
        monthly_mb = daily_mb * 30
        
        estimate = TrafficEstimate(
            name="Anime API",
            daily_mb=daily_mb,
            monthly_mb=monthly_mb,
            description="Bahamut 動畫追蹤",
            risk_level="low"
        )
        
        print_info(f"API 端點: https://api.gamer.com.tw")
        print_info(f"網頁爬蟲: https://ani.gamer.com.tw")
        print_info(f"每日檢查: 1 次 (~30 KB)")
        print(estimate)
        
        return estimate
    
    
    # ========== 備份 API 檢查 ==========
    async def check_backup_api(self) -> Optional[TrafficEstimate]:
        """檢查備份流量"""
        print_header("週備份檢查")
        
        # 備份特性
        db_size_mb = 5  # 估計資料庫大小
        backup_frequency = 1  # 週 1 次
        
        # 兩個地方: 本機 + Google Sheets
        daily_mb = (db_size_mb * backup_frequency * 2) / 7  # ~1.4 MB/天
        monthly_mb = daily_mb * 30
        
        estimate = TrafficEstimate(
            name="週備份",
            daily_mb=daily_mb,
            monthly_mb=monthly_mb,
            description="本機 + Google Sheets",
            risk_level="low"
        )
        
        print_info(f"資料庫大小: ~{db_size_mb} MB")
        print_info(f"備份頻率: 每週 1 次")
        print_info(f"目標: 本機 + Google Sheets")
        print(estimate)
        
        return estimate
    
    # ========== 生成報告 ==========
    def generate_report(self):
        """生成完整的流量估計報告"""
        print_header("📊 GCP 出站流量月度估計")
        
        if not self.estimates:
            print_error("無數據可用，請先執行檢查")
            return
        
        total_daily = sum(e.daily_mb for e in self.estimates)
        total_monthly = sum(e.monthly_mb for e in self.estimates)
        
        # 按風險等級分類
        high_risk = [e for e in self.estimates if e.risk_level == "high"]
        medium_risk = [e for e in self.estimates if e.risk_level == "medium"]
        low_risk = [e for e in self.estimates if e.risk_level == "low"]
        
        print("\n" + "="*70)
        print("📈 按流量大小排序:")
        print("="*70)
        for est in sorted(self.estimates, key=lambda x: x.monthly_mb, reverse=True):
            print(est)
        
        print("\n" + "="*70)
        print("⚠️  高風險流量源（需要優化）:")
        print("="*70)
        if high_risk:
            for est in high_risk:
                print(f"  {est}")
        else:
            print_success("無高風險源")
        
        print("\n" + "="*70)
        print("📊 總計:")
        print("="*70)
        print(f"  Daily:   {Color.BOLD}{total_daily:8.2f} MB{Color.END}")
        print(f"  Monthly: {Color.BOLD}{total_monthly:8.2f} MB{Color.END}")
        print(f"  Yearly:  {Color.BOLD}{total_monthly * 12:8.2f} MB{Color.END}")
        
        # 成本估計 (假設 $0.12 per GB 出站)
        monthly_gb = total_monthly / 1024
        monthly_cost = monthly_gb * 0.12
        annual_cost = monthly_cost * 12
        
        print("\n" + "="*70)
        print("💰 GCP 網路出站成本估計 (@$0.12/GB):")
        print("="*70)
        print(f"  Monthly: ${Color.BOLD}{monthly_cost:.2f}{Color.END}")
        print(f"  Annual:  ${Color.BOLD}{annual_cost:.2f}{Color.END}")
        print(f"  (Data: {Color.BOLD}{monthly_gb:.2f} GB/月{Color.END})")
        
        print("\n" + "="*70)
        print("🎯 優化建議:")
        print("="*70)

        print("2. yfinance: 提高快取時間或使用記憶體快取")
        print("3. Discord: 考慮使用 CDN 託管靜態圖表")
        print("4. Sheets: 只同步變更的行，降低同步頻率")

async def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="GCP 出站流量監控工具")
    parser.add_argument("--check-all", action="store_true", help="執行所有檢查")
    parser.add_argument("--api", help="只檢查特定 API (discord, yfinance, sheets, ai, anime)")
    parser.add_argument("--estimate", action="store_true", help="只生成流量估計")
    
    args = parser.parse_args()
    
    monitor = NetworkTrafficMonitor()
    
    try:
        if args.check_all or (not args.api and not args.estimate):
            # 執行所有檢查
            est = await monitor.check_discord()
            if est:
                monitor.estimates.append(est)
            
            est = await monitor.check_yfinance()
            if est:
                monitor.estimates.append(est)
            
            est = await monitor.check_google_sheets()
            if est:
                monitor.estimates.append(est)
            
            est = await monitor.check_ai_apis()
            if est:
                monitor.estimates.append(est)
            
            est = await monitor.check_anime_api()
            if est:
                monitor.estimates.append(est)
            

            
            est = await monitor.check_backup_api()
            if est:
                monitor.estimates.append(est)
        
        elif args.api:
            if args.api == "discord":
                est = await monitor.check_discord()
            elif args.api == "yfinance":
                est = await monitor.check_yfinance()
            elif args.api == "sheets":
                est = await monitor.check_google_sheets()
            elif args.api == "ai":
                est = await monitor.check_ai_apis()
            elif args.api == "anime":
                est = await monitor.check_anime_api()

            else:
                print_error(f"未知的 API: {args.api}")
                sys.exit(1)
            
            if est:
                monitor.estimates.append(est)
        
        # 生成報告
        monitor.generate_report()
        
        elapsed = (datetime.now() - monitor.start_time).total_seconds()
        print(f"\n檢查完成 (耗時: {elapsed:.2f} 秒)\n")
    
    except KeyboardInterrupt:
        print_warning("\n用戶中斷")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
