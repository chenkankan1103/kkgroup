import asyncio
import discord
import datetime
from discord.ext import tasks
from db_adapter import get_all_users, set_user_field, get_user_field


class LockerTasks:
    """置物櫃相關的後台任務"""
    
    def __init__(self, cog):
        self.cog = cog
        self.bot = cog.bot
        self.FORUM_CHANNEL_ID = cog.FORUM_CHANNEL_ID
    
    async def update_all_locker_embeds(self):
        """定期更新所有置物櫃embed的View"""
        await self._do_locker_embeds_update()
        
        while not self.bot.is_closed():
            try:
                forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
                if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                    await asyncio.sleep(1800)
                    continue
                
                all_users = get_all_users()
                
                # 過濾和排序活躍用戶
                active_users = []
                for user_data in all_users:
                    user_id = user_data.get('user_id')
                    thread_id = user_data.get('thread_id')
                    if not user_id or not thread_id:
                        continue
                    
                    try:
                        # fetch thread by ID via bot (ForumChannel.fetch_thread isn't available on all discord.py builds)
                        thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                        if not thread or not isinstance(thread, discord.Thread):
                            # thread missing / not a Thread -> clear stored thread
                            set_user_field(user_id, 'thread_id', None)
                            set_user_field(user_id, 'locker_message_id', None)
                            continue
                        if getattr(thread, 'archived', False):
                            continue
                    except discord.NotFound:
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    except Exception:
                        continue
                    
                    last_activity = get_user_field(user_id, 'last_activity', default=0)
                    active_users.append((user_data, last_activity))
                
                active_users.sort(key=lambda x: x[1], reverse=True)
                
                updated_count = 0
                for user_data, _ in active_users:
                    user_id = user_data.get('user_id')
                    locker_message_id = user_data.get('locker_message_id')

                    # 如果 locker_message_id 缺失，嘗試使用 thread_id 在 thread 歷史中尋找置物櫃訊息並回填
                    if not locker_message_id:
                        thread_id = user_data.get('thread_id')
                        if thread_id:
                            try:
                                # use bot.fetch_channel/get_channel to support environments without ForumChannel.fetch_thread
                                thread_tmp = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                                if not thread_tmp or not isinstance(thread_tmp, discord.Thread):
                                    continue
                                async for m in thread_tmp.history(limit=200):
                                    if m.author and m.author.id == self.bot.user.id and m.embeds:
                                        e = m.embeds[0]
                                        title = e.title or ''
                                        if '置物櫃' in title or '個人置物櫃' in title or title.startswith('📦'):
                                            locker_message_id = m.id
                                            try:
                                                set_user_field(user_id, 'locker_message_id', locker_message_id)
                                                print(f"🔁 回填 locker_message_id for user {user_id}: {locker_message_id}")
                                            except Exception:
                                                pass
                                            break
                            except Exception:
                                # 任何錯誤都跳過回填，之後會繼續下一個使用者
                                pass

                    if not locker_message_id:
                        continue

                    try:
                        thread_id = user_data.get('thread_id')
                        try:
                            thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                            if not thread or not isinstance(thread, discord.Thread):
                                set_user_field(user_id, 'thread_id', None)
                                set_user_field(user_id, 'locker_message_id', None)
                                continue
                            if getattr(thread, 'archived', False):
                                continue
                        except discord.NotFound:
                            set_user_field(user_id, 'thread_id', None)
                            set_user_field(user_id, 'locker_message_id', None)
                            continue
                        
                        message = await thread.fetch_message(locker_message_id)
                        if not message:
                            continue
                        
                        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                        embed = await self.cog.create_user_embed(user_data, user)
                        character_image_url = await self.cog.get_character_image_url(user_data)
                        
                        if character_image_url:
                            embed.set_image(url=character_image_url)
                        
                        from uicommands.views import LockerPanelView
                        view = LockerPanelView(self.cog, user_id, thread)
                        
                        await message.edit(embed=embed, view=view)
                        updated_count += 1
                        
                        set_user_field(user_id, 'last_activity', int(datetime.datetime.now().timestamp()))
                        
                    except Exception as e:
                        print(f"⚠️ 更新用戶 {user_id} 的embed失敗: {e}")
                        continue
                    
                    await asyncio.sleep(5)
                
                if updated_count > 0:
                    print(f"✅ 已更新 {updated_count} 個活躍用戶的置物櫃embed")
                
            except Exception as e:
                print(f"❌ 更新embed任務出錯: {e}")
            
            await asyncio.sleep(1800)
    
    async def _do_locker_embeds_update(self):
        """執行一次置物櫃embed更新（用於重啟後立即更新）"""
        print("🔄 開始重啟後初始置物櫃embed更新")
        try:
            forum_channel = self.bot.get_channel(self.FORUM_CHANNEL_ID)
            if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
                print("❌ 找不到論壇頻道")
                return
            
            all_users = get_all_users()
            print(f"📊 找到 {len(all_users)} 個用戶")
            
            active_users = []
            for user_data in all_users:
                user_id = user_data.get('user_id')
                thread_id = user_data.get('thread_id')
                if not user_id or not thread_id:
                    continue
                
                try:
                    # fetch thread via bot (more compatible across discord.py builds)
                    thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                    if not thread or not isinstance(thread, discord.Thread):
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    if getattr(thread, 'archived', False):
                        continue
                except discord.NotFound:
                    set_user_field(user_id, 'thread_id', None)
                    set_user_field(user_id, 'locker_message_id', None)
                    continue
                except Exception:
                    continue
                
                last_activity = get_user_field(user_id, 'last_activity', default=0)
                active_users.append((user_data, last_activity))
            
            print(f"🎯 找到 {len(active_users)} 個活躍用戶需要更新")
            
            active_users.sort(key=lambda x: x[1], reverse=True)
            
            updated_count = 0
            for user_data, _ in active_users[:10]:
                user_id = user_data.get('user_id')
                locker_message_id = user_data.get('locker_message_id')

                # fallback: 若 locker_message_id 不存在，使用 thread_id 在 thread 歷史中搜尋並回填
                if not locker_message_id:
                    thread_id = user_data.get('thread_id')
                    if thread_id:
                        try:
                            thread_tmp = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                            if not thread_tmp or not isinstance(thread_tmp, discord.Thread):
                                continue
                            async for m in thread_tmp.history(limit=200):
                                if m.author and m.author.id == self.bot.user.id and m.embeds:
                                    e = m.embeds[0]
                                    title = e.title or ''
                                    if '置物櫃' in title or '個人置物櫃' in title or title.startswith('📦'):
                                        locker_message_id = m.id
                                        try:
                                            set_user_field(user_id, 'locker_message_id', locker_message_id)
                                            print(f"🔁 回填 locker_message_id for user {user_id}: {locker_message_id}")
                                        except Exception:
                                            pass
                                        break
                        except Exception:
                            pass

                if not locker_message_id:
                    continue

                try:
                    thread_id = user_data.get('thread_id')
                    try:
                        thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                        if not thread or not isinstance(thread, discord.Thread):
                            set_user_field(user_id, 'thread_id', None)
                            set_user_field(user_id, 'locker_message_id', None)
                            continue
                        if getattr(thread, 'archived', False):
                            continue
                    except discord.NotFound:
                        set_user_field(user_id, 'thread_id', None)
                        set_user_field(user_id, 'locker_message_id', None)
                        continue
                    
                    message = await thread.fetch_message(locker_message_id)
                    if not message:
                        continue
                    
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    embed = await self.cog.create_user_embed(user_data, user)
                    character_image_url = await self.cog.get_character_image_url(user_data)
                    
                    if character_image_url:
                        embed.set_image(url=character_image_url)
                    
                    from uicommands.views import LockerPanelView
                    view = LockerPanelView(self.cog, user_id, thread)
                    
                    await message.edit(embed=embed, view=view)
                    updated_count += 1
                    print(f"✅ 更新用戶 {user_id} 的embed")
                    
                except Exception as e:
                    print(f"⚠️ 初始更新用戶 {user_id} 的embed失敗: {e}")
                    continue
                
                await asyncio.sleep(5)
            
            if updated_count > 0:
                print(f"✅ 重啟後初始更新完成，已更新 {updated_count} 個活躍用戶的置物櫃embed")
            
        except Exception as e:
            print(f"❌ 初始更新embed出錯: {e}")
            import traceback
            traceback.print_exc()
        print("🏁 _do_locker_embeds_update 方法結束")
