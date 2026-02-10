"""
統一的啟動資訊發送器 - 使用 Webhook
"""
import os
import aiohttp
from datetime import datetime
from dotenv import load_dotenv, set_key

load_dotenv()

# 簡單的文件日誌寫入函數
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webhook_logger.log')
def log_webhook(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[WEBHOOK] {msg}")

log_webhook("🔄 Webhook logger started")

WEBHOOK_URL = os.getenv("STARTUP_WEBHOOK_URL", "")
webhook_message_id = None
log_webhook(f"WEBHOOK_URL: {WEBHOOK_URL[:50] if WEBHOOK_URL else 'Not Set'}...")

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
        log_webhook(f"✅ {bot_type.upper()} 資訊已更新 - 啟動時間: {startup_time}, 指令: {len(commands)}, 擴展: {len(extensions)}")
        print(f"[DEBUG] {bot_type} bots_info 更新成功")
    else:
        log_webhook(f"❌ {bot_type} 不在 bots_info 中 (可用的: {list(bots_info.keys())})")
        print(f"[DEBUG] {bot_type} 更新失敗 - 鍵不存在")


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


async def send_or_update_startup_info(bot_type: str = None):
    """
    統一發送啟動資訊
    只有 bot 會實際發送訊息，其他機器人只更新資訊
    """
    global webhook_message_id
    
    # 如果指定了 bot_type 且不是 "bot"，就不發送訊息
    if bot_type and bot_type != "bot":
        log_webhook(f"ℹ️ {bot_type} 已更新資訊")
        return
    
    if not WEBHOOK_URL:
        log_webhook("❌ WEBHOOK_URL 未設定")
        return
    
    try:
        log_webhook("🔄 準備發送啟動資訊...")
        
        # 等待機器人啟動（最少等20秒，最多等40秒，或所有機器人都啟動）
        import asyncio
        start_time = asyncio.get_event_loop().time()
        min_wait = 20  # 最小等待秒數
        max_wait = 40  # 最大等待秒數
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            all_started = all(bots_info[bot]["啟動時間"] for bot in ["bot", "shopbot", "uibot"])
            
            # 條件 1: 所有機器人都啟動且滿足最小等待時間
            if all_started and elapsed >= min_wait:
                log_webhook(f"✅ 所有機器人已啟動 ({int(elapsed)} 秒)，準備發送訊息")
                break
            
            # 條件 2: 超過最大等待時間
            if elapsed >= max_wait:
                if all_started:
                    log_webhook(f"✅ 所有機器人已啟動，準備發送訊息")
                else:
                    missing_bots = [bot for bot in ["bot", "shopbot", "uibot"] if not bots_info[bot]["啟動時間"]]
                    log_webhook(f"🔴 異常：機器人未在 {max_wait} 秒內啟動 {missing_bots}，強制發送訊息")
                break
            
            await asyncio.sleep(0.5)
        
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
                log_webhook(f"📝 嘗試編輯訊息 ID={webhook_message_id}")
                url = f"{WEBHOOK_URL}/messages/{webhook_message_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.patch(url, json=payload) as resp:
                        log_webhook(f"📝 PATCH 響應碼: {resp.status}")
                        if resp.status in [200, 204]:
                            log_webhook(f"✅ 啟動資訊已更新 (HTTP {resp.status})")
                            return
            except Exception as patch_err:
                log_webhook(f"⚠️ 編輯訊息失敗: {patch_err}")
        
        # 發送新訊息
        log_webhook("📨 發送新的啟動訊息...")
        async with aiohttp.ClientSession() as session:
            async with session.post(WEBHOOK_URL, json=payload) as resp:
                log_webhook(f"📨 POST 響應碼: {resp.status}")
                if resp.status in [200, 204]:
                    if resp.status == 200:
                        data = await resp.json()
                        webhook_message_id = data.get("id")
                        if webhook_message_id:
                            set_key(".env", "WEBHOOK_MESSAGE_ID", str(webhook_message_id))
                            log_webhook(f"✅ 啟動資訊已發送，訊息 ID={webhook_message_id}")
                        else:
                            log_webhook("⚠️ 無法獲取訊息 ID")
                    else:
                        log_webhook(f"✅ 啟動資訊已發送 (HTTP {resp.status})")
                else:
                    resp_text = await resp.text()
                    log_webhook(f"❌ Webhook 失敗 (HTTP {resp.status}): {resp_text[:200]}")
    except Exception as e:
        import traceback
        log_webhook(f"❌ 訊息失敗: {e}")
        log_webhook(traceback.format_exc())


_stored_msg_id = os.getenv("WEBHOOK_MESSAGE_ID")
if _stored_msg_id:
    try:
        webhook_message_id = int(_stored_msg_id)
    except:
        pass
