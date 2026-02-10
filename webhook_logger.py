import os
import discord
from discord.ext import commands
import asyncio

async def delete_old_webhook_message(webhook, old_message_id):
    try:
        old_message = await webhook.fetch_message(old_message_id)
        await old_message.delete()
    except discord.NotFound:
        print("Old message not found, it might have been deleted already.")
    except discord.Forbidden:
        print("Error: Missing permissions to delete the old message.")
    except Exception as e:
        print(f"An error occurred while deleting the old message: {e}")

async def send_new_webhook_message(webhook, content):
    try:
        new_message = await webhook.send(content)
        return new_message.id
    except Exception as e:
        print(f"Failed to send new webhook message: {e}")
        return None

async def main():
    # Load old message ID from .env
    old_message_id = os.getenv("OLD_MESSAGE_ID")
    webhook_url = os.getenv("WEBHOOK_URL")
    content = "New webhook message content"
    
    webhook = discord.Webhook.from_url(webhook_url, adapter=discord.RequestsWebhookAdapter())

    if old_message_id:
        await delete_old_webhook_message(webhook, old_message_id)
    
    new_message_id = await send_new_webhook_message(webhook, content)
    if new_message_id is not None:
        # Save new message ID in .env or a file
        save_new_message_id(new_message_id)
        print(f"New message sent with ID: {new_message_id}")
    else:
        print("Failed to send new message.")

# Other functionalities (load_bots_info, save_bots_info, update_bot_info, create embeds, etc.) go here.

if __name__ == '__main__':
    asyncio.run(main()) 
