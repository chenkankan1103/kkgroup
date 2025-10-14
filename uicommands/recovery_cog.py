import sqlite3
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import logging
import traceback
import discord
import aiohttp
import json

class UserRecoveryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "user_data.db"
        self.recovery_loop.start()

    def cog_unload(self):
        """Cog 卸載時停止循環任務"""
        self.recovery_loop.cancel()

    @tasks.loop(hours=1)
    async def recovery_loop(self):
        """每小時執行一次自動回復"""
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

    def ensure_database_structure(self, cursor):
        """確保資料庫結構正確"""
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                logging.error("users 表不存在！請先創建用戶資料表")
                return False
            
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            logging.debug(f"資料表現有欄位: {columns}")
            
            if 'last_recovery' not in columns:
                logging.info("添加 last_recovery 欄位...")
                cursor.execute('ALTER TABLE users ADD COLUMN last_recovery TEXT')
                initial_time = int(datetime.now().timestamp())
                cursor.execute('UPDATE users SET last_recovery = ? WHERE last_recovery IS NULL', 
                             (initial_time,))
                logging.info("last_recovery 欄位已添加並初始化")
            
            if 'injury_recovery_time' not in columns:
                logging.info("添加 injury_recovery_time 欄位...")
                cursor.execute('ALTER TABLE users ADD COLUMN injury_recovery_time TEXT')
                logging.info("injury_recovery_time 欄位已添加")
            
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
        conn = None
        recovered_count = 0
        
        try:
            logging.debug(f"連接資料庫: {self.db_path}")
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if not self.ensure_database_structure(cursor):
                return 0
            
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            logging.info(f"資料庫中共有 {total_users} 位用戶")
            
            if total_users == 0:
                logging.info("資料庫中沒有用戶數據")
                return 0
            
            cursor.execute('''
                SELECT user_id, hp, stamina, last_recovery, is_stunned, injury_recovery_time
                FROM users 
                WHERE hp IS NOT NULL AND stamina IS NOT NULL
            ''')
            
            users = cursor.fetchall()
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
                                cursor.execute('''
                                    UPDATE users 
                                    SET hp = 100, stamina = 100, is_stunned = 0, injury_recovery_time = NULL, last_recovery = ?
                                    WHERE user_id = ?
                                ''', (current_timestamp, user_id))
                                
                                # 發送信號給醫院 cog 以移除身分組
                                await self.notify_recovery_complete(user_id)
                                recovered_count += 1
                            else:
                                # 還在恢復中
                                cursor.execute('''
                                    UPDATE users 
                                    SET stamina = ?, injury_recovery_time = ?
                                    WHERE user_id = ?
                                ''', (new_stamina, current_timestamp, user_id))
                                
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
                                cursor.execute('''
                                    UPDATE users 
                                    SET hp = 0, stamina = 0, is_stunned = 1, injury_recovery_time = ?, last_recovery = ?
                                    WHERE user_id = ?
                                ''', (current_timestamp, current_timestamp, user_id))
                                
                                # 發送信號移除會員身分組
                                await self.notify_injury_status(user_id)
                                recovered_count += 1
                            elif new_hp != hp or new_stamina != stamina:
                                cursor.execute('''
                                    UPDATE users 
                                    SET hp = ?, stamina = ?, last_recovery = ?
                                    WHERE user_id = ?
                                ''', (new_hp, new_stamina, current_timestamp, user_id))
                                
                                recovered_count += 1
                                logging.info(f"用戶 {user_id} 回復成功: HP {hp}→{new_hp} (+{new_hp-hp}), Stamina {stamina}→{new_stamina} (+{new_stamina-stamina})")
                            else:
                                cursor.execute('''
                                    UPDATE users 
                                    SET last_recovery = ?
                                    WHERE user_id = ?
                                ''', (current_timestamp, user_id))
                                logging.debug(f"用戶 {user_id} 已滿血滿體力，僅更新回復時間")
                        else:
                            logging.debug(f"用戶 {user_id} 距離上次回復僅過 {hours_passed:.2f} 小時，不足1小時，跳過")
                
                except Exception as e:
                    logging.error(f"處理用戶 {user_id} 回復時發生錯誤: {e}")
                    logging.error(f"錯誤詳情: {traceback.format_exc()}")
                    continue
            
            conn.commit()
            logging.info(f"回復處理完成，成功更新 {recovered_count} 位用戶")
            return recovered_count
            
        except sqlite3.Error as e:
            logging.error(f"資料庫操作錯誤: {e}")
            return 0
        except Exception as e:
            logging.error(f"處理用戶回復時發生未預期錯誤: {e}")
            return 0
        finally:
            if conn:
                conn.close()
                logging.debug("資料庫連接已關閉")

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
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT hp, stamina, last_recovery, is_stunned FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result:
                hp, stamina, last_recovery, is_stunned = result
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
            
        except sqlite3.Error as e:
            logging.error(f"獲取用戶 {user_id} 狀態時發生資料庫錯誤: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_user_stats(self, user_id: int, hp=None, stamina=None):
        """更新用戶狀態"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if not cursor.fetchone():
                logging.warning(f"用戶 {user_id} 不存在，無法更新狀態")
                return False
            
            updates = []
            params = []
            
            if hp is not None:
                updates.append("hp = ?")
                params.append(max(0, min(hp, 100)))
            
            if stamina is not None:
                updates.append("stamina = ?")
                params.append(max(0, min(stamina, 100)))
            
            if updates:
                updates.append("last_recovery = ?")
                params.append(int(datetime.now().timestamp()))
                params.append(user_id)
                
                query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
                cursor.execute(query, params)
                conn.commit()
                
                logging.info(f"成功更新用戶 {user_id} 狀態")
                return True
            
            logging.warning(f"沒有提供要更新的數據給用戶 {user_id}")
            return False
            
        except sqlite3.Error as e:
            logging.error(f"更新用戶 {user_id} 狀態時發生資料庫錯誤: {e}")
            return False
        finally:
            if conn:
                conn.close()

    @commands.command(name="debug_recovery")
    @commands.is_owner()
    async def debug_recovery(self, ctx):
        """調試回復系統（僅限機器人擁有者）"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_stunned = 0")
            normal_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_stunned = 1")
            injured_users = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT user_id, hp, stamina, is_stunned 
                FROM users 
                LIMIT 5
            ''')
            sample_users = cursor.fetchall()
            
            status = self.recovery_loop.is_running()
            
            embed = discord.Embed(title="回復系統調試信息", color=0x00ff00)
            embed.add_field(name="資料庫狀態", 
                          value=f"總用戶數: {total_users}\n正常用戶: {normal_users}\n傷病用戶: {injured_users}", 
                          inline=False)
            embed.add_field(name="循環狀態", 
                          value=f"運行中: {status}", 
                          inline=False)
            
            if sample_users:
                sample_info = []
                for user_id, hp, stamina, is_stunned in sample_users:
                    state = "傷病中" if is_stunned == 1 else "正常"
                    sample_info.append(f"用戶{user_id}: HP{hp} 體力{stamina} [{state}]")
                
                embed.add_field(name="用戶樣本 (前5位)", 
                              value="\n".join(sample_info), 
                              inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"調試時發生錯誤: {e}")
        finally:
            if conn:
                conn.close()

    @commands.command(name="force_recovery")
    @commands.is_owner()
    async def manual_recovery(self, ctx):
        """手動觸發回復處理"""
        await ctx.send("開始手動回復處理...")
        recovered = await self.process_all_users_recovery()
        await ctx.send(f"手動回復完成，{recovered} 位用戶狀態更新")

async def setup(bot):
    await bot.add_cog(UserRecoveryCog(bot))
    logging.info("UserRecoveryCog 已成功載入")
