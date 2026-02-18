import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import logging
import traceback
import discord
from discord import app_commands
import aiohttp
import json
from db_adapter import get_user, set_user, get_user_field, set_user_field, get_all_users

class UserRecoveryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 不在這裡啟動，而是在 ready 事件中啟動
        self._recovery_loop_started = False

    def cog_unload(self):
        """Cog 卸載時停止循環任務"""
        if self.recovery_loop.is_running():
            self.recovery_loop.cancel()

    @tasks.loop(minutes=10)
    async def recovery_loop(self):
        """每10分鐘執行一次自動回復"""
        try:
            logging.info("開始執行自動回復任務...")
            recovered_users = await self.process_all_users_recovery()
            if recovered_users > 0:
                logging.info(f"自動回復完成，{recovered_users} 位用戶狀態更新")
            else:
                logging.info("自動回復完成，沒有用戶需要更新")
        except Exception as e:
            logging.error(f"自動回復過程發生錯誤: {e}")
            logging.error(f"錯誤詳情: {traceback.format_exc()}")

    @recovery_loop.before_loop
    async def before_recovery_loop(self):
        """等待 bot 準備完成"""
        await self.bot.wait_until_ready()
        logging.info("機器人已準備就緒，自動回復系統啟動")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot 準備完成時啟動回復循環"""
        if not self._recovery_loop_started:
            self._recovery_loop_started = True
            if not self.recovery_loop.is_running():
                self.recovery_loop.start()
                logging.info("✅ 自動回復循環已啟動")

    def ensure_database_structure(self):
        """確保資料庫結構正確 - db_adapter 會自動管理欄位"""
        # db_adapter 會自動處理欄位創建，這裡只需確保資料表存在
        # 通過獲取所有用戶來觸發資料庫初始化
        try:
            get_all_users(limit=1)
            logging.debug("資料庫結構檢查完成")
            return True
        except Exception as e:
            logging.error(f"確保資料庫結構時發生錯誤: {e}")
            return False

    def parse_recovery_time(self, time_value):
        """統一解析回復時間的函數"""
        try:
            if time_value is None:
                return datetime.now() - timedelta(hours=2)
            
            if isinstance(time_value, (int, float)):
                return datetime.fromtimestamp(time_value)
            
            if isinstance(time_value, str):
                try:
                    timestamp = float(time_value)
                    return datetime.fromtimestamp(timestamp)
                except ValueError:
                    pass
                
                try:
                    clean_time = time_value.replace('Z', '')
                    if '+' in clean_time[-6:] or '-' in clean_time[-6:]:
                        return datetime.fromisoformat(time_value.replace('Z', '+00:00'))
                    else:
                        return datetime.fromisoformat(clean_time)
                except ValueError:
                    pass
            
            logging.warning(f"無法解析時間值: {time_value}，使用預設時間")
            return datetime.now() - timedelta(hours=2)
            
        except Exception as e:
            logging.error(f"解析時間時發生錯誤: {e}")
            return datetime.now() - timedelta(hours=2)

    async def process_all_users_recovery(self):
        """處理所有用戶的自動回復"""
        recovered_count = 0
        
        try:
            logging.debug("開始處理用戶回復...")
            
            if not self.ensure_database_structure():
                return 0
            
            # 使用 db_adapter 獲取所有用戶
            all_users = get_all_users()
            logging.info(f"資料庫中共有 {len(all_users)} 位用戶")
            
            if len(all_users) == 0:
                logging.info("資料庫中沒有用戶數據")
                return 0
            
            # 過濾出需要處理的用戶（有 hp 和 stamina 數據）
            users = [(u.get('user_id'), u.get('hp'), u.get('stamina'), 
                     u.get('last_recovery'), u.get('is_stunned', 0), 
                     u.get('injury_recovery_time'))
                    for u in all_users 
                    if u.get('hp') is not None and u.get('stamina') is not None]
            
            logging.info(f"找到 {len(users)} 位用戶需要檢查回復狀態")
            
            if not users:
                logging.info("沒有找到可處理的用戶數據")
                return 0
            
            now = datetime.now()
            current_timestamp = int(now.timestamp())
            
            for user_id, hp, stamina, last_recovery_value, is_stunned, injury_recovery_time in users:
                try:
                    # 如果用戶處於傷病狀態，檢查體力恢復
                    if is_stunned == 1:
                        injury_time = self.parse_recovery_time(injury_recovery_time)
                        time_diff = now - injury_time
                        hours_passed = time_diff.total_seconds() / 3600
                        
                        logging.debug(f"用戶 {user_id} 傷病中: Stamina={stamina}, 經過時間={hours_passed:.2f}小時")
                        
                        if hours_passed >= 1.0:
                            # 體力恢復 (每小時 +25)
                            recovery_cycles = int(hours_passed)
                            stamina_recovery = recovery_cycles * 25
                            new_stamina = min(stamina + stamina_recovery, 100)
                            
                            # 檢查是否完全恢復
                            if new_stamina >= 100:
                                # 體力滿了，恢復原狀態
                                logging.info(f"用戶 {user_id} 體力完全恢復，恢復原始狀態")
                                set_user(user_id, {
                                    'hp': 100,
                                    'stamina': 100,
                                    'is_stunned': 0,
                                    'injury_recovery_time': None,
                                    'last_recovery': current_timestamp
                                })
                                
                                # 發送信號給醫院 cog 以移除身分組
                                await self.notify_recovery_complete(user_id)
                                recovered_count += 1
                            else:
                                # 還在恢復中
                                set_user(user_id, {
                                    'stamina': new_stamina,
                                    'injury_recovery_time': current_timestamp
                                })
                                
                                logging.info(f"用戶 {user_id} 體力恢復: {stamina}→{new_stamina} (週期: {recovery_cycles})")
                                recovered_count += 1
                        else:
                            logging.debug(f"用戶 {user_id} 傷病中，距離上次恢復僅過 {hours_passed:.2f} 小時")
                    else:
                        # 正常狀態下的血量回復邏輯
                        last_recovery = self.parse_recovery_time(last_recovery_value)
                        time_diff = now - last_recovery
                        hours_passed = time_diff.total_seconds() / 3600
                        
                        logging.debug(f"用戶 {user_id}: HP={hp}, Stamina={stamina}, 經過時間={hours_passed:.2f}小時")
                        
                        if hours_passed >= 1.0:
                            recovery_cycles = int(hours_passed)
                            hp_recovery = recovery_cycles * 1
                            stamina_recovery = recovery_cycles * 5
                            
                            new_hp = min(hp + hp_recovery, 100)
                            new_stamina = min(stamina + stamina_recovery, 100)
                            
                            # 檢查血量是否歸零 (只在本次回復檢查中)
                            if new_hp <= 0:
                                new_hp = 0
                                # 觸發擊暈狀態
                                logging.warning(f"用戶 {user_id} 血量歸零，進入傷病狀態")
                                set_user(user_id, {
                                    'hp': 0,
                                    'stamina': 0,
                                    'is_stunned': 1,
                                    'injury_recovery_time': current_timestamp,
                                    'last_recovery': current_timestamp
                                })
                                
                                # 發送信號移除會員身分組
                                await self.notify_injury_status(user_id)
                                recovered_count += 1
                            elif new_hp != hp or new_stamina != stamina:
                                set_user(user_id, {
                                    'hp': new_hp,
                                    'stamina': new_stamina,
                                    'last_recovery': current_timestamp
                                })
                                
                                recovered_count += 1
                                logging.info(f"用戶 {user_id} 回復成功: HP {hp}→{new_hp} (+{new_hp-hp}), Stamina {stamina}→{new_stamina} (+{new_stamina-stamina})")
                            else:
                                set_user_field(user_id, 'last_recovery', current_timestamp)
                                logging.debug(f"用戶 {user_id} 已滿血滿體力，僅更新回復時間")
                        else:
                            logging.debug(f"用戶 {user_id} 距離上次回復僅過 {hours_passed:.2f} 小時，不足1小時，跳過")
                
                except Exception as e:
                    logging.error(f"處理用戶 {user_id} 回復時發生錯誤: {e}")
                    logging.error(f"錯誤詳情: {traceback.format_exc()}")
                    continue
            
            logging.info(f"回復處理完成，成功更新 {recovered_count} 位用戶")
            return recovered_count
            
        except Exception as e:
            logging.error(f"處理用戶回復時發生未預期錯誤: {e}")
            return 0

    async def notify_injury_status(self, user_id: int):
        """通知系統用戶進入傷病狀態"""
        try:
            # 這會被 HospitalMerchant cog 監聽
            self.bot.dispatch('user_injured', user_id)
        except Exception as e:
            logging.error(f"通知傷病狀態失敗: {e}")

    async def notify_recovery_complete(self, user_id: int):
        """通知系統用戶完全恢復"""
        try:
            self.bot.dispatch('user_recovery_complete', user_id)
        except Exception as e:
            logging.error(f"通知恢復完成失敗: {e}")

    def get_user_stats(self, user_id: int):
        """獲取用戶狀態"""
        try:
            user = get_user(user_id)
            
            if user:
                hp = user.get('hp')
                stamina = user.get('stamina')
                last_recovery = user.get('last_recovery')
                is_stunned = user.get('is_stunned', 0)
                
                logging.debug(f"獲取用戶 {user_id} 狀態: HP={hp}, Stamina={stamina}, Stunned={is_stunned}")
                return {
                    'hp': hp,
                    'stamina': stamina,
                    'last_recovery': last_recovery,
                    'is_stunned': is_stunned
                }
            else:
                logging.warning(f"找不到用戶 {user_id} 的數據")
            return None
            
        except Exception as e:
            logging.error(f"獲取用戶 {user_id} 狀態時發生錯誤: {e}")
            return None

    def update_user_stats(self, user_id: int, hp=None, stamina=None):
        """更新用戶狀態"""
        try:
            user = get_user(user_id)
            if not user:
                logging.warning(f"用戶 {user_id} 不存在，無法更新狀態")
                return False
            
            current_timestamp = int(datetime.now().timestamp())
            update_data = {'last_recovery': current_timestamp}
            
            if hp is not None:
                update_data['hp'] = max(0, min(hp, 100))
            
            if stamina is not None:
                update_data['stamina'] = max(0, min(stamina, 100))
            
            # Batch update all fields at once
            set_user(user_id, update_data)
            
            logging.info(f"成功更新用戶 {user_id} 狀態")
            return True
            
        except Exception as e:
            logging.error(f"更新用戶 {user_id} 狀態時發生錯誤: {e}")
            return False





async def setup(bot):
    await bot.add_cog(UserRecoveryCog(bot))
    logging.info("UserRecoveryCog 已成功載入")
