from discord.ext import commands
import discord
import os
import json
import traceback
import asyncio
import logging
from datetime import datetime, timedelta
from .database import init_db, get_user, update_user, get_all_users
from .work_system import (
    LEVELS, 
    process_checkin, 
    process_work_action,
    check_level_up,
    required_days_for_level,
    get_taiwan_time
)
from status_dashboard import add_log

def get_bot_type(client):
    """根據機器人用戶名確定bot_type"""
    username = str(client.user.name).lower()
    if "shop" in username:
        return "shopbot"
    elif "ui" in username:
        return "uibot"
    else:
        return "bot"

# Configure logger for work module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler if not already configured
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(name)s] %(levelname)s: %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

async def log_error(interaction, error_msg, exception=None):
    """
    Unified error logging function that logs to both console and Discord channel.
    
    Args:
        interaction: Discord interaction object (can be None for non-interaction errors)
        error_msg: Error message to log
        exception: Optional exception object
    """
    # Log to console
    if exception:
        logger.error(f"{error_msg}: {exception}", exc_info=True)
    else:
        logger.error(error_msg)
    
    # Try to send to Discord channel where the interaction occurred
    if interaction and hasattr(interaction, 'channel'):
        try:
            # Create an embed for better visibility
            embed = discord.Embed(
                title="⚠️ 系統錯誤",
                description=error_msg,
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            if exception:
                embed.add_field(name="錯誤詳情", value=f"```{str(exception)[:1000]}```", inline=False)
            
            # Send to channel (not as ephemeral, so admins can see it)
            await interaction.channel.send(embed=embed)
        except Exception as e:
            # If we can't send to Discord, at least log it
            logger.error(f"Failed to send error to Discord channel: {e}")

class CheckInView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CheckInButton())
        self.add_item(RestButton())

class CheckInButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="打卡上班", style=discord.ButtonStyle.success, custom_id="work:checkin")

    async def callback(self, interaction: discord.Interaction):
        # 初始化變數以避免異常處理時的NameError
        user_id = None
        user_name = None
        
        try:
            await interaction.response.defer(ephemeral=True)
            user_id = interaction.user.id
            user_name = interaction.user.name
            
            logger.info(f"\n🕐 【打卡開始】 使用者: {user_name} (ID: {user_id})")
            
            user = get_user(user_id)
            
            # 檢查用戶是否成功取得
            if not user:
                error_msg = f"❌ 打卡失敗: 無法獲取用戶資料 (user: {user_name}, ID: {user_id})"
                logger.error(error_msg)
                await interaction.followup.send("❌ 無法獲取用戶資料，請稍後重試。", ephemeral=True)
                return
            
            logger.info(f"✓ 用戶資料已取得: Lv.{user.get('level')} {user.get('title')} (user: {user_name})")
            
            # 檢查是否已領取工作證
            if not user.get('pre_job'):
                logger.info(f"❌ 打卡失敗: 未領取工作證 (user: {user_name})")
                await interaction.followup.send(
                    "❌ 你還沒領取工作證！請先到置物櫃申請身份證件。\n"
                    "使用 `/我的面板` → 選擇「領取工作證」",
                    ephemeral=True
                )
                return
            
            today = get_taiwan_time().strftime("%Y-%m-%d")
            last_work_date = user.get('last_work_date', None)

            if last_work_date == today:
                logger.info(f"⚠️  打卡失敗: 今日已打卡 (user: {user_name})")
                await interaction.followup.send("你今天已經打過卡囉！", ephemeral=True)
                return

            logger.info(f"💼 開始處理打卡邏輯 (user: {user_name})...")
            embeds_tuple, updated_user, salary_multiplier, daily_story = await process_checkin(
                interaction.user.id, 
                interaction.user,
                interaction.guild
            )
            
            if embeds_tuple and updated_user:
                work_view = WorkActionView(updated_user)
                
                base_salary = LEVELS[updated_user['level']]["salary"]
                actual_salary = int(base_salary * salary_multiplier)
                new_level = updated_user.get('level')
                new_streak = updated_user.get('streak')
                
                salary_percent = int(salary_multiplier * 100)
                if salary_multiplier > 0.8:
                    performance = "🔥大豐收！"
                elif salary_multiplier > 0.5:
                    performance = "✅普通"
                else:
                    performance = "⚠️不太順利..."
                
                # 記錄打卡成功日誌
                logger.info(f"✅ 打卡成功! (user: {user_name})")
                logger.info(f"   薪資: {actual_salary:,} / {base_salary:,} KK幣 ({salary_percent}%)")
                logger.info(f"   等級: Lv.{new_level}")
                logger.info(f"   連勤: {new_streak} 天")
                logger.info(f"   時間: {today}")
                
                # 添加到儀表板日誌
                bot_type = get_bot_type(interaction.client)
                add_log(bot_type, f"✅ {user_name} 打卡成功 - 獲得 {actual_salary:,} KK幣 ({performance})")
                
                checkin_msg = (
                    f"✅ **打卡成功！**\n\n"
                    f"📖 *{daily_story}*\n\n"
                    f"💰 今日薪資：{actual_salary:,} / {base_salary:,} KK幣 "
                    f"({salary_percent}%)\n"
                    f"📊 業績評價：{performance}"
                )
                
                if len(embeds_tuple) == 2:
                    logger.info(f"🎊 用戶升級到 Lv.{new_level} (user: {user_name})")
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
                error_msg = f"❌ 打卡失敗: process_checkin 返回 None (user: {user_name})"
                logger.error(error_msg)
                logger.error(f"   embeds_tuple: {embeds_tuple}")
                logger.error(f"   updated_user: {updated_user}")
                await interaction.followup.send(
                    "❌ 處理打卡失敗，請稍後再試或聯絡管理員", 
                    ephemeral=True
                )

        except asyncio.TimeoutError:
            error_msg = f"❌ 打卡處理超時 (user: {user_name})"
            await log_error(interaction, error_msg)
            try:
                await interaction.followup.send(
                    "❌ 處理超時，請稍後再試", 
                    ephemeral=True
                )
            except:
                pass
        except Exception as e:
            error_msg = f"❌ 打卡發生例外 (User: {user_name}, ID: {user_id})"
            await log_error(interaction, error_msg, e)
            try:
                await interaction.followup.send(
                    "❌ 發生錯誤，請稍後再試或聯絡管理員。", 
                    ephemeral=True
                )
            except:
                pass

class RestButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="休息一天", style=discord.ButtonStyle.secondary, custom_id="work:rest")

    async def callback(self, interaction: discord.Interaction):
        # 初始化變數以避免異常處理時的NameError
        user_id = None
        user_name = None
        
        try:
            await interaction.response.defer(ephemeral=True)
            user_id = interaction.user.id
            user_name = interaction.user.name
            
            logger.info(f"\n🛌 【休息開始】 使用者: {user_name} (ID: {user_id})")
            
            user = get_user(user_id)
            
            # 檢查用戶是否成功取得
            if not user:
                error_msg = f"❌ 休息失敗: 無法獲取用戶資料 (user: {user_name}, ID: {user_id})"
                logger.error(error_msg)
                await interaction.followup.send("❌ 無法獲取用戶資料，請稍後重試。", ephemeral=True)
                return
            
            today = get_taiwan_time().strftime("%Y-%m-%d")
            last_work_date = user.get('last_work_date', None)
            
            if last_work_date == today:
                logger.info(f"⚠️ 休息失敗: 今日已打卡/休息 (user: {user_name})")
                await interaction.followup.send("你今天已經打過卡或選擇休息了！", ephemeral=True)
                return
            
            old_streak = user.get('streak', 0)
            success = update_user(user_id, last_work_date=today, streak=0)
            
            if not success:
                logger.error(f"❌ 休息失敗: 資料保存失敗 (user: {user_name})")
                await interaction.followup.send("❌ 處理休息請求失敗，請稍後再試", ephemeral=True)
                return
            
            logger.info(f"✅ 成功休息 (user: {user_name})")
            logger.info(f"   連勤: {old_streak} → 0")
            
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
            error_msg = f"❌ 休息發生例外 (user: {user_name})"
            await log_error(interaction, error_msg, e)
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
        # 初始化變數以避免異常處理時的NameError
        user_id = None
        user_name = None
        
        try:
            await interaction.response.defer(ephemeral=True)
            user_id = interaction.user.id
            user_name = interaction.user.name
            
            parts = self.custom_id.split(':')
            if len(parts) < 4:
                error_msg = f"❌ 工作行動失敗: 按鈕 ID 格式錯誤 (user: {user_name})"
                logger.error(error_msg)
                await interaction.followup.send("❌ 按鈕 ID 格式錯誤", ephemeral=True)
                return
                
            action = parts[2]
            user_id_check = parts[3]
            
            logger.info(f"\n⚙️  【工作行動】 使用者: {user_name} (ID: {user_id}), 行動: {action}")
            
            if str(user_id) != user_id_check:
                logger.warning(f"❌ 工作行動失敗: 不是該按鈕的擁有者 (user: {user_name})")
                await interaction.followup.send("你不能使用別人的工作按鈕！", ephemeral=True)
                return
            
            current_user = get_user(user_id)
            
            # 檢查用戶是否成功取得
            if not current_user:
                error_msg = f"❌ 工作行動失敗: 無法獲取用戶資料 (user: {user_name}, ID: {user_id})"
                logger.error(error_msg)
                await interaction.followup.send("❌ 無法獲取用戶資料，請稍後重試。", ephemeral=True)
                return
            
            logger.info(f"✓ 使用者資料: Lv.{current_user.get('level')} {current_user.get('title')} (user: {user_name})")
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_work_date = current_user.get('last_work_date', None)
            
            # 改善日期檢查：允許當天和前一天（處理跨日邊界）
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            if last_work_date not in [today, yesterday]:
                logger.warning(f"❌ 工作行動失敗: 按鈕已過期 (user: {user_name}, last_work_date: {last_work_date})")
                await interaction.followup.send(
                    "⚠️ 此工作按鈕已過期，請重新打卡領取今日任務！", 
                    ephemeral=True
                )
                return
            
            logger.info(f"💼 處理工作行動: {action} (user: {user_name})")
            embeds_tuple, updated_user, message = await process_work_action(
                user_id, 
                interaction.user, 
                action
            )
            
            if embeds_tuple and updated_user:
                logger.info(f"✅ 工作行動成功！ (user: {user_name})")
                logger.info(f"   訊息: {message}")
                
                # 添加到儀表板日誌
                bot_type = get_bot_type(interaction.client)
                add_log(bot_type, f"⚙️ {user_name} 執行工作行動: {action}")
                
                await interaction.followup.send(
                    embed=embeds_tuple[0],
                    ephemeral=True
                )
                
                # 創建新的 View 並更新按鈕狀態
                view = WorkActionView(updated_user)
                actions_used = updated_user.get('actions_used', {})
                view.update_button_states(actions_used)
                
                try:
                    # 編輯原始訊息的 embed 和 view
                    await interaction.message.edit(embed=embeds_tuple[1], view=view)
                except discord.NotFound:
                    await interaction.followup.send(
                        embed=embeds_tuple[1],
                        view=view,
                        ephemeral=True
                    )
                except discord.HTTPException as e:
                    logger.warning(f"編輯訊息失敗 (user: {user_name}): {e}")
                    await interaction.followup.send(
                        embed=embeds_tuple[1],
                        view=view,
                        ephemeral=True
                    )
                
                if message:
                    await interaction.followup.send(message, ephemeral=True)
            else:
                error_msg = f"❌ 工作行動失敗: process_work_action 返回 None (user: {user_name})"
                logger.error(error_msg)
                logger.error(f"   訊息: {message}")
                if message:
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 處理失敗", ephemeral=True)
                
        except discord.errors.NotFound:
            logger.warning(f"⚠️ 交互已過期 (user: {user_name})")
            await interaction.followup.send(
                "❌ 交互已過期或機器人剛重啟，請重新打卡以獲取新的工作按鈕", 
                ephemeral=True
            )
        except discord.errors.InteractionResponded:
            # 交互已被回應（可能是重複點擊），靜默處理
            logger.info(f"⚠️ 交互已被回應（可能是重複點擊） (user: {user_name})")
            pass
        except Exception as e:
            error_msg = f"❌ 工作行動發生例外 (user: {user_name})"
            await log_error(interaction, error_msg, e)
            try:
                await interaction.followup.send("❌ 處理失敗，請稍後再試", ephemeral=True)
            except:
                pass

