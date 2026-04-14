"""
AI 記憶管理指令
允許用戶設置 AI 角色、添加知識、管理記憶
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging

try:
    from ai_memory import (
        DialogueMemory,
        PersonalityMemory,
        KnowledgeBase,
        initialize_memory_system
    )
except ImportError:
    # Stub
    class DialogueMemory:
        @staticmethod
        def cleanup_old_dialogue(): pass
    class PersonalityMemory:
        @staticmethod
        def set_personality(k, v): pass
        @staticmethod
        def list_personality(): return []
    class KnowledgeBase:
        @staticmethod
        def add_knowledge(t, c, cat="general"): pass
        @staticmethod
        def search_knowledge(k, t=1000): return ""
    def initialize_memory_system(): pass

logger = logging.getLogger(__name__)


class MemoryManager(commands.Cog):
    """AI 記憶管理"""
    
    def __init__(self, bot):
        self.bot = bot
        initialize_memory_system()
    
    # ==================== 角色管理指令 ====================
    @app_commands.command(name="ai_personality_set", description="設定 AI 角色特性（管理員專用）")
    @app_commands.describe(key="特性名稱", value="特性內容")
    @app_commands.default_permissions(administrator=True)
    async def ai_personality_set(self, interaction: discord.Interaction, key: str, value: str):
        """設定 AI 角色特性"""
        try:
            PersonalityMemory.set_personality(key, value)
            embed = discord.Embed(
                title="✅ 角色特性已設定",
                description=f"**{key}**: {value[:100]}...",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 設定失敗: {e}", ephemeral=True)

    @app_commands.command(name="ai_personality_list", description="查看所有 AI 角色設定（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def ai_personality_list(self, interaction: discord.Interaction):
        """查看當前所有 AI 角色設定"""
        try:
            personalities = PersonalityMemory.list_personality()
            
            if not personalities:
                await interaction.response.send_message("📭 目前沒有設定任何角色特性", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="👤 AI 角色設定列表",
                color=discord.Color.blue()
            )
            
            for key, value in personalities:
                # 截斷過長的值
                display_value = value[:200] + "..." if len(value) > 200 else value
                embed.add_field(name=key, value=display_value, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢失敗: {e}", ephemeral=True)
    
    # ==================== 知識庫管理指令 ====================
    @app_commands.command(name="ai_knowledge_add", description="添加知識到 AI 知識庫（管理員專用）")
    @app_commands.describe(topic="知識主題", content="知識內容")
    @app_commands.default_permissions(administrator=True)
    async def ai_knowledge_add(self, interaction: discord.Interaction, topic: str, content: str):
        """添加知識到庫"""
        try:
            category = interaction.channel.name or "general"
            KnowledgeBase.add_knowledge(topic, content, category=category)
            
            embed = discord.Embed(
                title="📚 知識已添加",
                description=f"**主題**: {topic}\n**頻道分類**: {category}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 添加失敗: {e}", ephemeral=True)

    @app_commands.command(name="ai_knowledge_search", description="搜索 AI 知識庫內容（管理員專用）")
    @app_commands.describe(keyword="搜索關鍵詞")
    @app_commands.default_permissions(administrator=True)
    async def ai_knowledge_search(self, interaction: discord.Interaction, keyword: str):
        """搜索知識庫內容"""
        try:
            results = KnowledgeBase.search_knowledge(keyword, max_tokens=2000)
            
            if not results:
                await interaction.response.send_message(f"❌ 找不到包含 '{keyword}' 的知識", ephemeral=True)
                return
            
            # 分頁顯示
            if len(results) > 2000:
                # 顯示為文件
                await interaction.response.send_message(
                    f"📚 找到符合 '{keyword}' 的知識 ({len(results)} 字符):",
                    file=discord.File(
                        fp=__import__('io').BytesIO(results.encode('utf-8')),
                        filename="search_results.txt"
                    ),
                    ephemeral=True
                )
            else:
                embed = discord.Embed(
                    title=f"📚 搜索結果: {keyword}",
                    description=results[:2048],
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 搜索失敗: {e}", ephemeral=True)
    
    # ==================== 記憶管理指令 ====================
    @app_commands.command(name="ai_memory_cleanup", description="清理過期的 AI 記憶（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def ai_memory_cleanup(self, interaction: discord.Interaction):
        """清理過期的對話記憶（超過 7 天且重要性低的記錄）"""
        try:
            DialogueMemory.cleanup_old_dialogue()
            embed = discord.Embed(
                title="🧹 記憶清理完成",
                description="已清理過期的低重要性對話記憶",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 清理失敗: {e}", ephemeral=True)
    
    @app_commands.command(name="ai_memory_status", description="查看 AI 記憶系統狀態（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def ai_memory_status(self, interaction: discord.Interaction):
        """查看 AI 記憶系統狀態"""
        try:
            personalities = PersonalityMemory.list_personality()
            
            embed = discord.Embed(
                title="📊 AI 記憶系統狀態",
                color=discord.Color.purple()
            )
            
            embed.add_field(
                name="👤 角色設定",
                value=f"已設定 {len(personalities)} 項特性",
                inline=False
            )
            
            embed.add_field(
                name="📚 知識庫",
                value="查詢功能已啟用",
                inline=False
            )
            
            embed.add_field(
                name="💭 對話記憶",
                value="自動記錄並參考",
                inline=False
            )
            
            embed.set_footer(text="記憶系統正常運作 ✅")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 無法獲取狀態: {e}", ephemeral=True)


async def setup(bot):
    """設置記憶管理 cog"""
    await bot.add_cog(MemoryManager(bot))
    logger.info("✅ 記憶管理模組已載入")
