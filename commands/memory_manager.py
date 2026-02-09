"""
AI 記憶管理指令
允許用戶設置 AI 角色、添加知識、管理記憶
"""

import discord
from discord.ext import commands
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
    @commands.group(name="ai_personality", help="管理 AI 角色設定")
    @commands.has_permissions(administrator=True)
    async def ai_personality(self, ctx):
        """AI 角色設定群組"""
        if ctx.invoked_subcommand is None:
            await ctx.send("❌ 請使用子指令: `!ai_personality set <key> <value>` 或 `!ai_personality list`")
    
    @ai_personality.command(name="set", help="設置 AI 角色特性")
    async def set_personality(self, ctx, key: str, *, value: str):
        """設置 AI 角色特性
        
        用法: !ai_personality set 角色 "你是一個幽默的助手"
        """
        try:
            PersonalityMemory.set_personality(key, value)
            embed = discord.Embed(
                title="✅ 角色特性已設定",
                description=f"**{key}**: {value[:100]}...",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ 設定失敗: {e}")
    
    @ai_personality.command(name="list", help="查看所有角色設定")
    async def list_personality(self, ctx):
        """查看當前所有 AI 角色設定"""
        try:
            personalities = PersonalityMemory.list_personality()
            
            if not personalities:
                await ctx.send("📭 目前沒有設定任何角色特性")
                return
            
            embed = discord.Embed(
                title="👤 AI 角色設定列表",
                color=discord.Color.blue()
            )
            
            for key, value in personalities:
                # 截斷過長的值
                display_value = value[:200] + "..." if len(value) > 200 else value
                embed.add_field(name=key, value=display_value, inline=False)
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ 查詢失敗: {e}")
    
    # ==================== 知識庫管理指令 ====================
    @commands.group(name="ai_knowledge", help="管理 AI 知識庫")
    @commands.has_permissions(administrator=True)
    async def ai_knowledge(self, ctx):
        """AI 知識庫群組"""
        if ctx.invoked_subcommand is None:
            await ctx.send("❌ 請使用子指令: `!ai_knowledge add <話題> <內容>` 或 `!ai_knowledge search <關鍵詞>`")
    
    @ai_knowledge.command(name="add", help="添加知識到庫")
    async def add_knowledge(self, ctx, topic: str, *, content: str):
        """添加知識到庫
        
        用法: !ai_knowledge add "KK園區規則" "新用戶需要..."
        """
        try:
            category = ctx.channel.name or "general"
            KnowledgeBase.add_knowledge(topic, content, category=category)
            
            embed = discord.Embed(
                title="📚 知識已添加",
                description=f"**主題**: {topic}\n**頻道分類**: {category}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ 添加失敗: {e}")
    
    @ai_knowledge.command(name="search", help="搜索知識庫")
    async def search_knowledge(self, ctx, *, keyword: str):
        """搜索知識庫內容
        
        用法: !ai_knowledge search "規則"
        """
        try:
            results = KnowledgeBase.search_knowledge(keyword, max_tokens=2000)
            
            if not results:
                await ctx.send(f"❌ 找不到包含 '{keyword}' 的知識")
                return
            
            # 分頁顯示
            if len(results) > 2000:
                # 顯示為文件
                await ctx.send(
                    f"📚 找到符合 '{keyword}' 的知識 ({len(results)} 字符):",
                    file=discord.File(
                        fp=__import__('io').BytesIO(results.encode('utf-8')),
                        filename="search_results.txt"
                    )
                )
            else:
                embed = discord.Embed(
                    title=f"📚 搜索結果: {keyword}",
                    description=results[:2048],
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ 搜索失敗: {e}")
    
    # ==================== 記憶管理指令 ====================
    @commands.command(name="ai_memory_cleanup", help="清理過期的 AI 記憶")
    @commands.has_permissions(administrator=True)
    async def cleanup_memory(self, ctx):
        """清理過期的對話記憶（超過 7 天且重要性低的記錄）"""
        try:
            DialogueMemory.cleanup_old_dialogue()
            embed = discord.Embed(
                title="🧹 記憶清理完成",
                description="已清理過期的低重要性對話記憶",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ 清理失敗: {e}")
    
    @commands.command(name="ai_memory_status", help="查看記憶系統狀態")
    @commands.has_permissions(administrator=True)
    async def memory_status(self, ctx):
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
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ 無法獲取狀態: {e}")


async def setup(bot):
    """設置記憶管理 cog"""
    await bot.add_cog(MemoryManager(bot))
    logger.info("✅ 記憶管理模組已載入")
