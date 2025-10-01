from discord.ext import commands
import discord
import os
import json
import traceback
import asyncio
from datetime import datetime
from commands.work_function.database import init_db, get_user, update_user
from commands.work_function.work_system import (
    LEVELS, 
    process_checkin, 
    process_work_action,
    check_level_up,
    required_days_for_level
)

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
            # 立即回應，避免超時
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_work_date = user.get('last_work_date', None)

            if last_work_date == today:
                await interaction.followup.send("你今天已經打過卡囉！", ephemeral=True)
                return

            # 使用 asyncio.wait_for 避免檢查介紹論壇時超時
            try:
                introduce_check_result = await asyncio.wait_for(
                    self.check_introduction_async(interaction),
                    timeout=8.0  # 8 秒超時
                )
                if not introduce_check_result:
                    return
            except asyncio.TimeoutError:
                print("⚠️ 介紹論壇檢查超時，跳過檢查")
                # 超時就跳過檢查，允許打卡
                pass

            # 處理打卡
            embeds_tuple, updated_user, salary_multiplier, daily_story = await process_checkin(
                interaction.user.id, 
                interaction.user,
                interaction.guild
            )
            
            if embeds_tuple and updated_user:
                work_view = WorkActionView(updated_user)
                
                base_salary = LEVELS[updated_user['level']]["salary"]
                actual_salary = int(base_salary * salary_multiplier)
                
                checkin_msg = (
                    f"✅ **打卡成功！**\n\n"
                    f"📖 *{daily_story}*\n\n"
                    f"💰 今日薪資：{actual_salary:,} / {base_salary:,} KK幣 "
                    f"({int(salary_multiplier*100)}%)\n"
                    f"📊 業績評價：{'🔥大豐收！' if salary_multiplier > 0.8 else '✅普通' if salary_multiplier > 0.5 else '⚠️不太順利...'}"
                )
                
                if len(embeds_tuple) == 2:
                    await interaction.followup.send(
                        content=f"## 🎊 恭喜升級！\n{checkin_msg}", 
                        embed=embeds_tuple[0], 
                        ephemeral=True
                    )
                    await interaction.followup.send(
                        embed=embeds_tuple[1], 
                        view=work_view, 
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        content=checkin_msg,
                        embed=embeds_tuple[0], 
                        view=work_view, 
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "❌ 處理打卡失敗，請稍後再試或聯絡管理員", 
                    ephemeral=True
                )

        except asyncio.TimeoutError:
            print("❌ 打卡處理超時")
            try:
                await interaction.followup.send(
                    "❌ 處理超時，請稍後再試", 
                    ephemeral=True
                )
            except:
                pass
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
        """優化的介紹論壇檢查"""
        try:
            introduce_channel_id = int(os.getenv("INTRODUCE_CHANNEL_ID", 0))
            if not introduce_channel_id:
                return True
            
            introduce_channel = interaction.guild.get_channel(introduce_channel_id)
            if not introduce_channel:
                return True  # 找不到頻道就跳過檢查

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
        except asyncio.TimeoutError:
            print("⚠️ 介紹論壇檢查超時")
            return True  # 超時就允許通過
        except Exception as e:
            print(f"⚠️ 檢查介紹論壇時發生錯誤：{e}")
            return True

    async def check_user_posts_optimized(self, forum_channel, user_id):
        """更快速的發文檢查"""
        try:
            # 只檢查活躍討論串
            active_threads_response = await asyncio.wait_for(
                forum_channel.guild.active_threads(),
                timeout=3.0
            )
            
            for thread in active_threads_response.threads:
                if thread.parent_id != forum_channel.id:
                    continue
                
                # 快速檢查創建者
                if hasattr(thread, 'owner_id') and thread.owner_id == user_id:
                    return True
                
                # 檢查初始訊息
                try:
                    starter_message = await asyncio.wait_for(
                        thread.fetch_message(thread.id),
                        timeout=1.0
                    )
                    if starter_message and starter_message.author.id == user_id:
                        return True
                except:
                    continue
            
            return False
                
        except asyncio.TimeoutError:
            print("⚠️ 發文檢查超時")
            return True  # 超時就允許通過
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
                description=(
                    "你選擇今天休息，連續出勤天數已重置為 0。\n\n"
                    "⚠️ **注意**：升級需要連續出勤達到指定周數，\n"
                    "休息會讓你的升級進度歸零！"
                ),
                color=0xff5555
            )
            
            await interaction.followup.send(embed=rest_embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("❌ 處理休息請求失敗", ephemeral=True)

class WorkActionButton(discord.ui.Button):
    def __init__(self, label, custom_id, risk_level):
        if risk_level <= 0.2:
            style = discord.ButtonStyle.success
        elif risk_level <= 0.4:
            style = discord.ButtonStyle.primary
        else:
            style = discord.ButtonStyle.danger
            
        super().__init__(
            label=label,
            style=style,
            custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            parts = self.custom_id.split(':')
            if len(parts) < 4:
                await interaction.followup.send("❌ 按鈕 ID 格式錯誤", ephemeral=True)
                return
                
            action = parts[2]
            user_id = parts[3]
            
            if str(interaction.user.id) != user_id:
                await interaction.followup.send("你不能使用別人的工作按鈕！", ephemeral=True)
                return
            
            # 先取得當前用戶資料，檢查按鈕是否過期
            current_user = get_user(interaction.user.id)
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_work_date = current_user.get('last_work_date', None)
            
            if last_work_date != today:
                await interaction.followup.send(
                    "⚠️ 此工作按鈕已過期，請重新打卡領取今日任務！", 
                    ephemeral=True
                )
                return
            
            embeds_tuple, updated_user, message = await process_work_action(
                interaction.user.id, 
                interaction.user, 
                action
            )
            
            if embeds_tuple and updated_user:
                await interaction.followup.send(
                    embed=embeds_tuple[0],
                    ephemeral=True
                )
                
                view = WorkActionView(updated_user)
                actions_used = json.loads(updated_user.get('actions_used', '{}'))
                view.update_button_states(actions_used)
                
                try:
                    # 嘗試編輯原始訊息
                    original_message = interaction.message
                    if original_message:
                        await original_message.edit(embed=embeds_tuple[1], view=view)
                except discord.NotFound:
                    # 如果找不到原始訊息，發送新訊息
                    await interaction.followup.send(
                        embed=embeds_tuple[1],
                        view=view,
                        ephemeral=True
                    )
                except discord.HTTPException as e:
                    print(f"編輯訊息失敗: {e}")
                    await interaction.followup.send(
                        embed=embeds_tuple[1],
                        view=view,
                        ephemeral=True
                    )
                
                if message:
                    await interaction.followup.send(message, ephemeral=True)
            else:
                if message:
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 處理失敗", ephemeral=True)
                
        except discord.errors.NotFound:
            await interaction.followup.send(
                "❌ 交互已過期，請重新打卡以獲取新的工作按鈕", 
                ephemeral=True
            )
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send("❌ 處理失敗，請稍後再試", ephemeral=True)
            except:
                pass

class WorkActionView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)  # 設為持久化 View
        self.user_id = user['user_id']
        
        level = user['level']
        level_info = LEVELS[level]
        actions_used = json.loads(user.get('actions_used', '{}'))
        
        for action_data in level_info['actions']:
            button = WorkActionButton(
                label=action_data['name'],
                custom_id=f"work:act:{action_data['name']}:{self.user_id}",
                risk_level=action_data['risk']
            )
            
            if action_data['name'] in actions_used:
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
        print("WorkCog 已載入")
        if self.work_channel_id:
            await self.deploy_work_system()

    async def deploy_work_system(self):
        """自動部署工作系統，會刪除舊的並部署新的"""
        try:
            await self.bot.wait_until_ready()
            
            channel = self.bot.get_channel(self.work_channel_id)
            if not channel:
                print(f"❌ 找不到工作頻道 ID: {self.work_channel_id}")
                return
            
            # 刪除所有舊的工作系統訊息
            deleted_count = 0
            async for message in channel.history(limit=100):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and ("KK園區值勤系統" in embed.title or "詐騙園區" in embed.title):
                            try:
                                await message.delete()
                                deleted_count += 1
                                print(f"🗑️ 已刪除舊的工作系統訊息 (ID: {message.id})")
                            except discord.Forbidden:
                                print(f"⚠️ 沒有權限刪除訊息 (ID: {message.id})")
                            except discord.HTTPException as e:
                                print(f"⚠️ 刪除訊息時發生錯誤: {e}")
                            break
            
            if deleted_count > 0:
                print(f"✅ 已刪除 {deleted_count} 個舊的工作系統訊息")
                await asyncio.sleep(1)  # 等待一秒確保刪除完成
            
            # 部署新的工作系統
            embed = self.create_work_system_embed()
            await channel.send(embed=embed, view=CheckInView())
            print(f"✅ 工作系統已部署到 #{channel.name}")
        
        except Exception as e:
            print(f"❌ 自動部署工作系統失敗: {e}")
            traceback.print_exc()

    def create_work_system_embed(self):
        embed = discord.Embed(
            title="👷‍♀️【KK園區值勤系統】",
            description=(
                "## 歡迎來到詐騙園區！\n"
                "這裡是高風險高報酬的世界，選擇你的道路！\n\n"
                "💰 **浮動薪資**：每日打卡薪資 0-100% 隨機，看你運氣！\n"
                "📈 **快速晉升**：持續出勤 + 累積經驗即可升職！\n"
                "🎲 **風險報酬**：行動有成功率，風險越高報酬越大！\n"
                "🎁 **豐厚獎勵**：升級可獲得額外紅包和新行動！"
            ),
            color=0xf39c12
        )
        
        salary_info = ""
        for lvl, info in LEVELS.items():
            weeks_needed = required_days_for_level(lvl) // 7 if lvl > 1 else 0
            salary_info += (
                f"**Lv.{lvl} {info['title']}**\n"
                f"├ 薪資：0-{info['salary']:,} KK幣/天\n"
                f"├ 升級：{'起始' if lvl == 1 else f'{weeks_needed}周 + {info['xp_required']:,} XP'}\n"
                f"└ 行動：{len(info['actions'])} 種\n\n"
            )
        
        embed.add_field(
            name="💼 職位階級表",
            value=salary_info,
            inline=False
        )
        
        embed.add_field(
            name="🎯 每日流程",
            value=(
                "**1️⃣ 打卡上班**\n"
                "領取浮動日薪 (0-100%) + 經驗值\n"
                "維持連續出勤紀錄\n\n"
                "**2️⃣ 執行行動**\n"
                "選擇工作任務，有成功/失敗機率\n"
                "🟢低風險 🟡中風險 🔴高風險\n\n"
                "**3️⃣ 累積升級**\n"
                "達到連續出勤周數 + 經驗值即可升級"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 重要規則",
            value=(
                "• 需先在介紹論壇發文才能開始工作\n"
                "• 打卡薪資每天隨機 0-100%\n"
                "• 行動有成功率，失敗不給錢但給少量經驗\n"
                "• 升級需**連續出勤指定周數** + **累積經驗值**\n"
                "• 選擇「休息」會重置連勤，影響升級進度\n"
                "• 風險越高的行動，報酬越大但失敗率也高"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 詐騙不是穩賺，但敢拼才會贏！")
        embed.timestamp = datetime.utcnow()
        
        return embed

    @discord.app_commands.command(name="work_info", description="查看詳細的工作行動資訊")
    async def work_info(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            current_level = user.get('level', 1)
            
            embed = discord.Embed(
                title="📚【詐騙園區 • 行動資料庫】",
                description="所有職位的工作行動詳細資訊",
                color=0x3498db
            )
            
            for lvl, info in LEVELS.items():
                actions_text = ""
                for action in info['actions']:
                    risk_emoji = "🟢" if action['risk'] <= 0.2 else "🟡" if action['risk'] <= 0.4 else "🔴"
                    
                    actions_text += (
                        f"{risk_emoji} **{action['name']}**\n"
                        f"  ├ 成功率：{int(action['success_rate']*100)}%\n"
                        f"  ├ 報酬：0-{action['base_reward']:,} KK幣\n"
                        f"  ├ 經驗：{action['xp']} XP (失敗 {action['xp']//4} XP)\n"
                        f"  └ 風險：{int(action['risk']*100)}%\n\n"
                    )
                
                level_marker = " 🔹 **你在這裡**" if lvl == current_level else ""
                
                embed.add_field(
                    name=f"Lv.{lvl} {info['title']}{level_marker}",
                    value=actions_text or "無可用行動",
                    inline=False
                )
            
            embed.add_field(
                name="💡 提示",
                value=(
                    "🟢 **低風險**：成功率高，報酬穩定\n"
                    "🟡 **中風險**：成功率中等，報酬不錯\n"
                    "🔴 **高風險**：成功率低，但報酬豐厚\n\n"
                    "失敗時只能獲得 25% 經驗值，不會獲得金幣。"
                ),
                inline=False
            )
            
            embed.set_footer(text="選擇適合你的風險策略！")
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 查詢失敗: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_stats", description="查看你的工作統計資料")
    async def work_stats(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            level = user.get('level', 1)
            level_info = LEVELS[level]
            
            embed = discord.Embed(
                title=f"📊【{interaction.user.display_name} 的工作統計】",
                color=0xe74c3c
            )
            
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            embed.add_field(
                name="👤 基本資料",
                value=(
                    f"**職稱**：{level_info['title']}\n"
                    f"**等級**：Lv.{level}\n"
                    f"**經驗值**：{user.get('xp', 0):,} XP\n"
                    f"**連續出勤**：{user.get('streak', 0)} 天"
                ),
                inline=True
            )
            
            embed.add_field(
                name="💰 財務狀況",
                value=(
                    f"**帳戶餘額**：{user.get('kkcoin', 0):,} KK幣\n"
                    f"**日薪範圍**：0-{level_info['salary']:,} KK幣\n"
                    f"**可用行動**：{len(level_info['actions'])} 種"
                ),
                inline=True
            )
            
            if level < 5:
                can_level_up, info = check_level_up(user)
                
                if can_level_up:
                    progress_text = "```diff\n+ 已達成升級條件！\n+ 下次打卡即可升級\n```"
                else:
                    required_weeks = info['required_days'] // 7
                    current_weeks = info['current_days'] // 7
                    
                    days_status = "✅" if info['days_met'] else "⏳"
                    xp_status = "✅" if info['xp_met'] else "⏳"
                    
                    progress_text = (
                        f"{days_status} **出勤進度**：{info['current_days']}/{info['required_days']} 天 "
                        f"({current_weeks}/{required_weeks} 周)\n"
                        f"{xp_status} **經驗進度**：{info['current_xp']:,}/{info['required_xp']:,} XP\n\n"
                        f"{'✅ 出勤達標！' if info['days_met'] else '⏳ 還需連續出勤'}\n"
                        f"{'✅ 經驗達標！' if info['xp_met'] else '⏳ 還需累積經驗'}"
                    )
                
                next_level_info = LEVELS[level + 1]
                embed.add_field(
                    name=f"🔼 升級進度 → Lv.{level + 1} {next_level_info['title']}",
                    value=progress_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="👑 最高等級",
                    value="你已達到詐騙機房等級！繼續累積財富吧！",
                    inline=False
                )
            
            actions_used = json.loads(user.get('actions_used', '{}'))
            if actions_used:
                actions_status = "\n".join([f"✅ {action}" for action in actions_used.keys()])
            else:
                actions_status = "尚未執行任何行動"
            
            embed.add_field(
                name="🎯 今日行動紀錄",
                value=actions_status,
                inline=False
            )
            
            embed.set_footer(text="持續努力，財富自由不是夢！")
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 查詢失敗: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_deploy", description="手動部署工作系統（管理員專用）")
    async def work_deploy(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 需要管理員權限！", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # 先刪除舊的工作系統訊息
            deleted_count = 0
            async for message in interaction.channel.history(limit=100):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and ("KK園區值勤系統" in embed.title or "詐騙園區" in embed.title):
                            try:
                                await message.delete()
                                deleted_count += 1
                            except:
                                pass
                            break
            
            # 部署新的工作系統
            embed = self.create_work_system_embed()
            await interaction.channel.send(embed=embed, view=CheckInView())
            
            result_msg = f"✅ 工作系統已部署到此頻道！"
            if deleted_count > 0:
                result_msg += f"\n🗑️ 已刪除 {deleted_count} 個舊的工作系統訊息"
            
            await interaction.followup.send(result_msg, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 部署失敗: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(WorkCog(bot))
