import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import json
import os
import asyncio
import requests
from dotenv import load_dotenv

# 載入 .env 文件中的環境變數
load_dotenv()

SETTINGS_DIR = "reaction_roles"
os.makedirs(SETTINGS_DIR, exist_ok=True)

PUNISHMENT_ROLE_ID = int(os.getenv("MUTE_ROLE_ID"))  # 懲罰用角色 ID
VIOLATION_THRESHOLD = 3  # 違規次數門檻
AI_API_URL = os.getenv("AI_API_URL")  # AI API URL
AI_API_KEY = os.getenv("AI_API_KEY")  # AI API 金鑰

# 儲存與載入反應角色設定
def load_reaction_roles(guild_id):
    """從檔案載入反應角色資料"""
    path = f"{SETTINGS_DIR}/reaction_roles_{guild_id}.json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_reaction_roles(guild_id, data):
    """將反應角色資料儲存至檔案"""
    path = f"{SETTINGS_DIR}/reaction_roles_{guild_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def generate_ai_response(prompt):
    """向 AI API 發送請求並獲取回應"""
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "system", "content": prompt}],
        "max_tokens": 50,
    }
    try:
        response = requests.post(AI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "⚠️ 無法生成回應，請稍後再試。")
    except requests.RequestException as e:
        print(f"❌ AI API 請求失敗: {e}")
        return "⚠️ 無法生成回應，請稍後再試。"

class RoleButton(Button):
    def __init__(self, role: discord.Role, label: str, emoji: str = None):
        super().__init__(label=label, style=discord.ButtonStyle.primary, emoji=emoji)
        self.role = role

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        if self.role in member.roles:
            # 如果成員已經有該角色，則移除角色
            await member.remove_roles(self.role, reason="移除角色")
            await interaction.response.send_message(f"❌ 已移除您的身分組：{self.role.name}", ephemeral=True)
        else:
            # 如果成員尚未有該角色，則添加角色
            await member.add_roles(self.role, reason="新增角色")
            await interaction.response.send_message(f"✅ 已新增您的身分組：{self.role.name}", ephemeral=True)

class RoleSelectionView(View):
    def __init__(self, roles):
        super().__init__(timeout=None)  # 設定為永不過期
        for role, config in roles.items():
            self.add_item(RoleButton(role=role, label=config["label"], emoji=config.get("emoji")))

class ReactionRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}
        self.violations = {}  # 記錄違規次數 {guild_id: {user_id: count}}

    async def cog_load(self):
        """在模組載入時初始化快取"""
        for guild in self.bot.guilds:
            self.cache[guild.id] = load_reaction_roles(guild.id)

    def update_guild_cache(self, guild_id):
        """更新快取並儲存至檔案"""
        save_reaction_roles(guild_id, self.cache[guild_id])

    async def punish_member(self, guild, member):
        """懲罰用戶並清空違規次數"""
        role = guild.get_role(PUNISHMENT_ROLE_ID)

        if not role:
            print("❌ 無法找到懲罰角色，請確認設定是否正確。")
            return

        # 添加懲罰角色
        await member.add_roles(role, reason="多次私自點擊反應表情")
        try:
            await member.send("⚠️ 您因多次違規已被關禁閉！")
        except discord.Forbidden:
            print(f"❌ 無法傳送私訊給用戶 {member.name}。")

        # 等待 3 分鐘後移除懲罰角色
        await asyncio.sleep(180)
        await member.remove_roles(role, reason="懲罰結束")
        self.violations[guild.id][member.id] = 0  # 清空違規次數

    @app_commands.command(name="新增反應角色", description="新增一個表情符號與角色的對應")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_reaction_role(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role
    ):
        """
        新增表情符號與角色對應
        - message_id: 訊息 ID
        - emoji: 表情符號
        - role: 角色
        """
        guild_id = interaction.guild_id
        channel = interaction.channel

        # 獲取目標訊息
        try:
            message = await channel.fetch_message(int(message_id))
        except discord.NotFound:
            await interaction.response.send_message("❌ 找不到該訊息，請檢查訊息 ID 是否正確。", ephemeral=True)
            return

        # 添加反應角色配置
        self.cache.setdefault(guild_id, {})
        self.cache[guild_id].setdefault(message_id, {})
        self.cache[guild_id][message_id][emoji] = role.id

        # 在訊息上添加表情符號
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            await interaction.response.send_message(f"❌ 無法添加表情符號：{emoji}，請確保其為有效表情。", ephemeral=True)
            return

        # 更新快取
        self.update_guild_cache(guild_id)
        await interaction.response.send_message(f"✅ 已成功新增表情符號 {emoji} 與角色 {role.name} 的對應！", ephemeral=True)

    @app_commands.command(name="自動發送反應角色訊息", description="讓機器人發送訊息並附加反應角色")
    @app_commands.checks.has_permissions(administrator=True)
    async def auto_post_reaction_roles(
        self,
        interaction: discord.Interaction,
        content: str,
        emoji_role_pairs: str
    ):
        """
        讓機器人發送訊息並附加反應角色
        """
        guild_id = interaction.guild_id
        channel = interaction.channel

        # 發送訊息
        message = await channel.send(content)

        # 處理表情符號與角色對應
        pairs = emoji_role_pairs.split(",")
        added_roles = []
        for pair in pairs:
            try:
                emoji, role_name = pair.split(":")
                emoji = emoji.strip()
                role_name = role_name.strip()

                # 獲取角色
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if not role:
                    await interaction.response.send_message(f"❌ 找不到角色：{role_name}", ephemeral=True)
                    return

                # 添加反應角色配置
                self.cache.setdefault(guild_id, {})
                self.cache[guild_id].setdefault(str(message.id), {})
                self.cache[guild_id][str(message.id)][emoji] = role.id

                # 在訊息上添加表情符號
                await message.add_reaction(emoji)
                added_roles.append(f"{emoji} -> {role.name}")
            except ValueError:
                await interaction.response.send_message(f"❌ 格式錯誤，請確保格式為 '表情符號:角色名稱'，用逗號分隔。", ephemeral=True)
                return

        # 更新快取
        self.update_guild_cache(guild_id)
        added_roles_str = "\n".join(added_roles)
        await interaction.response.send_message(f"✅ 訊息已發送，並成功新增以下表情符號與角色對應：\n{added_roles_str}", ephemeral=True)

    @app_commands.command(name="發送按鈕角色訊息", description="發送一條帶有互動按鈕的身分組訊息")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_button_roles(
        self,
        interaction: discord.Interaction,
        content: str,
        roles: str,  # 格式：`玩家:role_id1,學習者:role_id2`
        emojis: str = None  # 格式：`🎮,📚`
    ):
        """
        發送一條帶有互動按鈕的身分組訊息
        """
        roles_data = roles.split(",")
        emojis_data = emojis.split(",") if emojis else []

        guild = interaction.guild
        role_config = {}

        for i, role_data in enumerate(roles_data):
            label, role_id = role_data.split(":")
            role = guild.get_role(int(role_id))
            if not role:
                await interaction.response.send_message(f"❌ 找不到角色 ID：{role_id}", ephemeral=True)
                return

            role_config[role] = {
                "label": label.strip(),
                "emoji": emojis_data[i].strip() if i < len(emojis_data) else None
            }

        view = RoleSelectionView(role_config)
        await interaction.channel.send(content, view=view)
        await interaction.response.send_message("✅ 已成功發送按鈕角色訊息！", ephemeral=True)

    # 其他事件監聽器保留不變...

async def setup(bot):
    await bot.add_cog(ReactionRole(bot))