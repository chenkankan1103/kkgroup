from discord.ext import commands
import discord
import os
import json
import traceback
import asyncio
from datetime import datetime
from commands.work_function.database import init_db, get_user, update_user
from commands.work_function.work_system import LEVELS, process_checkin, process_work_action

class CheckInView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CheckInButton())
        self.add_item(RestButton())

class CheckInButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="打卡上班", style=discord.ButtonStyle.success, custom_id="work:checkin")

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_work_date = user.get('last_work_date', None)

            if last_work_date == today:
                await interaction.followup.send("你今天已經打過卡囉！", ephemeral=True)
                return

            # 檢查介紹論壇
            introduce_check_result = await self.check_introduction_async(interaction)
            if not introduce_check_result:
                return

            # ⭐ 修改這裡：傳入 guild 參數
            embeds_tuple, updated_user = await process_checkin(
                interaction.user.id, 
                interaction.user,
                interaction.guild  # 新增這個參數
            )
            
            if embeds_tuple and updated_user:
                work_view = WorkActionView(updated_user)
                
                # 如果有多個 embed（升級情況）
                if len(embeds_tuple) == 2:
                    # 先發送升級特效（公開）
                    await interaction.followup.send(
                        content=f"## 🎊 {interaction.user.mention} 升級了！", 
                        embed=embeds_tuple[0], 
                        ephemeral=False
                    )
                    # 再發送工作記錄卡（私密）
                    await interaction.followup.send(
                        embed=embeds_tuple[1], 
                        view=work_view, 
                        ephemeral=True
                    )
                else:
                    # 一般打卡
                    await interaction.followup.send(
                        embed=embeds_tuple[0], 
                        view=work_view, 
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "❌ 處理打卡失敗，請稍後再試或聯絡管理員", 
                    ephemeral=True
                )

        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    "❌ 發生錯誤，請稍後再試或聯絡管理員。", 
                    ephemeral=True
                )
            except:
                pass

    async def check_introduction_async(self, interaction):
        """異步檢查用戶是否在介紹論壇發過文章"""
        try:
            introduce_channel_id = int(os.getenv("INTRODUCE_CHANNEL_ID", 0))
            if not introduce_channel_id:
                return True  # 如果沒有設置介紹頻道，直接通過
            
            introduce_channel = interaction.guild.get_channel(introduce_channel_id)
            if not introduce_channel:
                await interaction.followup.send("❌ 找不到介紹論壇頻道，請聯絡管理員", ephemeral=True)
                return False

            if not isinstance(introduce_channel, discord.ForumChannel):
                return True  # 如果不是論壇頻道，直接通過

            # 使用更高效的檢查方式
            has_posted = await self.check_user_posts_optimized(introduce_channel, interaction.user.id)
            
            if not has_posted:
                await interaction.followup.send("⚠️ 你尚未在介紹論壇發過文章，請先完成介紹<#1338443519383179304>再來打卡！", ephemeral=True)
                return False
            
            return True
        except Exception as e:
            print(f"⚠️ 檢查介紹論壇時發生錯誤：{e}")
            return True  # 發生錯誤時允許通過，避免阻塞用戶

    async def check_user_posts_optimized(self, forum_channel, user_id):
        """優化的用戶發文檢查 - 增強版本"""
        try:
            print(f"🔍 開始檢查用戶 {user_id} 在論壇 {forum_channel.name} 的發文狀態")
            
            # 增加檢查範圍和時間限制
            MAX_THREADS_TO_CHECK = 100  # 大幅增加檢查數量
            MAX_MESSAGES_PER_THREAD = 50  # 增加每個討論串的檢查訊息數
            
            # 獲取所有討論串的多種方式
            all_threads = []
            thread_ids_seen = set()
            
            # 方法1: 獲取活躍討論串
            try:
                active_threads_response = await forum_channel.guild.active_threads()
                for thread in active_threads_response.threads:
                    if thread.parent_id == forum_channel.id and thread.id not in thread_ids_seen:
                        all_threads.append(thread)
                        thread_ids_seen.add(thread.id)
                print(f"📌 找到 {len(all_threads)} 個活躍討論串")
            except Exception as e:
                print(f"⚠️ 獲取活躍討論串失敗: {e}")
            
            # 方法2: 獲取已封存的討論串（公開）
            try:
                count = 0
                async for thread in forum_channel.archived_threads(limit=None, private=False):
                    if thread.id not in thread_ids_seen:
                        all_threads.append(thread)
                        thread_ids_seen.add(thread.id)
                        count += 1
                    if count >= 50:  # 限制檢查數量避免太慢
                        break
                print(f"📁 找到 {count} 個公開已封存討論串")
            except Exception as e:
                print(f"⚠️ 獲取公開已封存討論串失敗: {e}")
            
            # 方法3: 獲取已封存的討論串（私人）
            try:
                count = 0
                async for thread in forum_channel.archived_threads(limit=None, private=True):
                    if thread.id not in thread_ids_seen:
                        all_threads.append(thread)
                        thread_ids_seen.add(thread.id)
                        count += 1
                    if count >= 50:  # 限制檢查數量避免太慢
                        break
                print(f"🔒 找到 {count} 個私人已封存討論串")
            except Exception as e:
                print(f"⚠️ 獲取私人已封存討論串失敗: {e}")
            
            # 方法4: 嘗試從論壇頻道歷史中查找討論串
            try:
                count = 0
                async for message in forum_channel.history(limit=200):
                    if message.thread and message.thread.id not in thread_ids_seen:
                        all_threads.append(message.thread)
                        thread_ids_seen.add(message.thread.id)  
                        count += 1
                print(f"📜 從歷史訊息找到 {count} 個額外討論串")
            except Exception as e:
                print(f"⚠️ 從歷史訊息查找討論串失敗: {e}")
            
            # 限制檢查數量並按時間排序（較新的優先）
            all_threads = sorted(all_threads, key=lambda t: t.created_at, reverse=True)
            threads_to_check = all_threads[:MAX_THREADS_TO_CHECK]
            
            if not threads_to_check:
                print("⚠️ 沒有找到任何討論串，允許用戶通過")
                return True
            
            print(f"🎯 總共找到 {len(all_threads)} 個討論串，將檢查前 {len(threads_to_check)} 個")
            
            # 分批檢查，避免超時
            batch_size = 10
            found_posts = []
            
            for i in range(0, len(threads_to_check), batch_size):
                batch = threads_to_check[i:i + batch_size]
                print(f"🔄 檢查第 {i//batch_size + 1} 批 ({len(batch)} 個討論串)")
                
                tasks = []
                for thread in batch:
                    task = self.check_thread_for_user(thread, user_id, MAX_MESSAGES_PER_THREAD)
                    tasks.append(task)
                
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True), 
                        timeout=10.0
                    )
                    
                    for j, result in enumerate(results):
                        if result is True:
                            found_posts.append(batch[j].name)
                            print(f"✅ 在討論串 '{batch[j].name}' 中找到用戶發文")
                        elif isinstance(result, Exception):
                            print(f"⚠️ 檢查討論串 '{batch[j].name}' 時發生異常: {result}")
                    
                    # 找到發文就可以提前返回
                    if found_posts:
                        print(f"🎉 用戶 {user_id} 在以下討論串中有發文: {found_posts}")
                        return True
                        
                except asyncio.TimeoutError:
                    print(f"⏰ 第 {i//batch_size + 1} 批檢查超時，繼續下一批")
                    continue
            
            print(f"❌ 用戶 {user_id} 在所有 {len(threads_to_check)} 個討論串中都沒有發文")
            
            # 最後嘗試：直接搜尋用戶在論壇頻道的所有訊息
            print("🔍 嘗試最後的搜尋方法...")
            final_result = await self.final_search_attempt(forum_channel, user_id)
            return final_result
                
        except Exception as e:
            print(f"⚠️ 檢查時發生嚴重錯誤：{e}")
            traceback.print_exc()
            return True  # 錯誤時允許通過

    async def check_thread_for_user(self, thread, user_id, max_messages):
        """檢查單個討論串是否有用戶發文 - 增強版本"""
        try:
            # 首先檢查討論串的創建者
            if hasattr(thread, 'owner_id') and thread.owner_id == user_id:
                print(f"✅ 用戶 {user_id} 是討論串 '{thread.name}' 的創建者")
                return True
            
            # 檢查討論串的初始訊息（創建討論串時的第一條訊息）
            try:
                starter_message = await thread.fetch_message(thread.id)
                if starter_message and starter_message.author.id == user_id:
                    print(f"✅ 用戶 {user_id} 是討論串 '{thread.name}' 的初始訊息作者")
                    return True
            except:
                pass  # 無法獲取初始訊息，繼續其他檢查
            
            # 檢查討論串中的所有訊息
            message_count = 0
            try:
                async for message in thread.history(limit=max_messages, oldest_first=True):
                    if message.author.id == user_id:
                        print(f"✅ 在討論串 '{thread.name}' 中找到用戶 {user_id} 的訊息 (第{message_count+1}條)")
                        return True
                    message_count += 1
                    
                    # 每10條訊息輸出一次進度
                    if message_count % 10 == 0:
                        print(f"🔍 已檢查討論串 '{thread.name}' 的 {message_count} 條訊息")
                        
                    if message_count >= max_messages:
                        break
            except Exception as e:
                print(f"⚠️ 檢查訊息歷史時發生錯誤: {e}")
            
            print(f"❌ 在討論串 '{thread.name}' 的 {message_count} 條訊息中未找到用戶 {user_id}")
            return False
            
        except discord.Forbidden:
            print(f"⚠️ 沒有權限檢查討論串 '{thread.name}'")
            return False
        except discord.NotFound:
            print(f"⚠️ 討論串 '{thread.name}' 不存在或已被刪除")
            return False
        except Exception as e:
            print(f"⚠️ 檢查討論串 '{thread.name}' 時發生未知錯誤: {e}")
            return False

    async def final_search_attempt(self, forum_channel, user_id):
        """最後的搜尋嘗試：直接在論壇頻道中搜尋用戶訊息"""
        try:
            print(f"🔍 進行最後搜尋：直接在論壇頻道中查找用戶 {user_id} 的訊息")
            
            # 嘗試搜尋論壇頻道中用戶的訊息
            message_count = 0
            async for message in forum_channel.history(limit=500):
                if message.author.id == user_id:
                    print(f"🎉 在論壇頻道中找到用戶 {user_id} 的訊息！")
                    return True
                message_count += 1
                
                if message_count % 50 == 0:
                    print(f"🔍 已搜尋論壇頻道的 {message_count} 條訊息")
            
            print(f"❌ 在論壇頻道的 {message_count} 條訊息中未找到用戶 {user_id}")
            
            # 最後嘗試：檢查論壇頻道的成員列表（如果可用）
            try:
                guild = forum_channel.guild
                member = guild.get_member(user_id)
                if member:
                    print(f"ℹ️ 確認用戶 {user_id} ({member.display_name}) 是伺服器成員")
                    
                    # 嘗試獲取用戶的最近活動
                    print(f"ℹ️ 用戶加入時間: {member.joined_at}")
                    print(f"ℹ️ 用戶創建時間: {member.created_at}")
                else:
                    print(f"⚠️ 用戶 {user_id} 不是當前伺服器成員")
            except Exception as e:
                print(f"⚠️ 獲取用戶資訊時發生錯誤: {e}")
            
            return False
            
        except Exception as e:
            print(f"⚠️ 最後搜尋嘗試時發生錯誤: {e}")
            return True  # 錯誤時允許通過

class RestButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="休息一天", style=discord.ButtonStyle.secondary, custom_id="work:rest")

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            today = datetime.utcnow().strftime("%Y-%m-%d")
            
            last_work_date = user.get('last_work_date', None)
            
            if last_work_date == today:
                await interaction.followup.send("你今天已經打過卡或選擇休息了！", ephemeral=True)
                return
            
            update_user(interaction.user.id, last_work_date=today, streak=0)
            
            rest_embed = discord.Embed(
                title="🛌 休息通知",
                description="你選擇今天休息，連續出勤天數已重置為 0。",
                color=0xff5555
            )
            
            await interaction.followup.send(embed=rest_embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("❌ 處理休息請求失敗，請稍後再試或聯絡管理員", ephemeral=True)

class WorkActionButton(discord.ui.Button):
    def __init__(self, label, custom_id):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=False)
            
            parts = self.custom_id.split(':')
            action = parts[2]
            user_id = parts[3]
            
            if str(interaction.user.id) != user_id:
                await interaction.followup.send("你不能使用別人的工作按鈕！", ephemeral=True)
                return
            
            embed, updated_user, message = await process_work_action(interaction.user.id, interaction.user, action)
            
            if embed and updated_user:
                view = WorkActionView(updated_user)
                actions_used = json.loads(updated_user.get('actions_used', '{}'))
                view.update_button_states(actions_used)
                
                await interaction.edit_original_response(embed=embed, view=view)
                
                if message:
                    await interaction.followup.send(message, ephemeral=True)
            else:
                if message:
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 處理失敗，請稍後再試或聯絡管理員", ephemeral=True)
                
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send("❌ 處理失敗，請稍後再試或聯絡管理員", ephemeral=True)
            except:
                pass

