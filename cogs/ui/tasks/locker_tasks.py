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
        self.last_sync_time = {}
    
    async def update_all_locker_embeds(self):
        """主背景任務入口"""
        await self._backfill_locker_message_ids()
        print("🔄 置物櫃增量同步任務已啟動（每 10 分鐘執行一次）")
        
        while not self.bot.is_closed():
            try:
                await self._sync_changed_users()
            except Exception as e:
                print(f"❌ 增量同步任務出錯: {e}")
                import traceback
                traceback.print_exc()
            
            await asyncio.sleep(600)
    
    async def _backfill_locker_message_ids(self):
        """初始化回填 locker_message_id"""
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
                
                if locker_message_id:
                    try:
                        thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                        if thread and isinstance(thread, discord.Thread):
                            message = await thread.fetch_message(locker_message_id)
                            if message:
                                continue
                    except:
                        pass
                
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
                    
                    found_msg = None
                    try:
                        async for m in thread.history(limit=200):
                            if m.author and m.author.id == self.bot.user.id and m.embeds:
                                e = m.embeds[0]
                                title = e.title or ''
                                if '置物櫃' in title or '個人置物櫃' in title or title.startswith('📦'):
                                    found_msg = m
                                    break
                    except Exception as _e:
                        print(f"⚠️ 無法掃描 {user_id} 的 thread 歷史: {_e}")
                    
                    if found_msg:
                        set_user_field(user_id, 'locker_message_id', found_msg.id)
                        print(f"✅ 回填 locker_message_id: user {user_id} → {found_msg.id}")
                        backfilled_count += 1
                    else:
                        try:
                            user_obj = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                            
                            summary_embed = await self.cog.create_user_embed(user_data, user_obj)
                            summary_embed.set_image(url=None)
                            
                            appearance_embed = discord.Embed(
                                title=f"📦 {user_obj.display_name or user_obj.name} - 裝備",
                                color=0x9933ff,
                            )
                            
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
                    
                    await asyncio.sleep(1)
                
                except Exception as e:
                    print(f"⚠️ 回填用戶 {user_id} 時出錯: {e}")
            
            print(f"✅ 回填完成：共處理 {backfilled_count} 個使用者")
        
        except Exception as e:
            print(f"❌ 回填失敗: {e}")
            import traceback
            traceback.print_exc()
    
    async def _sync_changed_users(self):
        """增量同步主邏輯"""
        try:
            all_users = get_all_users()
            changed_count = 0
            
            for user_data in all_users:
                user_id = user_data.get('user_id')
                if not user_id:
                    continue
                
                thread_id = user_data.get('thread_id')
                locker_message_id = user_data.get('locker_message_id')
                
                if not thread_id or not locker_message_id:
                    continue
                
                try:
                    thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                    if not thread or not isinstance(thread, discord.Thread):
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    
                    if getattr(thread, 'archived', False):
                        continue
                    
                    try:
                        message = await thread.fetch_message(locker_message_id)
                    except discord.NotFound:
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    
                    changed = await self._detect_field_changes(user_id, user_data, message)
                    if changed:
                        await self._trigger_events_for_changes(user_id, changed)
                        changed_count += 1
                
                except Exception as e:
                    print(f"⚠️ 處理 user {user_id} 時出錯: {e}")
            
            if changed_count > 0:
                print(f"🔄 增量同步完成：{changed_count} 個使用者有變更")
        
        except Exception as e:
            print(f"❌ 增量同步失敗: {e}")
    
    async def _detect_field_changes(self, user_id, user_data, message):
        """檢測是否有欄位變更"""
        try:
            now = time.time()
            last_check = self.last_sync_time.get(user_id, 0)
            if now - last_check < 5:
                return False
            
            self.last_sync_time[user_id] = now
            
            if not message.embeds:
                return False
            
            summary_embed = message.embeds[0]
            embed_text = str(summary_embed.description or "") + " ".join([str(f.value or "") for f in summary_embed.fields])
            
            # 簡單的變更檢測
            kkcoin_str = str(user_data.get('kkcoin', 0))
            hp_str = str(user_data.get('hp', 100))
            
            if kkcoin_str not in embed_text or hp_str not in embed_text:
                return True
            
            return False
        
        except Exception as e:
            print(f"⚠️ 檢測變更時出錯: {e}")
            return False
    
    async def _trigger_events_for_changes(self, user_id, _changed):
        """觸發事件"""
        try:
            from uicommands.events.locker_events import FullRefreshEvent
            
            event = FullRefreshEvent(user_id, {'*'})
            self.bot.dispatch('locker_full_refresh', event)
            print(f"📤 觸發 FullRefreshEvent: user {user_id}")
        
        except Exception as e:
            print(f"⚠️ 觸發事件時出錯: {e}")
