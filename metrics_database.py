"""
GCP Metrics 本地數據庫管理
存儲：
  • 網路出站流量（每30分鐘採集一個時間點）
  • 系統資源使用率（CPU、內存、磁盤）
  • 計費信息（月累積）
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# 台灣時區（UTC+8）
TAIWAN_TZ = timezone(timedelta(hours=8))

class MetricsDatabase:
    """GCP Metrics 本地 SQLite 數據庫"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'metrics_data.db')
        
        self.db_path = db_path
        self.init_tables()
    
    def get_connection(self):
        """取得數據庫連接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_tables(self):
        """初始化數據庫表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 網路流量時間序列表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS egress_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL UNIQUE,
                bytes REAL NOT NULL,
                mb REAL NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # 系統資源表（每個時間點）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL UNIQUE,
                cpu_percent REAL,
                memory_percent REAL,
                disk_percent REAL,
                created_at TEXT NOT NULL
            )
        """)
        
        # 計費信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS billing_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                total_cost REAL NOT NULL,
                currency TEXT,
                status TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        
        # 月累積流量表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_egress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                total_gb REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # 索引以加快查詢
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_egress_timestamp 
            ON egress_timeseries(timestamp DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_system_timestamp 
            ON system_stats(timestamp DESC)
        """)
        
        conn.commit()
        conn.close()
        print(f"[MetricsDB] ✅ 數據庫初始化完成: {self.db_path}")
    
    def add_egress_point(self, timestamp: datetime, bytes_value: float) -> bool:
        """
        添加一個出站流量數據點
        
        Args:
            timestamp: 數據時間點（datetime 對象）
            bytes_value: 字節數
            
        Returns:
            bool: 是否成功
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            timestamp_str = timestamp.isoformat()
            mb_value = bytes_value / (1024 * 1024)
            now = datetime.now(TAIWAN_TZ).isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO egress_timeseries 
                (timestamp, bytes, mb, created_at)
                VALUES (?, ?, ?, ?)
            """, (timestamp_str, bytes_value, mb_value, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[MetricsDB ERROR] 添加出站流量失敗: {e}")
            return False
    
    def add_system_stats(self, timestamp: datetime, cpu_percent: Optional[float], 
                         memory_percent: Optional[float], disk_percent: Optional[float]) -> bool:
        """
        添加系統資源統計
        
        Args:
            timestamp: 數據時間點
            cpu_percent: CPU 使用率（%）
            memory_percent: 內存使用率（%）
            disk_percent: 磁盤使用率（%）
            
        Returns:
            bool: 是否成功
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            timestamp_str = timestamp.isoformat()
            now = datetime.now(TAIWAN_TZ).isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO system_stats 
                (timestamp, cpu_percent, memory_percent, disk_percent, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (timestamp_str, cpu_percent, memory_percent, disk_percent, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[MetricsDB ERROR] 添加系統統計失敗: {e}")
            return False
    
    def add_billing_data(self, month: str, total_cost: float, currency: str = "USD", 
                         status: str = "✓ 正常") -> bool:
        """
        添加計費信息
        
        Args:
            month: 月份（YYYY-MM 格式）
            total_cost: 總成本
            currency: 貨幣（默認 USD）
            status: 狀態說明
            
        Returns:
            bool: 是否成功
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now(TAIWAN_TZ).isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO billing_data 
                (month, total_cost, currency, status, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (month, total_cost, currency, status, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[MetricsDB ERROR] 添加計費數據失敗: {e}")
            return False
    
    def add_monthly_egress(self, month: str, total_gb: float) -> bool:
        """
        添加月累積出站流量
        
        Args:
            month: 月份（YYYY-MM 格式）
            total_gb: 累積流量（GB）
            
        Returns:
            bool: 是否成功
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now(TAIWAN_TZ).isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO monthly_egress 
                (month, total_gb, updated_at)
                VALUES (?, ?, ?)
            """, (month, total_gb, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[MetricsDB ERROR] 添加月累積流量失敗: {e}")
            return False
    
    def get_egress_data(self, hours: int = 6) -> List[Dict]:
        """
        獲取最近 N 小時的出站流量數據
        
        Args:
            hours: 小時數
            
        Returns:
            List[Dict]: 數據點列表 [{"timestamp": datetime, "mb": float}, ...]
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cutoff_time = (datetime.now(TAIWAN_TZ) - timedelta(hours=hours)).isoformat()
            
            cursor.execute("""
                SELECT timestamp, mb FROM egress_timeseries
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """, (cutoff_time,))
            
            rows = cursor.fetchall()
            conn.close()
            
            data = []
            for row in rows:
                data.append({
                    "timestamp": datetime.fromisoformat(row['timestamp']),
                    "mb": row['mb']
                })
            
            return data
        except Exception as e:
            print(f"[MetricsDB ERROR] 獲取出站流量數據失敗: {e}")
            return []
    
    def get_system_stats(self, hours: int = 6) -> List[Dict]:
        """
        獲取最近 N 小時的系統統計
        
        Args:
            hours: 小時數
            
        Returns:
            List[Dict]: 統計點列表
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cutoff_time = (datetime.now(TAIWAN_TZ) - timedelta(hours=hours)).isoformat()
            
            cursor.execute("""
                SELECT timestamp, cpu_percent, memory_percent, disk_percent 
                FROM system_stats
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """, (cutoff_time,))
            
            rows = cursor.fetchall()
            conn.close()
            
            data = []
            for row in rows:
                data.append({
                    "timestamp": datetime.fromisoformat(row['timestamp']),
                    "cpu_percent": row['cpu_percent'],
                    "memory_percent": row['memory_percent'],
                    "disk_percent": row['disk_percent']
                })
            
            return data
        except Exception as e:
            print(f"[MetricsDB ERROR] 獲取系統統計失敗: {e}")
            return []
    
    def get_billing_data(self, months: int = 3) -> Dict:
        """
        獲取最近 N 個月的計費信息
        
        Args:
            months: 月份數
            
        Returns:
            Dict: {month: {"total_cost": float, "currency": str, "status": str}, ...}
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT month, total_cost, currency, status
                FROM billing_data
                ORDER BY month DESC
                LIMIT ?
            """, (months,))
            
            rows = cursor.fetchall()
            conn.close()
            
            data = {}
            for row in rows:
                data[row['month']] = {
                    "total_cost": row['total_cost'],
                    "currency": row['currency'],
                    "status": row['status']
                }
            
            return data
        except Exception as e:
            print(f"[MetricsDB ERROR] 獲取計費數據失敗: {e}")
            return {}
    
    def get_monthly_egress(self, months: int = 3) -> Dict[str, float]:
        """
        獲取最近 N 個月的累積出站流量
        
        Args:
            months: 月份數
            
        Returns:
            Dict[str, float]: {month: total_gb, ...}
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT month, total_gb
                FROM monthly_egress
                ORDER BY month DESC
                LIMIT ?
            """, (months,))
            
            rows = cursor.fetchall()
            conn.close()
            
            data = {}
            for row in rows:
                data[row['month']] = row['total_gb']
            
            return data
        except Exception as e:
            print(f"[MetricsDB ERROR] 獲取月累積流量失敗: {e}")
            return {}
    
    def cleanup_old_data(self, days: int = 90):
        """
        清理 N 天以前的舊數據
        
        Args:
            days: 天數門檻
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cutoff_time = (datetime.now(TAIWAN_TZ) - timedelta(days=days)).isoformat()
            
            cursor.execute("DELETE FROM egress_timeseries WHERE timestamp < ?", (cutoff_time,))
            deleted_egress = cursor.rowcount
            cursor.execute("DELETE FROM system_stats WHERE timestamp < ?", (cutoff_time,))
            deleted_stats = cursor.rowcount
            
            deleted_count = deleted_egress + deleted_stats
            conn.commit()
            conn.close()
            
            print(f"[MetricsDB] 清理完成：刪除了 {deleted_count} 行舊數據（超過 {days} 天）")
        except Exception as e:
            print(f"[MetricsDB ERROR] 清理舊數據失敗: {e}")
    
    def get_last_update_time(self, table: str) -> Optional[datetime]:
        """
        獲取最後一次更新時間
        
        Args:
            table: 表名（'egress_timeseries', 'system_stats', 'billing_data'）
            
        Returns:
            Optional[datetime]: 最後更新時間或 None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if table == 'egress_timeseries':
                cursor.execute("SELECT timestamp FROM egress_timeseries ORDER BY timestamp DESC LIMIT 1")
            elif table == 'system_stats':
                cursor.execute("SELECT timestamp FROM system_stats ORDER BY timestamp DESC LIMIT 1")
            elif table == 'billing_data':
                cursor.execute("SELECT updated_at FROM billing_data ORDER BY updated_at DESC LIMIT 1")
            else:
                return None
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                timestamp_str = row[0]
                return datetime.fromisoformat(timestamp_str)
            
            return None
        except Exception as e:
            print(f"[MetricsDB ERROR] 獲取最後更新時間失敗: {e}")
            return None
    
    def get_data_count(self, table: str) -> int:
        """
        獲取表中的數據行數
        
        Args:
            table: 表名
            
        Returns:
            int: 行數
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            print(f"[MetricsDB ERROR] 獲取數據行數失敗: {e}")
            return 0
