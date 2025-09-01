import discord
from discord import app_commands
from discord.ext import commands
import sqlite3, os, io, time, aiohttp
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from dotenv import load_dotenv, set_key
from io import BytesIO

# 載入 .env 檔案
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

# 取得 Discord 使用者頭像
async def fetch_avatar(session, url):
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()
            return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        print(f"❌ 取得頭像失敗: {e}")
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
    # 標題左側貼獎杯
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
        self.last_update_time = 0
        self.last_leaderboard_data = None

    @app_commands.command(name="kkcoin", description="查詢你的 KK 幣餘額")
    async def kkcoin(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        balance = get_user_balance(str(member.id))
        await interaction.response.send_message(f"💰 {member.display_name} 目前擁有 KK 幣：{balance}", ephemeral=True)

    @app_commands.command(name="kkcoin_rank", description="顯示 KK 幣排行榜")
    async def kkcoin_rank(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        guild = interaction.guild

        # 確保設定 row_factory 為 sqlite3.Row
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
            await interaction.followup.send("❌ 沒有找到任何使用者資料", ephemeral=True)
            return

        try:
            image = await make_leaderboard_image(members_data)
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rank.png")
                msg = await interaction.followup.send(file=file)

            # 儲存排行榜訊息到 .env
            save_to_env("KKCOIN_RANK_CHANNEL_ID", interaction.channel.id)
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
            self.rank_channel_id = interaction.channel.id
            self.rank_message_id = msg.id
            
            # 快取目前資料
            self.last_leaderboard_data = members_data.copy()
            self.last_update_time = time.time()

            print(f"✅ 排行榜已建立在頻道 {interaction.channel.id}，訊息 ID: {msg.id}")
        except Exception as e:
            print(f"❌ 建立排行榜時發生錯誤: {e}")
            await interaction.followup.send("❌ 建立排行榜時發生錯誤", ephemeral=True)

    def get_current_leaderboard_data(self):
        """取得當前排行榜資料"""
        if not self.rank_channel_id:
            return []
            
        # 取得 guild
        channel = self.bot.get_channel(self.rank_channel_id)
        if not channel:
            return []
            
        guild = channel.guild
        
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            members_data = []
            
            # 取得所有有 KK 幣的使用者
            users = conn.execute("SELECT user_id, kkcoin FROM users WHERE kkcoin > 0 ORDER BY kkcoin DESC LIMIT 20").fetchall()
            
            for row in users:
                member = guild.get_member(int(row["user_id"]))
                if member:  # 確保成員還在伺服器中
                    members_data.append((member, row["kkcoin"]))
            
        return members_data

    def _data_unchanged(self, new_data):
        """檢查資料是否有變化 - 修正版本"""
        if not self.last_leaderboard_data:
            print("🔍 沒有快取資料，需要更新")
            return False
            
        if len(new_data) != len(self.last_leaderboard_data):
            print(f"🔍 資料筆數變化：{len(self.last_leaderboard_data)} → {len(new_data)}")
            return False
        
        for i, (member, kkcoin) in enumerate(new_data):
            if i >= len(self.last_leaderboard_data):
                print(f"🔍 索引超出範圍：{i}")
                return False
                
            old_member, old_kkcoin = self.last_leaderboard_data[i]
            
            if member.id != old_member.id:
                print(f"🔍 排名變化：位置 {i+1} 從 {old_member.display_name} 變成 {member.display_name}")
                return False
                
            if kkcoin != old_kkcoin:
                print(f"🔍 KK幣變化：{member.display_name} 從 {old_kkcoin} 變成 {kkcoin}")
                return False
        
        print("🔍 資料沒有變化，跳過更新")
        return True

    async def update_leaderboard(self):
        current_time = time.time()
        
        # 1. 檢查基本條件
        if not self.rank_channel_id or not self.rank_message_id:
            print("❌ 排行榜未設定，跳過更新")
            return

        # 2. 時間間隔控制 - 每30秒最多更新一次（縮短間隔以便測試）
        if current_time - self.last_update_time < 30:
            print(f"⏰ 距離上次更新僅 {current_time - self.last_update_time:.1f} 秒，跳過更新")
            return

        try:
            # 3. 取得頻道和訊息
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到頻道 {self.rank_channel_id}")
                return

            try:
                msg = await channel.fetch_message(self.rank_message_id)
            except discord.NotFound:
                print("❌ 排行榜訊息已被刪除")
                self.rank_channel_id = 0
                self.rank_message_id = 0
                save_to_env("KKCOIN_RANK_CHANNEL_ID", 0)
                save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
                return
            except Exception as e:
                print(f"❌ 取得訊息失敗: {e}")
                return

            # 4. 取得最新資料
            members_data = self.get_current_leaderboard_data()
            
            if not members_data:
                print("❌ 沒有使用者資料")
                return

            # 5. 檢查資料是否有變化
            if self._data_unchanged(members_data):
                return

            # 6. 更新圖片
            print(f"🔄 開始更新排行榜...")
            image = await make_leaderboard_image(members_data)
            
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rank.png")
                
                # 重要：使用 edit 更新訊息內容
                await msg.edit(attachments=[file])
            
            # 更新快取
            self.last_leaderboard_data = members_data.copy()
            self.last_update_time = current_time
            print(f"✅ 排行榜更新成功 ({len(members_data)} 名使用者)")

        except discord.HTTPException as e:
            print(f"❌ Discord API 錯誤: {e}")
        except Exception as e:
            print(f"❌ 更新排行榜時發生錯誤: {e}")
            import traceback
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.strip()
        user_id = str(message.author.id)
        now = time.time()

        # 檢查條件
        if (
            len(content) < 10 or
            now - self.last_kkcoin_time[user_id] < USER_COOLDOWN_SECONDS or
            content == self.last_message_cache[user_id]
        ):
            return

        # 計算獎勵
        reward = 3 if len(content) >= 50 else 2 if len(content) >= 25 else 1

        # 更新使用者資料
        self.last_kkcoin_time[user_id] = now
        self.last_message_cache[user_id] = content
        update_user_balance(user_id, reward)

        print(f"💰 {message.author.display_name} 獲得了 {reward} KK幣! (總計: {get_user_balance(user_id)})")
        
        # 非同步更新排行榜
        try:
            await self.update_leaderboard()
        except Exception as e:
            print(f"❌ 更新排行榜時發生錯誤: {e}")

    @app_commands.command(name="reset_rank", description="重置排行榜設定（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def reset_rank(self, interaction: discord.Interaction):
        """重置排行榜設定"""
        self.rank_channel_id = 0
        self.rank_message_id = 0
        self.last_leaderboard_data = None
        self.last_update_time = 0
        save_to_env("KKCOIN_RANK_CHANNEL_ID", 0)
        save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
        await interaction.response.send_message("✅ 排行榜設定已重置", ephemeral=True)

    @app_commands.command(name="force_update_rank", description="強制更新排行榜（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def force_update_rank(self, interaction: discord.Interaction):
        """強制更新排行榜"""
        await interaction.response.defer(ephemeral=True)
        
        if not self.rank_channel_id or not self.rank_message_id:
            await interaction.followup.send("❌ 尚未設定排行榜", ephemeral=True)
            return
        
        # 強制更新：清除快取和時間限制
        old_time = self.last_update_time
        old_data = self.last_leaderboard_data
        
        self.last_update_time = 0
        self.last_leaderboard_data = None
        
        try:
            await self.update_leaderboard()
            await interaction.followup.send("✅ 排行榜已強制更新", ephemeral=True)
        except Exception as e:
            # 還原舊資料
            self.last_update_time = old_time
            self.last_leaderboard_data = old_data
            await interaction.followup.send(f"❌ 更新失敗: {str(e)}", ephemeral=True)

    # 新增：調試指令，顯示目前狀態
    @app_commands.command(name="debug_rank", description="顯示排行榜調試資訊（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def debug_rank(self, interaction: discord.Interaction):
        """顯示排行榜調試資訊"""
        current_time = time.time()
        time_since_update = current_time - self.last_update_time
        
        # 取得當前資料
        current_data = self.get_current_leaderboard_data()
        
        debug_info = f"""
**排行榜調試資訊**
📍 頻道 ID: {self.rank_channel_id}
📨 訊息 ID: {self.rank_message_id}
⏰ 距離上次更新: {time_since_update:.1f} 秒
📊 當前資料筆數: {len(current_data)}
📊 快取資料筆數: {len(self.last_leaderboard_data) if self.last_leaderboard_data else 0}

**前5名當前資料:**
"""
        
        for i, (member, kkcoin) in enumerate(current_data[:5]):
            debug_info += f"{i+1}. {member.display_name}: {kkcoin} KK幣\n"
        
        if self.last_leaderboard_data:
            debug_info += "\n**前5名快取資料:**\n"
            for i, (member, kkcoin) in enumerate(self.last_leaderboard_data[:5]):
                debug_info += f"{i+1}. {member.display_name}: {kkcoin} KK幣\n"
        
        data_changed = not self._data_unchanged(current_data)
        debug_info += f"\n🔄 資料是否有變化: {'是' if data_changed else '否'}"
        
        await interaction.response.send_message(debug_info, ephemeral=True)

async def setup(bot):
    await bot.add_cog(KKCoin(bot))
