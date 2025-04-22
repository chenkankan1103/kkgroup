import discord
from discord import ui, app_commands
from discord.ext import commands
import os
import json

reaction_role_messages = {}  # msg_id: {emoji: role_id}

# 儲存設定到檔案
def save_reaction_roles(guild_id):
    file_path = f"reaction_roles_{guild_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(reaction_role_messages, f)

# 載入設定檔案
def load_reaction_roles(guild_id):
    global reaction_role_messages
    file_path = f"reaction_roles_{guild_id}.json"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            reaction_role_messages = json.load(f)

class ReactionRoleModal(ui.Modal, title="新增反應角色"):
    emoji = ui.TextInput(label="表情符號 (emoji)", placeholder="例如: 🔥 或 🅰️")
    role_id = ui.TextInput(label="角色 ID", placeholder="請輸入數字")
    channel = ui.TextInput(label="頻道 ID", placeholder="請輸入目標頻道 ID")

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        emoji = str(self.emoji.value)
        role_id = int(self.role_id.value)
        channel_id = int(self.channel.value)
        
        # 嘗試發送訊息到指定頻道
        try:
            target_channel = interaction.guild.get_channel(channel_id)
            if not target_channel:
                await interaction.response.send_message("無效的頻道 ID！", ephemeral=True)
                return

            sent_message = await target_channel.send("請選擇反應角色表情：")
            await sent_message.add_reaction(emoji)

            # 儲存此訊息及對應的角色
            if sent_message.id not in reaction_role_messages:
                reaction_role_messages[sent_message.id] = {}

            reaction_role_messages[sent_message.id][emoji] = role_id
            save_reaction_roles(interaction.guild.id)

            await interaction.response.send_message(f"✅ 設置成功！表情 {emoji} 對應角色 ID {role_id} 並發送至頻道 {target_channel.mention}。", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"錯誤: {e}", ephemeral=True)

class ReactionRoleView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="➕ 新增反應角色", style=discord.ButtonStyle.primary)
    async def add_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ReactionRoleModal())

# 註冊反應角色指令
async def setup_reaction_roles(tree, client):
    command_name = "表情添加身分組"
    # 檢查命令是否已經註冊
    if not any(cmd.name == command_name for cmd in tree.get_commands()):
        @tree.command(name="表情添加身分組", description="設置反應角色 (僅限管理員)")
        @app_commands.checks.has_permissions(administrator=True)
        async def reaction_role_setup(interaction: discord.Interaction):
            await interaction.response.send_modal(ReactionRoleModal())

    # 註冊事件：當有反應時
    @client.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        msg_id = str(payload.message_id)
        if msg_id not in reaction_role_messages:
            return
        if payload.user_id == client.user.id:
            return

        emoji = str(payload.emoji)
        allowed_emojis = reaction_role_messages[msg_id]

        guild = client.get_guild(payload.guild_id)
        if not guild:
            return

        channel = client.get_channel(payload.channel_id)
        member = guild.get_member(payload.user_id)

        if emoji not in allowed_emojis:
            return

        role_id = allowed_emojis.get(emoji)
        if role_id and member:
            role = guild.get_role(role_id)
            if role:
                await member.add_roles(role)

    @client.event
    async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
        msg_id = str(payload.message_id)
        if msg_id not in reaction_role_messages:
            return

        guild = client.get_guild(payload.guild_id)
        if not guild:
            return

        emoji = str(payload.emoji)
        role_id = reaction_role_messages[msg_id].get(emoji)
        if role_id:
            role = guild.get_role(role_id)
            member = guild.get_member(payload.user_id)
            if role and member:
                await member.remove_roles(role)

    load_reaction_roles(client.guilds[0].id)
