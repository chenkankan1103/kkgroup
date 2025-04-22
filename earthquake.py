import discord
from discord import app_commands
import aiohttp
import os
from discord.ext import tasks

last_earthquake_id = None
is_task_running = False

@tasks.loop(seconds=60)
async def monitor_earthquake_task(client):
    global last_earthquake_id, is_task_running
    if is_task_running:
        return
    is_task_running = True
    try:
        print("正在監控地震...")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001",
                params={"Authorization": os.getenv("CWB_API_KEY")}
            ) as resp:
                data = await resp.json()

        records = data.get("records", {}).get("Earthquake", [])
        if not records:
            print("找不到地震資料，跳過此次檢查。")
            return

        quake = records[0]
        quake_id = quake.get("EarthquakeNo")
        if quake_id == last_earthquake_id:
            print(f"地震ID {quake_id} 已經發送過了，跳過此次通知。")
            return

        last_earthquake_id = quake_id
        report_time = quake.get("ReportContent", "無")
        origin_time = quake.get("OriginTime", "無")
        magnitude = quake.get("MagnitudeValue", "無")
        location = quake.get("Location", "無")
        img_url = quake.get("ReportImageURI", None)
        if img_url and img_url.startswith("/"):
            img_url = "https://www.cwa.gov.tw" + img_url

        ai_response = await get_ai_response(float(magnitude) if magnitude not in ["", "無", None] else 0)

        embed = discord.Embed(
            title="地震速報",
            description=report_time,
            color=0xffcc00
        )
        embed.add_field(name="發生時間", value=origin_time, inline=True)
        embed.add_field(name="震央位置", value=location, inline=True)
        embed.add_field(name="芮氏規模", value=str(magnitude), inline=True)
        if img_url:
            embed.set_image(url=img_url)
        else:
            embed.set_footer(text="⚠️ 本次地震無速報圖片")
        embed.add_field(name="AI 回應", value=ai_response, inline=False)

        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        channel = await client.fetch_channel(int(channel_id))
        await channel.send(embed=embed)
        print("✅ 已發送地震速報。")

    except Exception as e:
        print(f"地震監控錯誤: {e}")
    finally:
        is_task_running = False

async def get_ai_response(magnitude: float):
    if magnitude < 3.0:
        style = "輕鬆的吐槽"
    elif magnitude < 6.0:
        style = "認真提醒"
    else:
        style = "警告與正式"

    prompt = f"請用{style}的語氣回應一場規模 {magnitude} 的地震，地點是某地，請加一些人性化的感受。"

    api_url = os.getenv("AI_API_URL")
    api_key = os.getenv("AI_API_KEY")
    model = os.getenv("AI_API_MODEL", "gpt-3.5-turbo")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位地震播報員"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as resp:
                resp_data = await resp.json()
                return resp_data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"AI 回應失敗: {e}")
        return "⚠️ AI 回應失敗，請稍後再試。"

async def setup_earthquake(tree, client):
    if not monitor_earthquake_task.is_running():
        monitor_earthquake_task.start(client)
        print("✅ 地震監控已啟動")

    @tree.command(name="earthquake", description="查詢最新地震資訊")
    async def earthquake_command(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001",
                    params={"Authorization": os.getenv("CWB_API_KEY")}
                ) as resp:
                    data = await resp.json()

            records = data.get("records", {}).get("Earthquake", [])
            if not records:
                await interaction.followup.send("目前沒有地震資料可顯示。")
                return

            quake = records[0]
            report_time = quake.get("ReportContent", "無")
            origin_time = quake.get("OriginTime", "無")
            magnitude = quake.get("MagnitudeValue", "無")
            location = quake.get("Location", "無")
            img_url = quake.get("ReportImageURI", None)
            if img_url and img_url.startswith("/"):
                img_url = "https://www.cwa.gov.tw" + img_url

            embed = discord.Embed(
                title="最新地震資訊",
                description=report_time,
                color=0xffcc00
            )
            embed.add_field(name="發生時間", value=origin_time, inline=True)
            embed.add_field(name="震央位置", value=location, inline=True)
            embed.add_field(name="芮氏規模", value=str(magnitude), inline=True)
            if img_url:
                embed.set_image(url=img_url)
            else:
                embed.set_footer(text="⚠️ 本次地震無速報圖片")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"取得地震資料時發生錯誤: {e}")
            await interaction.followup.send(f"取得地震資料時發生錯誤: {str(e)}")

    @tree.command(name="monitor", description="啟動或停止地震監控")
    @app_commands.choices(action=[
        app_commands.Choice(name="啟動", value="start"),
        app_commands.Choice(name="停止", value="stop")
    ])
    async def monitor_command(interaction: discord.Interaction, action: str):
        if action == "start":
            if not monitor_earthquake_task.is_running():
                monitor_earthquake_task.start(client)
                await interaction.response.send_message("✅ 地震監控已啟動")
            else:
                await interaction.response.send_message("❗ 地震監控已經在運行中")
        else:
            if monitor_earthquake_task.is_running():
                monitor_earthquake_task.cancel()
                await interaction.response.send_message("🛑 地震監控已停止")
            else:
                await interaction.response.send_message("❗ 地震監控未在運行中")

    print("✅ 地震模組已載入")