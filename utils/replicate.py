import aiohttp
import os
import asyncio
from io import BytesIO

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")  # 你的API金鑰，從.env載入
REPLICATE_API_BASE = "https://api.replicate.com/v1"

# 自動取得最新的模型版本 ID
async def get_latest_version(model_name: str) -> str:
    """
    自動取得指定模型的最新版本 ID
    :param model_name: 模型名稱，例如 "black-forest-labs/flux-1.1-pro"
    :return: 最新版的 version id 字串
    """
    url = f"{REPLICATE_API_BASE}/models/{model_name}/versions"
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"取得模型版本失敗：HTTP {resp.status} {await resp.text()}")
            data = await resp.json()
            if "results" not in data or not data["results"]:
                raise Exception(f"找不到模型 {model_name} 的任何版本")
            latest_version = data["results"][0]["id"]  # 最新的一個
            return latest_version


# 呼叫 Replicate 生成圖片
async def generate_image_from_replicate(user_input: str, model_name: str) -> BytesIO:
    """
    生成圖片並從 Replicate 取得結果
    :param user_input: 用戶輸入的文字描述
    :param model_name: 模型名稱，例如 "black-forest-labs/flux-1.1-pro"
    :return: 生成的圖片資料
    """
    version_id = await get_latest_version(model_name)

    payload = {
        "version": version_id,
        "input": {"prompt": user_input}
    }
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{REPLICATE_API_BASE}/predictions"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            response_data = await resp.json()

    # 確保成功取得圖片結果
    if "error" in response_data:
        raise Exception(f"Replicate 生圖失敗：{response_data['error']}")

    prediction_url = response_data.get("urls", {}).get("get")
    if not prediction_url:
        raise Exception("Replicate 預測創建失敗，無法獲取預測 URL。")

    # 等待結果
    while True:
        async with session.get(prediction_url, headers=headers) as status_resp:
            status_data = await status_resp.json()
            if status_data.get("status") == "succeeded":
                output_url = status_data["output"][0]
                async with session.get(output_url) as img_resp:
                    image_data = await img_resp.read()
                return BytesIO(image_data)
            elif status_data.get("status") in ("failed", "canceled"):
                raise Exception("Replicate 生圖失敗。")
            await asyncio.sleep(2)
