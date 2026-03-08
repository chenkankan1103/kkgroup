"""
GCP Metrics 監控模組
監控：
  • 網路出站流量（Cloud Monitoring）
  • 成本/計費（Cloud Billing）
  • 生成圖表並上傳到 Discord
"""

import asyncio
import json
import matplotlib
matplotlib.use('Agg')  # 非圖形界面後端
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional
from google.cloud import monitoring_v3, billing_v1
from google.protobuf.timestamp_pb2 import Timestamp
import io
import discord
import os
from dotenv import load_dotenv

load_dotenv()

# 台灣時區（UTC+8）
TAIWAN_TZ = timezone(timedelta(hours=8))

# 設置 matplotlib 支持中文（使用系統可用的字體）
import platform
if platform.system() == 'Linux':
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans']  # Linux 上使用 DejaVu Sans
else:
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']

class GCPMetricsMonitor:
    """GCP 指標監控器"""
    
    def __init__(self, project_id: str = "kkgroup"):
        self.project_id = project_id
        self.metric_client = monitoring_v3.MetricServiceClient()
        self.billing_client = billing_v1.CloudBillingClient()
        
    async def get_network_egress_data(self, hours: int = 6) -> List[Dict]:
        """
        獲取 GCP 網路出站流量數據（最近 N 小時）
        
        Returns:
            List[Dict]: 包含時間戳和 MB 流量的列表
        """
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
            
            # 查詢網路出站流量 metric
            metric_filter = 'metric.type="compute.googleapis.com/instance/network/sent_bytes_count"'
            
            request = monitoring_v3.ListTimeSeriesRequest(
                name=f"projects/{self.project_id}",
                filter=metric_filter,
                interval=interval,
            )
            
            results = self.metric_client.list_time_series(request=request)
            series_list = list(results)
            
            data_points = []
            
            if series_list:
                series = series_list[0]
                for point in reversed(series.points):  # 從早到晚排序
                    timestamp = point.interval.end_time.timestamp()
                    # 轉換為 MB（字節 / 1024 / 1024）
                    bytes_value = point.value.double_value if point.value else 0
                    mb_value = bytes_value / (1024 * 1024)
                    
                    data_points.append({
                        "timestamp": datetime.fromtimestamp(timestamp, tz=TAIWAN_TZ),
                        "bytes": bytes_value,
                        "mb": mb_value
                    })
            
            return data_points
            
        except Exception as e:
            print(f"[GCP METRICS] 獲取網路流量失敗: {e}")
            return []
    
    async def get_monthly_egress_data(self, days: int = 30) -> float:
        """
        獲取月累積出站流量（單位: GB）
        
        Args:
            days: 查詢天數（默認 30 天）
            
        Returns:
            float: 月累積出站流量（GB）
        """
        try:
            now = datetime.utcnow()
            start_time = now - timedelta(days=days)
            
            start_ts = Timestamp()
            start_ts.FromDatetime(start_time)
            end_ts = Timestamp()
            end_ts.FromDatetime(now)
            
            interval = monitoring_v3.TimeInterval(
                {"start_time": start_ts, "end_time": end_ts}
            )
            
            # 查詢網路出站流量 metric - 使用 delta 以獲得累積值
            metric_filter = 'metric.type="compute.googleapis.com/instance/network/sent_bytes_count"'
            
            request = monitoring_v3.ListTimeSeriesRequest(
                name=f"projects/{self.project_id}",
                filter=metric_filter,
                interval=interval,
            )
            
            results = self.metric_client.list_time_series(request=request)
            series_list = list(results)
            
            total_bytes = 0
            
            if series_list:
                for series in series_list:
                    for point in series.points:
                        bytes_value = point.value.double_value if point.value else 0
                        total_bytes += bytes_value
            
            # 轉換為 GB
            gb_value = total_bytes / (1024 * 1024 * 1024)
            return gb_value
            
        except Exception as e:
            print(f"[GCP METRICS] 獲取月累積流量失敗: {e}")
            return 0.0
    
    async def get_billing_data(self) -> Dict:
        """
        獲取當月計費信息
        
        Returns:
            Dict: 包含成本、配額等信息
        """
        try:
            # 獲取計費帳戶
            billing_accounts = self.billing_client.list_billing_accounts()
            
            billing_info = {
                "currency": "USD",
                "total_cost": "N/A",
                "current_month": datetime.now(TAIWAN_TZ).strftime("%Y-%m"),
                "status": "查詢中"
            }
            
            # 注意：Cloud Billing API 的成本查詢需要額外的權限和配置
            # 這裡只返回基本信息
            
            return billing_info
            
        except Exception as e:
            print(f"[GCP METRICS] 獲取計費信息失敗: {e}")
            return {
                "currency": "USD",
                "total_cost": "Error",
                "current_month": datetime.now(TAIWAN_TZ).strftime("%Y-%m"),
                "status": f"失敗: {str(e)[:30]}"
            }
    
    async def generate_metrics_chart(self, data_points: List[Dict]) -> Optional[discord.File]:
        """
        生成 metrics 圖表（網路流量趨勢）
        
        Args:
            data_points: 時間序列數據
            
        Returns:
            discord.File: 圖表文件或 None
        """
        try:
            if not data_points or len(data_points) < 2:
                print("[GCP METRICS] 數據點不足，無法生成圖表")
                return None
            
            fig, ax = plt.subplots(figsize=(12, 5))
            
            # 提取時間和數值
            timestamps = [point["timestamp"] for point in data_points]
            mb_values = [point["mb"] for point in data_points]
            
            # Plot line chart
            ax.plot(timestamps, mb_values, marker='o', linewidth=2, markersize=4, color='#3498db')
            ax.fill_between(timestamps, mb_values, alpha=0.3, color='#3498db')
            
            # Set format
            ax.set_xlabel('Time (Taiwan)', fontsize=10)
            ax.set_ylabel('Egress Traffic (MB)', fontsize=10)
            ax.set_title('GCP VM Network Egress (Last 6 Hours)', fontsize=12, fontweight='bold')
            
            # Format X-axis time - use Taiwan timezone
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=TAIWAN_TZ))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=TAIWAN_TZ))
            plt.xticks(rotation=45, ha='right')
            
            # Add grid
            ax.grid(True, alpha=0.3)
            
            # Calculate statistics
            total_egress = sum(mb_values)
            max_egress = max(mb_values)
            avg_egress = sum(mb_values) / len(mb_values)
            
            # Display stats on chart
            stats_text = f"Total: {total_egress:.2f} MB | Max: {max_egress:.2f} MB | Avg: {avg_egress:.2f} MB"
            ax.text(0.5, 1.05, stats_text, transform=ax.transAxes, 
                   ha='center', fontsize=9, style='italic')
            
            # Compact layout
            plt.tight_layout()
            
            # Save as binary file
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            plt.close(fig)
            
            # Convert to Discord File
            return discord.File(buffer, filename='gcp_metrics.png')
            
        except Exception as e:
            print(f"[GCP METRICS] 生成圖表失敗: {e}")
            plt.close('all')
            return None
    
    def create_metrics_embed(self, data_points: List[Dict], billing_info: Dict, monthly_gb: float = 0.0) -> discord.Embed:
        """
        創建 metrics embed
        """
        # 使用台灣時間作為 embed 的時間戳
        taiwan_now = datetime.now(TAIWAN_TZ)
        
        embed = discord.Embed(
            title="📊 GCP 資源監控",
            description="網路流量和計費信息監控",
            color=discord.Color.from_rgb(66, 133, 244),
        )
        
        # 網路出站流量 - 過去 6 小時
        if data_points:
            total_mb = sum(p["mb"] for p in data_points)
            max_mb = max(p["mb"] for p in data_points)
            avg_mb = sum(p["mb"] for p in data_points) / len(data_points)
            
            embed.add_field(
                name="🌐 網路出站流量 (過去 6 小時)",
                value=f"**總計**: {total_mb:.2f} MB\n**最大**: {max_mb:.2f} MB\n**平均**: {avg_mb:.2f} MB",
                inline=True
            )
        else:
            embed.add_field(
                name="🌐 網路出站流量 (過去 6 小時)",
                value="暫無數據",
                inline=True
            )
        
        # 添加月累積流量
        embed.add_field(
            name="📊 月累積出站流量",
            value=f"**本月**: {monthly_gb:.2f} GB / 200 GB (免費額度)",
            inline=True
        )
        
        # 計費信息
        embed.add_field(
            name="💰 計費信息",
            value=f"**月份**: {billing_info.get('current_month', 'N/A')}\n**成本**: {billing_info.get('total_cost', 'N/A')} {billing_info.get('currency', 'USD')}\n**狀態**: {billing_info.get('status', '✓ 正常')}",
            inline=True
        )
        
        # 免費額度提示
        embed.add_field(
            name="🎁 GCP 免費額度",
            value="📤 **出站流量**: 200 GB/月\n🔄 **API 請求**: 根據服務而定",
            inline=False
        )
        
        # 圖表提示
        embed.add_field(
            name="📈 圖表",
            value="查看下方的流量趨勢圖（台灣時間）",
            inline=False
        )
        
        # 使用台灣時間顯示最後更新時間
        embed.set_footer(text=f"每 20 分鐘自動更新 | 台灣時間 • {taiwan_now.strftime('%Y-%m-%d %H:%M:%S')}")
        embed.set_image(url="attachment://gcp_metrics.png")
        
        return embed


async def test_metrics_monitor():
    """測試 metrics 監控"""
    monitor = GCPMetricsMonitor()
    
    print("[TEST] 開始獲取網路流量數據...")
    egress_data = await monitor.get_network_egress_data(hours=6)
    print(f"[TEST] 获得 {len(egress_data)} 個數據點")
    
    if egress_data:
        total_mb = sum(p["mb"] for p in egress_data)
        print(f"[TEST] 總出站流量: {total_mb:.2f} MB")
    
    print("[TEST] 開始獲取計費信息...")
    billing_info = await monitor.get_billing_data()
    print(f"[TEST] 計費信息: {billing_info}")
    
    print("[TEST] 生成圖表...")
    chart_file = await monitor.generate_metrics_chart(egress_data)
    if chart_file:
        print(f"[TEST] 圖表生成成功")
    else:
        print(f"[TEST] 圖表生成失敗")
    
    embed = monitor.create_metrics_embed(egress_data, billing_info)
    print(f"[TEST] Embed 創建成功")


if __name__ == "__main__":
    asyncio.run(test_metrics_monitor())
