#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 KKGroup 出站流量文檔和工具索引

此文件列出所有與流量分析、測試和監控相關的文檔和代碼
"""

import os
from pathlib import Path
from datetime import datetime

class TrafficDocumentIndex:
    """流量文檔索引"""
    
    ANALYSIS_DOCS = {
        "GCP_OUTBOUND_TRAFFIC_ANALYSIS.md": {
            "created": "2026-04-11",
            "description": "完整的出站流量深度分析",
            "sections": [
                "流量來源概覽 (Discord, yfinance, Sheets, AI, 動畫)",
                "詳細流量分析 (每個源的估計和代碼位置)",
                "月度流量估計總結",
                "優化建議",
                "行動清單"
            ],
            "size_kb": "~50"
        }
    }
    
    MONITORING_TOOLS = {
        "network_traffic_monitor.py": {
            "created": "2026-04-11",
            "description": "實時網路流量監控工具",
            "purpose": "檢查和估計各個 API 的流量",
            "features": [
                "Discord API 檢查",
                "yfinance 流量檢查",
                "Google Sheets 同步檢查",
                "AI APIs 檢查",
                "動畫追蹤 API 檢查",
                "週備份檢查",
                "完整報告生成",
                "成本估計 (@$0.12/GB)"
            ],
            "usage": "python3 network_traffic_monitor.py --check-all",
            "args": [
                "--check-all   # 執行所有檢查",
                "--api yfinance # 只檢查特定 API",
                "--estimate    # 只生成流量估計"
            ]
        },
        
        "traffic_optimization_audit.py": {
            "created": "2026-04-11",
            "description": "流量優化審計工具",
            "purpose": "找出瓶頸和優化機會",
            "features": [
                "yfinance 快取檢查",
                "Google Sheets 同步檢查",
                "資料庫大小檢查",
                "Discord 配置檢查",
                "AI API 備用方案檢查",
                "優先級清單生成"
            ],
            "usage": "python3 traffic_optimization_audit.py"
        }
    }
    
    DIAGNOSTIC_TOOLS = {
        "oauth_health_check.py": {
            "description": "OAuth 健康檢查",
            "checks": [
                "環境配置驗證",
                "隧道連接檢查",
                "OAuth 端點檢查",
                "Discord API 連接"
            ],
            "api_base": "https://katrina-brief-fish-educators.trycloudflare.com/api/auth"
        },
        
        "diagnose_tunnel.py": {
            "description": "隧道診斷工具",
            "checks": [
                "Nginx 監聽狀態",
                "Nginx 配置",
                "存取日誌",
                "靜態檔案驗證"
            ],
            "gcp_instance": "e193752468@instance-20250501-142333"
        },
        
        "verify_user_id.py": {
            "description": "用戶 ID 驗證",
            "purpose": "檢查用戶 ID 和資料庫完整性"
        },
        
        "verify_kkcoin.py": {
            "description": "KK幣計算驗證",
            "purpose": "驗證 KK幣排行榜正確性"
        },
        
        "verify_tools.py": {
            "description": "工具驗證",
            "purpose": "驗證 AI 工具和函數呼叫"
        },
        
        "verify_new_api_key.py": {
            "description": "API 密鑰驗證",
            "purpose": "驗證 API 密鑰是否有效"
        },
        
        "inspect_db.py": {
            "description": "資料庫檢查",
            "purpose": "檢查資料庫完整性和修復"
        }
    }
    
    BACKUP_AND_SYNC = {
        "weekly_backup.py": {
            "description": "週備份腳本",
            "features": [
                "本機備份 (backups/ 目錄)",
                "Google Sheets 備份",
                "保留最近 8 週備份"
            ],
            "schedule": "0 3 * * 1 (每週一 03:00)",
            "db_size_mb": "~5",
            "traffic_impact": "~10 MB/週"
        },
        
        "sync_to_sheet.py": {
            "description": "Google Sheets 同步",
            "purpose": "與 Google Sheets 雙向同步用戶數據",
            "sync_types": [
                "SHEET → DB (gspread 讀取)",
                "DB → SHEET (gspread 寫入)"
            ]
        },
        
        "sheet_sync_manager.py": {
            "description": "Sheets 同步管理器",
            "features": [
                "自動表頭檢測",
                "動態欄位適應",
                "完整日誌記錄"
            ]
        },
        
        "sync_gcp_database.py": {
            "description": "從 GCP 複製資料庫",
            "purpose": "使用 gcloud compute scp 複製 VM 上的資料庫"
        }
    }
    
    TESTING_TOOLS = {
        "test_welcome_resilience.py": {
            "description": "歡迎流程異常容限測試",
            "tests": [
                "create_user_data 重試機制",
                "圖片獲取 3 層級降級",
                "on_member_join 容限檢查清單",
                "視覺代碼審查指引"
            ],
            "location": "uicommands/welcome_message.py"
        }
    }
    
    API_CODE_LOCATIONS = {
        "Discord Bot": {
            "files": ["bot.py", "shopbot.py", "uibot.py"],
            "traffic": "40-80% (WebSocket + embed 更新)",
            "location": "根目錄"
        },
        
        "yfinance": {
            "files": ["utils/stock_api.py", "shop_commands/stock_market.py"],
            "traffic": "10-15% (股票/加密/原物料查詢)",
            "cache": "5 分鐘",
            "estimate": "225 MB/月"
        },
        
        "Google Sheets": {
            "files": ["sync_to_sheet.py", "sheet_sync_manager.py", "sheet_driven_db.py"],
            "traffic": "3-5% (雙向同步)",
            "estimate": "18 MB/月"
        },
        
        "AI APIs": {
            "files": ["commands/AI.py", "prompt_function_calling.py"],
            "apis": ["Gemini (主)", "GitHub Models (備)", "Groq (備)"],
            "traffic": "5-10% (function calling)",
            "estimate": "1-5 MB/月"
        },
        
        "Anime Tracker": {
            "files": ["commands/anime_tracker.py"],
            "apis": ["api.gamer.com.tw", "ani.gamer.com.tw"],
            "traffic": "<2% (每日定時)",
            "estimate": "7-8 MB/月"
        },
        

    }
    
    @classmethod
    def print_index(cls):
        """打印完整索引"""
        
        print("\n" + "="*80)
        print("📚 KKGroup 出站流量文檔和工具索引")
        print("="*80 + "\n")
        
        # 分析文檔
        print("📄 分析文檔")
        print("─" * 80)
        for doc_name, info in cls.ANALYSIS_DOCS.items():
            print(f"\n  📘 {doc_name}")
            print(f"     建立: {info['created']}")
            print(f"     描述: {info['description']}")
            print(f"     大小: {info['size_kb']} KB")
            print(f"     章節:")
            for section in info['sections']:
                print(f"       • {section}")
        
        # 監控工具
        print("\n\n🔧 監控工具")
        print("─" * 80)
        
        for tool_name, info in cls.MONITORING_TOOLS.items():
            print(f"\n  🛠️  {tool_name}")
            print(f"     建立: {info['created']}")
            print(f"     描述: {info['description']}")
            print(f"     功能:")
            for feature in info['features']:
                print(f"       • {feature}")
            print(f"     使用: {info['usage']}")
            print(f"     參數:")
            for arg in info.get('args', []):
                print(f"       $ {arg}")
        
        # 診斷工具
        print("\n\n🔍 診斷工具")  
        print("─" * 80)
        for tool_name, info in cls.DIAGNOSTIC_TOOLS.items():
            print(f"\n  🛠️  {tool_name}")
            print(f"     描述: {info['description']}")
            print(f"     檢查: {', '.join(info.get('checks', []))}")
        
        # 備份和同步
        print("\n\n💾 備份和同步工具")
        print("─" * 80)
        for tool_name, info in cls.BACKUP_AND_SYNC.items():
            print(f"\n  🛠️  {tool_name}")
            print(f"     描述: {info['description']}")
        
        # 測試工具
        print("\n\n🧪 測試工具")
        print("─" * 80)
        for tool_name, info in cls.TESTING_TOOLS.items():
            print(f"\n  🛠️  {tool_name}")
            print(f"     描述: {info['description']}")
        
        # API 代碼位置
        print("\n\n📍 API 代碼位置")
        print("─" * 80)
        for api_name, info in cls.API_CODE_LOCATIONS.items():
            print(f"\n  🌐 {api_name}")
            print(f"     文件: {', '.join(info['files'])}")
            print(f"     流量: {info.get('traffic', '未知')}")
            if 'estimate' in info:
                print(f"     估計: {info['estimate']}")
        
        # 快速開始
        print("\n\n🚀 快速開始")
        print("─" * 80)
        print("""
  執行完整流量檢查:
    $ python3 network_traffic_monitor.py --check-all

  檢查特定 API:
    $ python3 network_traffic_monitor.py --api yfinance

  執行優化審計:
    $ python3 traffic_optimization_audit.py

  檢查 OAuth 健康狀態:
    $ python3 oauth_health_check.py

  查看隧道狀態:
    $ python3 diagnose_tunnel.py

  驗證 KK幣排行榜:
    $ python3 verify_kkcoin.py

  執行週備份:
    $ python3 weekly_backup.py
        """)
        
        # 統計信息
        print("\n\n📊 統計")
        print("─" * 80)
        total_docs = len(cls.ANALYSIS_DOCS)
        total_tools = len(cls.MONITORING_TOOLS) + len(cls.DIAGNOSTIC_TOOLS)
        total_api = len(cls.API_CODE_LOCATIONS)
        
        print(f"  分析文檔: {total_docs}")
        print(f"  監控工具: {total_tools}")
        print(f"  API 源: {total_api}")
        print(f"  建立日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    TrafficDocumentIndex.print_index()
    
    print("\n\n💡 建議:")
    print("─" * 80)
    print("""
  1. 閱讀 GCP_OUTBOUND_TRAFFIC_ANALYSIS.md 了解完整分析

  2. 執行 network_traffic_monitor.py 檢查當前流量

  3. 執行 traffic_optimization_audit.py 找出優化機會

  4. 優先實施:
     • 優化 yfinance 快取 (可節省 20-30%)
     • 優化 Google Sheets 同步 (可節省 50%)

  5. 每月執行一次 network_traffic_monitor.py 以監控成本
    """)
