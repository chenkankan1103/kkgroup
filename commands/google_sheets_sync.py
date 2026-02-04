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
import sys
import os

# 導入 SHEET 同步管理器
sys.path.insert(0, os.path.dirname(__file__) + '/..')
from sheet_sync_manager import SheetSyncManager

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
        self.sync_manager = SheetSyncManager('user_data.db')  # ✅ 使用新的管理器
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
        """
        內部同步方法：Google Sheet → 資料庫（SHEET 主導）
        
        使用 SheetSyncManager 自動化：
        1. 讀取 SHEET 表頭（第 2 行）
        2. 自動同步 DB schema（添加缺失的欄位）
        3. 解析和同步記錄
        """
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
            
            # 使用 SheetSyncManager 處理
            try:
                # 1. 提取表頭
                headers = self.sync_manager.get_sheet_headers(all_values)
                print(f"📋 SHEET 表頭 (第 2 行，共 {len(headers)} 列): {headers[:5]}...")
                
                # 2. 自動同步 DB schema（添加缺失的欄位）
                print(f"🔧 檢查並自動同步 DB schema...")
                self.sync_manager.ensure_db_schema(headers)
                
                # 3. 提取數據行
                data_rows = self.sync_manager.get_sheet_data_rows(all_values)
                print(f"📊 SHEET 數據行: {len(data_rows)} 筆")
                
                if not data_rows:
                    print(f"❌ 沒有數據記錄")
                    return 0, 0, 0
                
                # 4. 解析記錄
                records = self.sync_manager.parse_records(headers, data_rows)
                print(f"✅ 解析完成: {len(records)} 筆有效記錄")
                
                # Debug：打印前 3 筆
                for i in range(min(3, len(records))):
                    user_id = records[i].get('user_id')
                    kkcoin = records[i].get('kkcoin')
                    level = records[i].get('level')
                    print(f"🔍 記錄 {i+1}: user_id={user_id}, kkcoin={kkcoin}, level={level}")
                
                # 5. 同步到 DB
                updated, inserted, errors = self.sync_manager.sync_records(records)
                
                print(f"✅ [SHEET→DB 同步] 更新={updated}, 新增={inserted}, 錯誤={errors} ({datetime.now().strftime('%H:%M:%S')})")
                return updated, inserted, errors
            
            except Exception as e:
                print(f"❌ SheetSyncManager 處理失敗: {e}")
                import traceback
                traceback.print_exc()
                return 0, 0, 1
        
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
                
                # SHEET 結構：
                # Row 1: 分組標題【# 第1欄】【第2欄】...（保留不覆蓋）
                # Row 2: 實際標題 user_id, nickname, level, ...
                # Row 3+: 數據
                
                # 首先讀取現有的 Row 1（分組標題），避免覆蓋
                try:
                    all_values = self.sheet.get_all_values()
                    group_headers = all_values[0] if all_values else None
                except:
                    group_headers = None
                
                headers = [
                    'user_id', 'nickname', 'level', 'xp', 'kkcoin', 'title', 'hp', 'stamina',
                    'inventory', 'character_config', 'face', 'hair', 'skin',
                    'top', 'bottom', 'shoes', 'streak', 'last_work_date',
                    'last_action_date', 'actions_used', 'gender', 'is_stunned',
                    'is_locked', 'last_recovery'
                ]
                
                # 構建數據：保留 Row 1（分組標題），覆蓋 Row 2+（表頭和數據）
                data = []
                if group_headers:
                    data.append(group_headers)  # Row 1: 分組標題
                else:
                    # 如果沒有分組標題，創建一個
                    data.append(['【# 第1欄】'] + ['【第' + str(i+2) + '欄】' for i in range(len(headers)-1)])
                
                data.append(headers)  # Row 2: 實際標題
                for row in rows:
                    user = self.bot.get_user(row[0])
                    nickname = user.display_name if user else f"Unknown_{row[0]}"
                    
                    # 重要：user_id 必須以文本格式寫入，否則 Google Sheets 會轉成科學記號
                    # 例如：123456789012345678 → 1.23456789012E+17
                    data.append([
                        f"{int(row[0])}",  # ✅ user_id 轉成字符串，防止科學記號
                        nickname, 
                        int(row[1]), int(row[2]), int(row[3]),
                        row[4], int(row[5]), int(row[6]), row[7], row[8],
                        int(row[9]), int(row[10]), int(row[11]), int(row[12]),
                        int(row[13]), int(row[14]), int(row[15]),
                        row[16] or '', row[17] or '', row[18], row[19],
                        'TRUE' if row[20] else 'FALSE', 'TRUE' if row[21] else 'FALSE',
                        row[22] or ''
                    ])
                
                self.sheet.clear()  # 清空整個 SHEET
                # 使用 USER_ENTERED 讓 Google Sheets 自動判斷數據類型
                # 但 user_id 已經轉成字符串，所以不會被轉成科學記號
                self.sheet.append_rows(data, value_input_option='USER_ENTERED')
                
                print(f"✅ 導出完成: 保留 Row 1（分組標題），更新 Row 2+（表頭和數據）")
                print(f"   - Row 1: 分組標題（保留）")
                print(f"   - Row 2: 實際表頭")
                print(f"   - Row 3+: {len(rows)} 筆玩家數據")
                
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
