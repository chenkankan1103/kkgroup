import discord
from discord import app_commands
from discord.ext import commands, tasks
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
UPDATE_INTERVAL = 10  # 更新間隔改為 10 秒

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
    DESCRIPTION_HEIGHT = 80
    WIDTH, HEIGHT = 900, 75 + 60 * len(members_data) + DESCRIPTION_HEIGHT
    AVATAR_SIZE = 48
    MARGIN = 20
    BG_COLOR = (255,255,255)
    RANK_COLOR = (240,200,80)
    try:
        FONT_BIG = ImageFont.truetype(FONT_PATH, 28)
        FONT_SMALL = ImageFont.truetype(FONT_PATH, 22)
        FONT_KKCOIN = ImageFont.truetype(FONT_PATH, 24)
        FONT_DESC = ImageFont.truetype(FONT_PATH, 16)
    except Exception as e:
        print(f"❌ 載入字體失敗: {e}")
        FONT_BIG = ImageFont.load_default()
        FONT_SMALL = ImageFont.load_default()
        FONT_KKCOIN = ImageFont.load_default()
        FONT_DESC = ImageFont.load_default()
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
    if trophy_img:
        img.paste(trophy_img.resize((44,44)), (MARGIN, 12), trophy_img.resize((44,44)))
        title_x = MARGIN + 54
    else:
        title_x = MARGIN
    draw.text((title_x, 18), "KK幣排行榜（前20名）", fill=(60,60,60), font=FONT_BIG)

    async with aiohttp.ClientSession() as session:
        for i, (member, kkcoin) in enumerate(members_data):
            y = 75 + i*60
            if i < 3 and medal_imgs[i]:
                img.paste(medal_imgs[i].resize((36,36)), (MARGIN, y+6), medal_imgs[i].resize((36,36)))
                rank_x = MARGIN + 44
            else:
                rank_x = MARGIN
            draw.text((rank_x, y), f"{i+1:2d}", fill=RANK_COLOR, font=FONT_SMALL)
            avatar = await fetch_avatar(session, member.display_avatar.url)
            if avatar:
                avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE))
                img.paste(avatar, (rank_x + 40, y), avatar)
            name_x = rank_x + 100
            name_y = y+8
            draw.text((name_x, name_y), member.display_name, fill=(30,30,30), font=FONT_SMALL)
            draw.text((WIDTH-180, y+8), f"{kkcoin} KK幣", fill=(50,110,210), font=FONT_KKCOIN)
    
    desc_y = 75 + len(members_data) * 60 + 15
    draw.line([(MARGIN, desc_y - 8), (WIDTH - MARGIN, desc_y - 8)], fill=(200,200,200), width=1)
    descriptions = [
        " 發送訊息獲得KK幣：10字+1幣 | 25字+2幣 | 50字+3幣 （冷卻30秒）",
        " 限制：重複訊息、純表情不給幣 |  語音掛機可獲得額外獎勵"
    ]
    draw.text((MARGIN, desc_y), " KKcoin獲得方法：", fill=(80,80,80), font=FONT_SMALL)
    for i, desc in enumerate(descriptions):
        desc_text_y = desc_y + 25 + i * 22
        draw.text((MARGIN + 10, desc_text_y), desc, fill=(100,100,100), font=FONT_DESC)
    
    return img

def is_only_emojis(text):
    import regex
    emoji_pattern = regex.compile(r'^\s*(?:\p{Emoji_Presentation}|\p{Emoji}\uFE0F|\p{Emoji_Modifier_Base}|\p{Emoji_Component})+\s*$')
    return bool(emoji_pattern.fullmatch(text))

class KKCoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        initialize_database()
        
        # 從 .env 讀取排行榜頻道 ID
        self.rank_channel_id = int(get_from_env("KKCOIN_RANK_CHANNEL_ID", 0))
        self.rank_message_id = int(get_from_env("KKCOIN_RANK_MESSAGE_ID", 0))
        
        self.last_kkcoin_time = defaultdict(lambda: 0)
        self.last_message_cache = defaultdict(str)
        self.last_update_time = 0
        self.last_leaderboard_data = None
        
        # 啟動定時更新任務
        self.auto_update_leaderboard.start()
        print(f"✅ KKCoin 系統已載入，排行榜頻道: {self.rank_channel_id}")

    def cog_unload(self):
        """當 Cog 卸載時停止定時任務"""
        self.auto_update_leaderboard.cancel()

    @tasks.loop(minutes=5)
    async def auto_update_leaderboard(self):
        """每 5 分鐘自動更新排行榜"""
        if not self.rank_channel_id:
            return
            
        # 如果沒有訊息 ID，嘗試創建排行榜
        if not self.rank_message_id:
            await self.create_leaderboard()
        else:
            # 否則更新現有排行榜
            await self.update_leaderboard(min_interval=0)

    @auto_update_leaderboard.before_loop
    async def before_auto_update(self):
        """等待 bot 準備完成"""
        await self.bot.wait_until_ready()
        print("✅ 排行榜自動更新任務已啟動")

    async def create_leaderboard(self):
        """自動創建排行榜訊息"""
        if not self.rank_channel_id:
            print("❌ 未設定排行榜頻道 ID")
            return
            
        try:
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到頻道 {self.rank_channel_id}")
                return
            
            guild = channel.guild
            members_data = self.get_current_leaderboard_data()
            
            if not members_data:
                print("❌ 沒有使用者資料，無法創建排行榜")
                return
            
            # 創建圖片
            image = await make_leaderboard_image(members_data)
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rank.png")
                msg = await channel.send(file=file)
            
            # 儲存訊息 ID
            self.rank_message_id = msg.id
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
            
            # 快取資料
            self.last_leaderboard_data = members_data.copy()
            self.last_update_time = time.time()
            
            print(f"✅ 排行榜已自動創建在頻道 {channel.name}，訊息 ID: {msg.id}")
            
        except Exception as e:
            print(f"❌ 自動創建排行榜失敗: {e}")
            import traceback
            traceback.print_exc()

    @app_commands.command(name="kkcoin", description="查詢你的 KK 幣餘額")
    async def kkcoin(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        balance = get_user_balance(str(member.id))
        await interaction.response.send_message(f"💰 {member.display_name} 目前擁有 KK 幣：{balance}", ephemeral=True)

    @app_commands.command(name="kkcoin_rank", description="顯示 KK 幣排行榜")
    async def kkcoin_rank(self, interaction: discord.Interaction):
        """手動創建排行榜（如果需要的話）"""
        await interaction.response.defer()
        
        guild = interaction.guild
        members_data = self.get_current_leaderboard_data()

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

            # 更新設定
            save_to_env("KKCOIN_RANK_CHANNEL_ID", interaction.channel.id)
            save_to_env("KKCOIN_RANK_MESSAGE_ID", msg.id)
            self.rank_channel_id = interaction.channel.id
            self.rank_message_id = msg.id
            
            self.last_leaderboard_data = members_data.copy()
            self.last_update_time = time.time()

            print(f"✅ 排行榜已手動建立在頻道 {interaction.channel.id}，訊息 ID: {msg.id}")
        except Exception as e:
            print(f"❌ 建立排行榜時發生錯誤: {e}")
            await interaction.followup.send("❌ 建立排行榜時發生錯誤", ephemeral=True)

    @app_commands.command(name="kkcoin_admin", description="管理用戶的 KK 幣（管理員專用）")
    @app_commands.describe(
        member="要修改 KK 幣的用戶",
        action="操作類型",
        amount="數量"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="增加", value="add"),
        app_commands.Choice(name="減少", value="subtract"),
        app_commands.Choice(name="設定為", value="set")
    ])
    @app_commands.default_permissions(administrator=True)
    async def kkcoin_admin(self, interaction: discord.Interaction, member: discord.Member, action: str, amount: int):
        """管理用戶的 KK 幣"""
        if amount < 0:
            await interaction.response.send_message("❌ 數量不能為負數", ephemeral=True)
            return
            
        user_id = str(member.id)
        current_balance = get_user_balance(user_id)
        
        if action == "add":
            new_balance = current_balance + amount
            update_user_balance(user_id, amount)
            action_text = f"增加了 {amount}"
        elif action == "subtract":
            if current_balance < amount:
                await interaction.response.send_message(f"❌ {member.display_name} 目前只有 {current_balance} KK幣，不足扣除 {amount} KK幣", ephemeral=True)
                return
            new_balance = current_balance - amount
            update_user_balance(user_id, -amount)
            action_text = f"減少了 {amount}"
        else:  # set
            difference = amount - current_balance
            update_user_balance(user_id, difference)
            new_balance = amount
            action_text = f"設定為 {amount}"
        
        await interaction.response.send_message(
            f"✅ 已為 {member.display_name} {action_text} KK幣\n"
            f"💰 變更前：{current_balance} KK幣\n"
            f"💰 變更後：{new_balance} KK幣",
            ephemeral=True
        )
        
        print(f"🔧 管理員 {interaction.user.display_name} 為 {member.display_name} {action_text} KK幣 ({current_balance} → {new_balance})")
        
        # 異步更新排行榜
        try:
            await self.update_leaderboard(min_interval=0)
        except Exception as e:
            print(f"❌ 更新排行榜時發生錯誤: {e}")

    def get_current_leaderboard_data(self):
        """取得當前排行榜資料"""
        if not self.rank_channel_id:
            return []
            
        channel = self.bot.get_channel(self.rank_channel_id)
        if not channel:
            return []
            
        guild = channel.guild
        
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            members_data = []
            users = conn.execute("SELECT user_id, kkcoin FROM users WHERE kkcoin > 0 ORDER BY kkcoin DESC LIMIT 20").fetchall()
            
            for row in users:
                member = guild.get_member(int(row["user_id"]))
                if member:
                    members_data.append((member, row["kkcoin"]))
            
        return members_data

    def has_data_changed(self, new_data):
        """檢查資料是否有變化，返回 True 表示有變化"""
        if not self.last_leaderboard_data:
            print("🔍 沒有快取資料，需要更新")
            return True
            
        if len(new_data) != len(self.last_leaderboard_data):
            print(f"🔍 資料筆數變化：{len(self.last_leaderboard_data)} → {len(new_data)}")
            return True
        
        for i, (member, kkcoin) in enumerate(new_data):
            if i >= len(self.last_leaderboard_data):
                print(f"🔍 索引超出範圍：{i}")
                return True
                
            old_member, old_kkcoin = self.last_leaderboard_data[i]
            
            if member.id != old_member.id:
                print(f"🔍 排名變化：位置 {i+1} 從 {old_member.display_name} 變成 {member.display_name}")
                return True
                
            if kkcoin != old_kkcoin:
                print(f"🔍 KK幣變化：{member.display_name} 從 {old_kkcoin} 變成 {kkcoin}")
                return True
        
        print("🔍 資料沒有變化，跳過更新")
        return False

    async def update_leaderboard(self, min_interval=UPDATE_INTERVAL, force=False):
        """
        更新排行榜
        min_interval: 最小更新間隔（秒）
        force: 是否強制更新（忽略時間和資料變化檢查）
        """
        current_time = time.time()
        
        if not self.rank_channel_id or not self.rank_message_id:
            return

        if not force and current_time - self.last_update_time < min_interval:
            return

        try:
            channel = self.bot.get_channel(self.rank_channel_id)
            if not channel:
                print(f"❌ 找不到頻道 {self.rank_channel_id}")
                return

            try:
                msg = await channel.fetch_message(self.rank_message_id)
            except discord.NotFound:
                print("❌ 排行榜訊息已被刪除，將重新創建")
                self.rank_message_id = 0
                save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
                await self.create_leaderboard()
                return
            except Exception as e:
                print(f"❌ 取得訊息失敗: {e}")
                return

            members_data = self.get_current_leaderboard_data()
            
            if not members_data:
                return

            if not force and not self.has_data_changed(members_data):
                self.last_update_time = current_time
                return

            print(f"🔄 開始更新排行榜...")
            image = await make_leaderboard_image(members_data)
            
            with io.BytesIO() as img_bytes:
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                file = discord.File(img_bytes, filename="kkcoin_rank.png")
                await msg.edit(attachments=[file])
            
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

        print(f"💰 {message.author.display_name} 獲得了 {reward} KK幣! (總計: {get_user_balance(user_id)})")
        
        try:
            await self.update_leaderboard()
        except Exception as e:
            print(f"❌ 更新排行榜時發生錯誤: {e}")

    @app_commands.command(name="reset_rank", description="重置排行榜設定（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def reset_rank(self, interaction: discord.Interaction):
        """重置排行榜設定"""
        self.rank_message_id = 0
        self.last_leaderboard_data = None
        self.last_update_time = 0
        save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
        await interaction.response.send_message("✅ 排行榜訊息已重置，將在下次自動更新時重新創建", ephemeral=True)

    @app_commands.command(name="force_update_rank", description="強制更新排行榜（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def force_update_rank(self, interaction: discord.Interaction):
        """強制更新排行榜"""
        await interaction.response.defer(ephemeral=True)
        
        if not self.rank_channel_id:
            await interaction.followup.send("❌ 尚未設定排行榜頻道", ephemeral=True)
            return
        
        try:
            await self.update_leaderboard(force=True)
            await interaction.followup.send("✅ 排行榜已強制更新", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 更新失敗: {str(e)}", ephemeral=True)

    @app_commands.command(name="debug_rank", description="顯示排行榜調試資訊（管理員專用）")
    @app_commands.default_permissions(administrator=True)
    async def debug_rank(self, interaction: discord.Interaction):
        """顯示排行榜調試資訊"""
        current_time = time.time()
        time_since_update = current_time - self.last_update_time
        
        current_data = self.get_current_leaderboard_data()
        
        debug_info = f"""
**排行榜調試資訊**
📍 頻道 ID: {self.rank_channel_id}
📨 訊息 ID: {self.rank_message_id}
⏰ 距離上次更新: {time_since_update:.1f} 秒
⏱️ 更新間隔設定: {UPDATE_INTERVAL} 秒
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
        
        data_changed = self.has_data_changed(current_data)
        debug_info += f"\n🔄 資料是否有變化: {'是' if data_changed else '否'}"
        
        await interaction.response.send_message(debug_info, ephemeral=True)

    @app_commands.command(name="set_rank_channel", description="設定排行榜頻道（管理員專用）")
    @app_commands.describe(channel="排行榜要顯示的頻道")
    @app_commands.default_permissions(administrator=True)
    async def set_rank_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """設定排行榜頻道"""
        self.rank_channel_id = channel.id
        self.rank_message_id = 0
        save_to_env("KKCOIN_RANK_CHANNEL_ID", channel.id)
        save_to_env("KKCOIN_RANK_MESSAGE_ID", 0)
        
        await interaction.response.send_message(
            f"✅ 排行榜頻道已設定為 {channel.mention}\n"
            f"排行榜將在下次更新時自動創建",
            ephemeral=True
        )
        
        # 立即嘗試創建排行榜
        await self.create_leaderboard()

async def setup(bot):
    await bot.add_cog(KKCoin(bot))
