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
        """註冊所有活躍的指令（共 45 個）"""
        
        # ========================================
        # UI 模組指令 (24 個)
        # ========================================
        
        # 置物櫃管理 (7 個)
        locker_commands = [
            ('admin_refresh_all_lockers', '批量刷新所有用戶置物櫃', 'administrator'),
            ('locker_check', '查看自己的置物櫃', 'user'),
            ('locker_init', '初始化新用戶置物櫃', 'user'),
            ('locker_check_all', '管理員查看所有置物櫃', 'administrator'),
            ('locker_fix_missing', '修復缺失的置物櫃數據', 'administrator'),
            ('locker_remake_thread', '重建置物櫃論壇線程', 'administrator'),
            ('update_forum_lockers', '更新論壇置物櫃顯示', 'administrator'),
        ]
        for cmd_name, desc, perm in locker_commands:
            self.registry.register_active(cmd_name, 'UI / 置物櫃', None, desc, perm)
        
        # 紙娃娃系統 (1 個)
        self.registry.register_active(
            'admin_refresh_all_paperdolls',
            'UI / 紙娃娃',
            None,
            '刷新所有置物櫃的紙娃娃圖片',
            'administrator'
        )
        
        # 動畫追蹤 (4 個)
        anime_commands = [
            ('anime_test', '測試動畫推送系統', 'administrator'),
            ('anime_weekly', '查看本週動畫推送', 'user'),
            ('anime_ranking', '查看動畫排行榜', 'user'),
            ('anime_stats', '查看動畫統計數據', 'user'),
        ]
        for cmd_name, desc, perm in anime_commands:
            self.registry.register_active(cmd_name, 'UI / 動畫追蹤', None, desc, perm)
        
        # 新年紅包系統 (4 個)
        redenvelope_commands = [
            ('發紅包', '發送新年紅包', 'user'),
            ('紅包修復', '修復紅包分配問題', 'administrator'),
            ('紅包狀態', '查看紅包發放狀態', 'user'),
            ('紅包掃描', '掃描未領取紅包', 'administrator'),
        ]
        for cmd_name, desc, perm in redenvelope_commands:
            self.registry.register_active(cmd_name, 'UI / 紅包系統', None, desc, perm)
        
        # 歡迎系統 (4 個)
        welcome_commands = [
            ('debug_welcome', '調試歡迎消息', 'administrator'),
            ('debug_confirm', '調試確認按鈕', 'administrator'),
            ('debug_press_buttons', '調試按鈕按下', 'administrator'),
            ('debug_simulate_buttons', '模擬按鈕交互', 'administrator'),
        ]
        for cmd_name, desc, perm in welcome_commands:
            self.registry.register_active(cmd_name, 'UI / 歡迎系統', None, desc, perm)
        
        # ID 診斷 (2 個)
        id_commands = [
            ('check_user_ids', '檢查用戶 ID 映射', 'administrator'),
            ('list_id_issues', '列出 ID 不匹配的用戶', 'administrator'),
        ]
        for cmd_name, desc, perm in id_commands:
            self.registry.register_active(cmd_name, 'UI / ID 診斷', None, desc, perm)
        
        # 角色設置 (3 個)
        character_commands = [
            ('set_character', '設置紙娃娃外觀', 'user'),
            ('view_character', '查看紙娃娃外觀', 'user'),
            ('random_character', '隨機生成紙娃娃', 'user'),
        ]
        for cmd_name, desc, perm in character_commands:
            self.registry.register_active(cmd_name, 'UI / 角色設置', None, desc, perm)
        
        # 置物櫃事件測試 (4 個)
        locker_test_commands = [
            ('test_locker_equipment', '測試裝備變更', 'administrator'),
            ('test_locker_currency', '測試 KK幣變更', 'administrator'),
            ('test_locker_health', '測試血量變更', 'administrator'),
            ('test_locker_full_refresh', '測試完整刷新', 'administrator'),
        ]
        for cmd_name, desc, perm in locker_test_commands:
            self.registry.register_active(cmd_name, 'UI / 置物櫃測試', None, desc, perm)
        
        # ========================================
        # Common 模組指令 (16 個)
        # ========================================
        
        # KK 幣系統 (2 個)
        kkcoin_commands = [
            ('kkcoin_admin', 'KK幣管理工具', 'administrator'),
            ('reserve_admin', '園區儲備金管理', 'administrator'),
        ]
        for cmd_name, desc, perm in kkcoin_commands:
            self.registry.register_active(cmd_name, 'Common / 經濟系統', None, desc, perm)
        
        # 趨勢樂透 (2 個)
        trends_commands = [
            ('trends_predict', '預測趨勢走向', 'user'),
            ('trends_test', '測試樂透系統', 'administrator'),
        ]
        for cmd_name, desc, perm in trends_commands:
            self.registry.register_active(cmd_name, 'Common / 趨勢樂透', None, desc, perm)
        
        # 暱稱管理 (5 個)
        nickname_commands = [
            ('assign_nickname_id', '分配用戶 ID 暱稱', 'manage_nicknames'),
            ('remove_nickname_id', '移除暱稱映射', 'manage_nicknames'),
            ('test_assign_nickname_id', '測試暱稱分配', 'administrator'),
            ('test_remove_nickname_id', '測試暱稱移除', 'administrator'),
            ('restore_global_nicknames', '恢復全域暱稱', 'administrator'),
        ]
        for cmd_name, desc, perm in nickname_commands:
            self.registry.register_active(cmd_name, 'Common / 暱稱管理', None, desc, perm)
        
        # AI 工具 (1 個)
        self.registry.register_active(
            'shellagent',
            'Common / AI 工具',
            None,
            '啟動 AI Shell Agent',
            'administrator'
        )
        
        # 語音頻道 (1 個)
        self.registry.register_active(
            'setup_scam_hub',
            'Common / 語音管理',
            None,
            '設置詐騙中樞語音頻道',
            'manage_guild'
        )
        
        # 系統工具 (4 個)
        system_commands = [
            ('commands_list', '列出所有活躍指令', 'user'),
            ('update_and_restart', '檢查更新並重啟', 'administrator'),
            ('status', '查看系統狀態', 'user'),
            ('restart_all', '重啟所有 Bot 服務', 'administrator'),
        ]
        for cmd_name, desc, perm in system_commands:
            self.registry.register_active(cmd_name, 'Common / 系統工具', None, desc, perm)
        
        # ========================================
        # Shop 模組指令 (3 個)
        # ========================================
        
        shop_commands = [
            ('grant_temporary_role', '授予臨時身分', 'administrator'),
            ('check_my_roles', '查看臨時身分', 'user'),
            ('shopping', '打開商店', 'user'),
        ]
        for cmd_name, desc, perm in shop_commands:
            self.registry.register_active(cmd_name, 'Shop / 商店', None, desc, perm)
        
        # ========================================
        # 統計
        # ========================================
        stats = self.registry.get_stats()
        logger.info(f"✅ 已註冊 {stats['total_active']} 個指令")
        logger.info(f"   分類: {stats['by_category']}")
    
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
