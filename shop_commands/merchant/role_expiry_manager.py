import discord
from discord.ext import commands, tasks
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import traceback

class RoleExpiryManager(commands.Cog):
    """管理身份組到期的系統"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = './user_data.db'
        
    async def cog_load(self):
        """Cog 載入時初始化資料庫並啟動檢查任務"""
        try:
            await self.init_database()
            self.check_expired_roles.start()
            print("✅ 身份組到期管理系統已啟動")
        except Exception as e:
            print(f"❌ 身份組到期管理系統啟動失敗: {e}")
            traceback.print_exc()
    
    async def cog_unload(self):
        """Cog 卸載時停止檢查任務"""
        self.check_expired_roles.cancel()
        print("⚠️ 身份組到期管理系統已停止")
    
    async def init_database(self):
        """初始化資料庫表格"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 創建身份組購買記錄表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS role_purchases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        guild_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        role_name TEXT NOT NULL,
                        purchase_time TEXT NOT NULL,
                        expire_time TEXT NOT NULL,
                        is_expired INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 創建索引以提高查詢效率
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_expire_time 
                    ON role_purchases(expire_time, is_expired)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_role 
                    ON role_purchases(user_id, role_id, is_expired)
                """)
                
                await db.commit()
                print("✅ 身份組購買記錄資料庫初始化完成")
                
        except Exception as e:
            print(f"❌ 資料庫初始化失敗: {e}")
            traceback.print_exc()
    
    async def record_role_purchase(self, user_id: int, guild_id: int, role_id: int, 
                                   role_name: str, duration_seconds: int):
        """記錄身份組購買
        
        Args:
            user_id: 用戶 ID
            guild_id: 伺服器 ID
            role_id: 身份組 ID
            role_name: 身份組名稱
            duration_seconds: 持續時間（秒）
        """
        try:
            now = datetime.now()
            expire_time = now + timedelta(seconds=duration_seconds)
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO role_purchases 
                    (user_id, guild_id, role_id, role_name, purchase_time, expire_time, is_expired)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (
                    user_id,
                    guild_id,
                    role_id,
                    role_name,
                    now.isoformat(),
                    expire_time.isoformat()
                ))
                await db.commit()
                
            print(f"✅ 記錄身份組購買: 用戶 {user_id} 購買 {role_name}，將於 {expire_time} 到期")
            return True
            
        except Exception as e:
            print(f"❌ 記錄身份組購買失敗: {e}")
            traceback.print_exc()
            return False
    
    @tasks.loop(minutes=10)
    async def check_expired_roles(self):
        """每10分鐘檢查一次到期的身份組"""
        try:
            print(f"[{datetime.now()}] 🔍 開始檢查到期的身份組...")
            
            now = datetime.now().isoformat()
            
            async with aiosqlite.connect(self.db_path) as db:
                # 查詢所有到期但尚未處理的身份組
                cursor = await db.execute("""
                    SELECT id, user_id, guild_id, role_id, role_name, expire_time
                    FROM role_purchases
                    WHERE expire_time <= ? AND is_expired = 0
                    ORDER BY expire_time ASC
                """, (now,))
                
                expired_records = await cursor.fetchall()
                
                if not expired_records:
                    print("✅ 沒有到期的身份組")
                    return
                
                print(f"📋 找到 {len(expired_records)} 個到期的身份組記錄")
                
                # 處理每個到期記錄
                for record in expired_records:
                    record_id, user_id, guild_id, role_id, role_name, expire_time = record
                    
                    success = await self.remove_expired_role(
                        record_id, user_id, guild_id, role_id, role_name, expire_time
                    )
                    
                    if success:
                        # 標記為已處理
                        await db.execute("""
                            UPDATE role_purchases 
                            SET is_expired = 1 
                            WHERE id = ?
                        """, (record_id,))
                        await db.commit()
                
                print(f"✅ 到期身份組檢查完成")
                
        except Exception as e:
            print(f"❌ 檢查到期身份組時發生錯誤: {e}")
            traceback.print_exc()
    
    @check_expired_roles.before_loop
    async def before_check_expired_roles(self):
        """等待機器人準備就緒後再開始檢查"""
        await self.bot.wait_until_ready()
        print("✅ 機器人已就緒，身份組到期檢查任務準備啟動")
    
    async def remove_expired_role(self, record_id: int, user_id: int, guild_id: int, 
                                  role_id: int, role_name: str, expire_time: str):
        """移除到期的身份組
        
        Returns:
            bool: 是否成功移除
        """
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"⚠️ 找不到伺服器 {guild_id}，跳過記錄 {record_id}")
                return True  # 標記為已處理，避免重複嘗試
            
            member = guild.get_member(user_id)
            if not member:
                print(f"⚠️ 用戶 {user_id} 已離開伺服器 {guild.name}，跳過記錄 {record_id}")
                return True
            
            role = guild.get_role(role_id)
            if not role:
                print(f"⚠️ 找不到身份組 {role_id} ({role_name})，跳過記錄 {record_id}")
                return True
            
            # 檢查用戶是否還擁有該身份組
            if role not in member.roles:
                print(f"ℹ️ 用戶 {member.display_name} 已經沒有身份組 {role_name}，跳過記錄 {record_id}")
                return True
            
            # 移除身份組
            await member.remove_roles(role, reason=f"身份組到期 (過期時間: {expire_time})")
            print(f"✅ 成功移除 {member.display_name} 的身份組 {role_name} (記錄 {record_id})")
            
            # 發送通知給用戶（可選）
            try:
                embed = discord.Embed(
                    title="⏰ 身份組已到期",
                    description=f"你在 **{guild.name}** 的 **{role_name}** 身份組已到期並被移除。",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="到期時間", value=expire_time, inline=False)
                embed.set_footer(text="如需繼續使用，請重新購買")
                
                await member.send(embed=embed)
                print(f"📧 已向 {member.display_name} 發送到期通知")
            except discord.Forbidden:
                print(f"⚠️ 無法向 {member.display_name} 發送私訊")
            except Exception as e:
                print(f"⚠️ 發送通知時發生錯誤: {e}")
            
            return True
            
        except discord.Forbidden:
            print(f"❌ 權限不足，無法移除 {role_name} (記錄 {record_id})")
            return False
        except Exception as e:
            print(f"❌ 移除身份組時發生錯誤 (記錄 {record_id}): {e}")
            traceback.print_exc()
            return False
    
    async def get_user_active_roles(self, user_id: int, guild_id: int):
        """獲取用戶所有活躍的身份組購買記錄"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT role_id, role_name, purchase_time, expire_time
                    FROM role_purchases
                    WHERE user_id = ? AND guild_id = ? AND is_expired = 0
                    ORDER BY expire_time ASC
                """, (user_id, guild_id))
                
                records = await cursor.fetchall()
                return records
                
        except Exception as e:
            print(f"❌ 獲取用戶活躍身份組失敗: {e}")
            return []
    
    async def cancel_role_purchase(self, user_id: int, guild_id: int, role_id: int):
        """取消身份組購買記錄（用於手動移除或退款）"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE role_purchases 
                    SET is_expired = 1 
                    WHERE user_id = ? AND guild_id = ? AND role_id = ? AND is_expired = 0
                """, (user_id, guild_id, role_id))
                await db.commit()
                
            print(f"✅ 已取消用戶 {user_id} 的身份組 {role_id} 購買記錄")
            return True
            
        except Exception as e:
            print(f"❌ 取消身份組購買記錄失敗: {e}")
            return False
    
    @commands.command(name="check_my_roles")
    async def check_my_roles(self, ctx):
        """檢查自己購買的身份組狀態"""
        try:
            records = await self.get_user_active_roles(ctx.author.id, ctx.guild.id)
            
            if not records:
                await ctx.send("你目前沒有購買任何限時身份組。", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📋 你的限時身份組",
                description=f"共有 {len(records)} 個活躍的身份組",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            for role_id, role_name, purchase_time, expire_time in records:
                expire_dt = datetime.fromisoformat(expire_time)
                time_left = expire_dt - datetime.now()
                
                if time_left.total_seconds() > 0:
                    days = time_left.days
                    hours = time_left.seconds // 3600
                    minutes = (time_left.seconds % 3600) // 60
                    
                    time_left_str = []
                    if days > 0:
                        time_left_str.append(f"{days}天")
                    if hours > 0:
                        time_left_str.append(f"{hours}小時")
                    if minutes > 0:
                        time_left_str.append(f"{minutes}分鐘")
                    
                    time_str = " ".join(time_left_str) if time_left_str else "即將到期"
                else:
                    time_str = "已到期（等待系統處理）"
                
                embed.add_field(
                    name=f"🎭 {role_name}",
                    value=f"剩餘時間: {time_str}\n到期時間: {expire_time}",
                    inline=False
                )
            
            await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"❌ 檢查身份組狀態失敗: {e}")
            await ctx.send("檢查身份組狀態時發生錯誤。", ephemeral=True)

async def setup(bot):
    """Cog 設置函數"""
    try:
        await bot.add_cog(RoleExpiryManager(bot))
        print("✅ RoleExpiryManager Cog 已成功加載")
    except Exception as e:
        print(f"❌ 加載 RoleExpiryManager Cog 失敗: {e}")
        traceback.print_exc()
