import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging

# 載入環境變數
load_dotenv()

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 機器人設定
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class ShopBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',  # 你可以自行調整前綴
            intents=intents,
            help_command=None
        )
    
    async def setup_hook(self):
        """機器人啟動時執行"""
        await self.load_extensions()
    
    async def load_extensions(self):
        """載入shop_commands資料夾中的所有擴展"""
        try:
            shop_commands_path = "shop_commands"
            
            if os.path.exists(shop_commands_path):
                loaded_count = 0
                for filename in os.listdir(shop_commands_path):
                    if filename.endswith('.py') and not filename.startswith('__'):
                        extension = f"shop_commands.{filename[:-3]}"
                        try:
                            await self.load_extension(extension)
                            logger.info(f"✅ 成功載入擴展: {extension}")
                            loaded_count += 1
                        except Exception as e:
                            logger.error(f"❌ 載入擴展失敗 {extension}: {e}")
                
                if loaded_count == 0:
                    logger.warning("⚠️ shop_commands 資料夾中沒有找到有效的擴展文件")
                else:
                    logger.info(f"📦 總共載入了 {loaded_count} 個擴展")
            else:
                logger.warning("⚠️ shop_commands 資料夾不存在，將自動創建")
                os.makedirs(shop_commands_path)
                
        except Exception as e:
            logger.error(f"❌ 載入擴展時發生錯誤: {e}")
    
    async def on_ready(self):
        """機器人準備就緒時觸發"""
        logger.info(f'🛒 黑市商人BOT已上線: {self.user}')
        logger.info(f'📊 連接到 {len(self.guilds)} 個伺服器')
        
        # 設置狀態
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="黑市交易"
            )
        )
    
    async def on_command_error(self, ctx, error):
        """錯誤處理"""
        if isinstance(error, commands.CommandNotFound):
            return  # 忽略未知指令
        elif isinstance(error, commands.MissingPermissions):
            logger.warning(f"權限不足: {ctx.author} 在 {ctx.guild} 嘗試執行 {ctx.command}")
        elif isinstance(error, commands.BotMissingPermissions):
            logger.warning(f"機器人權限不足: {ctx.command} 在 {ctx.guild}")
        else:
            logger.error(f"指令錯誤 [{ctx.command}]: {error}")

# 建立機器人實例
bot = ShopBot()

if __name__ == "__main__":
    try:
        # 獲取Discord Token
        token = os.getenv('SHOP_DISCORD_BOT_TOKEN')
        
        if not token:
            logger.error("❌ 找不到 SHOP_DISCORD_BOT_TOKEN，請檢查 .env 文件")
            exit(1)
        
        logger.info("🚀 啟動黑市商人BOT...")
        bot.run(token)
        
    except KeyboardInterrupt:
        logger.info("👋 黑市商人BOT已手動停止")
    except discord.LoginFailure:
        logger.error("❌ Discord Token 無效")
    except Exception as e:
        logger.error(f"❌ 啟動失敗: {e}")