import discord
from discord import app_commands
from discord.ext import commands
import sqlite3, os, io, time, aiohttp
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from dotenv import load_dotenv, set_key
from io import BytesIO

# 載入 .env 文件
load_dotenv()

# 配置常數
DB_FILE = "user_data.db"
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKtc-Regular.otf")
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "..", "assets")
TROPHY_PATH = os.path.join(ASSETS_PATH, "trophy.png")
MEDAL_PATHS = [
    os.path.join(ASSETS_PATH, "1.png"),  # 金牌
    os.path.join(ASSETS_PATH, "2.png"),  # 銀牌
    os.path.join(ASSETS_PATH, "3.png"),  # 銅牌
]
USER_COOLDOWN_SECONDS = 30

# 資料庫初始化
def initialize_database():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                kkcoin INTEGER DEFAULT 0
            )
        """)

# 資料庫操作方法
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

# 環境變數操作
def get_from_env(variable_name, default=None):
    return os.getenv(variable_name, default)

def save_to_env(variable_name, value):
    set_key(".env", variable_name, str(value))

# 獲取 Discord 用戶頭像
async def fetch_avatar(session, url):
    async with session.get(url) as resp:
        if resp.status != 200:
            return None
        data = await resp.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")

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
        print(f"❌ 載入字體失敗: {e}")
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
    try:
        trophy_img = Image.open(TROPHY_PATH).convert("RGBA")
    except Exception as e:
        print(f"❌ 載入 trophy.png 失敗: {e}")
        trophy_img = None
    medal_imgs = []
    for idx, path in enumerate(MEDAL_PATHS):
        try:
            medal_imgs.append(Image.open(path).convert("RGBA"))
        except Exception as e:
            print(f"❌ 載入 medal {idx+1} 失敗: {e}")
            medal_imgs.append(None)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    # 標題左側貼獎盃
    if trophy_img:
        img.paste(trophy_img.resize((44,44)), (MARGIN, 12), trophy_img.resize((44,44)))
        title_x = MARGIN + 54
    else:
        title_x = MARGIN
    draw.text((title_x, 18), "KK幣排行榜（前20名）", fill=(60,60,60), font=FONT_BIG)

    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            y = 75 + i*60
            # 前三名加金銀銅牌
            if i < 3 and medal_imgs[i]:
                img.paste(medal_imgs[i].resize((36,36)), (MARGIN, y+6), medal_imgs[i].resize((36,36)))
                rank_x = MARGIN + 44
            else:
                rank_x = MARGIN
            # 排名
            draw.text((rank_x, y), f"{i+1:2d}", fill=RANK_COLOR, font=FONT_SMALL)
            # 頭像
            avatar = await fetch_avatar(session, member.display_avatar.url)
            if avatar:
                avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
                img.paste(avatar, (rank_x + 40, y), avatar)
            # 暱稱
            name_x = rank_x + 100
            name_y = y+8
            draw.text((name_x, name_y), member.display_name, fill=(30,30,30), font=FONT_SMALL)
            # KK幣
            draw.text((WIDTH-180, y+8), f"{kkcoin} KK幣", fill=(50,110,210), font=FONT_KKCOIN)
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

    @app_commands.command(name="kkcoin", description="查詢你的 KK 幣餘額")
    async def kkcoin(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        balance = get_user_balance(str(member.id))
        await interaction.response.send_message(f"💰 {member.display_name} 目前擁有 KK 幣：{balance}", ephemeral=True)

    @app_commands.command(name="kkcoin_rank", description="顯示 KK 幣排行榜")
    async def kkcoin_rank(self, interaction: discord.Interaction):
        guild = interaction.guild

        # 確保設置 row_factory 為 sqlite3.Row
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            members_data = [
                (guild.get_member(int(row["user_id"])), get_user_balance(row["user_id"]))
                for row in conn.execute("SELECT user_id FROM users")
                if guild.get_member(int(row["user_id"]))
            ]

        members_data.sort(key=lambda x: x[1], reverse=True)
        members_data = members_data[:20]

        image = await make_leaderboard_image(members_data)
        with io.BytesIO() as img_bytes:
            image.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            file = discord.File(img_bytes, filename="kkcoin_rank.png")
            msg = await interaction.channel.send(file=file)

        # 保存排行榜訊息到 .env
        save_to_env("KKCOIN_RANK_CHANNEL_ID", interaction.channel.id)
        save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
        self.rank_channel_id = interaction.channel.id
        self.rank_message_id = msg.id

        await interaction.response.send_message("✅ 排行榜已建立", ephemeral=True)

    async def update_leaderboard(self):
        if not self.rank_channel_id or not self.rank_message_id:
            return

        try:
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                return

            msg = await channel.fetch_message(self.rank_message_id)

            guild = channel.guild
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                members_data = [
                    (guild.get_member(int(row["user_id"])), get_user_balance(row["user_id"]))
                    for row in conn.execute("SELECT user_id FROM users")
                    if guild.get_member(int(row["user_id"]))
                ]

            members_data.sort(key=lambda x: x[1], reverse=True)
            members_data = members_data[:20]

            image = await make_leaderboard_image(members_data)
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                await msg.edit(attachments=[discord.File(img_bytes, filename="kkcoin_rank.png")])
        except Exception as e:
            print(f"Failed to update leaderboard: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.strip()
        user_id = str(message.author.id)
        now = time.time()

        if (
            len(content) < 10 or
            now - self.last_kkcoin_time[user_id] < USER_COOLDOWN_SECONDS or
            content == self.last_message_cache[user_id]
        ):
            return

        reward = 3 if len(content) >= 50 else 2 if len(content) >= 25 else 1

        self.last_kkcoin_time[user_id] = now
        self.last_message_cache[user_id] = content
        update_user_balance(user_id, reward)

        print(f"{message.author} earned {reward} KKcoin!")
        await self.update_leaderboard()


async def setup(bot):
    await bot.add_cog(KKCoin(bot))