class WorkActionView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user_id = user['user_id']
        
        level = user['level']
        level_info = LEVELS[level]
        actions_used = user.get('actions_used', {})
        
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
        self.work_channel_id = int(os.getenv("WORK_CHANNEL_ID", 0))

    async def cog_load(self):
        logger.info("WorkCog 已載入")
        
        # 先註冊持久化 CheckInView
        self.bot.add_view(CheckInView())
        logger.info("✅ CheckInView 已註冊（持久化）")
        
        # 註冊工作 View（包含今天和昨天的，處理跨日邊界）
        await self.register_persistent_views()
        
        # 使用 task 來確保機器人完全準備好後才部署
        if self.work_channel_id:
            self.bot.loop.create_task(self.deploy_work_system_when_ready())
    
    async def deploy_work_system_when_ready(self):
        """等待機器人完全準備好後再部署工作系統"""
        try:
            await self.bot.wait_until_ready()
            logger.info(f"🤖 機器人已準備好，開始檢查工作頻道 ID: {self.work_channel_id}")
            
            # 額外等待一下確保快取建立
            await asyncio.sleep(2)
            
            await self.deploy_work_system()
        except Exception as e:
            error_msg = "❌ deploy_work_system_when_ready 失敗"
            logger.error(error_msg, exc_info=True)

    async def register_persistent_views(self):
        """註冊並重建所有持久化 View - 改善版"""
        try:
            logger.info("🔄 開始重建工作 View...")
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            all_users = get_all_users()
            
            registered_count = 0
            for user in all_users:
                last_work_date = user.get('last_work_date', None)
                # 為今天和昨天打卡的用戶都註冊（防止跨日問題）
                if last_work_date in [today, yesterday]:
                    try:
                        view = WorkActionView(user)
                        self.bot.add_view(view)
                        registered_count += 1
                    except Exception as e:
                        logger.warning(f"⚠️ 註冊用戶 {user.get('user_id')} 的 View 失敗: {e}")
                        continue
            
            logger.info(f"✅ 已註冊 {registered_count} 個工作 View")
            
        except Exception as e:
            logger.error("⚠️ 註冊工作 View 時發生錯誤", exc_info=True)

    async def deploy_work_system(self):
        """部署工作系統到指定頻道（優先編輯現有訊息）"""
        try:
            channel = self.bot.get_channel(self.work_channel_id)
            if not channel:
                logger.error(f"❌ 找不到工作頻道 ID: {self.work_channel_id}")
                logger.error(f"   請檢查環境變數 WORK_CHANNEL_ID 是否正確設定")
                logger.error(f"   當前值: {self.work_channel_id}")
                return
            
            logger.info(f"✅ 找到工作頻道: #{channel.name} (ID: {channel.id})")
            
            # 尋找現有的工作系統訊息
            existing_message = None
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and ("KK園區值勤系統" in embed.title or "詐騙園區" in embed.title):
                            existing_message = message
                            logger.info(f"📝 找到現有工作系統訊息 (ID: {message.id})")
                            break
                    if existing_message:
                        break
            
            # 建立新的 embed 和 view
            new_embed = self.create_work_system_embed()
            new_view = CheckInView()
            
            if existing_message:
                # 編輯現有訊息
                try:
                    await existing_message.edit(embed=new_embed, view=new_view)
                    logger.info(f"✅ 已更新現有工作系統訊息 (ID: {existing_message.id})")
                except discord.HTTPException as e:
                    logger.warning(f"⚠️ 編輯訊息失敗，將發送新訊息: {e}")
                    sent_message = await channel.send(embed=new_embed, view=new_view)
                    logger.info(f"✅ 工作系統已部署到 #{channel.name} (訊息ID: {sent_message.id})")
            else:
                # 沒有現有訊息，發送新的
                sent_message = await channel.send(embed=new_embed, view=new_view)
                logger.info(f"✅ 工作系統已部署到 #{channel.name} (訊息ID: {sent_message.id})")
        
        except discord.Forbidden:
            logger.error(f"❌ 沒有權限在頻道 {self.work_channel_id} 發送訊息")
        except discord.HTTPException as e:
            logger.error(f"❌ 發送訊息時發生 HTTP 錯誤", exc_info=True)
        except Exception as e:
            logger.error("❌ 部署工作系統失敗", exc_info=True)

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
            weeks_needed = required_days_for_level(lvl) if lvl > 0 else 0
            xp_req = info["xp_required"]
            salary = info['salary']
            actions_count = len(info['actions'])
            
            if lvl == 1:
                upgrade_text = "起始"
            else:
                upgrade_text = f"{weeks_needed}周 + {xp_req:,} XP"
            
            salary_info += (
                f"**Lv.{lvl} {info['title']}**\n"
                f"├ 薪資：0-{salary:,} KK幣/天\n"
                f"├ 升級：{upgrade_text}\n"
                f"└ 行動：{actions_count} 種\n\n"
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
            
            # 檢查用戶是否成功取得
            if not user:
                await interaction.followup.send("❌ 無法獲取用戶資料，請稍後重試。", ephemeral=True)
                return
            
            current_level = user.get('level', 0)
            
            embed = discord.Embed(
                title="📚【詐騙園區 • 行動資料庫】",
                description="所有職位的工作行動詳細資訊",
                color=0x3498db
            )
            
            for lvl, info in LEVELS.items():
                actions_text = ""
                for action in info['actions']:
                    risk_emoji = "🟢" if action['risk'] <= 0.2 else "🟡" if action['risk'] <= 0.4 else "🔴"
                    success_rate = int(action['success_rate'] * 100)
                    base_reward = action['base_reward']
                    xp = action['xp']
                    xp_fail = xp // 4
                    risk_percent = int(action['risk'] * 100)
                    
                    actions_text += (
                        f"{risk_emoji} **{action['name']}**\n"
                        f"  ├ 成功率：{success_rate}%\n"
                        f"  ├ 報酬：0-{base_reward:,} KK幣\n"
                        f"  ├ 經驗：{xp} XP (失敗 {xp_fail} XP)\n"
                        f"  └ 風險：{risk_percent}%\n\n"
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
            
            # 檢查用戶是否成功取得
            if not user:
                await interaction.followup.send("❌ 無法獲取用戶資料，請稍後重試。", ephemeral=True)
                return
            
            level = user.get('level', 0)
            level_info = LEVELS[level]
            
            embed = discord.Embed(
                title=f"📊【{interaction.user.display_name} 的工作統計】",
                color=0xe74c3c
            )
            
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            xp_val = user.get('xp', 0)
            streak_val = user.get('streak', 0)
            kkcoin_val = user.get('kkcoin', 0)
            salary_val = level_info['salary']
            actions_count = len(level_info['actions'])
            
            embed.add_field(
                name="👤 基本資料",
                value=(
                    f"**職稱**：{level_info['title']}\n"
                    f"**等級**：Lv.{level}\n"
                    f"**經驗值**：{xp_val:,} XP\n"
                    f"**連續出勤**：{streak_val} 天"
                ),
                inline=True
            )
            
            embed.add_field(
                name="💰 財務狀況",
                value=(
                    f"**帳戶餘額**：{kkcoin_val:,} KK幣\n"
                    f"**日薪範圍**：0-{salary_val:,} KK幣\n"
                    f"**可用行動**：{actions_count} 種"
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
                    
                    current_days_text = f"{info['current_days']}/{info['required_days']} 天"
                    weeks_text = f"({current_weeks}/{required_weeks} 周)"
                    xp_text = f"{info['current_xp']:,}/{info['required_xp']:,} XP"
                    days_met_text = "✅ 出勤達標！" if info['days_met'] else "⏳ 還需連續出勤"
                    xp_met_text = "✅ 經驗達標！" if info['xp_met'] else "⏳ 還需累積經驗"
                    
                    progress_text = (
                        f"{days_status} **出勤進度**：{current_days_text} {weeks_text}\n"
                        f"{xp_status} **經驗進度**：{xp_text}\n\n"
                        f"{days_met_text}\n"
                        f"{xp_met_text}"
                    )
                
                next_level_info = LEVELS[level + 1]
                next_level_title = next_level_info['title']
                embed.add_field(
                    name=f"🔼 升級進度 → Lv.{level + 1} {next_level_title}",
                    value=progress_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="👑 最高等級",
                    value="你已達到詐騙機房等級！繼續累積財富吧！",
                    inline=False
                )
            
            actions_used = user.get('actions_used', {})
            if actions_used:
                actions_list = [f"✅ {action}" for action in actions_used.keys()]
                actions_status = "\n".join(actions_list)
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

    @discord.app_commands.command(name="work_health", description="檢查工作系統狀態（管理員專用）")
    async def work_health(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 需要管理員權限！", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # 檢查今天打卡的用戶數
            today = datetime.utcnow().strftime("%Y-%m-%d")
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            all_users = get_all_users()
            
            active_today = sum(1 for u in all_users if u.get('last_work_date') == today)
            active_yesterday = sum(1 for u in all_users if u.get('last_work_date') == yesterday)
            
            # 檢查註冊的 View 數量
            try:
                all_views = list(self.bot._connection._view_store._views.values())
                work_action_views = [v for v in all_views if isinstance(v, WorkActionView)]
                view_count = len(work_action_views)
            except:
                view_count = "無法取得"
            
            embed = discord.Embed(
                title="🏥 工作系統健康檢查",
                color=0x00ff00
            )
            
            total_users = len(all_users)
            user_stats = (
                f"**今日打卡**：{active_today} 人\n"
                f"**昨日打卡**：{active_yesterday} 人\n"
                f"**總用戶數**：{total_users} 人"
            )
            embed.add_field(
                name="📊 用戶統計",
                value=user_stats,
                inline=True
            )
            
            # 判斷狀態
            if isinstance(view_count, int):
                status = "✅ 正常" if view_count >= active_today else "⚠️ 可能需要重啟"
                expected_views = f"至少 {active_today}"
            else:
                status = "⚠️ 無法判斷"
                expected_views = "無法取得"
            
            system_stats = (
                f"**註冊的 View**：{view_count}\n"
                f"**預期 View 數**：{expected_views}\n"
                f"**狀態**：{status}"
            )
            embed.add_field(
                name="🔧 系統狀態",
                value=system_stats,
                inline=True
            )
            
            # 檢查是否有異常
            warnings = []
            if isinstance(view_count, int) and view_count < active_today:
                warnings.append("• View 數量少於今日打卡用戶，部分按鈕可能失效")
            if active_today == 0 and active_yesterday > 5:
                warnings.append("• 今日無人打卡但昨日有多人，可能系統異常")
            
            if warnings:
                warnings_text = "\n".join(warnings)
                embed.add_field(
                    name="⚠️ 警告",
                    value=warnings_text,
                    inline=False
                )
            
            embed.add_field(
                name="💡 建議",
                value=(
                    "• 如果 View 數量不足，使用 `/work_rebuild` 重建\n"
                    "• 定期檢查此狀態以確保系統正常運作\n"
                    "• 機器人重啟後會自動重建 View"
                ),
                inline=False
            )
            
            embed.set_footer(text="系統健康檢查")
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 健康檢查失敗: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_rebuild", description="重建工作系統 View（管理員專用，用於修復按鈕失效）")
    async def work_rebuild(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 需要管理員權限！", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # 重新註冊所有 View
            await self.register_persistent_views()
            
            embed = discord.Embed(
                title="🔄 系統重建完成",
                description="已重新註冊所有工作 View，用戶的按鈕應該恢復正常。",
                color=0x00ff00
            )
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            all_users = get_all_users()
            
            active_dates = [today, yesterday]
            active_count = sum(1 for u in all_users if u.get('last_work_date') in active_dates)
            
            rebuild_stats = f"已為 **{active_count}** 位近期活躍用戶重建 View"
            embed.add_field(
                name="📊 重建統計",
                value=rebuild_stats,
                inline=False
            )
            
            embed.set_footer(text="如問題持續，請聯絡開發人員")
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 重建失敗: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_deploy", description="手動部署工作系統（管理員專用）")
    async def work_deploy(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 需要管理員權限！", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # 尋找現有的工作系統訊息
            existing_message = None
            async for message in interaction.channel.history(limit=50):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and ("KK園區值勤系統" in embed.title or "詐騙園區" in embed.title):
                            existing_message = message
                            break
                    if existing_message:
                        break
            
            new_embed = self.create_work_system_embed()
            new_view = CheckInView()
            
            if existing_message:
                # 編輯現有訊息
                try:
                    await existing_message.edit(embed=new_embed, view=new_view)
                    await interaction.followup.send(
                        f"✅ 已更新現有的工作系統訊息！\n📝 訊息ID: {existing_message.id}",
                        ephemeral=True
                    )
                except discord.HTTPException as e:
                    # 編輯失敗，發送新的
                    await interaction.channel.send(embed=new_embed, view=new_view)
                    await interaction.followup.send(
                        f"⚠️ 無法編輯現有訊息，已發送新的工作系統！\n錯誤: {str(e)}",
                        ephemeral=True
                    )
            else:
                # 沒有現有訊息，發送新的
                sent_message = await interaction.channel.send(embed=new_embed, view=new_view)
                await interaction.followup.send(
                    f"✅ 工作系統已部署到此頻道！\n📝 訊息ID: {sent_message.id}",
                    ephemeral=True
                )
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"❌ 部署失敗: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(WorkCog(bot))
