# utils/earthquake.py
import aiohttp
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 每次查詢間隔（秒）
POLL_INTERVAL = 60

# API URL
CWB_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001"
CWB_API_KEY = os.getenv("CWB_API_KEY")

# 狀態紀錄用
last_quake_id = None

async def fetch_quake_data():
    params = {"Authorization": CWB_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(CWB_API_URL, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def monitor_quake(client):
    global last_quake_id
    await client.wait_until_ready()

    while not client.is_closed():
        data = await fetch_quake_data()
        if data and "records" in data:
            quakes = data["records"].get("earthquake", [])
            if quakes:
                latest = quakes[0]
                quake_id = latest.get("earthquakeNo")

                if quake_id != last_quake_id:
                    last_quake_id = quake_id

                    # 解析訊息
                    time = latest["earthquakeInfo"]["originTime"]
                    location = latest["earthquakeInfo"]["epiCenter"]["location"]
                    magnitude = latest["earthquakeInfo"]["magnitude"]["magnitudeValue"]

                    threshold = float(os.getenv("MAG_THRESHOLD", 2.0))
                    if float(magnitude) >= threshold:
                        msg = f"🌏 **地震速報**\n時間：{time}\n震央：{location}\n芮氏規模：{magnitude}"

                        channel_id = os.getenv("DISCORD_CHANNEL_ID")
                        if channel_id:
                            channel = client.get_channel(int(channel_id))
                            if channel:
                                await channel.send(msg)

        await asyncio.sleep(POLL_INTERVAL)

# 在主程式中呼叫此函式即可
def start_quake_monitor(client):
    client.loop.create_task(monitor_quake(client))