class WorkActionView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=180)
        self.user_id = user['user_id']
        
        level = user['level']
        actions = LEVELS[level]["actions"]
        actions_used = json.loads(user.get('actions_used', '{}'))
        
        for idx, act in enumerate(actions):
            button = WorkActionButton(
                label=act,
                custom_id=f"work:act:{act}:{self.user_id}"
            )
            
            if act in actions_used:
                button.disabled = True
                
            self.add_item(button)
    
    def update_button_states(self, actions_used):
        for item in self.children:
            if isinstance(item, WorkActionButton):
                action = item.custom_id.split(':')[2]
                if action in actions_used:
                    item.disabled = True

class WorkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init_db()
        self.bot.add_view(CheckInView())

    async def cog_load(self):
        """當 Cog 載入時執行"""
        print("WorkCog 已載入")

    @commands.Cog.listener()
    async def on_ready(self):
        """當機器人準備就緒時同步命令"""
        try:
            synced = await self.bot.tree.sync()
            print(f"已同步 {len(synced)} 個斜杠命令")
        except Exception as e:
            print(f"同步命令失敗: {e}")

    @discord.app_commands.command(name="work", description="開啟詐騙園區值勤系統")
    @discord.app_commands.describe(action="選擇操作類型")
    @discord.app_commands.choices(action=[
        discord.app_commands.Choice(name="部署系統", value="deploy"),
        discord.app_commands.Choice(name="查看狀態", value="status"),
        discord.app_commands.Choice(name="測試介紹檢查", value="test_intro")
    ])
    async def work(self, interaction: discord.Interaction, action: str = "deploy"):
        try:
            # 檢查管理員權限
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 你沒有權限使用此指令，需要管理員權限！", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
        
            if action == "deploy":
                embed = discord.Embed(
                    title="👷‍♀️【KK園區值勤系統】",
                    description=(
                        "## 歡迎來到詐騙園區！\n"
                        "請選擇今日行動，開始你的詐騙生涯！\n\n"
                        "💰 **高薪誘惑**：日薪最低 200 KK幣起跳！\n"
                        "📈 **快速晉升**：持續出勤即可升職加薪！\n"
                        "🎁 **豐厚獎勵**：升級可獲得額外紅包！"
                    ),
                    color=0xf39c12
                )
                
                # 等級薪資展示
                salary_info = "\n".join([
                    f"**Lv.{lvl} {info['title']}**：{info['salary']:,} KK幣/天"
                    for lvl, info in LEVELS.items()
                ])
                
                embed.add_field(
                    name="💼 職位薪資表",
                    value=salary_info,
                    inline=False
                )
                
                embed.add_field(
                    name="🎯 每日行動",
                    value=(
                        "**打卡上班**：領取日薪 + 經驗值 + 維持連勤\n"
                        "**休息一天**：重置連勤（不影響等級）\n"
                        "**執行任務**：打卡後可執行額外行動賺更多！"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="⚠️ 重要提示",
                    value=(
                        "• 需先在<#1338443519383179304>發文才能打卡\n"
                        "• 升級需同時滿足**連續出勤**和**經驗值**\n"
                        "• 升級可獲得專屬身分組和升級紅包\n"
                        "• 等級越高，日薪和行動收益越高！"
                    ),
                    inline=False
                )
                
                embed.set_footer(text="💡 提示：持續出勤是致富關鍵！")
                embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1234567890.png")  # 可選：加入縮圖
                
                await interaction.followup.send(embed=embed, view=CheckInView())
                await interaction.followup.send("✅ 值勤系統已部署成功！", ephemeral=True)

    async def test_user_introduction(self, interaction):
        """測試用戶是否在介紹論壇發過文章（管理員專用）"""
        try:
            introduce_channel_id = int(os.getenv("INTRODUCE_CHANNEL_ID", 0))
            
            if not introduce_channel_id:
                await interaction.followup.send("❌ 未設置介紹頻道ID (INTRODUCE_CHANNEL_ID)", ephemeral=True)
                return
            
            introduce_channel = interaction.guild.get_channel(introduce_channel_id)
            if not introduce_channel:
                await interaction.followup.send(f"❌ 找不到介紹論壇頻道 (ID: {introduce_channel_id})", ephemeral=True)
                return
            
            if not isinstance(introduce_channel, discord.ForumChannel):
                await interaction.followup.send(f"❌ 頻道不是論壇類型 (當前類型: {type(introduce_channel)})", ephemeral=True)
                return
            
            # 測試自己的發文狀態
            test_button = CheckInButton()
            result = await test_button.check_user_posts_optimized(introduce_channel, interaction.user.id)
            
            embed = discord.Embed(
                title="🔍 介紹論壇檢查測試",
                color=0x00ff00 if result else 0xff0000
            )
            embed.add_field(name="頻道", value=f"{introduce_channel.mention} (ID: {introduce_channel_id})", inline=False)
            embed.add_field(name="測試用戶", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="檢查結果", value="✅ 已發文" if result else "❌ 未發文", inline=False)
            embed.set_footer(text="此測試使用與打卡系統相同的檢查邏輯")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 測試時發生錯誤: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(WorkCog(bot))
