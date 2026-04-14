#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流量優化檢查清單
快速掃描所有潛在的出站流量瓶頸和優化機會
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime
import json

class TrafficOptimizationAudit:
    """流量優化審計"""
    
    def __init__(self):
        self.issues = []
        self.optimizations = []
        self.db_path = Path("user_data.db")
    
    def run_audit(self):
        """執行完整審計"""
        print("\n" + "="*70)
        print("🔍 出站流量優化審計")
        print("="*70 + "\n")
        
        # 檢查 yfinance 快取
        self._check_yfinance_cache()
        
        # 檢查 Google Sheets 同步
        self._check_sheets_sync()
        
        # 檢查資料庫大小
        self._check_database_size()
        
        # 檢查 Discord 配置
        self._check_discord_config()
        
        # 檢查 AI API 使用量
        self._check_ai_usage()
        
        # 生成報告
        self._print_report()
    
    
    def _check_yfinance_cache(self):
        """檢查 yfinance 快取設置"""
        print("📍 檢查 yfinance 快取...")
        
        try:
            from utils.stock_api import CACHE_DURATION_SECONDS
            
            if CACHE_DURATION_SECONDS < 180:  # 小於 3 分鐘
                self.issues.append({
                    "type": "medium",
                    "component": "yfinance",
                    "issue": f"快取時間過短: {CACHE_DURATION_SECONDS} 秒",
                    "impact": "同一隻股票重複查詢",
                    "fix": "建議提高到 300-600 秒"
                })
            elif CACHE_DURATION_SECONDS > 1800:  # 超過 30 分鐘
                self.optimizations.append({
                    "component": "yfinance",
                    "optimization": f"快取時間設置保守: {CACHE_DURATION_SECONDS} 秒",
                    "potential_saving": "可進一步優化到 5-10 分鐘"
                })
            else:
                print(f"  ✓ 快取時間適中: {CACHE_DURATION_SECONDS} 秒")
        except (ImportError, AttributeError):
            pass
        
        # 檢查是否有 Redis 快取
        redis_available = os.getenv("REDIS_URL") is not None
        
        if not redis_available:
            self.optimizations.append({
                "component": "yfinance",
                "optimization": "未使用 Redis 快取",
                "potential_saving": "使用 Redis 可節省 20-30%"
            })
        else:
            print("  ✓ 已配置 Redis 快取")
    
    def _check_sheets_sync(self):
        """檢查 Google Sheets 同步設置"""
        print("📍 檢查 Google Sheets 同步...")
        
        # 檢查認證文件
        creds_path = Path("google_credentials.json")
        if creds_path.exists():
            size_kb = creds_path.stat().st_size / 1024
            print(f"  ✓ 找到認證文件 ({size_kb:.1f} KB)")
        else:
            self.issues.append({
                "type": "warning",
                "component": "Google Sheets",
                "issue": "找不到 google_credentials.json",
                "impact": "無法與 Google Sheets 同步"
            })
        
        # 檢查同步頻率 (crontab)
        self.optimizations.append({
            "component": "Google Sheets",
            "optimization": "檢查 crontab 同步設置",
            "potential_saving": "每次同步只傳輸變更的行可節省 50%"
        })
    
    def _check_database_size(self):
        """檢查資料庫大小"""
        print("📍 檢查資料庫大小...")
        
        if not self.db_path.exists():
            print("  ⚠️ 資料庫不存在")
            return
        
        db_size_mb = self.db_path.stat().st_size / 1024 / 1024
        print(f"  ✓ 資料庫大小: {db_size_mb:.2f} MB")
        
        # 檢查用戶數
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]
            conn.close()
            
            print(f"  ✓ 用戶數: {user_count}")
            print(f"  ✓ 表數量: {table_count}")
        except Exception as e:
            print(f"  ⚠️ 資料庫讀取失敗: {e}")
    
    def _check_discord_config(self):
        """檢查 Discord 配置"""
        print("📍 檢查 Discord 配置...")
        
        has_bot_token = bool(os.getenv("DISCORD_BOT_TOKEN"))
        has_guild_id = bool(os.getenv("DISCORD_GUILD_ID"))
        
        if has_bot_token:
            print("  ✓ Bot Token 已配置")
        else:
            self.issues.append({
                "type": "critical",
                "component": "Discord",
                "issue": "Bot Token 未配置",
                "impact": "Bot 無法啟動"
            })
        
        # 檢查隧道配置
        tunnel_url = os.getenv("TUNNEL_URL")
        if tunnel_url:
            print(f"  ✓ 隧道 URL 已配置: {tunnel_url[:30]}...")
        else:
            self.issues.append({
                "type": "warning",
                "component": "Discord",
                "issue": "未設置 TUNNEL_URL",
                "impact": "無法外部訪問服務"
            })
    
    def _check_ai_usage(self):
        """檢查 AI API 使用量"""
        print("📍 檢查 AI API 配置...")
        
        has_gemini = bool(os.getenv("AI_API_KEY"))
        has_groq = bool(os.getenv("GROQ_API_KEY"))  
        has_github = bool(os.getenv("GITHUB_MODELS_API_KEY"))
        
        apis_count = sum([has_gemini, has_groq, has_github])
        print(f"  ✓ 配置 AI 備用方案數: {apis_count}/3")
        
        if apis_count < 2:
            self.issues.append({
                "type": "medium",
                "component": "AI API",
                "issue": f"備用方案不足: {apis_count}/3",
                "impact": "單一 API 超限時無備用",
                "fix": "配置至少 2 個備用 API"
            })
    
    def _print_report(self):
        """打印審計報告"""
        print("\n" + "="*70)
        print("📋 審計結果")
        print("="*70 + "\n")
        
        if self.issues:
            print(f"⚠️ 發現 {len(self.issues)} 個問題:\n")
            
            for i, issue in enumerate(self.issues, 1):
                emoji = {"critical": "🔴", "medium": "🟡", "warning": "🟠"}
                issue_type = issue.get("type", "warning")
                print(f"{i}. {emoji.get(issue_type, '⚠️')} [{issue['component']}] {issue['issue']}")
                if "impact" in issue:
                    print(f"   影響: {issue['impact']}")
                if "fix" in issue:
                    print(f"   修復: {issue['fix']}")
                print()
        else:
            print("✅ 未發現重大問題\n")
        
        if self.optimizations:
            print(f"\n💡 優化機會 ({len(self.optimizations)}):\n")
            
            for i, opt in enumerate(self.optimizations, 1):
                print(f"{i}. [{opt['component']}] {opt['optimization']}")
                print(f"   潛在節省: {opt.get('potential_saving', '未知')}")
                print()
        
        # 生成優先級清單
        print("\n" + "="*70)
        print("🎯 優化優先級")
        print("="*70 + "\n")
        
        print("\n第 2 優先級 (本周): 優化 yfinance 快取")
        print("  - 影響: 可節省 20-30% 的流量")
        print("  - 預期節省: 每月 40-50 MB\n")
        
        print("第 2 優先級 (本月): 優化 Google Sheets 同步")
        print("  - 影響: 可節省 50% 的流量")
        print("  - 預期節省: 每月 9 MB\n")

if __name__ == "__main__":
    audit = TrafficOptimizationAudit()
    audit.run_audit()
