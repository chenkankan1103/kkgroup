from discord.ext import commands
import discord
import os
import json
import traceback
import asyncio
from datetime import datetime, timedelta
from .database import init_db, get_user, update_user, get_all_users
from .work_system import (
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
        super().__init__(label="??????", style=discord.ButtonStyle.success, custom_id="work:checkin")

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            
            # ???????????????
            if not user:
                await interaction.followup.send("?????????????????????????", ephemeral=True)
                return
            
            # ???????????????
            if not user.get('pre_job'):
                await interaction.followup.send(
                    "????????????????????????????????????\n"
                    "??? `/??????` ?????????????????",
                    ephemeral=True
                )
                return
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_work_date = user.get('last_work_date', None)

            if last_work_date == today:
                await interaction.followup.send("???????????????", ephemeral=True)
                return

            try:
                introduce_check_result = await asyncio.wait_for(
                    self.check_introduction_async(interaction),
                    timeout=8.0
                )
                # ??? #3: ??????????????????????????????
                if not introduce_check_result:
                    return
            except asyncio.TimeoutError:
                print("?????????????????????")
                # ??????????????????????pass
                await interaction.followup.send(
                    "??? ??????????????????????????????",
                    ephemeral=True
                )
                return

            embeds_tuple, updated_user, salary_multiplier, daily_story = await process_checkin(
                interaction.user.id, 
                interaction.user,
                interaction.guild
            )
            
            if embeds_tuple and updated_user:
                work_view = WorkActionView(updated_user)
                
                base_salary = LEVELS[updated_user['level']]["salary"]
                actual_salary = int(base_salary * salary_multiplier)
                
                salary_percent = int(salary_multiplier * 100)
                if salary_multiplier > 0.8:
                    performance = "????????"
                elif salary_multiplier > 0.5:
                    performance = "??????"
                else:
                    performance = "?????????..."
                
                checkin_msg = (
                    f"??**????????*\n\n"
                    f"?? *{daily_story}*\n\n"
                    f"?? ????????actual_salary:,} / {base_salary:,} KK??"
                    f"({salary_percent}%)\n"
                    f"?? ????????performance}"
                )
                
                if len(embeds_tuple) == 2:
                    await interaction.followup.send(
                        content=f"## ?? ????????n{checkin_msg}", 
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
                    "?????????????????????????????", 
                    ephemeral=True
                )

        except asyncio.TimeoutError:
            print("???????????")
            try:
                await interaction.followup.send(
                    "?????????????????", 
                    ephemeral=True
                )
            except:
                pass
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    "????????????????????????????",
                    ephemeral=True
                )
            except:
                pass

    async def check_introduction_async(self, interaction):
        try:
            introduce_channel_id = int(os.getenv("INTRODUCE_CHANNEL_ID", 0))
            if not introduce_channel_id:
                return True
            
            introduce_channel = interaction.guild.get_channel(introduce_channel_id)
            if not introduce_channel:
                return True

            if not isinstance(introduce_channel, discord.ForumChannel):
                return True

            has_posted = await self.check_user_posts_optimized(introduce_channel, interaction.user.id)
            
            if not has_posted:
                await interaction.followup.send(
                    "??? ????????????????????????????????????\n"
                    f"?? ????????introduce_channel.mention}", 
                    ephemeral=True
                )
                return False
            
            return True
        except asyncio.TimeoutError:
            print("??? ????????????")
            return True
        except Exception as e:
            print(f"??? ??????????????????{e}")
            return True

    async def check_user_posts_optimized(self, forum_channel, user_id):
        try:
            active_threads_response = await asyncio.wait_for(
                forum_channel.guild.active_threads(),
                timeout=3.0
            )
            
            for thread in active_threads_response.threads:
                if thread.parent_id != forum_channel.id:
                    continue
                
                if hasattr(thread, 'owner_id') and thread.owner_id == user_id:
                    return True
                
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
            print("??? ?????????")
            return True
        except Exception as e:
            print(f"??? ????????????{e}")
            return True

class RestButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="???????", style=discord.ButtonStyle.secondary, custom_id="work:rest")

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            
            # ???????????????
            if not user:
                await interaction.followup.send("?????????????????????????", ephemeral=True)
                return
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_work_date = user.get('last_work_date', None)
            
            if last_work_date == today:
                await interaction.followup.send("???????????????????????", ephemeral=True)
                return
            
            update_user(interaction.user.id, last_work_date=today, streak=0)
            
            rest_embed = discord.Embed(
                title="?? ??????",
                description=(
                    "??????????????????????????? 0??n\n"
                    "??? **???**?????????????????????????n"
                    "????????????????????"
                ),
                color=0xff5555
            )
            
            await interaction.followup.send(embed=rest_embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("??????????????", ephemeral=True)

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
                await interaction.followup.send("????? ID ??????", ephemeral=True)
                return
                
            action = parts[2]
            user_id = parts[3]
            
            if str(interaction.user.id) != user_id:
                await interaction.followup.send("????????????????????", ephemeral=True)
                return
            
            current_user = get_user(interaction.user.id)
            
            # ???????????????
            if not current_user:
                await interaction.followup.send("?????????????????????????", ephemeral=True)
                return
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_work_date = current_user.get('last_work_date', None)
            
            # ???????????????????????????????????            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            if last_work_date not in [today, yesterday]:
                await interaction.followup.send(
                    "??? ????????????????????????????????",
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
                
                # ?????? View ???????????                view = WorkActionView(updated_user)
                actions_used = json.loads(updated_user.get('actions_used', '{}'))
                view.update_button_states(actions_used)
                
                try:
                    # ???????????embed ??view
                    await interaction.message.edit(embed=embeds_tuple[1], view=view)
                except discord.NotFound:
                    await interaction.followup.send(
                        embed=embeds_tuple[1],
                        view=view,
                        ephemeral=True
                    )
                except discord.HTTPException as e:
                    print(f"?????????: {e}")
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
                    await interaction.followup.send("????????", ephemeral=True)
                
        except discord.errors.NotFound:
            await interaction.followup.send(
                "???????????????????????????????????????????",
                ephemeral=True
            )
        except discord.errors.InteractionResponded:
            # ??????????????????????????????
            pass
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.followup.send("?????????????????", ephemeral=True)
            except:
                pass

class WorkActionView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
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
        self.work_channel_id = int(os.getenv("WORK_CHANNEL_ID", 0))

    async def cog_load(self):
        print("WorkCog ?????")
        
        # ????????? CheckInView
        self.bot.add_view(CheckInView())
        print("??CheckInView ????????????")
        
        # ?????? View??????????????????????????        await self.register_persistent_views()
        
        # ??? task ???????????????????????        if self.work_channel_id:
            self.bot.loop.create_task(self.deploy_work_system_when_ready())
    
    async def deploy_work_system_when_ready(self):
        """???????????????????????????"""
        try:
            await self.bot.wait_until_ready()
            print(f"?? ???????????????????????? ID: {self.work_channel_id}")
            
            # ???????????????????            await asyncio.sleep(2)
            
            await self.deploy_work_system()
        except Exception as e:
            print(f"??deploy_work_system_when_ready ???: {e}")
            traceback.print_exc()

    async def register_persistent_views(self):
        """??????????????? View - ?????""
        try:
            print("?? ????????? View...")
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            all_users = get_all_users()
            
            registered_count = 0
            for user in all_users:
                last_work_date = user.get('last_work_date', None)
                # ?????????????????????????????????
                if last_work_date in [today, yesterday]:
                    try:
                        view = WorkActionView(user)
                        self.bot.add_view(view)
                        registered_count += 1
                    except Exception as e:
                        print(f"??? ?????? {user.get('user_id')} ??View ???: {e}")
                        continue
            
            print(f"???????{registered_count} ?????View")
            
        except Exception as e:
            print(f"??? ?????? View ???????? {e}")
            traceback.print_exc()

    async def deploy_work_system(self):
        """????????????????????????????????""
        try:
            channel = self.bot.get_channel(self.work_channel_id)
            if not channel:
                print(f"?????????????ID: {self.work_channel_id}")
                print(f"   ???????????WORK_CHANNEL_ID ?????????")
                print(f"   ????? {self.work_channel_id}")
                return
            
            print(f"???????????: #{channel.name} (ID: {channel.id})")
            
            # ?????????????????            existing_message = None
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and ("KK?????????" in embed.title or "??????" in embed.title):
                            existing_message = message
                            print(f"?? ??????????????? (ID: {message.id})")
                            break
                    if existing_message:
                        break
            
            # ?????? embed ??view
            new_embed = self.create_work_system_embed()
            new_view = CheckInView()
            
            if existing_message:
                # ?????????
                try:
                    await existing_message.edit(embed=new_embed, view=new_view)
                    print(f"???????????????????(ID: {existing_message.id})")
                except discord.HTTPException as e:
                    print(f"??? ????????????????????: {e}")
                    sent_message = await channel.send(embed=new_embed, view=new_view)
                    print(f"?????????????? #{channel.name} (???ID: {sent_message.id})")
            else:
                # ?????????????????                sent_message = await channel.send(embed=new_embed, view=new_view)
                print(f"?????????????? #{channel.name} (???ID: {sent_message.id})")
        
        except discord.Forbidden:
            print(f"?????????????{self.work_channel_id} ???????")
        except discord.HTTPException as e:
            print(f"????????????? HTTP ???: {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"??????????????: {e}")
            traceback.print_exc()

    def create_work_system_embed(self):
        embed = discord.Embed(
            title="?????????K???????????",
            description=(
                "## ??????????????n"
                "??????????????????????????????\n\n"
                "?? **??????**???????????0-100% ????????????\n"
                "?? **???????*????????+ ??????????????n"
                "?? **??????**??????????????????????????n"
                "?? **??????**???????????????????????"
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
                upgrade_text = "???"
            else:
                upgrade_text = f"{weeks_needed}??+ {xp_req:,} XP"
            
            salary_info += (
                f"**Lv.{lvl} {info['title']}**\n"
                f"???????-{salary:,} KK????n"
                f"???????upgrade_text}\n"
                f"???????actions_count} ??n\n"
            )
        
        embed.add_field(
            name="?? ????????",
            value=salary_info,
            inline=False
        )
        
        embed.add_field(
            name="?? ??????",
            value=(
                "**1??? ??????**\n"
                "????????? (0-100%) + ?????n"
                "?????????????n\n"
                "**2??? ??????**\n"
                "???????????????/??????\n"
                "?????????????????????n\n"
                "**3??? ??????**\n"
                "???????????? + ???????????"
            ),
            inline=False
        )
        
        embed.add_field(
            name="??? ??????",
            value=(
                "?????????????????????????\n"
                "?????????????? 0-100%\n"
                "?????????????????????????????\n"
                "???????**????????????** + **????????*\n"
                "??????????????????????????????\n"
                "?????????????????????????????"
            ),
            inline=False
        )
        
        embed.set_footer(text="?? ?????????????????????")
        embed.timestamp = datetime.utcnow()
        
        return embed

    @discord.app_commands.command(name="work_info", description="?????????????????")
    async def work_info(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            
            # ???????????????
            if not user:
                await interaction.followup.send("?????????????????????????", ephemeral=True)
                return
            
            current_level = user.get('level', 0)
            
            embed = discord.Embed(
                title="?????????? ????????????",
                description="????????????????????",
                color=0x3498db
            )
            
            for lvl, info in LEVELS.items():
                actions_text = ""
                for action in info['actions']:
                    risk_emoji = "??" if action['risk'] <= 0.2 else "??" if action['risk'] <= 0.4 else "??"
                    success_rate = int(action['success_rate'] * 100)
                    base_reward = action['base_reward']
                    xp = action['xp']
                    xp_fail = xp // 4
                    risk_percent = int(action['risk'] * 100)
                    
                    actions_text += (
                        f"{risk_emoji} **{action['name']}**\n"
                        f"  ????????{success_rate}%\n"
                        f"  ???????-{base_reward:,} KK??n"
                        f"  ???????xp} XP (??? {xp_fail} XP)\n"
                        f"  ???????risk_percent}%\n\n"
                    )
                
                level_marker = " ?? **??????**" if lvl == current_level else ""
                embed.add_field(
                    name=f"Lv.{lvl} {info['title']}{level_marker}",
                    value=actions_text or "????????",
                    inline=False
                )
            
            embed.add_field(
                name="?? ???",
                value=(
                    "?? **?????*???????????????\n"
                    "?? **?????*?????????????????n"
                    "?? **?????*?????????????????n\n"
                    "???????????25% ?????????????????"
                ),
                inline=False
            )
            
            embed.set_footer(text="?????????????????")
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"????????: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_stats", description="???????????????")
    async def work_stats(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user = get_user(interaction.user.id)
            
            # ???????????????
            if not user:
                await interaction.followup.send("?????????????????????????", ephemeral=True)
                return
            
            level = user.get('level', 0)
            level_info = LEVELS[level]
            
            embed = discord.Embed(
                title=f"{interaction.user.display_name} ??????????",
                color=0xe74c3c
            )
            
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            xp_val = user.get('xp', 0)
            streak_val = user.get('streak', 0)
            kkcoin_val = user.get('kkcoin', 0)
            salary_val = level_info['salary']
            actions_count = len(level_info['actions'])
            
            embed.add_field(
                name="?? ??????",
                value=(
                    f"**???**??{level_info['title']}\n"
                    f"**???**??Lv.{level}\n"
                    f"**?????*??{xp_val:,} XP\n"
                    f"**??????**??{streak_val} ??"
                ),
                inline=True
            )
            
            embed.add_field(
                name="?? ???????",
                value=(
                    f"**??????**??{kkcoin_val:,} KK??n"
                    f"**??????**??-{salary_val:,} KK??n"
                    f"**??????**??{actions_count} ??"
                ),
                inline=True
            )
            
            if level < 5:
                can_level_up, info = check_level_up(user)
                
                if can_level_up:
                    progress_text = "```diff\n+ ????????????\n+ ????????????\n```"
                else:
                    required_weeks = info['required_days'] // 7
                    current_weeks = info['current_days'] // 7
                    
                    days_status = "✅" if info['days_met'] else "❌"
                    xp_status = "✅" if info['xp_met'] else "❌"
                    
                    current_days_text = f"{info['current_days']}/{info['required_days']} 天"
                    weeks_text = f"({current_weeks}/{required_weeks} 週)"
                    xp_text = f"{info['current_xp']:,}/{info['required_xp']:,} XP"
                    days_met_text = "達到天數要求" if info['days_met'] else "未達到天數要求"
                    xp_met_text = "達到經驗要求" if info['xp_met'] else "未達到經驗要求"
                    
                    progress_text = (
                        f"{days_status} **天數進度**：{current_days_text} {weeks_text}\n"
                        f"{xp_status} **經驗進度**：{xp_text}\n\n"
                        f"{days_met_text}\n"
                        f"{xp_met_text}"
                    )
                
                next_level_info = LEVELS[level + 1]
                next_level_title = next_level_info['title']
                embed.add_field(
                    name=f"?? ?????? ??Lv.{level + 1} {next_level_title}",
                    value=progress_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="?? ???????",
                    value="?????????????????????????????",
                    inline=False
                )
            
            actions_used = json.loads(user.get('actions_used', '{}'))
            if actions_used:
                actions_list = [f"??{action}" for action in actions_used.keys()]
                actions_status = "\n".join(actions_list)
            else:
                actions_status = "????????????"
            
            embed.add_field(
                name="?? ??????????",
                value=actions_status,
                inline=False
            )
            
            embed.set_footer(text="????????????????????)
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"????????: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_health", description="???????????????????????")
    async def work_health(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("???????????????, ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # ???????????????
            today = datetime.utcnow().strftime("%Y-%m-%d")
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            all_users = get_all_users()
            
            active_today = sum(1 for u in all_users if u.get('last_work_date') == today)
            active_yesterday = sum(1 for u in all_users if u.get('last_work_date') == yesterday)
            
            # ????????View ???
            try:
                all_views = list(self.bot._connection._view_store._views.values())
                work_action_views = [v for v in all_views if isinstance(v, WorkActionView)]
                view_count = len(work_action_views)
            except:
                view_count = "??????"
            
            embed = discord.Embed(
                title="?? ????????????",
                color=0x00ff00
            )
            
            total_users = len(all_users)
            user_stats = (
                f"**??????**??active_today} ??n"
                f"**??????**??active_yesterday} ??n"
                f"**??????**??total_users} ??
            )
            embed.add_field(
                name="?? ??????",
                value=user_stats,
                inline=True
            )
            
            # ???????            if isinstance(view_count, int):
                status = "?????" if view_count >= active_today else "??? ??????????
                expected_views = f"??? {active_today}"
            else:
                status = "??? ??????"
                expected_views = "??????"
            
            system_stats = (
                f"**?????View**??view_count}\n"
                f"**??? View ??*??expected_views}\n"
                f"**????*??status}"
            )
            embed.add_field(
                name="?? ???????",
                value=system_stats,
                inline=True
            )
            
            # ???????????            warnings = []
            if isinstance(view_count, int) and view_count < active_today:
                warnings.append("??View ?????????????????????????????)
            if active_today == 0 and active_yesterday > 5:
                warnings.append("???????????????????????????????)
            
            if warnings:
                warnings_text = "\n".join(warnings)
                embed.add_field(
                    name="??? ???",
                    value=warnings_text,
                    inline=False
                )
            
            embed.add_field(
                name="?? ???",
                value=(
                    "????? View ???????????`/work_rebuild` ???\n"
                    "??????????????????????????\n"
                    "???????????????????View"
                ),
                inline=False
            )
            
            embed.set_footer(text="?????????")
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"???????????: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_rebuild", description="????????? View????????????????????????")
    async def work_rebuild(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("???????????????, ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # ??????????View
            await self.register_persistent_views()
            
            embed = discord.Embed(
                title="?? ?????????",
                description="??????????????View????????????????????",
                color=0x00ff00
            )
            
            today = datetime.utcnow().strftime("%Y-%m-%d")
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            all_users = get_all_users()
            
            active_dates = [today, yesterday]
            active_count = sum(1 for u in all_users if u.get('last_work_date') in active_dates)
            
            rebuild_stats = f"??? **{active_count}** ??????????????View"
            embed.add_field(
                name="?? ??????",
                value=rebuild_stats,
                inline=False
            )
            
            embed.set_footer(text="????????????????????)
            embed.timestamp = datetime.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"????????: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="work_deploy", description="???????????????????????)
    async def work_deploy(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("???????????????, ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # ?????????????????            existing_message = None
            async for message in interaction.channel.history(limit=50):
                if message.author == self.bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and ("KK?????????" in embed.title or "??????" in embed.title):
                            existing_message = message
                            break
                    if existing_message:
                        break
            
            new_embed = self.create_work_system_embed()
            new_view = CheckInView()
            
            if existing_message:
                # ?????????
                try:
                    await existing_message.edit(embed=new_embed, view=new_view)
                    await interaction.followup.send(
                        f"??????????????????????n?? ???ID: {existing_message.id}",
                        ephemeral=True
                    )
                except discord.HTTPException as e:
                    # ??????????????                    await interaction.channel.send(embed=new_embed, view=new_view)
                    await interaction.followup.send(
                        f"??? ?????????????????????????????\n???: {str(e)}",
                        ephemeral=True
                    )
            else:
                # ?????????????????                sent_message = await interaction.channel.send(embed=new_embed, view=new_view)
                await interaction.followup.send(
                    f"????????????????????\n?? ???ID: {sent_message.id}",
                    ephemeral=True
                )
            
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"????????: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(WorkCog(bot))
