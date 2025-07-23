import sqlite3
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import logging
import traceback

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
                logging.info(f"自動回復完成，{recovered_users} 位用戶獲得回復")
            else:
                logging.info("自動回復完成，沒有用戶需要回復")
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
            # 檢查 users 表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                logging.error("users 表不存在！請先創建用戶資料表")
                return False
            
            # 檢查資料表欄位
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            logging.debug(f"資料表現有欄位: {columns}")
            
            # 如果沒有 last_recovery 欄位，則添加它
            if 'last_recovery' not in columns:
                logging.info("添加 last_recovery 欄位...")
                cursor.execute('ALTER TABLE users ADD COLUMN last_recovery TIMESTAMP')
                # 為現有用戶設置初始時間
                cursor.execute('UPDATE users SET last_recovery = ? WHERE last_recovery IS NULL', 
                             (datetime.now().isoformat(),))
                logging.info("last_recovery 欄位已添加並初始化")
            
            return True
        except Exception as e:
            logging.error(f"確保資料庫結構時發生錯誤: {e}")
            return False
    
    async def process_all_users_recovery(self):
        """處理所有用戶的自動回復"""
        conn = None
        recovered_count = 0
        
        try:
            logging.debug(f"連接資料庫: {self.db_path}")
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 確保資料庫結構正確
            if not self.ensure_database_structure(cursor):
                return 0
            
            # 獲取所有用戶數據
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            logging.info(f"資料庫中共有 {total_users} 位用戶")
            
            if total_users == 0:
                logging.info("資料庫中沒有用戶數據")
                return 0
            
            # 獲取所有需要回復的用戶
            cursor.execute('''
                SELECT user_id, hp, stamina, last_recovery 
                FROM users 
                WHERE hp IS NOT NULL AND stamina IS NOT NULL
            ''')
            
            users = cursor.fetchall()
            logging.info(f"找到 {len(users)} 位用戶需要檢查回復狀態")
            
            if not users:
                logging.info("沒有找到可處理的用戶數據")
                return 0
            
            now = datetime.now()
            
            for user_id, hp, stamina, last_recovery_str in users:
                try:
                    # 處理 last_recovery 時間
                    if last_recovery_str is None:
                        # 如果沒有 last_recovery，設置為當前時間
                        last_recovery = now - timedelta(hours=1)  # 假設1小時前
                        logging.debug(f"用戶 {user_id} 沒有 last_recovery，設置為1小時前")
                    else:
                        # 處理時間格式
                        if isinstance(last_recovery_str, str):
                            # 移除 Z 並處理 ISO 格式
                            clean_time = last_recovery_str.replace('Z', '')
                            if '+' not in clean_time and '-' not in clean_time[-6:]:
                                last_recovery = datetime.fromisoformat(clean_time)
                            else:
                                last_recovery = datetime.fromisoformat(last_recovery_str.replace('Z', '+00:00'))
                        else:
                            last_recovery = datetime.fromisoformat(str(last_recovery_str))
                    
                    # 計算經過的小時數
                    time_diff = now - last_recovery
                    hours_passed = time_diff.total_seconds() / 3600
                    
                    logging.debug(f"用戶 {user_id}: HP={hp}, Stamina={stamina}, 經過時間={hours_passed:.2f}小時")
                    
                    if hours_passed >= 1:
                        # 計算回復量
                        recovery_cycles = int(hours_passed)
                        new_hp = min(hp + recovery_cycles * 1, 100)  # 每小時回復1血
                        new_stamina = min(stamina + recovery_cycles * 5, 100)  # 每小時回復5體力
                        
                        # 只有數值有變化時才更新
                        if new_hp != hp or new_stamina != stamina:
                            cursor.execute('''
                                UPDATE users 
                                SET hp = ?, stamina = ?, last_recovery = ?
                                WHERE user_id = ?
                            ''', (new_hp, new_stamina, now.isoformat(), user_id))
                            
                            recovered_count += 1
                            
                            logging.info(f"用戶 {user_id} 回復成功: HP {hp}→{new_hp}, Stamina {stamina}→{new_stamina} ({recovery_cycles}小時)")
                        else:
                            logging.debug(f"用戶 {user_id} 已滿血滿體力，跳過回復")
                    else:
                        logging.debug(f"用戶 {user_id} 距離上次回復不足1小時，跳過")
                
                except Exception as e:
                    logging.error(f"處理用戶 {user_id} 回復時發生錯誤: {e}")
                    logging.error(f"錯誤詳情: {traceback.format_exc()}")
                    continue
            
            conn.commit()
            logging.info(f"回復處理完成，成功回復 {recovered_count} 位用戶")
            return recovered_count
            
        except sqlite3.Error as e:
            logging.error(f"資料庫操作錯誤: {e}")
            logging.error(f"錯誤詳情: {traceback.format_exc()}")
            return 0
        except Exception as e:
            logging.error(f"處理用戶回復時發生未預期錯誤: {e}")
            logging.error(f"錯誤詳情: {traceback.format_exc()}")
            return 0
        finally:
            if conn:
                conn.close()
                logging.debug("資料庫連接已關閉")
    
    def get_user_stats(self, user_id):
        """獲取用戶狀態（可被其他 cog 調用）"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT hp, stamina, last_recovery FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result:
                hp, stamina, last_recovery = result
                logging.debug(f"獲取用戶 {user_id} 狀態: HP={hp}, Stamina={stamina}")
                return {
                    'hp': hp,
                    'stamina': stamina,
                    'last_recovery': last_recovery
                }
            else:
                logging.warning(f"找不到用戶 {user_id} 的數據")
            return None
            
        except sqlite3.Error as e:
            logging.error(f"獲取用戶 {user_id} 狀態時發生資料庫錯誤: {e}")
            return None
        except Exception as e:
            logging.error(f"獲取用戶 {user_id} 狀態時發生錯誤: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def update_user_stats(self, user_id, hp=None, stamina=None):
        """更新用戶狀態（可被其他 cog 調用）"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 先檢查用戶是否存在
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if not cursor.fetchone():
                logging.warning(f"用戶 {user_id} 不存在，無法更新狀態")
                return False
            
            updates = []
            params = []
            
            if hp is not None:
                updates.append("hp = ?")
                params.append(max(0, min(hp, 100)))  # 限制在 0-100 之間
            
            if stamina is not None:
                updates.append("stamina = ?")
                params.append(max(0, min(stamina, 100)))  # 限制在 0-100 之間
            
            if updates:
                # 同時更新 last_recovery 時間
                updates.append("last_recovery = ?")
                params.append(datetime.now().isoformat())
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
        except Exception as e:
            logging.error(f"更新用戶 {user_id} 狀態時發生錯誤: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def force_recovery_for_user(self, user_id):
        """強制為特定用戶執行回復檢查"""
        conn = None
        try:
            logging.info(f"開始強制回復用戶 {user_id}")
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT hp, stamina, last_recovery FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                logging.warning(f"找不到用戶 {user_id}")
                return None
            
            hp, stamina, last_recovery_str = result
            logging.debug(f"用戶 {user_id} 當前狀態: HP={hp}, Stamina={stamina}, last_recovery={last_recovery_str}")
            
            if last_recovery_str:
                try:
                    # 處理時間格式
                    clean_time = last_recovery_str.replace('Z', '')
                    if '+' not in clean_time and '-' not in clean_time[-6:]:
                        last_recovery = datetime.fromisoformat(clean_time)
                    else:
                        last_recovery = datetime.fromisoformat(last_recovery_str.replace('Z', '+00:00'))
                    
                    now = datetime.now()
                    hours_passed = (now - last_recovery).total_seconds() / 3600
                    
                    logging.debug(f"用戶 {user_id} 距離上次回復已過 {hours_passed:.2f} 小時")
                    
                    if hours_passed >= 1:
                        recovery_cycles = int(hours_passed)
                        new_hp = min(hp + recovery_cycles * 1, 100)
                        new_stamina = min(stamina + recovery_cycles * 5, 100)
                        
                        cursor.execute('''
                            UPDATE users 
                            SET hp = ?, stamina = ?, last_recovery = ?
                            WHERE user_id = ?
                        ''', (new_hp, new_stamina, now.isoformat(), user_id))
                        
                        conn.commit()
                        
                        logging.info(f"用戶 {user_id} 強制回復成功: HP {hp}→{new_hp}, Stamina {stamina}→{new_stamina}")
                        
                        return {
                            'old_hp': hp,
                            'new_hp': new_hp,
                            'old_stamina': stamina,
                            'new_stamina': new_stamina,
                            'hours_passed': recovery_cycles,
                            'recovered': True
                        }
                except Exception as time_error:
                    logging.error(f"處理時間格式時發生錯誤: {time_error}")
            
            return {
                'hp': hp,
                'stamina': stamina,
                'recovered': False
            }
            
        except Exception as e:
            logging.error(f"強制回復用戶 {user_id} 時發生錯誤: {e}")
            logging.error(f"錯誤詳情: {traceback.format_exc()}")
            return None
        finally:
            if conn:
                conn.close()
    
    async def get_recovery_status(self):
        """獲取回復系統狀態"""
        return {
            'is_running': self.recovery_loop.is_running(),
            'next_iteration': self.recovery_loop.next_iteration,
            'current_loop_count': self.recovery_loop.current_loop
        }
    
    # 添加調試命令
    @commands.command(name="debug_recovery")
    @commands.is_owner()
    async def debug_recovery(self, ctx):
        """調試回復系統（僅限機器人擁有者）"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 檢查資料庫狀態
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE hp IS NOT NULL AND stamina IS NOT NULL")
            valid_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE last_recovery IS NOT NULL")
            users_with_recovery = cursor.fetchone()[0]
            
            status = await self.get_recovery_status()
            
            embed = discord.Embed(title="回復系統調試信息", color=0x00ff00)
            embed.add_field(name="資料庫狀態", 
                          value=f"總用戶數: {total_users}\n有效用戶數: {valid_users}\n有回復記錄用戶數: {users_with_recovery}", 
                          inline=False)
            embed.add_field(name="循環狀態", 
                          value=f"運行中: {status['is_running']}\n循環次數: {status['current_loop_count']}", 
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
        """手動觸發回復處理（僅限機器人擁有者）"""
        await ctx.send("開始手動回復處理...")
        recovered = await self.process_all_users_recovery()
        await ctx.send(f"手動回復完成，{recovered} 位用戶獲得回復")

# 設置 Cog
async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(UserRecoveryCog(bot))
    logging.info("UserRecoveryCog 已成功載入")

# 卸載 Cog  
async def teardown(bot):
    """卸載 Cog"""
    logging.info("UserRecoveryCog 已卸載")