import discord
from discord.ext import commands
from discord import app_commands
from db_adapter import get_user, set_user, get_all_users
from typing import Optional

class AvatarReset(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_user_data(self, user_id: int) -> Optional[dict]:
        """獲取使用者資料"""
        try:
            return get_user(user_id)
        except Exception as e:
            print(f"獲取使用者資料錯誤: {e}")
            return None

    def update_user_avatar(self, user_id: int, avatar_data: dict) -> bool:
        """更新單一使用者的紙娃娃資料"""
        try:
            return set_user(user_id, avatar_data)
        except Exception as e:
            print(f"更新使用者外觀錯誤: {e}")
            return False

    def reset_all_avatars_by_gender(self) -> dict:
        """重製所有使用者的紙娃娃為預設外觀"""
        try:
            # 獲取所有使用者資料
            users = get_all_users()
            
            reset_count = {'male': 0, 'female': 0, 'error': 0}
            
            for user_data in users:
                user_id = user_data.get('user_id')
                gender = user_data.get('gender', 'male')
                
                if gender == 'female':
                    # 女性預設外觀
                    avatar_data = {
                        'face': 21731,
                        'hair': 34410,
                        'skin': 12000,
                        'top': 1041004,
                        'bottom': 1061008,
                        'shoes': 1072005
                    }
                    reset_count['female'] += 1
                else:
                    # 男性預設外觀（包含未設定性別的使用者）
                    avatar_data = {
                        'face': 20005,
                        'hair': 30120,
                        'skin': 12000,
                        'top': 1040014,
                        'bottom': 1060096,
                        'shoes': 1072005
                    }
                    reset_count['male'] += 1
                
                # 更新該使用者的外觀
                set_user(user_id, avatar_data)
            
            return reset_count
            
        except Exception as e:
            print(f"批量重製紙娃娃錯誤: {e}")
            return {'male': 0, 'female': 0, 'error': 1}







async def setup(bot):
    await bot.add_cog(AvatarReset(bot))