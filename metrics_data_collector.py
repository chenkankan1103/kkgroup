"""
GCP Metrics 數據採集器
定期從 GCP Cloud Monitoring 採集數據並存入本地 SQLite 數據庫
獨立的任務負責此工作，不影響 Discord bot 運行
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv
from metrics_database import MetricsDatabase

# 台灣時區（UTC+8）
TAIWAN_TZ = timezone(timedelta(hours=8))

# 嘗試導入 Google Cloud 庫
GOOGLE_CLOUD_AVAILABLE = False
try:
    from google.cloud import monitoring_v3, billing_v1
    from google.protobuf.timestamp_pb2 import Timestamp
    GOOGLE_CLOUD_AVAILABLE = True
    print("[GCP Collector] ✅ Google Cloud 庫已成功導入")
except ImportError as e:
    print(f"[GCP Collector] ⚠️ 無法導入 Google Cloud 庫: {e}")

load_dotenv()

class MetricsDataCollector:
    """GCP Metrics 數據採集器"""
    
    def __init__(self, project_id: str = "kkgroup", db_path: str = None):
        self.project_id = project_id
        self.db = MetricsDatabase(db_path)
        self.available = GOOGLE_CLOUD_AVAILABLE
        
        if self.available:
            try:
                self.metric_client = monitoring_v3.MetricServiceClient()
                self.billing_client = billing_v1.CloudBillingClient()
                print(f"[GCP Collector] ✅ 已初始化（project={project_id}）")
            except Exception as e:
                print(f"[GCP Collector] ⚠️ 初始化失敗: {e}")
                self.available = False
                self.metric_client = None
                self.billing_client = None
        else:
            self.metric_client = None
            self.billing_client = None
            print("[GCP Collector] ⚠️ Google Cloud 庫不可用，無法採集數據")
    
    async def collect_egress_data(self, hours: int = 6, timeout_sec: float = 15.0) -> int:
        """
        從 GCP 採集最近 N 小時的出站流量數據
        
        Args:
            hours: 查詢小時數
            timeout_sec: 超時秒數
            
        Returns:
            int: 成功採集的數據點數
        """
        if not self.available:
            print("[GCP Collector] ⚠️ GCP 不可用，跳過出站流量採集")
            return 0
        
        try:
            now = datetime.utcnow()
            start_time = now - timedelta(hours=hours)
            
            start_ts = Timestamp()
            start_ts.FromDatetime(start_time)
            end_ts = Timestamp()
            end_ts.FromDatetime(now)
            
            interval = monitoring_v3.TimeInterval(
                {"start_time": start_ts, "end_time": end_ts}
            )
            
            # 嘗試多個 metric type
            metric_types = [
                'compute.googleapis.com/instance/network/sent_bytes_count',
                'compute.googleapis.com/instance/network/sent_packets_count',
            ]
            
            print(f"[GCP Collector] 採集出站流量 (hours={hours})")
            
            total_points = 0
            
            for metric_type in metric_types:
                try:
                    metric_filter = f'metric.type="{metric_type}"'
                    
                    request = monitoring_v3.ListTimeSeriesRequest(
                        name=f"projects/{self.project_id}",
                        filter=metric_filter,
                        interval=interval,
                    )
                    
                    # 使用 asyncio.wait_for 強制超時
                    loop = asyncio.get_event_loop()
                    results = await asyncio.wait_for(
                        loop.run_in_executor(None, self.metric_client.list_time_series, request),
                        timeout=timeout_sec
                    )
                    series_list = list(results)
                    
                    if series_list:
                        for series in series_list:
                            for point in reversed(series.points):  # 從早到晚
                                try:
                                    timestamp = point.interval.end_time.timestamp()
                                    dt = datetime.fromtimestamp(timestamp, tz=TAIWAN_TZ)
                                    bytes_value = point.value.double_value if point.value else 0
                                    
                                    # 存入數據庫
                                    if self.db.add_egress_point(dt, bytes_value):
                                        total_points += 1
                                except Exception as e:
                                    print(f"[GCP Collector] 處理數據點異常: {e}")
                        
                        print(f"[GCP Collector] ✅ 成功採集 {total_points} 個出站流量數據點")
                        return total_points
                
                except asyncio.TimeoutError:
                    print(f"[GCP Collector] ⏱️ {metric_type} 查詢超時")
                    continue
                except Exception as e:
                    print(f"[GCP Collector] {metric_type} 失敗: {e}")
                    continue
            
            print(f"[GCP Collector] ⚠️ 無法獲取任何出站流量數據")
            return 0
            
        except Exception as e:
            print(f"[GCP Collector] 採集出站流量異常: {e}")
            return 0
    
    async def collect_system_stats(self, timeout_sec: float = 15.0) -> bool:
        """
        從 GCP 採集系統資源統計
        
        Args:
            timeout_sec: 超時秒數
            
        Returns:
            bool: 是否成功
        """
        if not self.available:
            print("[GCP Collector] ⚠️ GCP 不可用，跳過系統統計採集")
            return False
        
        try:
            print("[GCP Collector] 採集系統統計...")
            
            now = datetime.utcnow()
            start_time = now - timedelta(hours=1)
            
            start_ts = Timestamp()
            start_ts.FromDatetime(start_time)
            end_ts = Timestamp()
            end_ts.FromDatetime(now)
            
            interval = monitoring_v3.TimeInterval(
                {"start_time": start_ts, "end_time": end_ts}
            )
            
            # 查詢 CPU 使用率
            loop = asyncio.get_event_loop()
            
            metrics = {
                'cpu': 'compute.googleapis.com/instance/cpu/utilization',
                'memory': 'agent.googleapis.com/memory/percent_used',
                'disk': 'agent.googleapis.com/disk/percent_used',
            }
            
            stats = {}
            
            for key, metric_type in metrics.items():
                try:
                    metric_filter = f'metric.type="{metric_type}"'
                    request = monitoring_v3.ListTimeSeriesRequest(
                        name=f"projects/{self.project_id}",
                        filter=metric_filter,
                        interval=interval,
                    )
                    
                    results = await asyncio.wait_for(
                        loop.run_in_executor(None, self.metric_client.list_time_series, request),
                        timeout=timeout_sec / 3
                    )
                    series_list = list(results)
                    
                    if series_list and series_list[0].points:
                        # 取最新的數據點
                        point = series_list[0].points[0]
                        value = point.value.double_value if point.value else None
                        stats[key] = value
                        print(f"[GCP Collector] {key} = {value}")
                    else:
                        stats[key] = None
                        print(f"[GCP Collector] {key} 無數據")
                    
                except asyncio.TimeoutError:
                    print(f"[GCP Collector] {key} 查詢超時")
                    stats[key] = None
                except Exception as e:
                    print(f"[GCP Collector] {key} 查詢失敗: {e}")
                    stats[key] = None
            
            # 存入數據庫
            dt = datetime.now(TAIWAN_TZ)
            self.db.add_system_stats(
                dt, 
                stats.get('cpu'),
                stats.get('memory'),
                stats.get('disk')
            )
            
            print(f"[GCP Collector] ✅ 系統統計採集完成")
            return True
            
        except Exception as e:
            print(f"[GCP Collector] 採集系統統計異常: {e}")
            return False
    
    async def collect_monthly_egress(self, timeout_sec: float = 20.0) -> bool:
        """
        從 GCP 採集月累積出站流量
        
        Args:
            timeout_sec: 超時秒數
            
        Returns:
            bool: 是否成功
        """
        if not self.available:
            print("[GCP Collector] ⚠️ GCP 不可用，跳過月累積採集")
            return False
        
        try:
            print("[GCP Collector] 採集月累積出站流量...")
            
            now = datetime.utcnow()
            start_time = now - timedelta(days=30)  # 最近 30 天
            
            start_ts = Timestamp()
            start_ts.FromDatetime(start_time)
            end_ts = Timestamp()
            end_ts.FromDatetime(now)
            
            interval = monitoring_v3.TimeInterval(
                {"start_time": start_ts, "end_time": end_ts}
            )
            
            metric_filter = 'metric.type="compute.googleapis.com/instance/network/sent_bytes_count"'
            
            request = monitoring_v3.ListTimeSeriesRequest(
                name=f"projects/{self.project_id}",
                filter=metric_filter,
                interval=interval,
            )
            
            loop = asyncio.get_event_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, self.metric_client.list_time_series, request),
                timeout=timeout_sec
            )
            series_list = list(results)
            
            total_bytes = 0
            
            if series_list:
                for series in series_list:
                    for point in series.points:
                        bytes_value = point.value.double_value if point.value else 0
                        total_bytes += bytes_value
            
            # 轉換為 GB
            gb_value = total_bytes / (1024 * 1024 * 1024)
            
            # 存入數據庫
            current_month = datetime.now(TAIWAN_TZ).strftime("%Y-%m")
            self.db.add_monthly_egress(current_month, gb_value)
            
            print(f"[GCP Collector] ✅ 月累積流量: {gb_value:.2f} GB")
            return True
            
        except asyncio.TimeoutError:
            print(f"[GCP Collector] ⏱️ 月累積流量查詢超時")
            return False
        except Exception as e:
            print(f"[GCP Collector] 採集月累積流量異常: {e}")
            return False
    
    async def collect_billing_data(self, timeout_sec: float = 15.0, skip_if_recent: bool = True, min_hours_between: int = 6) -> bool:
        """
        從 GCP 採集計費信息並存入數據庫
        
        Args:
            timeout_sec: 超時秒數
            skip_if_recent: 如果最近已採集過，則跳過（節省 API 配額）
            min_hours_between: 兩次採集之間的最少小時數（默認 6 小時）
            
        Returns:
            bool: 是否成功
        """
        if not self.available or not self.billing_client:
            print("[GCP Collector] ⚠️ GCP 或 Billing 客戶端不可用，跳過計費採集")
            return False
        
        try:
            # 檢查最後一次更新時間
            if skip_if_recent:
                current_month = datetime.now(TAIWAN_TZ).strftime("%Y-%m")
                
                # 從本地數據庫讀取上次更新時間
                billing_data = self.db.get_billing_data(months=1)
                if billing_data and current_month in billing_data:
                    print(f"[GCP Collector] 📊 計費數據已有緩存，跳過本次採集（節省 API 配額）")
                    return True  # 本月數據已存在，無需重新採集
            
            print("[GCP Collector] 採集計費信息...")
            
            current_month = datetime.now(TAIWAN_TZ).strftime("%Y-%m")
            
            # 嘗試從 BigQuery 導出表讀取計費數據
            billing_info = {
                "currency": "USD",
                "total_cost": 0.0,
                "current_month": current_month,
                "status": "✓ 正常 (免費額度機制)"
            }
            
            try:
                from google.cloud import bigquery
                
                bq = bigquery.Client()
                
                # 嘗試多個 BigQuery 表名
                tables = [
                    os.environ.get("GCP_BILLING_TABLE"),
                    "kkgroup.KKgroup.gcp_billing_export_resource_v1_018DDB_53FEDB_852041",
                    "kkgroup.KKgroup.gcp_billing_export_v1_018DDB_53FEDB_852041",
                ]
                tables = [t for t in tables if t]  # 過濾出 None 值
                
                for table in tables:
                    try:
                        query = f"""
                        SELECT
                          FORMAT_DATE('%Y-%m', DATE(_PARTITIONTIME)) AS month,
                          SUM(cost) AS total_cost,
                          ANY_VALUE(currency) AS currency
                        FROM `{table}`
                        WHERE DATE(_PARTITIONTIME) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 2 MONTH)
                        GROUP BY month
                        ORDER BY month DESC
                        """
                        
                        loop = asyncio.get_event_loop()
                        job = await loop.run_in_executor(None, lambda: bq.query(query))
                        result_list = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda: list(job.result())),
                            timeout=timeout_sec
                        )
                        
                        print(f"[GCP Collector] 🔍 BigQuery 查詢成功，獲得 {len(result_list)} 個月份數據")
                        
                        for row in result_list:
                            if row.month == current_month and row.total_cost is not None:
                                billing_info["total_cost"] = float(row.total_cost)
                                billing_info["currency"] = row.currency or "USD"
                                print(f"[GCP Collector] 💰 {row.month}: ${row.total_cost:.2f} {row.currency}")
                            
                            # 存入所有月份的數據到數據庫
                            if row.total_cost is not None:
                                self.db.add_billing_data(
                                    row.month,
                                    float(row.total_cost),
                                    row.currency or "USD",
                                    "✓ BigQuery"
                                )
                        
                        print(f"[GCP Collector] ✅ 計費數據採集完成")
                        return True
                        
                    except Exception as bq_err:
                        print(f"[GCP Collector] BigQuery 表 {table} 查詢失敗: {bq_err}")
                        continue
                
                print(f"[GCP Collector] ⚠️ 所有 BigQuery 表都查詢失敗")
                
            except ImportError:
                print("[GCP Collector] ⚠️ BigQuery 庫不可用")
            except asyncio.TimeoutError:
                print(f"[GCP Collector] ⏱️ 計費數據查詢超時 ({timeout_sec}s)")
            
            # 至少保存一個佔位符記錄
            self.db.add_billing_data(
                current_month,
                0.0,
                billing_info["currency"],
                billing_info["status"]
            )
            
            return True
            
        except Exception as e:
            print(f"[GCP Collector] 採集計費數據異常: {e}")
            return False
    
    async def run_collection_cycle(self):
        """
        運行一個完整的採集循環
        包括：出站流量、系統統計、月累積流量、計費信息
        """
        try:
            print(f"\n[GCP Collector] 🔄 開始採集循環 ({datetime.now(TAIWAN_TZ).strftime('%H:%M:%S')})")
            
            # 並行運行採集任務
            await asyncio.gather(
                self.collect_egress_data(hours=6),
                self.collect_system_stats(),
                self.collect_monthly_egress(),
                self.collect_billing_data(),
                return_exceptions=True
            )
            
            print(f"[GCP Collector] ✅ 採集循環完成\n")
            
        except Exception as e:
            print(f"[GCP Collector] ❌ 採集循環異常: {e}\n")
    
    async def start_background_collection(self, interval_minutes: int = 30):
        """
        啟動後台採集任務（每 N 分鐘運行一次）
        
        Args:
            interval_minutes: 採集間隔（分鐘）
        """
        print(f"[GCP Collector] 🚀 啟動後台採集（間隔: {interval_minutes} 分鐘）")
        
        first_run = True
        
        while True:
            try:
                if first_run:
                    # 立即運行第一次
                    await self.run_collection_cycle()
                    first_run = False
                else:
                    # 等待指定時間後再運行
                    await asyncio.sleep(interval_minutes * 60)
                    await self.run_collection_cycle()
                
            except Exception as e:
                print(f"[GCP Collector] ❌ 後台採集異常: {e}")
                await asyncio.sleep(60)  # 出現錯誤時等待 1 分鐘後重試


# 獨立的命令行界面
if __name__ == "__main__":
    async def main():
        collector = MetricsDataCollector()
        
        # 執行一次完整採集
        print("=" * 60)
        print("GCP Metrics 數據採集器 - 手動模式")
        print("=" * 60)
        
        await collector.run_collection_cycle()
        
        # 顯示數據庫統計
        print("\n數據庫統計:")
        print(f"  出站流量數據點: {collector.db.get_data_count('egress_timeseries')}")
        print(f"  系統統計數據點: {collector.db.get_data_count('system_stats')}")
        print(f"  計費記錄: {collector.db.get_data_count('billing_data')}")
        print(f"  月累積記錄: {collector.db.get_data_count('monthly_egress')}")
        
        # 清理舊數據
        collector.db.cleanup_old_data(days=90)
    
    asyncio.run(main())
