import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import os
import asyncio
import logging
from datetime import datetime, timedelta
import hashlib
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Earthquake(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processed_quakes = set()
        self.last_check_time = None
        self.initialization_complete = False
        self.api_error_count = 0
        self.last_successful_check = None
        
        # 設定台灣時區
        self.taiwan_tz = pytz.timezone('Asia/Taipei')
        
    async def cog_load(self):
        """Cog載入時啟動監控"""
        if not self.monitor_earthquake.is_running():
            self.monitor_earthquake.start()
            logger.info("地震監控已啟動")

    async def cog_unload(self):
        """Cog卸載時停止監控"""
        if self.monitor_earthquake.is_running():
            self.monitor_earthquake.stop()
            logger.info("地震監控已停止")

    async def get_earthquake_data(self):
        """獲取地震資料"""
        cwb_api_key = os.getenv("CWB_API_KEY")
        if not cwb_api_key:
            logger.error("CWB_API_KEY 未設置")
            return None

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                params = {"Authorization": cwb_api_key, "limit": 10}  # 恢復為10筆
                async with session.get(
                    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001",
                    params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        records = data.get("records", {}).get("Earthquake", [])
                        logger.info(f"成功獲取 {len(records)} 筆地震資料")
                        self.api_error_count = 0
                        self.last_successful_check = self.get_taiwan_time()
                        return records
                    else:
                        logger.error(f"API請求失敗: {resp.status}")
                        self.api_error_count += 1
                        return None
        except Exception as e:
            logger.error(f"獲取地震資料失敗: {e}")
            self.api_error_count += 1
            return None

    def get_quake_id(self, record):
        """生成地震唯一ID"""
        try:
            earthquake_info = record.get("EarthquakeInfo", {})
            origin_time = earthquake_info.get("OriginTime")
            magnitude = earthquake_info.get("EarthquakeMagnitude", {}).get("MagnitudeValue")
            location = earthquake_info.get("Epicenter", {}).get("Location")
            
            if origin_time and magnitude and location:
                # 簡化ID生成，只使用核心資訊
                id_string = f"{origin_time}_{magnitude}_{location}"
                return hashlib.md5(id_string.encode()).hexdigest()[:16]  # 縮短ID長度
        except Exception as e:
            logger.error(f"生成地震ID失敗: {e}")
        return None

    def get_taiwan_time(self):
        """獲取台灣當前時間"""
        utc_now = datetime.utcnow()
        utc_time = pytz.utc.localize(utc_now)
        taiwan_time = utc_time.astimezone(self.taiwan_tz)
        return taiwan_time

    def is_recent_earthquake(self, record, hours=4):  # 縮短為4小時
        """檢查地震是否在指定時間內發生"""
        try:
            earthquake_info = record.get("EarthquakeInfo", {})
            origin_time_str = earthquake_info.get("OriginTime")
            if not origin_time_str:
                logger.warning("地震記錄缺少時間資訊")
                return False
            
            # 嘗試多種時間格式
            time_formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ"
            ]
            
            origin_time = None
            for fmt in time_formats:
                try:
                    origin_time = datetime.strptime(origin_time_str, fmt)
                    break
                except ValueError:
                    continue
                    
            if not origin_time:
                logger.warning(f"無法解析時間格式: {origin_time_str}")
                return True  # 無法解析時假設是最近的
            
            # 將地震時間當作台灣時間處理
            origin_time = self.taiwan_tz.localize(origin_time)
            
            taiwan_now = self.get_taiwan_time()
            time_diff = taiwan_now - origin_time
            
            is_recent = time_diff <= timedelta(hours=hours)
            logger.debug(f"地震時間: {origin_time}, 當前時間: {taiwan_now}, 時差: {time_diff}, 是否最近: {is_recent}")
            
            return is_recent
        except Exception as e:
            logger.error(f"檢查地震時間失敗: {e}")
            return True

    async def get_ai_response(self, magnitude: float, location: str):
        """生成AI回應"""
        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            return self.get_fallback_response(magnitude)

        try:
            if magnitude >= 6.0:
                prompt = f"台灣{location}發生規模{magnitude}強震，請用緊急但溫暖的語氣提醒大家注意安全，80字內"
            elif magnitude >= 4.0:
                prompt = f"台灣{location}發生規模{magnitude}地震，請用關懷的語氣提醒注意，60字內"
            else:
                prompt = f"台灣{location}發生規模{magnitude}輕微地震，請用輕鬆親切的語氣告知，40字內"

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": os.getenv("AI_API_MODEL", "llama3-8b-8192"),
                "messages": [
                    {"role": "system", "content": "你是台灣氣象署的AI廣播員，回應要溫暖人性化"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.8,
                "max_tokens": 150
            }
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        return response if response else self.get_fallback_response(magnitude)
                    else:
                        logger.warning(f"AI API失敗: {resp.status}")
                        return self.get_fallback_response(magnitude)
        except Exception as e:
            logger.warning(f"AI回應生成失敗: {e}")
            return self.get_fallback_response(magnitude)

    def get_fallback_response(self, magnitude: float):
        """備用回應"""
        if magnitude >= 6.0:
            return "🚨 強震警報！請立即採取防護措施，蹲下掩護穩住，台灣人加油！"
        elif magnitude >= 4.0:
            return "⚠️ 有感地震，請大家保持冷靜，注意周圍環境安全"
        elif magnitude >= 3.0:
            return "📢 輕微地震，敏感的朋友可能有感覺，請安心"
        else:
            return "📡 微小地震活動記錄，一般不會有感覺"

    @tasks.loop(minutes=2)  # 固定2分鐘間隔，不要動態調整
    async def monitor_earthquake(self):
        """地震監控主任務"""
        try:
            logger.info("執行地震監控檢查...")
            
            # 如果連續API錯誤過多，暫時跳過
            if self.api_error_count >= 5:
                logger.warning(f"API錯誤次數過多({self.api_error_count})，跳過本次檢查")
                # 每30分鐘重置一次錯誤計數
                if not hasattr(self, '_last_reset') or \
                   (self.get_taiwan_time() - self._last_reset).total_seconds() > 1800:
                    self.api_error_count = 0
                    self._last_reset = self.get_taiwan_time()
                    logger.info("重置API錯誤計數器")
                return
            
            # 獲取地震資料
            records = await self.get_earthquake_data()
            if not records:
                logger.warning("未獲取到地震資料")
                return

            # 首次運行時的初始化
            if not self.initialization_complete:
                logger.info("開始初始化地震監控...")
                # 記錄最近4小時內的地震，避免重複推送
                for record in records:
                    if self.is_recent_earthquake(record, hours=4):
                        quake_id = self.get_quake_id(record)
                        if quake_id:
                            self.processed_quakes.add(quake_id)
                
                self.initialization_complete = True
                logger.info(f"監控初始化完成，已記錄 {len(self.processed_quakes)} 筆最近地震")
                return

            # 檢查新地震
            new_quakes = []
            for record in records:
                # 檢查是否為最近的地震
                if not self.is_recent_earthquake(record, hours=4):
                    continue
                
                quake_id = self.get_quake_id(record)
                if quake_id and quake_id not in self.processed_quakes:
                    earthquake_info = record.get("EarthquakeInfo", {})
                    magnitude = earthquake_info.get("EarthquakeMagnitude", {}).get("MagnitudeValue", 0)
                    location = earthquake_info.get("Epicenter", {}).get("Location", "未知")
                    
                    try:
                        magnitude_value = float(magnitude) if magnitude else 0
                    except (ValueError, TypeError):
                        magnitude_value = 0
                    
                    logger.info(f"發現新地震: ID={quake_id}, 地點={location}, 規模={magnitude_value}")
                    new_quakes.append(record)
                    self.processed_quakes.add(quake_id)

            # 清理過舊的記錄
            if len(self.processed_quakes) > 100:
                quake_list = list(self.processed_quakes)
                self.processed_quakes = set(quake_list[-50:])
                logger.info(f"清理舊地震記錄，保留 {len(self.processed_quakes)} 筆")

            # 處理新地震
            for record in new_quakes:
                try:
                    await self.process_earthquake(record)
                    await asyncio.sleep(2)  # 避免發送太快
                except Exception as e:
                    logger.error(f"處理地震事件失敗: {e}")

            if new_quakes:
                logger.info(f"處理了 {len(new_quakes)} 個新地震")
            else:
                logger.debug("沒有發現新地震")

        except Exception as e:
            logger.error(f"監控任務錯誤: {e}")
            self.api_error_count += 1

    async def process_earthquake(self, record):
        """處理單個地震事件"""
        try:
            earthquake_info = record.get("EarthquakeInfo", {})
            origin_time = earthquake_info.get("OriginTime", "未知時間")
            magnitude_info = earthquake_info.get("EarthquakeMagnitude", {})
            magnitude = magnitude_info.get("MagnitudeValue")
            location = earthquake_info.get("Epicenter", {}).get("Location", "未知地點")
            img_url = record.get("ReportImageURI")

            # 處理規模
            try:
                magnitude_value = float(magnitude) if magnitude else 0
            except (ValueError, TypeError):
                magnitude_value = 0

            # 降低門檻為2.0，確保有感地震都會被通知
            if magnitude_value < 2.0:
                logger.debug(f"跳過規模過小的地震: {magnitude_value}")
                return

            # 處理圖片URL
            if img_url and img_url.startswith("/"):
                img_url = "https://www.cwa.gov.tw" + img_url

            # 生成AI回應
            ai_response = await self.get_ai_response(magnitude_value, location)

            # 決定警報等級
            if magnitude_value >= 6.0:
                color, title = 0xff0000, "🌋 **重大地震警報**"
            elif magnitude_value >= 4.0:
                color, title = 0xffa500, "⚠️ **地震速報**"
            elif magnitude_value >= 3.0:
                color, title = 0xffff00, "📢 **地震通知**"
            else:
                color, title = 0x00ff00, "📡 **地震記錄**"

            # 建立嵌入訊息
            embed = discord.Embed(title=title, color=color)
            embed.add_field(name="🕒 發生時間", value=origin_time, inline=True)
            embed.add_field(name="📍 震央位置", value=location, inline=True)
            embed.add_field(name="📊 芮氏規模", value=str(magnitude_value), inline=True)
            embed.add_field(name="🎙️ AI廣播", value=ai_response, inline=False)
            
            if img_url:
                embed.set_image(url=img_url)
            
            embed.set_footer(text=f"資料來源：中央氣象署 | 檢查時間：{self.get_taiwan_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")

            # 發送訊息
            await self.send_notification(embed)
            logger.info(f"地震通知已發送: {location} 規模{magnitude_value}")

        except Exception as e:
            logger.error(f"處理地震事件失敗: {e}")

    async def send_notification(self, embed):
        """發送通知到Discord頻道"""
        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        if not channel_id:
            logger.error("DISCORD_CHANNEL_ID 未設置")
            return

        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                channel = await self.bot.fetch_channel(int(channel_id))
            
            await channel.send(embed=embed)
            logger.info("Discord通知發送成功")
            
        except Exception as e:
            logger.error(f"Discord通知發送失敗: {e}")

    @app_commands.command(name="earthquake", description="查詢最新地震資訊")
    async def earthquake_command(self, interaction: discord.Interaction):
        """手動查詢地震資訊"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            records = await self.get_earthquake_data()
            if not records:
                await interaction.followup.send("❌ 無法獲取地震資料", ephemeral=True)
                return

            record = records[0]
            
            earthquake_info = record.get("EarthquakeInfo", {})
            origin_time = earthquake_info.get("OriginTime", "未知")
            magnitude = earthquake_info.get("EarthquakeMagnitude", {}).get("MagnitudeValue", "未知")
            location = earthquake_info.get("Epicenter", {}).get("Location", "未知")
            
            embed = discord.Embed(
                title="📍 最新地震資訊",
                description=f"時間：{origin_time}\n地點：{location}\n規模：{magnitude}",
                color=0x0099ff
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"手動查詢失敗: {e}")
            await interaction.followup.send("❌ 查詢失敗，請稍後再試", ephemeral=True)

    @app_commands.command(name="earthquake_status", description="查看監控狀態")
    async def status_command(self, interaction: discord.Interaction):
        """查看監控狀態"""
        await interaction.response.defer(ephemeral=True)
        
        status = "✅ 運行中" if self.monitor_earthquake.is_running() else "❌ 已停止"
        processed_count = len(self.processed_quakes)
        init_status = "✅ 已完成" if self.initialization_complete else "⏳ 進行中"
        
        # 顯示詳細狀態
        last_check_info = "從未成功"
        if self.last_successful_check:
            taiwan_now = self.get_taiwan_time()
            time_diff = taiwan_now - self.last_successful_check
            if time_diff.total_seconds() < 60:
                last_check_info = f"{int(time_diff.total_seconds())} 秒前"
            elif time_diff.total_seconds() < 3600:
                last_check_info = f"{int(time_diff.total_seconds() // 60)} 分鐘前"
            else:
                last_check_info = f"{int(time_diff.total_seconds() // 3600)} 小時前"
        
        taiwan_time = self.get_taiwan_time().strftime('%Y-%m-%d %H:%M:%S %Z')
        
        embed = discord.Embed(
            title="🤖 地震監控狀態",
            description=f"監控狀態：{status}\n初始化：{init_status}\n已處理地震：{processed_count} 筆\n上次成功檢查：{last_check_info}\nAPI錯誤次數：{self.api_error_count}\n台灣時間：{taiwan_time}",
            color=0x00ff00 if self.monitor_earthquake.is_running() else 0xff0000
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="earthquake_reset", description="重置監控系統")
    async def reset_command(self, interaction: discord.Interaction):
        """重置監控系統"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            self.processed_quakes.clear()
            self.initialization_complete = False
            self.last_check_time = None
            self.api_error_count = 0
            self.last_successful_check = None
            
            embed = discord.Embed(
                title="🔄 監控系統已重置",
                description="所有地震記錄已清空，系統將重新初始化",
                color=0x00ff00
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info("監控系統已手動重置")
            
        except Exception as e:
            logger.error(f"重置監控系統失敗: {e}")
            await interaction.followup.send("❌ 重置失敗，請稍後再試", ephemeral=True)

    @app_commands.command(name="earthquake_test", description="測試最新地震通知")
    async def test_command(self, interaction: discord.Interaction):
        """測試地震通知功能"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            records = await self.get_earthquake_data()
            if not records:
                await interaction.followup.send("❌ 無法獲取地震資料", ephemeral=True)
                return
            
            # 處理第一筆地震資料進行測試
            record = records[0]
            await self.process_earthquake(record)
            
            await interaction.followup.send("✅ 測試通知已發送", ephemeral=True)
            logger.info("地震通知測試完成")
            
        except Exception as e:
            logger.error(f"測試失敗: {e}")
            await interaction.followup.send("❌ 測試失敗，請稍後再試", ephemeral=True)

    @monitor_earthquake.before_loop
    async def before_monitor(self):
        """等待機器人準備就緒"""
        await self.bot.wait_until_ready()
        logger.info("機器人準備就緒，開始地震監控")

    @monitor_earthquake.error
    async def monitor_error(self, error):
        """處理監控任務錯誤"""
        logger.error(f"地震監控任務發生錯誤: {error}")
        self.api_error_count += 1

async def setup(bot: commands.Bot):
    await bot.add_cog(Earthquake(bot))
