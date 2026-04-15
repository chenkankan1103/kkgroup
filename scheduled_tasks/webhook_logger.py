"""
統一的啟動資訊發送器 - 使用 Webhook
"""
import os
import json
import aiohttp
import asyncio
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

# bots_info 文件路徑
bots_info_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bots_info.json')

def load_bots_info():
    """從文件加載 bots_info"""
    try:
        if os.path.exists(bots_info_file):
            with open(bots_info_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        log_webhook(f"❌ 加載 bots_info 失敗: {e}")

    # 返回默認值
    return {
        "bot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []},
        "shopbot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []},
        "uibot": {"啟動時間": None, "狀態": "⏳ 啟動中", "指令": [], "擴展": []}
    }

def save_bots_info(bots_info):
    """保存 bots_info 到文件"""
    try:
        with open(bots_info_file, 'w', encoding='utf-8') as f:
            json.dump(bots_info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_webhook(f"❌ 保存 bots_info 失敗: {e}")

# 初始化 bots_info
bots_info = load_bots_info()
log_webhook(f"✅ 已加載 bots_info: {list(bots_info.keys())}")


async def update_bot_info(bot_type: str, startup_time: str, commands: list, extensions: list):
    global bots_info

    # 從文件重新加載最新狀態
    bots_info = load_bots_info()

    if bot_type in bots_info:
        old_time = bots_info[bot_type]["啟動時間"]
        bots_info[bot_type]["啟動時間"] = startup_time
        bots_info[bot_type]["狀態"] = "🟢 在線"
        bots_info[bot_type]["指令"] = commands
        bots_info[bot_type]["擴展"] = extensions

        # 保存到文件
        save_bots_info(bots_info)

        log_webhook(f"✅ {bot_type.upper()} 資訊已更新 - 舊時間: {old_time}, 新時間: {startup_time}, 指令: {len(commands)}, 擴展: {len(extensions)}")
        print(f"[DEBUG] {bot_type} bots_info 更新成功 - 時間: {startup_time}")
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


async def delete_old_webhook_message(msg_id):
    """嘗試刪除舊訊息，出錯不崩潰"""
    try:
        if not msg_id or not WEBHOOK_URL:
            return False
        
        log_webhook(f"🗑️ 嘗試刪除舊訊息 ID={msg_id}")
        delete_url = f"{WEBHOOK_URL}/messages/{msg_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.delete(delete_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                log_webhook(f"🗑️ DELETE 響應碼: {resp.status}")
                if resp.status == 204:
                    log_webhook("✅ 舊訊息已成功刪除")
                    return True
                else:
                    log_webhook(f"⚠️ 刪除訊息返回: {resp.status}（可能訊息已不存在）")
                    return False
    except asyncio.TimeoutError:
        log_webhook("⚠️ 刪除訊息超時（網絡問題）")
        return False
    except Exception as e:
        log_webhook(f"⚠️ 刪除舊訊息失敗（非致命）: {type(e).__name__}: {e}")
        return False


async def send_new_webhook_message(payload):
    """發送新訊息，出錯不崩潰，返回訊息 ID"""
    try:
        log_webhook("📨 發送新的啟動訊息...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                log_webhook(f"📨 POST 響應碼: {resp.status}")
                
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        new_msg_id = data.get("id")
                        if new_msg_id:
                            log_webhook(f"✅ 啟動資訊已發送，訊息 ID={new_msg_id}")
                            return new_msg_id
                        else:
                            log_webhook("⚠️ 無法從響應中獲取訊息 ID")
                            return None
                    except Exception as e:
                        log_webhook(f"⚠️ 解析 JSON 失敗: {e}")
                        return None
                elif resp.status == 204:
                    log_webhook(f"✅ 啟動資訊已發送 (HTTP {resp.status})")
                    return None
                else:
                    try:
                        resp_text = await resp.text()
                        log_webhook(f"❌ Webhook 失敗 (HTTP {resp.status}): {resp_text[:200]}")
                    except:
                        log_webhook(f"❌ Webhook 失敗 (HTTP {resp.status})")
                    return None
    except asyncio.TimeoutError:
        log_webhook("❌ 發送訊息超時（網絡問題）")
        return None
    except Exception as e:
        log_webhook(f"❌ 發送訊息出錯（非致命）: {type(e).__name__}: {e}")
        return None


async def send_or_update_startup_info(bot_type: str = None):
    """
    統一發送啟動資訊
    只有 bot 會實際發送訊息，其他機器人只更新資訊
    """
    global webhook_message_id, bots_info

    try:
        # 從文件重新加載最新的 bots_info
        bots_info = load_bots_info()
        log_webhook(f"📂 已重新加載 bots_info: bot={bots_info['bot']['啟動時間']}, shopbot={bots_info['shopbot']['啟動時間']}, uibot={bots_info['uibot']['啟動時間']}")

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
                # 移除多餘的 embed 創建，日誌功能由 status_dashboard.py 處理
                # await create_overview_embed(),
                # await create_bot_detail_embed("bot"),
                # await create_bot_detail_embed("shopbot"),
                # await create_bot_detail_embed("uibot")
            ]
            
            # 如果沒有 embeds，跳過發送
            if not embeds:
                log_webhook("ℹ️ 沒有 embeds 需要發送，跳過 webhook")
                return
            
            payload = {"embeds": embeds}
            
            # 【改進】先刪除舊訊息，然後發送新訊息（確保不會堆積）
            old_msg_id = webhook_message_id
            if old_msg_id:
                # 嘗試刪除舊訊息（出錯不崩潰）
                await delete_old_webhook_message(old_msg_id)
            
            # 發送新訊息（出錯不崩潰）
            new_msg_id = await send_new_webhook_message(payload)
            
            # 更新全局和環境變數
            if new_msg_id:
                webhook_message_id = new_msg_id
                try:
                    set_key(".env", "WEBHOOK_MESSAGE_ID", str(new_msg_id))
                except Exception as e:
                    log_webhook(f"⚠️ 無法保存訊息 ID 到 .env: {e}")
            
        except Exception as e:
            import traceback
            log_webhook(f"❌ 訊息發送過程出錯（非致命）: {type(e).__name__}: {e}")
            log_webhook(f"完整堆棧: {traceback.format_exc()[:200]}")
            # 不重新拋出異常，讓機器人繼續運行
            
    except Exception as e:
        import traceback
        log_webhook(f"❌ 最高層級錯誤（防止機器人崩潰）: {type(e).__name__}: {e}")
        log_webhook(f"完整堆棧: {traceback.format_exc()[:200]}")
        # 不重新拋出異常，讓機器人繼續運行


_stored_msg_id = os.getenv("WEBHOOK_MESSAGE_ID")
if _stored_msg_id:
    try:
        webhook_message_id = int(_stored_msg_id)
    except:
        pass