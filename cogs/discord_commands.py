# -*- coding: utf-8 -*-
"""
Discord 指令中央管理系統
==========================================
所有 Discord 指令集中定義和管理，便於維護升級

當前活躍指令：
- 開發中的新指令
- 已過時指令標記為 deprecated

如何添加新指令：
1. 在此文件中定義
2. 通過 CommandManager 註冊
3. 更新 config/discord_commands_registry.json

如何移除指令：
1. 從原 cogs 文件中刪除
2. 標記為 deprecated 記錄
3. 更新註冊表
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)


class CommandRegistry:
    """Discord 指令註冊表
    
    集中管理所有活躍和已過時的指令
    """
    
    def __init__(self):
        self.active = {}        # 活躍指令
        self.deprecated = {}    # 已過時指令
        self.by_category = {}   # 按分類組織
    
    def register_active(self, name: str, category: str, handler, 
                       description: str = "", permissions: str = "user"):
        """註冊活躍指令"""
        self.active[name] = {
            'category': category,
            'handler': handler,
            'description': description,
            'permissions': permissions,
            'status': 'active'
        }
        
        if category not in self.by_category:
            self.by_category[category] = []
        self.by_category[category].append(name)
    
    def mark_deprecated(self, name: str, reason: str = "", 
                       replacement: str = None):
        """標記指令為已過時"""
        if name in self.active:
            del self.active[name]
        
        self.deprecated[name] = {
            'reason': reason,
            'replacement': replacement,
            'status': 'deprecated'
        }
        logger.info(f"指令 {name} 已標記為過時。原因: {reason}")
    
    def get_stats(self):
        """獲取指令統計"""
        return {
            'total_active': len(self.active),
            'total_deprecated': len(self.deprecated),
            'by_category': {cat: len(cmds) 
                           for cat, cmds in self.by_category.items()}
        }


class CommandManager(commands.Cog):
    """Discord 指令管理器
    
    負責：
    - 指令生命週期管理
    - 指令權限驗證
    - 指令錯誤處理
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.registry = CommandRegistry()
        self._register_commands()
    
    def _register_commands(self):
        """註冊所有活躍的指令"""
        # UI 模組命令
        self.registry.register_active(
            'admin_refresh_all_paperdolls',
            category='UI / 紙娃娃',
            handler=None,  # 指令由 admin_ui_commands.py 定義
            description='[UIBot 管理員] 刷新所有置物櫃的紙娃娃圖片 - 驗證 URL 生成狀態',
            permissions='administrator'
        )
    
    @app_commands.command(
        name="commands_list",
        description="列出所有活躍的 Discord 指令"
    )
    async def list_commands(self, interaction: discord.Interaction):
        """列出所有活躍指令"""
        stats = self.registry.get_stats()
        
        embed = discord.Embed(
            title="📋 Discord 指令列表",
            description=f"總計: {stats['total_active']} 個活躍指令",
            color=discord.Color.blue()
        )
        
        # 按分類顯示
        for category, commands_list in self.registry.by_category.items():
            embed.add_field(
                name=f"📁 {category} ({len(commands_list)})",
                value=", ".join(commands_list),
                inline=False
            )
        
        embed.set_footer(text="使用 /help 查看具體指令用法")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================
# 已移除的指令清單（保留歷史記錄）
# ============================================

REMOVED_COMMANDS = {
    # COMMON 模組 - 已由 embed+按鈕替代
    'kkcoin': '查詢 KK 幣餘額',
    'kkcoin_rank': 'KK 幣排行榜',
    'reserve_status': '查詢園區儲備金狀態',
    'sync_status': '查看同步狀態',
    'trends_jackpot': '查看當前獎池',
    'sync_from_sheet': '從 Google Sheet 同步資料',
    'export_to_sheet': '將資料匯出到 Google Sheet',
    'list_members': '列出伺服器成員',
    'ai_personality_set': '設定 AI 角色特性',
    'ai_personality_list': '查看 AI 角色設定',
    'ai_knowledge_add': '添加知識到 AI 知識庫',
    'ai_knowledge_search': '搜索 AI 知識庫',
    'ai_memory_cleanup': '清理過期 AI 記憶',
    'ai_memory_status': '查看 AI 記憶系統狀態',
    'shellagent': '啟動 AI Shell Agent',
    'update_and_restart': '檢查更新並重啟服務',
    'check_updates': '檢查 Git 更新',
    'restart_all': '重啟所有 bot 服務',
    'restart': '重啟指定 bot 服務',
    'status': '查看服務狀態',
    'trends_history': '查看投注歷史',
    
    # SHOP 模組
    'paperdoll': '開啟紙娃娃試衣間',
    'feedback': '提交玩家意見回饋',
    'grant_temporary_role': '給予用戶臨時身分',
    'check_my_roles': '查看臨時身分有效期',
    
    # UI 模組
    'anime_status': '查看動畫推送狀態',
    'ad_violations': '檢查廣告違規歷史',
    'ad_settings': '檢查防廣告系統設置',
    'anime_start': '手動啟動推送任務',
    'unmute': '解除禁言',
    'clear_violations': '清除違規記錄',
    'cross_channel_status': '檢查跨頻道洗版',
    'emergency_cleanup': '緊急清除訊息',
    'event_stats': '查看園區事件統計',
    'event_reset': '重置事件冷卻',
    'event_force': '強制觸發事件',
    'check_user_ids': '檢驗 user_id',
    'list_id_issues': '列出 ID 偏差用戶',
    'test_locker_equipment': '測試裝備變更',
    'test_locker_currency': '測試 KK幣變更',
    'test_locker_health': '測試血量變更',
    'test_locker_full_refresh': '測試完整刷新',
    'set_character': '設置紙娃娃外觀',
    'view_character': '查看紙娃娃外觀',
    'random_character': '隨機生成紙娃娃',
}


async def setup(bot):
    """載入此 Cog"""
    await bot.add_cog(CommandManager(bot))
