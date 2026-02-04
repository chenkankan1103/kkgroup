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
        if not self.auto_export_loop.is_running():
            self.auto_export_loop.start()
    
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
            spreadsheet = self.gc.open_by_key(self.SHEET_ID)
            print(f"📑 打開試算表，工作表清單: {[ws.title for ws in spreadsheet.worksheets()]}")
            
            self.sheet = spreadsheet.worksheet(self.SHEET_NAME)
            
            # 驗證連接
            all_rows = self.sheet.get_all_records()
            all_values = self.sheet.get_all_values()
            print(f"✅ Google Sheets 連接成功")
            print(f"   - 工作表名稱: {self.SHEET_NAME}")
            print(f"   - 行數: {len(all_values)}, 列數: {len(all_values[0]) if all_values else 0}")
            print(f"   - get_all_records() 返回: {len(all_rows)} 筆記錄")
            
            self._initialized = True
        except Exception as e:
            print(f"❌ Google Sheets 連接失敗: {e}")
            import traceback
            traceback.print_exc()
            self.gc = None
            self.sheet = None
            self._initialized = False
    
    def _ensure_connection(self):
        """確保連接存活（同步版本）"""
        if not self.gc or not self.sheet:
            self._init_gspread()
    
    @tasks.loop(minutes=1)
    async def auto_sync_loop(self):
        """每 1 分鐘檢查 SHEET 是否有手動編輯，若有則同步到資料庫"""
        try:
            # 使用 loop executor 以避免阻塞事件迴圈
            loop = asyncio.get_event_loop()
            
            # 確保連接
            await loop.run_in_executor(None, self._ensure_connection)
            
            if not self.sheet:
                return
            
            # 檢查 Sheet 是否有更新（例如手動編輯）
            all_records = await loop.run_in_executor(None, self.sheet.get_all_records)
            
            # 只計算關鍵欄位的 hash（user_id 和 kkcoin），不計算整個記錄
            # 這樣可以避免因為格式或空值的微小變化導致 hash 不同
            key_data = []
            for record in all_records:
                # 只提取重要欄位來判斷是否有編輯
                key_data.append({
                    'user_id': record.get('user_id', ''),
                    'kkcoin': record.get('kkcoin', ''),
                    'level': record.get('level', ''),
                    'xp': record.get('xp', ''),
                    'title': record.get('title', ''),
                    'hp': record.get('hp', ''),
                    'stamina': record.get('stamina', ''),
                })
            
            current_hash = hashlib.md5(str(key_data).encode()).hexdigest()
            
            # 如果 Sheet 資料有改變（例如手動編輯 KKCOIN 欄位），同步回資料庫
            if current_hash != self.last_sheet_hash:
                self.last_sheet_hash = current_hash
                print(f"🔍 [1分鐘檢查] 檢測到 SHEET 內容變化，準備同步...")
                updated, inserted, errors = await self._sync_from_sheet_internal()
                print(f"✅ [1分鐘同步] Google Sheet → 資料庫 (更新: {updated}, 新增: {inserted}, 錯誤: {errors}) ({datetime.now().strftime('%H:%M:%S')})")
            else:
                # Debug: 顯示一下目前的 hash 狀態
                print(f"⏸️ [1分鐘檢查] SHEET 內容未變化，無需同步 ({datetime.now().strftime('%H:%M:%S')})")
        
        except Exception as e:
            print(f"❌ 同步失敗: {e}")
            import traceback
            traceback.print_exc()
    
    @tasks.loop(minutes=5)
    async def auto_export_loop(self):
        """每 5 分鐘將資料庫匯出到 SHEET（供管理員查閱）"""
        try:
            loop = asyncio.get_event_loop()
            
            # 確保連接
            await loop.run_in_executor(None, self._ensure_connection)
            
            if not self.sheet:
                return
            
            # 匯出資料庫 → Google Sheet
            await self._export_to_sheet_internal()
            
            # 匯出後更新 hash，確保下次檢查時不會誤以為有編輯
            all_records_after = await loop.run_in_executor(None, self.sheet.get_all_records)
            self.last_sheet_hash = hashlib.md5(str(all_records_after).encode()).hexdigest()
            
            print(f"✅ [5分鐘更新] 資料庫 → Google Sheet ({datetime.now().strftime('%H:%M:%S')})")
        
        except Exception as e:
            print(f"❌ 匯出失敗: {e}")
    
    @auto_sync_loop.before_loop
    async def before_auto_sync_loop(self):
        """等待 bot 完全啟動，然後初始化 Google Sheets 連接"""
        await self.bot.wait_until_ready()
        # 在異步上下文中初始化（使用 executor 以避免阻塞）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._init_gspread)
    
    @auto_export_loop.before_loop
    async def before_auto_export_loop(self):
        """等待 bot 完全啟動"""
        await self.bot.wait_until_ready()
    
    def cog_unload(self):
        """卸載 Cog 時停止所有任務"""
        if self.auto_sync_loop.is_running():
            self.auto_sync_loop.cancel()
        if self.auto_export_loop.is_running():
            self.auto_export_loop.cancel()
    
    async def _sync_from_sheet_internal(self):
        """內部同步方法：Google Sheet → 資料庫"""
        try:
            self._ensure_connection()
            
            if not self.sheet:
                print("❌ SHEET 連接失敗")
                return 0, 0, 0
            
            # 用 get_all_values 讀取原始數據
            all_values = self.sheet.get_all_values()
            
            if not all_values or len(all_values) < 3:
                print(f"❌ SHEET 數據不足 (行數: {len(all_values)})")
                return 0, 0, 0
            
            # 第 1 行是分組標題，第 2 行是真實的欄位名稱
            headers = all_values[1]  # 使用第 2 行作為標題
            print(f"📊 同步前診斷: 行數={len(all_values)}, 列數={len(headers)}")
            print(f"📋 標題行（第2行）: {headers}")  # 打印完整標題行
            
            # Debug：也打印第 1 和 3 行看看內容
            print(f"🔍 第1行（分組標題）: {all_values[0][:5]}...")
            print(f"🔍 第3行（第一筆數據）: {all_values[2][:5]}...")
            
            # 將數據行轉換為字典列表（從第 3 行開始）
            all_records = []
            for row_idx, row_values in enumerate(all_values[2:], start=3):
                record = {}
                for col_idx, header in enumerate(headers):
                    if col_idx < len(row_values):
                        record[header] = row_values[col_idx]
                    else:
                        record[header] = ''
                all_records.append(record)
            
            if not all_records:
                print(f"❌ 沒有數據記錄")
                return 0, 0, 0
            
            print(f"📖 SHEET 中共有 {len(all_records)} 筆記錄，開始同步...")
            
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            
            updated = 0
            inserted = 0
            errors = 0
            skipped = 0  # 新增：追蹤被跳過的記錄
            
            for idx, row in enumerate(all_records):
                try:
                    # 清理欄位值：移除前導單引號、空格、並轉換為正確的數據類型
                    def clean_value(val):
                        if isinstance(val, str):
                            val = val.strip().lstrip("'").strip()  # 移除前導單引號和空格
                        return val
                    
                    def to_int(val):
                        """安全地轉換為整數，支持科學記數法和各種格式"""
                        val = clean_value(val)
                        
                        # 處理空值
                        if val == '' or val is None:
                            return 0
                        
                        # 如果已經是 int 直接返回
                        if isinstance(val, int):
                            return val
                        
                        # 如果是 float，直接轉 int
                        if isinstance(val, float):
                            return int(val)
                        
                        # 字符串處理
                        if isinstance(val, str):
                            # 移除可能的空格
                            val = val.strip()
                            if val == '':
                                return 0
                            
                            try:
                                # 嘗試直接轉換（包括科學記號如 "1E+17"）
                                return int(val)
                            except ValueError:
                                try:
                                    # 嘗試先轉 float 再轉 int（處理 "100.0" 和科學記號 "1E+17"）
                                    float_val = float(val)
                                    return int(float_val)
                                except ValueError:
                                    # 試著找出科學記號的模式
                                    if 'e' in val.lower():
                                        try:
                                            return int(float(val))
                                        except:
                                            pass
                                    # 如果全失敗，返回 0
                                    return 0
                        
                        return 0
                    
                    user_id = to_int(row.get('user_id', 0))
                    if user_id == 0:
                        # Debug: 顯示哪些行被跳過
                        raw_user_id = row.get('user_id', 'MISSING')
                        print(f"⏭️ 行 {idx+3} 被跳過：user_id 無效 (raw: '{raw_user_id}'，轉換後: {user_id})")
                    
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
                    
                    # Debug: 打印讀取的資料（只在第一次執行時打印）
                    if updated == 0 and inserted == 0:
                        print(f"📝 [Debug] 讀取 SHEET 資料範例 - user_id: {user_id}, kkcoin: {kkcoin}, level: {level}")
                    
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
            
            # 打印最終統計
            print(f"📊 同步統計: 更新={updated}, 新增={inserted}, 錯誤={errors}, 跳過={skipped}")
            
            return updated, inserted, errors
        
        except Exception as e:
            print(f"❌ 內部同步失敗: {e}")
            import traceback
            traceback.print_exc()
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
                f"🔄 同步策略:\n"
                f"   📥 SHEET → 資料庫: 每 1 分鐘\n"
                f"   📤 資料庫 → SHEET: 每 5 分鐘\n"
                f"⏰ 最後更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ 查詢失敗: {e}")

async def setup(bot):
    """載入此 Cog"""
    await bot.add_cog(GoogleSheetsSync(bot))
