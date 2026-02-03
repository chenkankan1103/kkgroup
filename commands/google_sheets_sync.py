import discord
from discord.ext import commands, tasks
from discord import app_commands
import gspread
from google.oauth2.service_account import Credentials
import sqlite3
import json
import asyncio
from datetime import datetime
import hashlib

class GoogleSheetsSync(commands.Cog):
    """Google Sheets 與 SQLite 資料庫雙向同步工具 (Slash 指令版本)"""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    SHEET_ID = "1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM"
    SHEET_NAME = "玩家資料"  # Google Sheet 的實際分頁名稱
    
    def __init__(self, bot):
        self.bot = bot
        self.gc = None
        self.sheet = None
        self.last_sheet_hash = None
        self._init_gspread()
        # 啟動自動同步
        if not self.auto_sync_loop.is_running():
            self.auto_sync_loop.start()
    
    def _init_gspread(self):
        """初始化 Google Sheets 連接"""
        try:
            creds = Credentials.from_service_account_file(
                'google_credentials.json',
                scopes=self.SCOPES
            )
            self.gc = gspread.authorize(creds)
            self.sheet = self.gc.open_by_key(self.SHEET_ID).worksheet(self.SHEET_NAME)
            print("✅ Google Sheets 連接成功")
        except Exception as e:
            print(f"❌ Google Sheets 連接失敗: {e}")
            self.gc = None
            self.sheet = None
    
    def _ensure_connection(self):
        """確保連接存活"""
        if not self.gc or not self.sheet:
            self._init_gspread()
    
    @tasks.loop(minutes=5)
    async def auto_sync_loop(self):
        """每 5 分鐘自動同步一次（資料庫 → Google Sheet，然後檢查 Sheet 更新）"""
        try:
            self._ensure_connection()
            if not self.sheet:
                return
            
            # 1. 先同步資料庫 → Google Sheet
            await self._export_to_sheet_internal()
            print(f"✅ [自動同步] 資料庫 → Google Sheet ({datetime.now().strftime('%H:%M:%S')})")
            
            # 2. 再檢查 Sheet 是否有更新（例如手動編輯）
            all_records = self.sheet.get_all_records()
            current_hash = hashlib.md5(str(all_records).encode()).hexdigest()
            
            # 如果 Sheet 資料有改變（例如手動編輯 KKCOIN 欄位），同步回資料庫
            if current_hash != self.last_sheet_hash:
                self.last_sheet_hash = current_hash
                await self._sync_from_sheet_internal()
                print(f"✅ [自動同步] Google Sheet → 資料庫（檢測到手動編輯）({datetime.now().strftime('%H:%M:%S')})")
            else:
                self.last_sheet_hash = current_hash
        
        except Exception as e:
            print(f"❌ 自動同步失敗: {e}")
    
    @auto_sync_loop.before_loop
    async def before_auto_sync_loop(self):
        """等待 bot 完全啟動"""
        await self.bot.wait_until_ready()
    
    async def _sync_from_sheet_internal(self):
        """內部同步方法：Google Sheet → 資料庫"""
        try:
            self._ensure_connection()
            
            if not self.sheet:
                return 0, 0, 0
            
            all_records = self.sheet.get_all_records()
            
            if not all_records:
                return 0, 0, 0
            
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            
            updated = 0
            inserted = 0
            errors = 0
            
            for row in all_records:
                try:
                    user_id = int(row.get('user_id', 0))
                    if user_id == 0:
                        continue
                    
                    level = int(row.get('level', 1))
                    xp = int(row.get('xp', 0))
                    kkcoin = int(row.get('kkcoin', 0))
                    title = row.get('title', '新手')
                    hp = int(row.get('hp', 100))
                    stamina = int(row.get('stamina', 100))
                    inventory = row.get('inventory', '[]')
                    character_config = row.get('character_config', '{}')
                    face = int(row.get('face', 20000))
                    hair = int(row.get('hair', 30000))
                    skin = int(row.get('skin', 12000))
                    top = int(row.get('top', 1040010))
                    bottom = int(row.get('bottom', 1060096))
                    shoes = int(row.get('shoes', 1072288))
                    streak = int(row.get('streak', 0))
                    last_work_date = row.get('last_work_date', None)
                    last_action_date = row.get('last_action_date', None)
                    actions_used = row.get('actions_used', '{}')
                    gender = row.get('gender', 'male')
                    is_stunned = 1 if row.get('is_stunned', 'FALSE').upper() == 'TRUE' else 0
                    is_locked = 1 if row.get('is_locked', 'FALSE').upper() == 'TRUE' else 0
                    last_recovery = row.get('last_recovery', None)
                    
                    # 建立字典，只包含要同步的欄位
                    user_data = {
                        'user_id': user_id,
                        'level': level,
                        'xp': xp,
                        'kkcoin': kkcoin,
                        'title': title,
                        'hp': hp,
                        'stamina': stamina,
                        'inventory': inventory,
                        'character_config': character_config,
                        'face': face,
                        'hair': hair,
                        'skin': skin,
                        'top': top,
                        'bottom': bottom,
                        'shoes': shoes,
                        'streak': streak,
                        'last_work_date': last_work_date,
                        'last_action_date': last_action_date,
                        'actions_used': actions_used,
                        'gender': gender,
                        'is_stunned': is_stunned,
                        'is_locked': is_locked,
                        'last_recovery': last_recovery
                    }
                    
                    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
                    exists = cursor.fetchone()
                    
                    if exists:
                        # UPDATE：只更新 Google Sheet 有的欄位
                        set_clause = ', '.join([f"{k}=?" for k in user_data.keys() if k != 'user_id'])
                        values = [v for k, v in user_data.items() if k != 'user_id']
                        values.append(user_id)
                        cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id=?", values)
                        updated += 1
                    else:
                        # INSERT：使用字典方式，缺少的欄位使用預設值
                        columns = ', '.join(user_data.keys())
                        placeholders = ', '.join(['?' for _ in user_data.keys()])
                        values = list(user_data.values())
                        cursor.execute(f"INSERT INTO users ({columns}) VALUES ({placeholders})", values)
                        inserted += 1
                
                except ValueError as e:
                    errors += 1
                    print(f"❌ 數值轉換錯誤 (user_id: {row.get('user_id')}): {e}")
                except Exception as e:
                    errors += 1
                    print(f"❌ 同步錯誤 (user_id: {row.get('user_id')}): {e}")
                    # 詳細日誌用於除錯
                    import traceback
                    traceback.print_exc()
            
            conn.commit()
            conn.close()
            return updated, inserted, errors
        
        except Exception as e:
            print(f"❌ 內部同步失敗: {e}")
            return 0, 0, 1
    
    async def _export_to_sheet_internal(self):
        """內部匯出方法：資料庫 → Google Sheet"""
        try:
            self._ensure_connection()
            
            if not self.sheet:
                return 0
            
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, level, xp, kkcoin, title, hp, stamina,
                inventory, character_config, face, hair, skin,
                top, bottom, shoes, streak, last_work_date,
                last_action_date, actions_used, gender, is_stunned,
                is_locked, last_recovery
                FROM users ORDER BY kkcoin DESC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return 0
            
            headers = [
                'user_id', 'nickname', 'level', 'xp', 'kkcoin', 'title', 'hp', 'stamina',
                'inventory', 'character_config', 'face', 'hair', 'skin',
                'top', 'bottom', 'shoes', 'streak', 'last_work_date',
                'last_action_date', 'actions_used', 'gender', 'is_stunned',
                'is_locked', 'last_recovery'
            ]
            
            data = [headers]
            for row in rows:
                user = self.bot.get_user(row[0])
                nickname = user.display_name if user else f"Unknown_{row[0]}"
                
                data.append([
                    str(row[0]), nickname, str(row[1]), str(row[2]), str(row[3]),
                    row[4], str(row[5]), str(row[6]), row[7], row[8],
                    str(row[9]), str(row[10]), str(row[11]), str(row[12]),
                    str(row[13]), str(row[14]), str(row[15]),
                    row[16] or '', row[17] or '', row[18], row[19],
                    'TRUE' if row[20] else 'FALSE', 'TRUE' if row[21] else 'FALSE',
                    row[22] or ''
                ])
            
            self.sheet.clear()
            self.sheet.append_rows(data, value_input_option='RAW')
            
            return len(rows)
        
        except Exception as e:
            print(f"❌ 匯出失敗: {e}")
            return 0
    
    # ============ SLASH 指令 ============
    
    @app_commands.command(name="sync_from_sheet", description="從 Google Sheet 同步資料到資料庫")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_from_sheet(self, interaction: discord.Interaction):
        """從 Google Sheet 同步資料到資料庫"""
        await interaction.response.defer()
        
        try:
            updated, inserted, errors = await self._sync_from_sheet_internal()
            
            await interaction.followup.send(f"✅ Google Sheet 同步完成\n"
                                          f"📊 更新: {updated} | 新增: {inserted} | 錯誤: {errors}\n"
                                          f"⏰ 同步時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        except Exception as e:
            await interaction.followup.send(f"❌ 同步失敗: {e}")
    
    @app_commands.command(name="export_to_sheet", description="將資料庫匯出到 Google Sheet")
    @app_commands.checks.has_permissions(administrator=True)
    async def export_to_sheet(self, interaction: discord.Interaction):
        """將資料庫匯出到 Google Sheet"""
        await interaction.response.defer()
        
        try:
            self._ensure_connection()
            
            if not self.sheet:
                await interaction.followup.send("❌ Google Sheets 連接失敗")
                return
            
            count = await self._export_to_sheet_internal()
            
            if count == 0:
                await interaction.followup.send("❌ 資料庫中沒有資料或匯出失敗")
                return
            
            await interaction.followup.send(f"✅ 匯出完成\n"
                                          f"📊 共匯出 {count} 筆玩家資料\n"
                                          f"⏰ 匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        except Exception as e:
            await interaction.followup.send(f"❌ 匯出失敗: {e}")
    
    @app_commands.command(name="list_members", description="列出所有伺服器成員的 Discord ID 與暱稱")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_members(self, interaction: discord.Interaction):
        """列出所有伺服器成員的 Discord ID 與暱稱"""
        await interaction.response.defer()
        
        try:
            members = interaction.guild.members
            lines = [f"{m.id},{m.display_name}" for m in members]
            
            if not lines:
                await interaction.followup.send("❌ 伺服器中沒有成員")
                return
            
            chunk_size = 50
            for i in range(0, len(lines), chunk_size):
                content = "\n".join(lines[i:i+chunk_size])
                await interaction.followup.send(f"```\nuser_id,display_name\n{content}\n```")
            
            await interaction.followup.send(f"✅ 共列出 {len(lines)} 位成員")
        except Exception as e:
            await interaction.followup.send(f"❌ 列出成員失敗: {e}")
    
    @app_commands.command(name="sync_status", description="查看同步狀態")
    async def sync_status(self, interaction: discord.Interaction):
        """查看目前的同步狀態"""
        await interaction.response.defer()
        
        try:
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            db_count = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(kkcoin) FROM users")
            total_kkcoin = cursor.fetchone()[0] or 0
            conn.close()
            
            sheet_records = self.sheet.get_all_records() if self.sheet else []
            
            await interaction.followup.send(
                f"📊 **同步狀態**\n"
                f"🗄️ 資料庫玩家數: {db_count}\n"
                f"💰 資料庫總 KKCOIN: {total_kkcoin}\n"
                f"📑 Google Sheet 記錄數: {len(sheet_records)}\n"
                f"🔄 自動同步: 每 5 分鐘一次\n"
                f"⏰ 最後更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ 查詢失敗: {e}")

async def setup(bot):
    """載入此 Cog"""
    await bot.add_cog(GoogleSheetsSync(bot))
