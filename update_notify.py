import os
import discord
import asyncio

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_SYS_CHANNEL_ID = int(os.getenv("DISCORD_SYS_CHANNEL_ID"))

async def main():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        channel = client.get_channel(DISCORD_SYS_CHANNEL_ID)
        if channel:
            await channel.send("🤖 Bot 已自動更新到最新版本 ✅")
        await client.close()

    await client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
