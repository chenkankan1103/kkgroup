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
        嘗試多個 metric type，直至找到可用的數據。
        
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
            
            # 嘗試多個 metric type
            metric_types = [
                'compute.googleapis.com/instance/network/sent_bytes_count',  # 主要
                'compute.googleapis.com/instance/network/sent_packets_count', # 替代
            ]
            
            print(f"[GCP METRICS] 查詢網路流量 (hours={hours}, 時間: {start_time} ~ {now})")
            
            for metric_type in metric_types:
                try:
                    metric_filter = f'metric.type="{metric_type}"'
                    print(f"[GCP METRICS] 嘗試 metric type: {metric_type}")
                    
                    request = monitoring_v3.ListTimeSeriesRequest(
                        name=f"projects/{self.project_id}",
                        filter=metric_filter,
                        interval=interval,
                    )
                    
                    results = self.metric_client.list_time_series(request=request)
                    series_list = list(results)
                    
                    print(f"[GCP METRICS] 找到 {len(series_list)} 個 time series")
                    
                    if series_list:
                        data_points = []
                        for series in series_list:
                            print(f"[GCP METRICS] series 包含 {len(series.points)} 個 points")
                            for point in reversed(series.points):  # 從早到晚排序
                                timestamp = point.interval.end_time.timestamp()
                                bytes_value = point.value.double_value if point.value else 0
                                mb_value = bytes_value / (1024 * 1024)
                                
                                data_points.append({
                                    "timestamp": datetime.fromtimestamp(timestamp, tz=TAIWAN_TZ),
                                    "bytes": bytes_value,
                                    "mb": mb_value
                                })
                        
                        if data_points:
                            print(f"[GCP METRICS] 成功獲取 {len(data_points)} 個數據點，總流量: {sum(p['mb'] for p in data_points):.2f} MB")
                            return data_points
                except Exception as e:
                    print(f"[GCP METRICS] metric type {metric_type} 失敗: {e}")
                    continue
            
            print(f"[GCP METRICS] 所有 metric type 都無數據")
            return []
            
        except Exception as e:
            print(f"[GCP METRICS] 獲取網路流量異常: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _get_agent_metric(self, metric_type: str, hours: int = 6) -> List[Dict]:
        """
        公用方法用於抓取 agent.googleapis.com 類型的指標。
        返回結構與 get_network_egress_data 相同。
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
            request = monitoring_v3.ListTimeSeriesRequest(
                name=f"projects/{self.project_id}",
                filter=f'metric.type="{metric_type}"',
                interval=interval,
            )
            results = self.metric_client.list_time_series(request=request)
            series_list = list(results)
            data_points = []
            if series_list:
                series = series_list[0]
                for point in reversed(series.points):
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
            print(f"[GCP METRICS] get_agent_metric {metric_type} failed: {e}")
            return []

    async def get_ops_egress_data(self, hours: int = 6) -> List[Dict]:
        """從 Ops Agent 取得 egress bytes（MB）"""
        return await self._get_agent_metric('agent.googleapis.com/network/egress_bytes_count', hours)

    async def get_ops_ingress_data(self, hours: int = 6) -> List[Dict]:
        """從 Ops Agent 取得 ingress bytes（MB）"""
        return await self._get_agent_metric('agent.googleapis.com/network/ingress_bytes_count', hours)

    async def get_system_metric(self, metric_type: str, hours: int = 1) -> Optional[float]:
        """Query a single-time-interval metric and return its most recent value.

        Returns None if no data could be fetched (e.g. metric not reported).
        """
        try:
            now = datetime.utcnow()
            start_time = now - timedelta(hours=hours)
            start_ts = Timestamp(); start_ts.FromDatetime(start_time)
            end_ts = Timestamp(); end_ts.FromDatetime(now)
            interval = monitoring_v3.TimeInterval({"start_time": start_ts, "end_time": end_ts})
            
            metric_filter = f'metric.type="{metric_type}"'
            print(f"[GCP METRICS] 查詢系統 metric: {metric_type}")
            
            request = monitoring_v3.ListTimeSeriesRequest(
                name=f"projects/{self.project_id}",
                filter=metric_filter,
                interval=interval,
            )
            results = list(self.metric_client.list_time_series(request=request))
            
            print(f"[GCP METRICS] 系統 metric {metric_type} 找到 {len(results)} 個 series")
            
            if results:
                # pick the most recent point across all series
                latest = None
                latest_ts = None
                for idx, series in enumerate(results):
                    if series.points:
                        print(f"[GCP METRICS] series {idx} 包含 {len(series.points)} 個 points")
                        pt = series.points[0]
                        ts = pt.interval.end_time
                        # ts may be a protobuf Timestamp or a datetime object
                        if hasattr(ts, 'seconds'):
                            key = ts.seconds
                        else:
                            # assume datetime-like
                            key = ts.timestamp()
                        if latest is None or key > latest_ts:
                            latest = pt
                            latest_ts = key
                if latest:
                    value = latest.value.double_value
                    print(f"[GCP METRICS] 系統 metric {metric_type} 值: {value}")
                    return value
            else:
                print(f"[GCP METRICS] ⚠️ 系統 metric {metric_type} 無數據")
            return None
        except Exception as e:
            print(f"[GCP METRICS] system metric {metric_type} failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _make_bar(self, ratio: float, length: int = 10) -> str:
        """Create a text bar █ for filled portion and ░ for empty."""
        filled = int(ratio * length)
        return '█' * filled + '░' * (length - filled)
    
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
            
            print(f"[GCP METRICS] 查詢月累積流量 (days={days}, {start_time} ~ {now})")
            
            # 查詢網路出站流量 metric - 使用 delta 以獲得累積值
            metric_filter = 'metric.type="compute.googleapis.com/instance/network/sent_bytes_count"'
            
            request = monitoring_v3.ListTimeSeriesRequest(
                name=f"projects/{self.project_id}",
                filter=metric_filter,
                interval=interval,
            )
            
            results = self.metric_client.list_time_series(request=request)
            series_list = list(results)
            
            print(f"[GCP METRICS] 月累積流量查詢找到 {len(series_list)} 個 series")
            
            total_bytes = 0
            point_count = 0
            
            if series_list:
                for idx, series in enumerate(series_list):
                    print(f"[GCP METRICS] series {idx} 包含 {len(series.points)} 個 points")
                    for point in series.points:
                        bytes_value = point.value.double_value if point.value else 0
                        total_bytes += bytes_value
                        point_count += 1
            
            # 轉換為 GB
            gb_value = total_bytes / (1024 * 1024 * 1024)
            print(f"[GCP METRICS] 月累積成功: {point_count} 個點，總 {gb_value:.4f} GB")
            return gb_value
            
        except Exception as e:
            print(f"[GCP METRICS] 獲取月累積流量失敗: {e}")
            import traceback
            traceback.print_exc()
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

            print(f"[GCP METRICS] 查詢計費信息 (月份: {current_month})")

            # first, make sure the billing API connection works so we know permission is ok
            try:
                accounts = list(self.billing_client.list_billing_accounts())
                print(f"[GCP METRICS] 找到 {len(accounts)} 個計費帳戶")
                if accounts:
                    billing_info["status"] = "✓ 計費查詢已連接"
            except Exception as api_error:
                err = str(api_error)
                print(f"[GCP METRICS] 計費 API 連接失敗: {err}")
                if "403" in err:
                    billing_info["status"] = "⚠️ 需要計費帳戶讀取權限 (IAM 角色)"
                elif "NOT_FOUND" in err:
                    billing_info["status"] = "⚠️ 計費帳戶未綁定"
                else:
                    billing_info["status"] = f"⚠️ 計費 API 連接失敗: {err[:50]}"
                return billing_info

            # optional: read actual costs from a BigQuery export table.  
            # try the resource-level export first (more detailed), then the
            # normal v1 export.  the environment variable can specify the
            # preferred table but we also attempt fallbacks.
            tables = []
            env_table = os.environ.get("GCP_BILLING_TABLE")
            if env_table:
                print(f"[GCP METRICS] 使用環境變數 table: {env_table}")
                tables.append(env_table)
            # common names users might see
            tables.extend([
                "kkgroup.KKgroup.gcp_billing_export_resource_v1_018DDB_53FEDB_852041",
                "kkgroup.KKgroup.gcp_billing_export_v1_018DDB_53FEDB_852041",
            ])

            found = False
            for table in tables:
                try:
                    print(f"[GCP METRICS] 嘗試 BigQuery table: {table}")
                    from google.cloud import bigquery
                    bq = bigquery.Client()
                    query = f"""
                    SELECT
                      SUM(cost) AS total_cost,
                      ANY_VALUE(currency) AS currency
                    FROM `{table}`
                    WHERE DATE(_PARTITIONTIME) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
                    """
                    job = bq.query(query)
                    result_list = list(job.result())
                    print(f"[GCP METRICS] BigQuery query 返回 {len(result_list)} 行")
                    
                    for row in result_list:
                        print(f"[GCP METRICS] row: total_cost={row.total_cost}, currency={row.currency}")
                        if row.total_cost is not None:
                            billing_info["total_cost"] = f"{row.total_cost:.2f}"
                        if row.currency:
                            billing_info["currency"] = row.currency
                    
                    billing_info["status"] += f" (BigQuery: {table.split('.')[-1][:30]})"
                    found = True
                    print(f"[GCP METRICS] BigQuery 查詢成功，成本: {billing_info['total_cost']} {billing_info['currency']}")
                    break
                except Exception as bq_err:
                    # try next table
                    print(f"[GCP METRICS] BigQuery table {table} 查詢失敗: {bq_err}")
            
            if not found:
                print(f"[GCP METRICS] 所有 BigQuery table 都查詢失敗")
                billing_info["status"] += " (無可用 BigQuery 導出)"

            return billing_info
        except Exception as e:
            print(f"[GCP METRICS] 計費資料錯誤: {e}")
            import traceback
            traceback.print_exc()
            return {
                "currency": "USD",
                "total_cost": "N/A",
                "current_month": datetime.now(TAIWAN_TZ).strftime("%Y-%m"),
                "status": f"⚠️ 計費查詢異常"
            }
    
    def generate_metrics_chart(self, data_points: List[Dict], ops_data: List[Dict] = None, ingress_data: List[Dict] = None, monthly_cost: Optional[float] = None) -> Optional[discord.File]:
        """
        生成 metrics 圖表（網路流量趨勢）。
        可傳入 ops_data 來顯示代理收集的出站 bytes，以及 ingress_data 顯示進站 bytes。
        同時可以傳入 monthly_cost 以在折線圖上疊加成本長條（右側 y 軸）。
        
        此函數不再是協程，內部全部同步運行，允許外部使用
        ``asyncio.to_thread`` 來將其移出事件循環。
        
        Args:
            data_points: 時間序列數據
            ops_data: 可選，由 agent.googleapis.com/network/egress_bytes_count 收集
            ingress_data: 可選，由 agent.googleapis.com/network/ingress_bytes_count 收集
            monthly_cost: optional monthly cost (USD) to plot as a bar
            
        Returns:
            discord.File: 圖表文件或 None
        """
        try:
            if not data_points or len(data_points) < 2:
                print("[GCP METRICS] 數據點不足，無法生成圖表")
                return None
            
            fig, ax = plt.subplots(figsize=(12, 5))
            # if monthly cost provided, create secondary axis for bars
            has_cost = monthly_cost is not None
            if has_cost:
                ax2 = ax.twinx()
                ax2.set_ylabel('成本 (USD)', color='#ffcc00')
                ax2.tick_params(axis='y', colors='#ffcc00')
            
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

            # if monthly cost provided, draw cost bar on secondary axis
            if has_cost:
                # width chosen as 10% of timespan to make visible
                span_seconds = (timestamps[-1] - timestamps[0]).total_seconds()
                bar_width = span_seconds * 0.1
                ax2.bar([timestamps[-1]], [monthly_cost], width=bar_width, alpha=0.4, color='#ffcc00', label='月成本 (USD)')
                ax2.legend(loc='upper right')

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
    
    def create_metrics_embed(self, data_points: List[Dict], billing_info: Dict, monthly_gb: float = 0.0, ops_egress: List[Dict] = None, ops_ingress: List[Dict] = None, sys_stats: Dict = None) -> discord.Embed:
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
        # Ops agent summaries
        if ops_egress:
            tot = sum(p.get("mb",0) for p in ops_egress)
            embed.add_field(
                name="📤 Agent Egress (6h)",
                value=f"{tot:.2f} MB",
                inline=True
            )
        if ops_ingress:
            tot2 = sum(p.get("mb",0) for p in ops_ingress)
            embed.add_field(
                name="📥 Agent Ingress (6h)",
                value=f"{tot2:.2f} MB",
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
        
        # 系統資源條狀顯示
        if sys_stats:
            # show values or N/A if None
            cpu_val = sys_stats.get('cpu')
            mem_val = sys_stats.get('mem')
            disk_val = sys_stats.get('disk')
            if cpu_val is not None:
                cpu_bar = self._make_bar(cpu_val)
                cpu_text = f"CPU {cpu_bar} {cpu_val*100:.0f}%"
            else:
                cpu_text = "CPU N/A"
            if mem_val is not None:
                mem_bar = self._make_bar(mem_val)
                mem_text = f"MEM {mem_bar} {mem_val*100:.0f}%"
            else:
                mem_text = "MEM N/A"
            if disk_val is not None:
                disk_bar = self._make_bar(disk_val)
                disk_text = f"DSK {disk_bar} {disk_val*100:.0f}%"
            else:
                disk_text = "DSK N/A"
            sys_text = f"{cpu_text}\n{mem_text}\n{disk_text}"
            embed.add_field(
                name="💻 系統資源",
                value=f"```\n{sys_text}\n```",
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
    # note: generate_metrics_chart is synchronous, so no await
    chart_file = monitor.generate_metrics_chart(egress_data)
