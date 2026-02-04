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
        self._initialized = False
        # ⚠️ 不在 __init__ 中進行同步操作，改用 before_loop
        if not self.auto_sync_loop.is_running():
            self.auto_sync_loop.start()
    
    def _init_gspread(self):
        """初始化 Google Sheets 連接（同步版本，用於非異步上下文）"""
        if self._initialized:
            return
        try:
            creds = Credentials.from_service_account_file(
                'google_credentials.json',
                scopes=self.SCOPES
            )
            self.gc = gspread.authorize(creds)
            self.sheet = self.gc.open_by_key(self.SHEET_ID).worksheet(self.SHEET_NAME)
            self._initialized = True
            print("✅ Google Sheets 連接成功")
        except Exception as e:
            print(f"❌ Google Sheets 連接失敗: {e}")
            self.gc = None
            self.sheet = None
            self._initialized = False
    
    def _ensure_connection(self):
        """確保連接存活（同步版本）"""
        if not self.gc or not self.sheet:
            self._init_gspread()
    
    @tasks.loop(minutes=5)
    async def auto_sync_loop(self):
        """每 5 分鐘自動同步一次（先檢查 Sheet 更新，再匯出資料庫）"""
        try:
            # 使用 loop executor 以避免阻塞事件迴圈
            loop = asyncio.get_event_loop()
            
            # 確保連接
            await loop.run_in_executor(None, self._ensure_connection)
            
            if not self.sheet:
                return
            
            # 1. 先讀取 Sheet 當前狀態，檢查是否有手動編輯（重要：要在匯出前做）
            all_records = await loop.run_in_executor(None, self.sheet.get_all_records)
            current_hash = hashlib.md5(str(all_records).encode()).hexdigest()
            
            # 如果 Sheet 資料有改變（例如手動編輯 KKCOIN 欄位），同步回資料庫
            if current_hash != self.last_sheet_hash:
                self.last_sheet_hash = current_hash
                await self._sync_from_sheet_internal()
                print(f"✅ [自動同步] Google Sheet → 資料庫（檢測到手動編輯）({datetime.now().strftime('%H:%M:%S')})")
            
            # 2. 最後才匯出資料庫 → Google Sheet（這樣才不會造成 hash 循環）
            await self._export_to_sheet_internal()
            
            # 3. 匯出後更新 hash，確保下次比對時是基於匯出後的狀態
            all_records_after = await loop.run_in_executor(None, self.sheet.get_all_records)
            self.last_sheet_hash = hashlib.md5(str(all_records_after).encode()).hexdigest()
            
            print(f"✅ [自動同步] 資料庫 → Google Sheet ({datetime.now().strftime('%H:%M:%S')})")
        
        except Exception as e:
            print(f"❌ 自動同步失敗: {e}")
    
    @auto_sync_loop.before_loop
    async def before_auto_sync_loop(self):
        """等待 bot 完全啟動，然後初始化 Google Sheets 連接"""
        await self.bot.wait_until_ready()
        # 在異步上下文中初始化（使用 executor 以避免阻塞）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._init_gspread)
    
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
                    # 清理欄位值：移除前導單引號、空格、並轉換為正確的數據類型
                    def clean_value(val):
                        if isinstance(val, str):
                            val = val.strip().lstrip("'").strip()  # 移除前導單引號和空格
                        return val
                    
                    def to_int(val):
                        """安全地轉換為整數"""
                        val = clean_value(val)
                        if isinstance(val, int):
                            return val
                        if isinstance(val, float):
                            return int(val)
                        try:
                            return int(float(val))  # 先轉 float 再轉 int，避免 "100.0" 轉換失敗
                        except (ValueError, TypeError):
                            return 0
                    
                    user_id = to_int(row.get('user_id', 0))
                    if user_id == 0:
                        continue
                    
                    level = to_int(row.get('level', 1))
                    xp = to_int(row.get('xp', 0))
                    kkcoin = to_int(row.get('kkcoin', 0))
                    title = clean_value(row.get('title', '新手'))
                    hp = to_int(row.get('hp', 100))
                    stamina = to_int(row.get('stamina', 100))
                    inventory = clean_value(row.get('inventory', '[]'))
                    character_config = clean_value(row.get('character_config', '{}'))
                    face = to_int(row.get('face', 20000))
                    hair = to_int(row.get('hair', 30000))
                    skin = to_int(row.get('skin', 12000))
                    top = to_int(row.get('top', 1040010))
                    bottom = to_int(row.get('bottom', 1060096))
                    shoes = to_int(row.get('shoes', 1072288))
                    streak = to_int(row.get('streak', 0))
                    last_work_date = clean_value(row.get('last_work_date', None))
                    last_action_date = clean_value(row.get('last_action_date', None))
                    actions_used = clean_value(row.get('actions_used', '{}'))
                    gender = clean_value(row.get('gender', 'male'))
                    is_stunned = 1 if clean_value(row.get('is_stunned', 'FALSE')).upper() == 'TRUE' else 0
                    is_locked = 1 if clean_value(row.get('is_locked', 'FALSE')).upper() == 'TRUE' else 0
                    last_recovery = clean_value(row.get('last_recovery', None))
                    
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
            loop = asyncio.get_event_loop()
            
            # 在 executor 中執行同步操作以避免阻塞事件迴圈
            def do_export():
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
                    
                    # 直接寫數字，不要轉成字符串，讓 Google Sheets 自動判斷格式
                    data.append([
                        int(row[0]), nickname, int(row[1]), int(row[2]), int(row[3]),
                        row[4], int(row[5]), int(row[6]), row[7], row[8],
                        int(row[9]), int(row[10]), int(row[11]), int(row[12]),
                        int(row[13]), int(row[14]), int(row[15]),
                        row[16] or '', row[17] or '', row[18], row[19],
                        'TRUE' if row[20] else 'FALSE', 'TRUE' if row[21] else 'FALSE',
                        row[22] or ''
                    ])
                
                self.sheet.clear()
                # 使用 USER_ENTERED 讓 Google Sheets 自動判斷數據類型（數字、文本等）
                self.sheet.append_rows(data, value_input_option='USER_ENTERED')
                
                return len(rows)
            
            # 在 executor 中執行
            return await loop.run_in_executor(None, do_export)
        
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
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ensure_connection)
            
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
