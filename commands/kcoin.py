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
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()
            return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        print(f"❌ 獲取頭像失敗: {e}")
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
        self.update_counter = 0  # 新增：用於控制更新頻率

    @app_commands.command(name="kkcoin", description="查詢你的 KK 幣餘額")
    async def kkcoin(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        balance = get_user_balance(str(member.id))
        await interaction.response.send_message(f"💰 {member.display_name} 目前擁有 KK 幣：{balance}", ephemeral=True)

    @app_commands.command(name="kkcoin_rank", description="顯示 KK 幣排行榜")
    async def kkcoin_rank(self, interaction: discord.Interaction):
        await interaction.response.defer()  # 先延遲回應，避免超時
        
        guild = interaction.guild

        # 確保設置 row_factory 為 sqlite3.Row
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            members_data = []
            for row in conn.execute("SELECT user_id FROM users ORDER BY kkcoin DESC"):
                member = guild.get_member(int(row["user_id"]))
                if member:
                    balance = get_user_balance(row["user_id"])
                    members_data.append((member, balance))

        # 限制前 20 名
        members_data = members_data[:20]

        if not members_data:
            await interaction.followup.send("❌ 沒有找到任何用戶數據", ephemeral=True)
            return

        try:
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

            await interaction.followup.send("✅ 排行榜已建立", ephemeral=True)
        except Exception as e:
            print(f"❌ 建立排行榜失敗: {e}")
            await interaction.followup.send("❌ 建立排行榜時發生錯誤", ephemeral=True)

    async def update_leaderboard(self):
        """更新排行榜"""
        if not self.rank_channel_id or not self.rank_message_id:
            print("⚠️ 排行榜訊息 ID 或頻道 ID 未設置")
            return

        # 降低更新頻率，每10次訊息才更新一次排行榜
        self.update_counter += 1
        if self.update_counter % 10 != 0:
            return

        try:
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"⚠️ 找不到頻道 ID: {self.rank_channel_id}")
                return

            try:
                msg = await channel.fetch_message(self.rank_message_id)
            except discord.NotFound:
                print("⚠️ 排行榜訊息已被刪除，清除設置")
                self.rank_channel_id = 0
                self.rank_message_id = 0
                save_to_env("KKCOIN_RANK_CHANNEL_ID", 0)
                save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
                return
            except discord.Forbidden:
                print("⚠️ 沒有權限獲取排行榜訊息")
                return

            guild = channel.guild
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                members_data = []
                for row in conn.execute("SELECT user_id FROM users ORDER BY kkcoin DESC LIMIT 20"):
                    member = guild.get_member(int(row["user_id"]))
                    if member:
                        balance = get_user_balance(row["user_id"])
                        members_data.append((member, balance))

            if not members_data:
                print("⚠️ 沒有用戶數據可更新")
                return

            image = await make_leaderboard_image(members_data)
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                await msg.edit(attachments=[discord.File(img_bytes, filename="kkcoin_rank.png")])
            
            print(f"✅ 排行榜更新成功 (第 {self.update_counter} 次)")

        except discord.HTTPException as e:
            print(f"❌ Discord HTTP 錯誤更新排行榜: {e}")
        except Exception as e:
            print(f"❌ 更新排行榜失敗: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """訊息監聽器，用於發放 KK 幣"""
        if message.author.bot:
            return

        content = message.content.strip()
        user_id = str(message.author.id)
        now = time.time()

        # 檢查訊息長度、冷卻時間和重複訊息
        if (
            len(content) < 10 or
            now - self.last_kkcoin_time[user_id] < USER_COOLDOWN_SECONDS or
            content == self.last_message_cache[user_id]
        ):
            return

        # 計算獎勵
        if len(content) >= 50:
            reward = 3
        elif len(content) >= 25:
            reward = 2
        else:
            reward = 1

        # 更新用戶數據
        self.last_kkcoin_time[user_id] = now
        self.last_message_cache[user_id] = content
        update_user_balance(user_id, reward)

        print(f"💰 {message.author.display_name} 獲得了 {reward} KK幣！")
        
        # 異步更新排行榜，不阻塞訊息處理
        try:
            await self.update_leaderboard()
        except Exception as e:
            print(f"❌ 更新排行榜時發生錯誤: {e}")

    @app_commands.command(name="reset_rank", description="重置排行榜設置（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def reset_rank(self, interaction: discord.Interaction):
        """重置排行榜設置"""
        self.rank_channel_id = 0
        self.rank_message_id = 0
        save_to_env("KKCOIN_RANK_CHANNEL_ID", 0)
        save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
        await interaction.response.send_message("✅ 排行榜設置已重置", ephemeral=True)

async def setup(bot):
    await bot.add_cog(KKCoin(bot))
