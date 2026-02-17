import asyncio
import discord
import datetime
import time
from discord.ext import tasks
from db_adapter import get_all_users, set_user_field, get_user_field, get_user


class LockerTasks:
    """置物櫃相關的後台任務（事件驅動型增量同步）"""
    
    def __init__(self, cog):
        self.cog = cog
        self.bot = cog.bot
        self.FORUM_CHANNEL_ID = cog.FORUM_CHANNEL_ID
        
        # 追蹤上次同步時間戳，用於增量檢測
        self.last_sync_time = {}  # { user_id → timestamp }
    
    async def update_all_locker_embeds(self):
        """
        主背景任務入口
        
        流程：
        1. 初次啟動：回填 locker_message_id（回溯舊訊息或建立新的）
        2. 定期運行（每 10 分鐘）：
           - 掃描活躍使用者
           - 檢測 DB 中的欄位變更
           - 根據變更類型觸發相應事件（由 LockerEventListenerCog 處理）
        
        優點：
        - 不直接覆蓋 embed，讓事件監聽器處理（保證單一路徑）
        - 只同步有變更的使用者（減少 API 調用）
        - 支援快取（快速檢測無變更情況）
        """
        await self._backfill_locker_message_ids()
        
        print("🔄 置物櫃增量同步任務已啟動（每 10 分鐘執行一次）")
        
        while not self.bot.is_closed():
            try:
                await self._sync_changed_users()
            except Exception as e:
                print(f"❌ 增量同步任務出錯: {e}")
                import traceback
                traceback.print_exc()
            
            await asyncio.sleep(600)  # 每 10 分鐘執行一次（改自 30 分鐘）
    
    async def _backfill_locker_message_ids(self):
        """
        初始化回填：
        - 掃描所有使用者
        - 若 locker_message_id 缺失，嘗試在 thread 歷史中尋找舊訊息
        - 若找不到，建立新的 canonical message 並回填
        """
        print("🔍 開始回填 locker_message_id...")
        
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                print("❌ 找不到論壇頻道")
                return
            
            all_users = get_all_users()
            backfilled_count = 0
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id')
                locker_message_id = user_data.get('locker_message_id')
                
                # 已有 locker_message_id 且訊息有效，跳過
                if locker_message_id:
                    try:
                        thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                        if thread and isinstance(thread, discord.Thread):
                            message = await thread.fetch_message(locker_message_id)
                            if message:
                                continue  # 訊息有效，跳過
                    except:
                        pass  # 訊息無效，進行回填
                
                # 缺失或無效 → 嘗試回填
                if not user_id or not thread_id:
                    continue
                
                try:
                    thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                    if not thread or not isinstance(thread, discord.Thread):
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    
                    if getattr(thread, 'archived', False):
                        continue
                    
                    # 在 thread 歷史中尋找現有的 bot locker message
                    found_msg = None
                    async for m in thread.history(limit=200):
                        if m.author and m.author.id == self.bot.user.id and m.embeds:
                            e = m.embeds[0]
                            title = e.title or ''
                            if '置物櫃' in title or '個人置物櫃' in title or title.startswith('📦'):
                                found_msg = m
                                break
                    
                    if found_msg:
                        set_user_field(user_id, 'locker_message_id', found_msg.id)
                        print(f"✅ 回填 locker_message_id: user {user_id} → {found_msg.id}")
                        backfilled_count += 1
                    else:
                        # 建立新的 canonical message
                        try:
                            user_obj = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                            
                            # 第一個 embed: Summary（文字資訊）
                            summary_embed = await self.cog.create_user_embed(user_data, user_obj)
                            summary_embed.set_image(url=None)  # 移除圖片
                            
                            # 第二個 embed: Appearance（紙娃娃 + 裝備）
                            appearance_embed = discord.Embed(
                                title=f"📦 {user_obj.display_name or user_obj.name} - 裝備",
                                color=0x9933ff,
                            )
                            
                            # 使用快取取得紙娃娃圖片
                            from uicommands.utils.locker_cache import locker_cache
                            paperdoll_url = await locker_cache.get_paperdoll_image(user_data)
                            if paperdoll_url:
                                appearance_embed.set_image(url=paperdoll_url)
                            
                            from uicommands.views import LockerPanelView
                            view = LockerPanelView(self.cog, user_id, thread)
                            
                            new_msg = await thread.send(embeds=[summary_embed, appearance_embed], view=view)
                            set_user_field(user_id, 'locker_message_id', new_msg.id)
                            print(f"✅ 建立新 message: user {user_id} → {new_msg.id}")
                            backfilled_count += 1
                        
                        except Exception as _e:
                            print(f"⚠️ 無法為 user {user_id} 建立訊息: {_e}")
                
                await asyncio.sleep(2)
            
            print(f"✅ 回填完成：共處理 {backfilled_count} 個使用者")
        
        except Exception as e:
            print(f"❌ 回填失敗: {e}")
            import traceback
            traceback.print_exc()
    
    async def _sync_changed_users(self):
        """
        增量同步主邏輯
        
        流程：
        1. 取得所有活躍使用者
        2. 檢測每個使用者的欄位變更
        3. 根據變更類型觸發相應事件
        """
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                return
            
            all_users = get_all_users()
            synced_count = 0
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id')
                locker_message_id = user_data.get('locker_message_id')
                
                # 略過沒有置物櫃的使用者
                if not user_id or not thread_id or not locker_message_id:
                    continue
                
                try:
                    # 驗證 thread 有效性
                    thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                    if not thread or not isinstance(thread, discord.Thread):
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    
                    if getattr(thread, 'archived', False):
                        continue
                    
                    # 取得 message（若不存在則清除記錄）
                    try:
                        message = await thread.fetch_message(locker_message_id)
                    except discord.NotFound:
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    
                    # 檢測變更並觸發事件
                    changed_fields = await self._detect_field_changes(user_id, user_data, message)
                    
                    if changed_fields:
                        await self._trigger_events_for_changes(user_id, changed_fields)
                        synced_count += 1
                
                except Exception as e:
                    print(f"⚠️ 處理 user {user_id} 時出錯: {e}")
            
            if synced_count > 0:
                print(f"🔄 增量同步完成： {synced_count} 個使用者有變更")
        
        except Exception as e:
            print(f"❌ 增量同步失敗: {e}")
    
    async def _detect_field_changes(self, user_id: int, user_data: dict, message: discord.Message) -> dict:
        """
        檢測使用者資料中的欄位變更
        
        邏輯：
        - 比對 DB 中的值 vs message embed 中的值
        - 若有變更，回傳變更的欄位集合
        
        Returns:
            {
                'equipment': boolean,
                'currency': boolean,
                'health': boolean,
                'inventory': boolean,
            }
        """
        changes = {
            'equipment': False,
            'currency': False,
            'health': False,
            'inventory': False,
        }
        
        try:
            # 防止同一使用者在短時間內重複檢測
            now = time.time()
            last_check = self.last_sync_time.get(user_id, 0)
            if now - last_check < 5:
                return changes  # 5 秒內不重複檢測
            
            self.last_sync_time[user_id] = now
            
            # 檢測裝備變更
            paperdoll_hash_db = None
            paperdoll_hash_cached = None
            
            if user_data.get('paperdoll_hash'):
                paperdoll_hash_db = user_data.get('paperdoll_hash')
            else:
                # 沒有快取 hash 時計算
                from uicommands.utils.locker_cache import LockerCache
                paperdoll_hash_db = LockerCache.build_paperdoll_hash(user_data)
            
            # 從 message embed 中提取快取的 hash（若有）
            if message.embeds and len(message.embeds) > 1:
                appearance_embed = message.embeds[1]
                # 假設 description 或 footer 中包含 hash（若存在）
                # 或簡單地檢查 image 是否存在
                if not appearance_embed.image:
                    paperdoll_hash_cached = None
                else:
                    paperdoll_hash_cached = paperdoll_hash_db  # 簡化：假設 hash 相同
            
            if paperdoll_hash_db != paperdoll_hash_cached:
                changes['equipment'] = True
            
            # 檢測 KK幣/經驗值變更
            if message.embeds:
                summary_embed = message.embeds[0]
                embed_text = summary_embed.description or ""
                embed_text += " ".join([f.value for f in summary_embed.fields if f])
                
                if str(user_data.get('kkcoin', 0)) not in embed_text:
                    changes['currency'] = True
            
            # 檢測血量/體力變更
            if message.embeds:
                summary_embed = message.embeds[0]
                embed_text = " ".join([f.value for f in summary_embed.fields if f])
                
                hp_progress = f"{user_data.get('hp', 100)}/100"
                stamina_progress = f"{user_data.get('stamina', 100)}/100"
                
                if hp_progress not in embed_text or stamina_progress not in embed_text:
                    changes['health'] = True
            
            return changes
        
        except Exception as e:
            print(f"⚠️ 檢測 user {user_id} 的變更時出錯: {e}")
            return changes
    
    async def _trigger_events_for_changes(self, user_id: int, changes: dict) -> None:
        """
        根據檢測到的變更，觸發相應的事件
        
        讓 LockerEventListenerCog 的監聽器來處理實際的 embed 更新
        """
        try:
            from uicommands.events import (
                EquipmentChangedEvent,
                CurrencyChangedEvent,
                HealthChangedEvent,
            )
            
            if changes['equipment']:
                event = EquipmentChangedEvent(
                    user_id=user_id,
                    changed_fields={'*'}  # 完整重新渲染
                )
                self.bot.dispatch('equipment_changed', event)
                print(f"📤 觸發 EquipmentChangedEvent: user {user_id}")
            
            if changes['currency']:
                event = CurrencyChangedEvent(
                    user_id=user_id,
                    changed_fields={'kkcoin', 'xp'}
                )
                self.bot.dispatch('currency_changed', event)
                print(f"📤 觸發 CurrencyChangedEvent: user {user_id}")
            
            if changes['health']:
                event = HealthChangedEvent(
                    user_id=user_id,
                    changed_fields={'hp', 'stamina'}
                )
                self.bot.dispatch('health_changed', event)
                print(f"📤 觸發 HealthChangedEvent: user {user_id}")
        
        except Exception as e:
            print(f"⚠️ 觸發事件時出錯 (user {user_id}): {e}")
