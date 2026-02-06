#!/usr/bin/env python3
"""
批量降級使用者職稱系統 - 所有會員降 1 級並同步資料庫

功能：
1. 讀取所有用戶
2. 將等級降 1 級（最低到 Lv.0）
3. 設定經驗為該新等級的升級所需最低值
4. 更新 Discord 身分組
5. 同步到資料庫
"""

import discord
import asyncio
import os
from dotenv import load_dotenv
from db_adapter import get_all_users, set_user_field, get_user
from commands.work_function.work_system import LEVELS

load_dotenv()

GUILD_ID = int(os.getenv("GUILD_ID", 0))
BOT_TOKEN = os.getenv("UI_DISCORD_BOT_TOKEN", "")

# 降級對應表（降 1 級）
DOWNGRADE_MAP = {
    0: 0,  # Lv.0 保持
    1: 0,  # Lv.1 → Lv.0
    2: 1,  # Lv.2 → Lv.1
    3: 2,  # Lv.3 → Lv.2
    4: 3,  # Lv.4 → Lv.3
    5: 4,  # Lv.5 → Lv.4
    6: 5,  # Lv.6 → Lv.5
}

# 新等級的 XP 設定（升級所需最低值）
XP_FOR_LEVEL = {
    0: 0,
    1: 500,
    2: 1500,
    3: 4000,
    4: 8500,
    5: 18000,
    6: 40000,
}


class DowngradeBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        
    async def on_ready(self):
        print(f"✅ 機器人已登入: {self.user}")
        await self.batch_downgrade()
        await self.close()
    
    async def batch_downgrade(self):
        """批量降級所有用戶"""
        try:
            guild = self.get_guild(GUILD_ID)
            if not guild:
                print(f"❌ 找不到伺服器 {GUILD_ID}")
                return
            
            # 獲取所有用戶
            all_users = get_all_users()
            if not all_users:
                print("⚠️ 沒有找到任何用戶")
                return
            
            # 如果 all_users 是 list，轉換為 dict
            if isinstance(all_users, list):
                users_dict = {}
                for user_data in all_users:
                    user_id = user_data.get('user_id')
                    if user_id:
                        users_dict[user_id] = user_data
                all_users = users_dict
            
            print(f"📊 開始處理 {len(all_users)} 個用戶...")
            
            success_count = 0
            error_count = 0
            
            for idx, (user_id, user_data) in enumerate(all_users.items(), 1):
                try:
                    old_level = user_data.get('level', 0)
                    new_level = DOWNGRADE_MAP.get(old_level, 0)
                    new_xp = XP_FOR_LEVEL.get(new_level, 0)
                    
                    # 更新資料庫
                    set_user_field(user_id, 'level', new_level)
                    set_user_field(user_id, 'xp', new_xp)
                    
                    # 更新 Discord 身分組
                    member = guild.get_member(int(user_id))
                    if member:
                        # 移除所有舊等級身分組
                        roles_to_remove = []
                        for lvl in LEVELS.keys():
                            role_id = LEVELS[lvl].get("role_id", 0)
                            if role_id:
                                role = guild.get_role(role_id)
                                if role and role in member.roles:
                                    roles_to_remove.append(role)
                        
                        if roles_to_remove:
                            await member.remove_roles(*roles_to_remove, reason="批量等級降級 - 移除舊身分")
                            print(f"  🔴 {user_id} | 移除 {len(roles_to_remove)} 個舊身分")
                        
                        # 添加新等級身分組
                        new_role_id = LEVELS[new_level].get("role_id", 0)
                        if new_role_id:
                            new_role = guild.get_role(new_role_id)
                            if new_role:
                                await member.add_roles(new_role, reason=f"批量等級降級 - 降至 Lv.{new_level}")
                                print(f"  ✅ {user_id} ({member.name}) | Lv.{old_level} → Lv.{new_level} | XP: {new_xp}")
                            else:
                                print(f"  ⚠️ {user_id} | 身分組 {new_role_id} 不存在")
                        else:
                            print(f"  ✅ {user_id} ({member.name}) | Lv.{old_level} → Lv.{new_level} | 無身分組（Lv.0）")
                    else:
                        # 只更新資料庫，成員不在伺服器
                        print(f"  ℹ️ {user_id} | 不在伺服器，僅更新資料庫 | Lv.{old_level} → Lv.{new_level}")
                    
                    success_count += 1
                    
                    # 顯示進度
                    if idx % 10 == 0:
                        print(f"  進度: {idx}/{len(all_users)} 已完成")
                    
                    # 避免 API 限流
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    error_count += 1
                    print(f"  ❌ 用戶 {user_id} | 錯誤: {e}")
            
            print("\n" + "="*70)
            print(f"✅ 批量降級完成！")
            print(f"  成功: {success_count}")
            print(f"  失敗: {error_count}")
            print(f"  總數: {len(all_users)}")
            print("="*70)
            
        except Exception as e:
            print(f"❌ 批量降級失敗: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主程式入口"""
    bot = DowngradeBot()
    async with bot:
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    print("🚀 開始批量等級降級程序...")
    print("⚠️ 警告: 這將修改所有用戶的等級！")
    print()
    
    # 確認
    confirm = input("確定要繼續嗎？(yes/no): ").strip().lower()
    if confirm != "yes":
        print("已取消")
        exit(0)
    
    print()
    asyncio.run(main())
