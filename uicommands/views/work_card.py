import discord
import datetime
from db_adapter import set_user_field, get_user


class WorkCardModal(discord.ui.Modal):
    """員工證信息表單"""
    title = "領取員工證"
    
    def __init__(self, cog, user_id: int):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        
        # 5 個輸入欄
        self.pre_job = discord.ui.TextInput(
            label="入園前身份",
            placeholder="如：上班族、學生、無業...",
            max_length=30,
            required=True
        )
        self.hobby = discord.ui.TextInput(
            label="業餘愛好",
            placeholder="如：玩遊戲、看動漫、健身...",
            max_length=50,
            required=True
        )
        
        self.add_item(self.pre_job)
        self.add_item(self.hobby)
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交表單"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 保存到資料庫
            set_user_field(self.user_id, 'pre_job', str(self.pre_job.value))
            set_user_field(self.user_id, 'hobby', str(self.hobby.value))
            set_user_field(self.user_id, 'work_card_enabled', 1)
            
            # 生成工作證 embed
            user_data = get_user(self.user_id)
            user_obj = await self.cog.bot.fetch_user(self.user_id)
            
            embed = await self.create_work_card_embed(user_data, user_obj)
            view = WorkCardEditView(self.cog, self.user_id)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            await interaction.followup.send("✅ 員工證已領取！該卡片已保存到你的置物櫃。", ephemeral=True)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 提交失敗：{str(e)[:100]}", ephemeral=True)
    
    async def create_work_card_embed(self, user_data, user_obj):
        """生成工作證卡片 embed"""
        from commands.work_function.work_system import LEVELS
        
        level = user_data.get('level', 0)
        level_info = LEVELS.get(level, {})
        xp = user_data.get('xp', 0)
        streak = user_data.get('streak', 0)
        
        # 計算下一級 XP
        next_level_xp = LEVELS.get(level + 1, {}).get('xp_required', xp) if level < 6 else xp
        
        # 生成員工編號
        user_id_suffix = str(self.user_id)[-6:].zfill(6)
        
        embed = discord.Embed(
            title="【 KK 園區聯合管理處 - 員工通行證 】",
            color=discord.Color.gold(),
            description=f"姓名：{user_obj.name}\n" +
                       f"員工編號：#{user_id_suffix}\n" +
                       f"職級：{level_info.get('title', '未知')} (Lv.{level})\n" +
                       f"業績：{xp:,} / {next_level_xp:,} XP"
        )
        
        embed.add_field(
            name="【 員工背後故事 】",
            value=(
                f"❖ 入園前身份：{user_data.get('pre_job', 'N/A')}\n"
                f"❖ 業餘愛好：{user_data.get('hobby', 'N/A')}"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 入職統計",
            value=f"連勤天數：{streak} 天 🔥",
            inline=False
        )
        
        embed.set_footer(text="🎫 此證件為 KK 園區正式員工的象徵 | 妥善保管，勿得轉讓")
        embed.timestamp = datetime.datetime.utcnow()
        
        return embed


class WorkCardEditView(discord.ui.View):
    """工作證修改選項視圖"""
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
    
    @discord.ui.button(label="修改設定", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="work_card_edit")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """修改工作證信息"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的員工證！", ephemeral=True)
            return
        
        await interaction.response.send_modal(WorkCardModal(self.cog, self.user_id))


class WorkCardActionView(discord.ui.View):
    """已有工作證時的操作視圖"""
    def __init__(self, cog, user_id: int, user_data: dict):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.user_data = user_data
    
    @discord.ui.button(label="查看我的員工證", style=discord.ButtonStyle.success, emoji="🎫", custom_id="view_my_card")
    async def view_card_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """查看員工證"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 这不是你的員工證！", ephemeral=True)
            return
        
        try:
            user_obj = await self.cog.bot.fetch_user(self.user_id)
            embed = await WorkCardModal(self.cog, self.user_id).create_work_card_embed(self.user_data, user_obj)
            view = WorkCardEditView(self.cog, self.user_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 錯誤：{str(e)[:100]}", ephemeral=True)
    
    @discord.ui.button(label="修改設定", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="modify_card_settings")
    async def modify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """修改員工證設定"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的員工證！", ephemeral=True)
            return
        
        await interaction.response.send_modal(WorkCardModal(self.cog, self.user_id))
