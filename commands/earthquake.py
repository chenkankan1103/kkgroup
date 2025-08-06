import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import os
import asyncio
import logging
from datetime import datetime, timedelta
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Earthquake(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processed_quakes = set()  # 使用 set 儲存已處理的地震ID
        self.last_check_time = None
        self.initialization_complete = False  # 新增初始化完成標記
        self.api_error_count = 0  # 追蹤API錯誤次數
        self.last_successful_check = None  # 上次成功檢查時間
        
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
            timeout = aiohttp.ClientTimeout(total=20)  # 增加超時時間
            async with aiohttp.ClientSession(timeout=timeout) as session:
                params = {"Authorization": cwb_api_key, "limit": 5}  # 減少限制數量從10改為5
                async with session.get(
                    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001",
                    params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        records = data.get("records", {}).get("Earthquake", [])
                        logger.info(f"成功獲取 {len(records)} 筆地震資料")
                        self.api_error_count = 0  # 重置錯誤計數
                        self.last_successful_check = datetime.now()
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
        """生成地震唯一ID - 使用更穩定的方法"""
        try:
            earthquake_info = record.get("EarthquakeInfo", {})
            origin_time = earthquake_info.get("OriginTime")
            magnitude = earthquake_info.get("EarthquakeMagnitude", {}).get("MagnitudeValue")
            location = earthquake_info.get("Epicenter", {}).get("Location")
            
            # 使用更多欄位來確保唯一性
            epicenter_info = earthquake_info.get("Epicenter", {})
            epicenter_lat = epicenter_info.get("EpicenterLatitude")
            epicenter_lon = epicenter_info.get("EpicenterLongitude")
            depth = earthquake_info.get("FocalDepth")
            
            if origin_time and magnitude and location:
                # 創建一個更穩定的ID，包含經緯度和深度
                id_string = f"{origin_time}_{magnitude}_{location}_{epicenter_lat}_{epicenter_lon}_{depth}"
                # 使用hash來避免ID過長
                return hashlib.md5(id_string.encode()).hexdigest()
        except Exception as e:
            logger.error(f"生成地震ID失敗: {e}")
        return None

    def is_recent_earthquake(self, record, hours=24):
        """檢查地震是否在指定時間內發生"""
        try:
            earthquake_info = record.get("EarthquakeInfo", {})
            origin_time_str = earthquake_info.get("OriginTime")
            if not origin_time_str:
                return False
            
            # 解析時間格式 (假設格式為 "2024-01-01 12:00:00")
            origin_time = datetime.strptime(origin_time_str, "%Y-%m-%d %H:%M:%S")
            time_diff = datetime.now() - origin_time
            
            return time_diff <= timedelta(hours=hours)
        except Exception as e:
            logger.error(f"檢查地震時間失敗: {e}")
            return True  # 如果無法解析時間，則假設是最近的

    async def get_ai_response(self, magnitude: float, location: str):
        """生成AI回應"""
        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            return self.get_fallback_response(magnitude)

        try:
            # 根據規模調整回應風格
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
            
            timeout = aiohttp.ClientTimeout(total=10)  # 增加AI API超時時間
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

    def get_dynamic_check_interval(self):
        """動態調整檢查間隔"""
        now = datetime.now()
        current_hour = now.hour
        
        # 深夜時間（23:00-06:00）較少檢查 - 10分鐘
        if current_hour >= 23 or current_hour < 6:
            return 10
        # 一般時間（06:00-23:00）- 5分鐘
        else:
            return 5

    @tasks.loop(minutes=5)  # 基礎間隔調整為5分鐘（從2分鐘增加）
    async def monitor_earthquake(self):
        """地震監控主任務"""
        try:
            # 動態檢查間隔控制
            now = datetime.now()
            if self.last_check_time:
                expected_interval = self.get_dynamic_check_interval()
                time_since_last = (now - self.last_check_time).total_seconds() / 60
                
                # 如果還沒到檢查時間，跳過
                if time_since_last < expected_interval:
                    logger.debug(f"距離上次檢查僅{time_since_last:.1f}分鐘，跳過檢查（需間隔{expected_interval}分鐘）")
                    return
            
            # 如果連續多次API錯誤，延長檢查間隔
            if self.api_error_count >= 3:
                skip_minutes = min(self.api_error_count * 5, 30)  # 最多跳過30分鐘
                logger.warning(f"API錯誤次數過多({self.api_error_count})，跳過{skip_minutes}分鐘檢查")
                
                if self.last_check_time:
                    time_since_last = (now - self.last_check_time).total_seconds() / 60
                    if time_since_last < skip_minutes:
                        return
                
                # 重置錯誤計數器，避免永久停止
                if self.api_error_count >= 12:  # 1小時後重置
                    self.api_error_count = 0
                    logger.info("重置API錯誤計數器")

            logger.debug("執行地震監控檢查...")
            self.last_check_time = now
            
            # 獲取地震資料
            records = await self.get_earthquake_data()
            if not records:
                return

            # 首次運行時初始化 - 記錄所有最近的地震
            if not self.initialization_complete:
                # 記錄所有最近24小時內的地震，避免重複推送
                for record in records:
                    if self.is_recent_earthquake(record, hours=24):
                        quake_id = self.get_quake_id(record)
                        if quake_id:
                            self.processed_quakes.add(quake_id)
                
                self.initialization_complete = True
                logger.info(f"監控初始化完成，已記錄 {len(self.processed_quakes)} 筆最近地震")
                return

            # 檢查新地震
            new_quakes = []
            for record in records:
                # 只處理最近24小時內的地震
                if not self.is_recent_earthquake(record, hours=24):
                    continue
                
                quake_id = self.get_quake_id(record)
                if quake_id and quake_id not in self.processed_quakes:
                    new_quakes.append(record)
                    self.processed_quakes.add(quake_id)
                    logger.info(f"發現新地震: {quake_id}")

            # 清理過舊的記錄，只保留最近150筆（從200減少）
            if len(self.processed_quakes) > 150:
                # 轉換為列表並保留最新的75筆（從100減少）
                quake_list = list(self.processed_quakes)
                self.processed_quakes = set(quake_list[-75:])
                logger.info(f"清理舊地震記錄，保留 {len(self.processed_quakes)} 筆")

            # 處理新地震
            for record in new_quakes:
                await self.process_earthquake(record)
                await asyncio.sleep(3)  # 增加延遲避免發送太快（從2秒增加到3秒）

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

            # 只處理有意義的地震（規模2.5以上，提高門檻減少通知）
            if magnitude_value < 2.5:
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
            
            embed.set_footer(text=f"資料來源：中央氣象署 | 檢查時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

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
            
            # 同時發送給查詢者
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
        
        # 計算上次成功檢查的時間
        last_check_info = "從未成功"
        if self.last_successful_check:
            time_diff = datetime.now() - self.last_successful_check
            if time_diff.total_seconds() < 60:
                last_check_info = f"{int(time_diff.total_seconds())} 秒前"
            elif time_diff.total_seconds() < 3600:
                last_check_info = f"{int(time_diff.total_seconds() // 60)} 分鐘前"
            else:
                last_check_info = f"{int(time_diff.total_seconds() // 3600)} 小時前"
        
        # 顯示當前檢查間隔
        current_interval = self.get_dynamic_check_interval()
        
        embed = discord.Embed(
            title="🤖 地震監控狀態",
            description=f"監控狀態：{status}\n初始化：{init_status}\n已處理地震：{processed_count} 筆\n上次成功檢查：{last_check_info}\nAPI錯誤次數：{self.api_error_count}\n當前檢查間隔：{current_interval} 分鐘",
            color=0x00ff00 if self.monitor_earthquake.is_running() else 0xff0000
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="earthquake_reset", description="重置監控系統")
    async def reset_command(self, interaction: discord.Interaction):
        """重置監控系統"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 清空已處理的地震記錄
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
