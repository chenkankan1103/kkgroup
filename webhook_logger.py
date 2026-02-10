"""
統一的啟動資訊發送器 - 使用 Webhook
"""
import os
import aiohttp
import logging
from datetime import datetime
from dotenv import load_dotenv, set_key

load_dotenv()

# 設定logging - 使用絕對路徑
import os.path
log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, 'webhook_logger.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('WEBHOOK')
logger.info(f"Webhook logger initialized, log file: {log_file}")

WEBHOOK_URL = os.getenv("STARTUP_WEBHOOK_URL", "")
webhook_message_id = None
logger.info(f"WEBHOOK_URL: {WEBHOOK_URL[:50] if WEBHOOK_URL else 'Not Set'}...")

bots_info = {
    "bot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []},
    "shopbot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []},
    "uibot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []}
}


async def update_bot_info(bot_type: str, startup_time: str, commands: list, extensions: list):
    if bot_type in bots_info:
        bots_info[bot_type]["啟動時間"] = startup_time
        bots_info[bot_type]["狀態"] = "🟢 在線"
        bots_info[bot_type]["指令"] = commands
        bots_info[bot_type]["擴展"] = extensions


async def create_overview_embed() -> dict:
    status_text = ""
    for bot_name in ["bot", "shopbot", "uibot"]:
        info = bots_info[bot_name]
        emoji = "🟢" if info["狀態"] == "🟢 在線" else "🔴"
        time_text = info["啟動時間"] if info["啟動時間"] else "未啟動"
        status_text += f"{emoji} **{bot_name.upper()}** - {time_text}\n"
    
    return {
        "title": "🤖 所有機器人狀態",
        "description": status_text,
        "color": 3447003,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "機器人監控系統"}
    }


async def create_bot_detail_embed(bot_type: str) -> dict:
    bot_name_map = {"bot": "🤖 Main Bot", "shopbot": "🛍️ Shop Bot", "uibot": "🎨 UI Bot"}
    color_map = {"bot": 3447003, "shopbot": 9442302, "uibot": 16776960}
    
    info = bots_info[bot_type]
    fields = []
    
    if info["擴展"]:
        ext_text = " | ".join(info["擴展"][:8])
        if len(info["擴展"]) > 8:
            ext_text += f"\n*...還有 {len(info['擴展']) - 8} 個*"
        fields.append({"name": f"📦 擴展 ({len(info['擴展'])})", "value": ext_text or "無", "inline": False})
    
    if info["指令"]:
        cmd_text = " | ".join(info["指令"][:10])
        if len(info["指令"]) > 10:
            cmd_text += f"\n*...還有 {len(info['指令']) - 10} 個*"
        fields.append({"name": f"⚡ Slash 指令 ({len(info['指令'])})", "value": cmd_text or "無", "inline": False})
    
    return {
        "title": f"{bot_name_map[bot_type]} 詳情",
        "color": color_map[bot_type],
        "fields": fields,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": f"狀態: {info['狀態']}"}
    }


async def send_or_update_startup_info():
    global webhook_message_id
    
    if not WEBHOOK_URL:
        logger.warning("WEBHOOK_URL 未設定")
        return
    
    try:
        logger.info("準備發送啟動資訊...")
        
        embeds = [
            await create_overview_embed(),
            await create_bot_detail_embed("bot"),
            await create_bot_detail_embed("shopbot"),
            await create_bot_detail_embed("uibot")
        ]
        
        payload = {"embeds": embeds}
        
        # 嘗試編輯
        if webhook_message_id:
            try:
                logger.info(f"嘗試編輯訊息 ID={webhook_message_id}")
                url = f"{WEBHOOK_URL}/messages/{webhook_message_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.patch(url, json=payload) as resp:
                        logger.info(f"PATCH 響應碼: {resp.status}")
                        if resp.status in [200, 204]:
                            logger.info(f"✅ 啟動資訊已更新 (HTTP {resp.status})")
                            return
            except Exception as patch_err:
                logger.warning(f"編輯訊息失敗: {patch_err}")
        
        # 發送新訊息
        logger.info("發送新的啟動訊息...")
        async with aiohttp.ClientSession() as session:
            async with session.post(WEBHOOK_URL, json=payload) as resp:
                logger.info(f"POST 響應碼: {resp.status}")
                if resp.status in [200, 204]:
                    if resp.status == 200:
                        data = await resp.json()
                        webhook_message_id = data.get("id")
                        if webhook_message_id:
                            set_key(".env", "WEBHOOK_MESSAGE_ID", str(webhook_message_id))
                            logger.info(f"✅ 啟動資訊已發送，訊息 ID={webhook_message_id}")
                        else:
                            logger.warning("無法獲取訊息 ID")
                    else:
                        logger.info(f"✅ 啟動資訊已發送 (HTTP {resp.status})")
                else:
                    resp_text = await resp.text()
                    logger.error(f"Webhook 失敗 (HTTP {resp.status}): {resp_text[:200]}")
    except Exception as e:
        import traceback
        logger.error(f"訊息失敗: {e}")
        logger.error(traceback.format_exc())


_stored_msg_id = os.getenv("WEBHOOK_MESSAGE_ID")
if _stored_msg_id:
    try:
        webhook_message_id = int(_stored_msg_id)
    except:
        pass
