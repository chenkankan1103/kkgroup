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
    # Linux 上優先使用開源中文字體，再降級到 DejaVu Sans
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
else:
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Zen Hei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

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
            Dict: 包含成本、配額等信息（若設置 BIGQUERY 導出，會嘗試查詢）
        """
        try:
            current_month = datetime.now(TAIWAN_TZ).strftime("%Y-%m")
            
            billing_info = {
                "currency": "USD",
                "total_cost": "0.00",
                "current_month": current_month,
                "status": "✓ 正常 (免費額度機制)"
            }

            # first, make sure the billing API connection works so we know permission is ok
            try:
                accounts = list(self.billing_client.list_billing_accounts())
                if accounts:
                    billing_info["status"] = "✓ 計費查詢已連接"
            except Exception as api_error:
                err = str(api_error)
                if "403" in err:
                    billing_info["status"] = "⚠️ 需要計費帳戶讀取權限 (IAM 角色)"
                elif "NOT_FOUND" in err:
                    billing_info["status"] = "⚠️ 計費帳戶未綁定"
                else:
                    billing_info["status"] = "⚠️ 計費 API 連接失敗"
                return billing_info

            # optional: read actual costs from a BigQuery export table
            billing_table = os.environ.get("GCP_BILLING_TABLE")
            if billing_table:
                try:
                    from google.cloud import bigquery
                    bq = bigquery.Client()
                    query = f"""
                    SELECT
                      SUM(cost) AS total_cost,
                      ANY_VALUE(currency) AS currency
                    FROM `{billing_table}`
                    WHERE DATE(_PARTITIONTIME) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
                    """
                    job = bq.query(query)
                    for row in job.result():
                        if row.total_cost is not None:
                            billing_info["total_cost"] = f"{row.total_cost:.2f}"
                        if row.currency:
                            billing_info["currency"] = row.currency
                except Exception as bq_err:
                    print(f"[GCP METRICS] BigQuery 計費查詢失敗: {bq_err}")
            else:
                # no export configured, leave cost at default zero
                billing_info["status"] += " (無 BigQuery 導出)"

            return billing_info
        except Exception as e:
            print(f"[GCP METRICS] 計費資料錯誤: {e}")
            return {
                "currency": "USD",
                "total_cost": "N/A",
                "current_month": datetime.now(TAIWAN_TZ).strftime("%Y-%m"),
                "status": f"⚠️ 計費查詢異常"
            }
    
    async def generate_metrics_chart(self, data_points: List[Dict], ops_data: List[Dict] = None, ingress_data: List[Dict] = None) -> Optional[discord.File]:
        """
        生成 metrics 圖表（網路流量趨勢）。
        可傳入 ops_data 來顯示代理收集的出站 bytes，以及 ingress_data 顯示進站 bytes。
        
        Args:
            data_points: 時間序列數據
            ops_data: 可選，由 agent.googleapis.com/network/egress_bytes_count 收集
            ingress_data: 可選，由 agent.googleapis.com/network/ingress_bytes_count 收集
            
        Returns:
            discord.File: 圖表文件或 None
        """
        try:
            if not data_points or len(data_points) < 2:
                print("[GCP METRICS] 數據點不足，無法生成圖表")
                return None
            
            fig, ax = plt.subplots(figsize=(12, 5))
            
            # Extract times and values
            timestamps = [point["timestamp"] for point in data_points]
            mb_values = [point["mb"] for point in data_points]
            
            # Set deep blue background with neon color
            fig.patch.set_facecolor('#1a2f4d')  # Deep blue background
            ax.set_facecolor('#0f1922')  # Darker blue for plot area
            
            # determine unit (KB or MB) depending on magnitude of bytes
            use_mb = True
            if mb_values:
                max_mb = max(mb_values)
                if max_mb < 0.1:
                    use_mb = False
            if use_mb:
                unit = 'MB'
                scale = 1.0
            else:
                unit = 'KB'
                scale = 1024.0
            
            # convert values to chosen unit
            vals_scaled = [v * scale for v in mb_values]
            neon_color = '#00d4ff'
            ax.plot(timestamps, vals_scaled, marker='o', linewidth=2.5, markersize=5, color=neon_color, label='monitor egress ('+unit+')')
            ax.fill_between(timestamps, vals_scaled, alpha=0.2, color=neon_color)

            # if agent egress data provided, plot as red line using same scale
            if ops_data:
                ops_vals = []
                for d in ops_data:
                    bytes_val = d.get('bytes', 0)
                    mb_val = bytes_val / (1024*1024)
                    ops_vals.append(mb_val * scale)
                ax.plot(timestamps, ops_vals, linestyle='-', linewidth=1.5, color='#ff4d4d', label='agent egress ('+unit+')')

            # if ingress data provided, plot as neon green line
            if ingress_data:
                ingress_vals = []
                for d in ingress_data:
                    bytes_val = d.get('bytes', 0)
                    mb_val = bytes_val / (1024*1024)
                    ingress_vals.append(mb_val * scale)
                ax.plot(timestamps, ingress_vals, linestyle='--', linewidth=1.5, color='#39ff14', label='agent ingress ('+unit+')')

            # show legend if any additional lines
            ax.legend(loc='upper left')
            
            # adjust y-label according to unit
            ax.set_ylabel(f'流量 ({unit})', fontsize=10, color='#e0e0e0')
            
            # Set Y-axis from 0, auto-scale based on data
            if mb_values and max(mb_values) > 0:
                max_val = max(mb_values)
                # Calculate reasonable Y-axis ceiling
                if max_val < 1:
                    y_limit = 1
                elif max_val < 10:
                    y_limit = 10
                elif max_val < 100:
                    y_limit = max_val * 1.3  # 30% padding
                else:
                    y_limit = max_val * 1.15  # 15% padding
                ax.set_ylim(bottom=0, top=y_limit)
            else:
                ax.set_ylim(bottom=0, top=1)
            
            # Set labels with light text color for dark background
            ax.set_xlabel('台灣時間', fontsize=10, color='#e0e0e0')
            ax.set_title('GCP VM 網路出站流量 (過去 6 小時)', fontsize=12, fontweight='bold', color=neon_color, pad=15)
            
            # Format X-axis time - use Taiwan timezone
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=TAIWAN_TZ))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=TAIWAN_TZ))
            plt.xticks(rotation=45, ha='right', color='#e0e0e0')
            plt.yticks(color='#e0e0e0')
            
            # Customize grid for dark background
            ax.grid(True, alpha=0.2, color='#555555', linestyle='--')
            ax.spines['bottom'].set_color('#666666')
            ax.spines['left'].set_color('#666666')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            
            # Calculate statistics
            total_egress = sum(mb_values)
            max_egress = max(mb_values) if mb_values else 0
            avg_egress = sum(mb_values) / len(mb_values) if mb_values else 0
            
            # Display stats with Chinese text and neon color
            stats_text = f"總計: {total_egress:.2f} MB | 最大: {max_egress:.2f} MB | 平均: {avg_egress:.2f} MB"
            ax.text(0.5, 1.05, stats_text, transform=ax.transAxes, 
                   ha='center', fontsize=9, style='italic', color=neon_color)
            
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
            value="查看下方的流量趨勢圖（台灣時間）；紅線為請求數量",
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
