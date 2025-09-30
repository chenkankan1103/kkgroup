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

            # 傳入 guild 參數
            embeds_tuple, updated_user = await process_checkin(
                interaction.user.id, 
                interaction.user,
                interaction.guild
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
                return True
            
            introduce_channel = interaction.guild.get_channel(introduce_channel_id)
            if not introduce_channel:
                await interaction.followup.send("❌ 找不到介紹論壇頻道，請聯絡管理員", ephemeral=True)
                return False

            if not isinstance(introduce_channel, discord.ForumChannel):
                return True

            has_posted = await self.check_user_posts_optimized(introduce_channel, interaction.user.id)
            
            if not has_posted:
                await interaction.followup.send(
                    "⚠️ 你尚未在介紹論壇發過文章，請先完成介紹再來打卡！\n"
                    f"📍 介紹論壇：{introduce_channel.mention}", 
                    ephemeral=True
                )
                return False
            
            return True
        except Exception as e:
            print(f"⚠️ 檢查介紹論壇時發生錯誤：{e}")
            return True

    async def check_user_posts_optimized(self, forum_channel, user_id):
        """優化的用戶發文檢查"""
        try:
            print(f"🔍 檢查用戶 {user_id} 的發文狀態")
            
            all_threads = []
            thread_ids_seen = set()
            
            # 方法1: 獲取活躍討論串
            try:
                active_threads_response = await forum_channel.guild.active_threads()
                for thread in active_threads_response.threads:
                    if thread.parent_id == forum_channel.id and thread.id not in thread_ids_seen:
                        all_threads.append(thread)
                        thread_ids_seen.add(thread.id)
            except Exception as e:
                print(f"⚠️ 獲取活躍討論串失敗: {e}")
            
            # 方法2: 獲取已封存的討論串
            try:
                async for thread in forum_channel.archived_threads(limit=50):
                    if thread.id not in thread_ids_seen:
                        all_threads.append(thread)
                        thread_ids_seen.add(thread.id)
            except Exception as e:
                print(f"⚠️ 獲取已封存討論串失敗: {e}")
            
            if not all_threads:
                print("⚠️ 沒有找到任何討論串")
                return True
            
            # 批次檢查討論串
            for thread in all_threads[:30]:  # 限制檢查數量
                try:
                    # 檢查創建者
                    if hasattr(thread, 'owner_id') and thread.owner_id == user_id:
                        print(f"✅ 用戶是討論串創建者")
                        return True
                    
                    # 檢查初始訊息
                    try:
                        starter_message = await thread.fetch_message(thread.id)
                        if starter_message and starter_message.author.id == user_id:
                            print(f"✅ 用戶是初始訊息作者")
                            return True
                    except:
                        pass
                    
                    # 檢查訊息歷史
                    async for message in thread.history(limit=20):
                        if message.author.id == user_id:
                            print(f"✅ 在討論串中找到用戶訊息")
                            return True
                except Exception as e:
                    continue
            
            print(f"❌ 未找到用戶發文")
            return False
                
        except Exception as e:
            print(f"⚠️ 檢查時發生錯誤：{e}")
            return True

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
            await interaction.followup.send("❌ 處理休息請求失敗", ephemeral=True)

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
                    await interaction.followup.send("❌ 處理失敗", ephemeral=True)
                
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("❌ 處理失敗", ephemeral=True)

class WorkActionView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=180)
        self.user_id = user['user_id']
        
        level = user['level']
        actions = LEVELS[level]["actions"]
        actions_used = json.loads(user.get('actions_used', '{}'))
        
        for act in actions:
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
        self.work_channel_id = int(os.getenv("WORK_CHANNEL_ID", 0))

    async def cog_load(self):
        """當 Cog 載入時執行"""
        print("WorkCog 已載入")
        
        # 自動發送工作系統 embed 到指定頻道
        if self.work_channel_id:
            await self.deploy_work_system()

    async def deploy_work_system(self):
        """自動部署工作系統到指定頻道"""
        try:
            await self.bot.wait_until_ready()
            
            channel = self.bot.get_channel(self.work_channel_id)
            if not channel:
                print(f"❌ 找不到工作頻道 ID: {self.work_channel_id}")
                return
            
            # 檢查頻道是否已有工作系統訊息
            has_system = False
            async for message in channel.history(limit=100):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and ("KK園區值勤系統" in embed.title or "詐騙園區" in embed.title):
                            has_system = True
                            print(f"✅ 工作系統已存在於頻道 #{channel.name}，跳過部署")
                            return  # 直接返回，不繼續執行
                
            if not has_system:
                embed = self.create_work_system_embed()
                await channel.send(embed=embed, view=CheckInView())
                print(f"✅ 工作系統已自動部署到 #{channel.name}")
        
        except Exception as e:
            print(f"❌ 自動部署工作系統失敗: {e}")
            traceback.print_exc()

    def create_work_system_embed(self):
        """創建工作系統 embed"""
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
                "• 需先在介紹論壇發文才能打卡\n"
                "• 升級需同時滿足**連續出勤**和**經驗值**\n"
                "• 升級可獲得專屬身分組和升級紅包\n"
                "• 等級越高，日薪和行動收益越高！"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 提示：持續出勤是致富關鍵！")
        embed.timestamp = datetime.utcnow()
        
        return embed

    @commands.Cog.listener()
    async def on_ready(self):
        """當機器人準備就緒時同步命令"""
        try:
            synced = await self.bot.tree.sync()
            print(f"已同步 {len(synced)} 個斜杠命令")
        except Exception as e:
            print(f"同步命令失敗: {e}")

    @discord.app_commands.command(name="work_deploy", description="手動部署工作系統（管理員專用）")
    async def work_deploy(self, interaction: discord.Interaction):
        """手動部署工作系統到當前頻道"""
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 需要管理員權限！", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            embed = self.create_work_system_embed()
            await interaction.channel.send(embed=embed, view=CheckInView())
            await interaction.followup.send("✅ 工作系統已部署到此頻道！", ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 部署失敗: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(WorkCog(bot))
