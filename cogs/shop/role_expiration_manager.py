"""
角色過期管理系統
- 持久化存儲購買的臨時角色
- 機器人啟動時自動清理過期角色
- 定期檢查並自動移除已過期角色
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
        保存臨時角色購買記錄
        
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
            
            # 計算過期時間
            expires_at = datetime.now() + timedelta(seconds=duration_seconds)
            
            # 使用 INSERT OR REPLACE 避免重複
            cursor.execute("""
                INSERT OR REPLACE INTO role_expirations 
                (user_id, guild_id, role_id, role_name, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (user_id, guild_id, role_id, role_name, expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
            print(f"[RoleExpiration] 已保存 {role_name} 到期時間: {expires_at}")
            return True
            
        except Exception as e:
            print(f"[RoleExpiration] 保存失敗: {e}")
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
        標記角色已移除
        
        Args:
            user_id: 用戶ID
            guild_id: 伺服器ID
            role_id: 角色ID
            
        Returns:
            是否成功
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
        
        for user_id, guild_id, role_id, role_name in expired_roles:
            try:
                guild = bot.get_guild(guild_id)
                if not guild:
                    print(f"[RoleExpiration] 找不到伺服器 {guild_id}")
                    self.mark_as_removed(user_id, guild_id, role_id)
                    continue
                
                member = guild.get_member(user_id)
                if not member:
                    print(f"[RoleExpiration] 找不到會員 {user_id} 在伺服器 {guild_id}")
                    self.mark_as_removed(user_id, guild_id, role_id)
                    continue
                
                role = guild.get_role(role_id)
                if not role:
                    print(f"[RoleExpiration] 找不到角色 {role_id}")
                    self.mark_as_removed(user_id, guild_id, role_id)
                    continue
                
                # 移除角色
                if role in member.roles:
                    await member.remove_roles(role)
                    print(f"[RoleExpiration] ✅ 已移除 {member.display_name} 的 {role_name}")
                    removed_count += 1
                
                # 標記為已移除
                self.mark_as_removed(user_id, guild_id, role_id)
                
            except Exception as e:
                print(f"[RoleExpiration] 移除失敗 ({user_id}, {role_id}): {e}")
        
        if removed_count > 0:
            print(f"[RoleExpiration] ✅ 本次清理移除了 {removed_count} 個過期角色")
        
        return removed_count


# 全局實例
_manager = None


def get_manager() -> RoleExpirationManager:
    """獲取全局管理器實例"""
    global _manager
    if _manager is None:
        _manager = RoleExpirationManager()
    return _manager
