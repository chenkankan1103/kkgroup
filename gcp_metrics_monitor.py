"""
GCP Metrics 監控模組 - 已停用

此模組已簡化為最小存根，不再進行以下操作：
  • 監控網路出站流量
  • 監控成本/計費
  • 生成圖表

bot 將繼續運行，但不再收集或顯示 metrics 數據。
"""

import discord
from typing import Dict, List, Optional


class GCPMetricsMonitor:
    """GCP 指標監控器 - 已停用"""
    
    def __init__(self, project_id: str = "kkgroup"):
        """初始化 Metrics Monitor（已停用）"""
        self.project_id = project_id
        self.available = False
        self.db = None
        print(f"[GCP] ⚠️ GCP Metrics Monitor 已停用（不再監控出站流量和計費）")
    
    def create_metrics_embed(self, data_points: List = None, billing_info: Dict = None, 
                            monthly_gb: float = 0, cpu_seconds: Optional[int] = None) -> discord.Embed:
        """
        建立 metrics embed - 已停用
        
        Args:
            data_points: 網路流量數據點（已忽略）
            billing_info: 計費資訊（已忽略）
            monthly_gb: 月度出站流量 GB（已忽略）
            cpu_seconds: CPU 秒數（已忽略）
            
        Returns:
            空的 Discord Embed
        """
        embed = discord.Embed(
            title="Metrics 監控已停用",
            description="網路監控和計費監控已被停用。",
            color=discord.Color.greyple()
        )
        embed.add_field(name="狀態", value="❌ 已停用", inline=False)
        return embed
    
    def get_latest_chart(self) -> Optional[discord.File]:
        """取得最新圖表 - 已停用"""
        return None
    
    def get_billing_info_from_database(self) -> Dict:
        """從數據庫取得計費資訊 - 已停用"""
        return {}
    
    def get_monthly_egress_from_database(self) -> float:
        """從數據庫取得月度出站流量 - 已停用"""
        return 0.0
