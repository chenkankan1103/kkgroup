"""
角色過期管理系統
- 持久化存儲購買的臨時角色
- 機器人啟動時自動清理過期角色
- 定期檢查（每小時）並自動移除已過期角色

重要說明：
- 「已處理」(is_active=0) 只是標記該過期記錄已被清理，不會禁止用戶再次購買
- 用戶可以在身分過期後再次購買相同的身分
- 每次購買都會在數據庫中新增或更新記錄
"""

import sqlite3
import discord
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from db_adapter import get_db
import asyncio
import os

DB_PATH = os.getenv("DB_PATH", "user_data.db")


class RoleExpirationManager:
    """管理臨時角色的過期邏輯"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self._init_role_table()
    
    def _init_role_table(self):
        """初始化角色過期記錄表"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS role_expirations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    role_name TEXT NOT NULL,
                    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(user_id, guild_id, role_id)
                )
            """)
            
            conn.commit()
            conn.close()
            print("[RoleExpiration] 角色過期表已初始化")
        except Exception as e:
            print(f"[RoleExpiration] 初始化失敗: {e}")
    
    def save_role_purchase(
        self, 
        user_id: int, 
        guild_id: int, 
        role_id: int, 
        role_name: str, 
        duration_seconds: int
    ) -> bool:
        """
        保存臨時角色購買記錄 - 支持時間疊加
        
        如果用戶已擁有該角色且未過期，新購買的時間會疊加到現有期限
        如果角色已過期或不存在，則以購買時間作為起點
        
        Args:
            user_id: 用戶ID
            guild_id: 伺服器ID
            role_id: 角色ID
            role_name: 角色名稱
            duration_seconds: 持續時間（秒）
            
        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 先查詢現有的過期時間
            cursor.execute("""
                SELECT expires_at FROM role_expirations
                WHERE user_id = ? AND guild_id = ? AND role_id = ? AND is_active = 1
            """, (user_id, guild_id, role_id))
            
            result = cursor.fetchone()
            current_time = datetime.now()
            
            # 計算新的過期時間
            if result:
                existing_expires_at = datetime.fromisoformat(result[0])
                # 如果現有期限還沒過期，則疊加時間
                if existing_expires_at > current_time:
                    expires_at = existing_expires_at + timedelta(seconds=duration_seconds)
                    action = "⏱️ 時間已疊加到現有期限"
                else:
                    # 現有期限已過期，重新開始計算
                    expires_at = current_time + timedelta(seconds=duration_seconds)
                    action = "🔄 期限已過期，重新計算"
            else:
                # 沒有現有記錄，新開始計算
                expires_at = current_time + timedelta(seconds=duration_seconds)
                action = "✨ 首次購買"
            
            # 使用 INSERT OR REPLACE 更新或新建記錄
            cursor.execute("""
                INSERT OR REPLACE INTO role_expirations 
                (user_id, guild_id, role_id, role_name, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (user_id, guild_id, role_id, role_name, expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
            log_msg = f"{action} 數據庫記錄: {role_name} 到期: {expires_at.strftime('%Y-%m-%d %H:%M')} (用戶 {user_id})"
            print(f"[RoleExpiration] ✅ {log_msg}")
            return True
            
        except Exception as e:
            print(f"[RoleExpiration] ❌ 保存失敗 (用戶 {user_id}, {role_name}): {e}")
            return False
    
    def get_expired_roles(self) -> List[Tuple[int, int, int, str]]:
        """
        獲取所有已過期的角色
        
        Returns:
            列表，每項為 (user_id, guild_id, role_id, role_name)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = datetime.now().isoformat()
            
            cursor.execute("""
                SELECT user_id, guild_id, role_id, role_name 
                FROM role_expirations
                WHERE is_active = 1 AND expires_at <= ?
            """, (current_time,))
            
            results = cursor.fetchall()
            conn.close()
            
            return results
            
        except Exception as e:
            print(f"[RoleExpiration] 查詢過期角色失敗: {e}")
            return []
    
    def mark_as_removed(self, user_id: int, guild_id: int, role_id: int) -> bool:
        """
        標記角色過期記錄已處理（不會禁止用戶重新購買）
        
        此方法只是在數據庫中標記 is_active=0，表示該過期記錄已被清理。
        用戶仍然可以在任何時間再次購買相同的身分，系統會新增一條新的記錄。
        
        Args:
            user_id: 用戶ID
            guild_id: 伺服器ID
            role_id: 角色ID
            
        Returns:
            是否成功標記為已處理
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE role_expirations
                SET is_active = 0
                WHERE user_id = ? AND guild_id = ? AND role_id = ?
            """, (user_id, guild_id, role_id))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"[RoleExpiration] 標記失敗: {e}")
            return False
    
    async def cleanup_expired_roles(self, bot: discord.Client) -> int:
        """
        清理所有過期的角色
        
        Args:
            bot: Discord bot 客戶端
            
        Returns:
            已移除的角色數量
        """
        expired_roles = self.get_expired_roles()
        removed_count = 0
        
        print(f"[RoleExpiration] 清理任務開始，找到 {len(expired_roles)} 個過期角色")
        
        for user_id, guild_id, role_id, role_name in expired_roles:
            try:
                guild = bot.get_guild(guild_id)
                if not guild:
                    print(f"[RoleExpiration] ⚠️ 伺服器 {guild_id} 不存在，標記為已處理")
                    self.mark_as_removed(user_id, guild_id, role_id)
                    removed_count += 1
                    continue
                
                member = guild.get_member(user_id)
                if not member:
                    print(f"[RoleExpiration] ⚠️ 用戶 {user_id} 不在伺服器 {guild_id}，標記為已處理")
                    self.mark_as_removed(user_id, guild_id, role_id)
                    removed_count += 1
                    continue
                
                role = guild.get_role(role_id)
                if not role:
                    print(f"[RoleExpiration] ⚠️ 角色 {role_id} ({role_name}) 不存在，標記為已處理")
                    self.mark_as_removed(user_id, guild_id, role_id)
                    removed_count += 1
                    continue
                
                # 檢查成員是否擁有該角色
                if role in member.roles:
                    await member.remove_roles(role, reason="臨時角色已過期")
                    print(f"[RoleExpiration] ✅ 已移除 {member.display_name} 的 {role_name} 身分")
                    removed_count += 1
                else:
                    # 角色已不在成員上，直接標記為已處理
                    print(f"[RoleExpiration] ℹ️ {member.display_name} 已不擁有 {role_name} 身分")
                
                # 標記為已移除（無論是否實際移除了角色）
                self.mark_as_removed(user_id, guild_id, role_id)
                
            except Exception as e:
                print(f"[RoleExpiration] ❌ 移除失敗 (用戶 {user_id}, 角色 {role_id}): {e}")
        
        if removed_count > 0:
            print(f"[RoleExpiration] ✅ 本次清理完成：移除了 {removed_count} 個過期角色")
        
        return removed_count


# 全局實例
_manager = None


def get_manager() -> RoleExpirationManager:
    """獲取全局管理器實例"""
    global _manager
    if _manager is None:
        _manager = RoleExpirationManager()
    return _manager
