import discord
from discord import app_commands
from discord.ext import commands
import sqlite3, os, io, time, aiohttp
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from dotenv import load_dotenv, set_key
from io import BytesIO

# 载入 .env 文件
load_dotenv()

# 配置常数
DB_FILE = "user_data.db"
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")
TROPHY_PATH = os.path.join(ASSETS_PATH, "trophy.png")
MEDAL_PATHS = [
    os.path.join(ASSETS_PATH, "1.png"),  # 金牌
    os.path.join(ASSETS_PATH, "2.png"),  # 银牌
    os.path.join(ASSETS_PATH, "3.png"),  # 铜牌
]
USER_COOLDOWN_SECONDS = 30

# 资料库初始化
def initialize_database():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                kkcoin INTEGER DEFAULT 0
            )
        """)

# 资料库操作方法
def get_user_balance(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        result = conn.execute("SELECT kkcoin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return result["kkcoin"] if result else 0

def update_user_balance(user_id, amount):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO users (user_id, kkcoin)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET kkcoin = kkcoin + excluded.kkcoin
        """, (user_id, amount))

# 环境变量操作
def get_from_env(variable_name, default=None):
    return os.getenv(variable_name, default)

def save_to_env(variable_name, value):
    set_key(".env", variable_name, str(value))

# 获取 Discord 用户头像
async def fetch_avatar(session, url):
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()
            return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        print(f"❌ 获取头像失败: {e}")
        return None

async def make_leaderboard_image(members_data):
    WIDTH, HEIGHT = 900, 75 + 60 * len(members_data)
    AVATAR_SIZE = 48
    MARGIN = 20
    BG_COLOR = (255,255,255)
    RANK_COLOR = (240,200,80)
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, 28)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, 22)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 24)
    except Exception as e:
        print(f"❌ 载入字体失败: {e}")
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
    try:
        trophy_img = Image.open(TROPHY_PATH).convert("RGBA")
    except Exception as e:
        print(f"❌ 载入 trophy.png 失败: {e}")
        trophy_img = None
    medal_imgs = []
    for idx, path in enumerate(MEDAL_PATHS):
        try:
            medal_imgs.append(Image.open(path).convert("RGBA"))
        except Exception as e:
            print(f"❌ 载入 medal {idx+1} 失败: {e}")
            medal_imgs.append(None)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    # 标题左侧贴奖杯
    if trophy_img:
        img.paste(trophy_img.resize((44,44)), (MARGIN, 12), trophy_img.resize((44,44)))
        title_x = MARGIN + 54
    else:
        title_x = MARGIN
    draw.text((title_x, 18), "KK币排行榜（前20名）", fill=(60,60,60), font=FONT_BIG)

    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            y = 75 + i*60
            # 前三名加金银铜牌
            if i < 3 and medal_imgs[i]:
                img.paste(medal_imgs[i].resize((36,36)), (MARGIN, y+6), medal_imgs[i].resize((36,36)))
                rank_x = MARGIN + 44
            else:
                rank_x = MARGIN
            # 排名
            draw.text((rank_x, y), f"{i+1:2d}", fill=RANK_COLOR, font=FONT_SMALL)
            # 头像
            avatar = await fetch_avatar(session, member.display_avatar.url)
            if avatar:
                avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
                img.paste(avatar, (rank_x + 40, y), avatar)
            # 暱称
            name_x = rank_x + 100
            name_y = y+8
            draw.text((name_x, name_y), member.display_name, fill=(30,30,30), font=FONT_SMALL)
            # KK币
            draw.text((WIDTH-180, y+8), f"{kkcoin} KK币", fill=(50,110,210), font=FONT_KKCOIN)
    return img

def is_only_emojis(text):
    import regex
    emoji_pattern = regex.compile(r'^\s*(?:\p{Emoji_Presentation}|\p{Emoji}\uFE0F|\p{Emoji_Modifier_Base}|\p{Emoji_Component})+\s*$')
    return bool(emoji_pattern.fullmatch(text))

class KKCoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        initialize_database()
        self.rank_channel_id = int(get_from_env("KKCOIN_RANK_CHANNEL_ID", 0))
        self.rank_message_id = int(get_from_env("KKCOIN_RANK_MESSAGE_ID", 0))
        self.last_kkcoin_time = defaultdict(lambda: 0)
        self.last_message_cache = defaultdict(str)
        self.last_update_time = 0  # 修改：改为时间间隔控制
        self.last_leaderboard_data = None  # 新增：缓存上次的排行榜数据

    @app_commands.command(name="kkcoin", description="查询你的 KK 币余额")
    async def kkcoin(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        balance = get_user_balance(str(member.id))
        await interaction.response.send_message(f"💰 {member.display_name} 目前拥有 KK 币：{balance}", ephemeral=True)

    @app_commands.command(name="kkcoin_rank", description="显示 KK 币排行榜")
    async def kkcoin_rank(self, interaction: discord.Interaction):
        await interaction.response.defer()  # 先延迟响应，避免超时
        
        guild = interaction.guild

        # 确保设置 row_factory 为 sqlite3.Row
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            members_data = [
                (guild.get_member(int(row["user_id"])), get_user_balance(row["user_id"]))
                for row in conn.execute("SELECT user_id FROM users WHERE EXISTS (SELECT 1 FROM users u2 WHERE u2.user_id = users.user_id AND u2.kkcoin > 0)")
                if guild.get_member(int(row["user_id"]))
            ]

        members_data.sort(key=lambda x: x[1], reverse=True)
        members_data = members_data[:20]

        if not members_data:
            await interaction.followup.send("❌ 没有找到任何用户数据", ephemeral=True)
            return

        try:
            image = await make_leaderboard_image(members_data)
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rank.png")
                msg = await interaction.followup.send(file=file)

            # 保存排行榜讯息到 .env
            save_to_env("KKCOIN_RANK_CHANNEL_ID", interaction.channel.id)
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
            self.rank_channel_id = interaction.channel.id
            self.rank_message_id = msg.id
            
            # 缓存当前数据
            self.last_leaderboard_data = members_data.copy()
            self.last_update_time = time.time()

            print(f"✅ 排行榜已建立在频道 {interaction.channel.id}，讯息 ID: {msg.id}")
        except Exception as e:
            print(f"❌ 建立排行榜时发生错误: {e}")
            await interaction.followup.send("❌ 建立排行榜时发生错误", ephemeral=True)

    async def update_leaderboard(self):
        current_time = time.time()
        
        # 1. 检查基本条件
        if not self.rank_channel_id or not self.rank_message_id:
            return

        # 2. 时间间隔控制 - 每60秒最多更新一次
        if current_time - self.last_update_time < 60:
            return

        try:
            # 3. 获取频道和讯息
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到频道 {self.rank_channel_id}")
                return

            try:
                msg = await channel.fetch_message(self.rank_message_id)
            except discord.NotFound:
                print("❌ 排行榜讯息已被删除")
                self.rank_channel_id = 0
                self.rank_message_id = 0
                save_to_env("KKCOIN_RANK_CHANNEL_ID", 0)
                save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
                return

            # 4. 获取最新数据
            guild = channel.guild
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                members_data = [
                    (guild.get_member(int(row["user_id"])), get_user_balance(row["user_id"]))
                    for row in conn.execute("SELECT user_id FROM users WHERE EXISTS (SELECT 1 FROM users u2 WHERE u2.user_id = users.user_id AND u2.kkcoin > 0)")
                    if guild.get_member(int(row["user_id"]))
                ]

            members_data.sort(key=lambda x: x[1], reverse=True)
            members_data = members_data[:20]

            # 5. 检查数据是否有变化
            if self._data_unchanged(members_data):
                return

            # 6. 更新图片
            if members_data:
                print(f"🔄 更新排行榜...")
                image = await make_leaderboard_image(members_data)
                with io.BytesIO() as img_bytes:
                    image.save(img_bytes, format="PNG")
                    img_bytes.seek(0)
                    await msg.edit(attachments=[discord.File(img_bytes, filename="kkcoin_rank.png")])
                
                # 更新缓存
                self.last_leaderboard_data = members_data.copy()
                self.last_update_time = current_time
                print(f"✅ 排行榜更新成功")

        except discord.HTTPException as e:
            print(f"❌ Discord API 错误: {e}")
        except Exception as e:
            print(f"❌ 更新排行榜时发生错误: {e}")

    def _data_unchanged(self, new_data):
        """检查数据是否有变化"""
        if not self.last_leaderboard_data or len(new_data) != len(self.last_leaderboard_data):
            return False
        
        for i, (member, kkcoin) in enumerate(new_data):
            if i >= len(self.last_leaderboard_data):
                return False
            old_member, old_kkcoin = self.last_leaderboard_data[i]
            if member.id != old_member.id or kkcoin != old_kkcoin:
                return False
        
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.strip()
        user_id = str(message.author.id)
        now = time.time()

        # 检查条件
        if (
            len(content) < 10 or
            now - self.last_kkcoin_time[user_id] < USER_COOLDOWN_SECONDS or
            content == self.last_message_cache[user_id]
        ):
            return

        # 计算奖励
        reward = 3 if len(content) >= 50 else 2 if len(content) >= 25 else 1

        # 更新用户数据
        self.last_kkcoin_time[user_id] = now
        self.last_message_cache[user_id] = content
        update_user_balance(user_id, reward)

        print(f"💰 {message.author.display_name} 获得了 {reward} KK币!")
        
        # 异步更新排行榜
        try:
            await self.update_leaderboard()
        except Exception as e:
            print(f"❌ 更新排行榜时发生错误: {e}")

    @app_commands.command(name="reset_rank", description="重置排行榜设置（管理员专用）")
    @app_commands.default_permissions(administrator=True)
    async def reset_rank(self, interaction: discord.Interaction):
        """重置排行榜设置"""
        self.rank_channel_id = 0
        self.rank_message_id = 0
        self.last_leaderboard_data = None
        save_to_env("KKCOIN_RANK_CHANNEL_ID", 0)
        save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
        await interaction.response.send_message("✅ 排行榜设置已重置", ephemeral=True)

    # 新增：手动强制更新命令
    @app_commands.command(name="force_update_rank", description="强制更新排行榜（管理员专用）")
    @app_commands.default_permissions(administrator=True)
    async def force_update_rank(self, interaction: discord.Interaction):
        """强制更新排行榜"""
        await interaction.response.defer(ephemeral=True)
        
        # 临时重置更新时间以强制更新
        old_time = self.last_update_time
        self.last_update_time = 0
        self.last_leaderboard_data = None
        
        try:
            await self.update_leaderboard()
            await interaction.followup.send("✅ 排行榜已强制更新", ephemeral=True)
        except Exception as e:
            self.last_update_time = old_time
            await interaction.followup.send(f"❌ 更新失败: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(KKCoin(bot))
