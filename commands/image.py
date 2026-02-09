import discord
from discord.ext import commands
import google.generativeai as genai
from io import BytesIO
from PIL import Image
import os
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# 圖片歷史記錄路徑
IMAGES_HISTORY_DIR = Path("data/image_history")
IMAGES_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

class ImageHandler:
    """處理所有圖片相關操作——生圖、編圖、看圖"""
    
    # 圖片相關關鍵詞檢測
    IMAGE_KEYWORDS = {
        "生圖": ["生", "生圖", "生成圖", "畫", "畫圖"],
        "編圖": ["編", "P圖", "編輯圖", "改", "修改", "調整", "改圖"],
        "看圖": ["看", "看圖", "分析圖", "檢查圖", "掃描圖", "檢查", "掃描"]
    }
    
    def __init__(self, api_key: str):
        """初始化圖片處理器"""
        genai.configure(api_key=api_key)
        self.api_key = api_key
        logger.info("✅ 圖片處理器已初始化")
    
    @staticmethod
    def detect_image_request(message_content: str) -> Optional[str]:
        """
        偵測訊息是否包含圖片相關請求
        回傳：'生圖', '編圖', '看圖', 或 None
        """
        content_lower = message_content.lower()
        
        for request_type, keywords in ImageHandler.IMAGE_KEYWORDS.items():
            # 將所有關鍵詞轉為小寫進行比較
            if any(kw.lower() in content_lower for kw in keywords):
                return request_type
        
        return None
    
    async def generate_image(self, prompt: str, user_id: int, aspect_ratio: str = "1:1") -> tuple[Optional[bytes], str]:
        """
        生成圖片
        
        Args:
            prompt: 描述文字
            user_id: 使用者ID（用於記錄）
            aspect_ratio: 圖片比例 (1:1, 4:3, 16:9, 9:16)
        
        Returns:
            (圖片位元組, 訊息)
        """
        try:
            logger.info(f"📸 開始生圖: {prompt[:50]}...")
            
            # 使用 gemini-2.5-flash-image 模型生成圖片
            model = genai.GenerativeModel('gemini-2.5-flash-image')
            
            # 生成圖片
            response = model.generate_content(prompt)
            
            # 檢查回應中是否包含圖片
            if not response.parts:
                return None, "❌ 圖片生成失敗：未返回圖片。"
            
            # 提取第一張圖片
            image_data = None
            for part in response.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    image_data = part.inline_data.data
                    break
            
            if not image_data:
                return None, "❌ 圖片生成失敗：回應中沒有圖片數據。"
            
            # 保存歷史記錄
            await self._save_history(
                user_id=user_id,
                action="generate",
                prompt=prompt,
                image_size=len(image_data),
                result="圖片已生成"
            )
            
            logger.info(f"✅ 生圖成功 (大小: {len(image_data)} bytes)")
            return image_data, f"✅ 圖片已生成"
            
        except Exception as e:
            error_msg = f"❌ 生圖失敗: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    async def edit_image(self, image_data: bytes, edit_prompt: str, user_id: int) -> tuple[Optional[bytes], str]:
        """
        編輯圖片
        
        Args:
            image_data: 原始圖片資料
            edit_prompt: 編輯指令
            user_id: 使用者ID
        
        Returns:
            (編輯後的圖片位元組, 訊息)
        """
        try:
            logger.info(f"🎨 開始編圖: {edit_prompt[:50]}...")
            
            # 轉換圖片為PIL Image
            image = Image.open(BytesIO(image_data))
            
            # 使用 gemini-2.5-flash-image 模型進行編輯
            model = genai.GenerativeModel('gemini-2.5-flash-image')
            response = model.generate_content([
                f"編輯這張圖片：{edit_prompt}",
                image
            ])
            
            # 檢查回應中是否包含圖片
            if not response.parts:
                return None, "❌ 圖片編輯失敗：未返回圖片。"
            
            # 提取第一張圖片
            edited_data = None
            for part in response.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    edited_data = part.inline_data.data
                    break
            
            if not edited_data:
                return None, "❌ 圖片編輯失敗：回應中沒有圖片數據。"
            
            # 保存歷史記錄
            await self._save_history(
                user_id=user_id,
                action="edit",
                prompt=edit_prompt,
                image_size=len(edited_data),
                result="圖片已編輯"
            )
            
            logger.info(f"✅ 編圖成功 (大小: {len(edited_data)} bytes)")
            return edited_data, f"✅ 圖片已編輯"
            
        except Exception as e:
            error_msg = f"❌ 編圖失敗: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    async def analyze_image(self, image_data: bytes, analysis_prompt: str, user_id: int) -> tuple[str, str]:
        """
        分析圖片內容
        
        Args:
            image_data: 圖片資料
            analysis_prompt: 分析問題
            user_id: 使用者ID
        
        Returns:
            (分析結果, 訊息)
        """
        try:
            logger.info(f"🔍 開始分析圖片: {analysis_prompt[:50]}...")
            
            # 轉換圖片為PIL Image
            image = Image.open(BytesIO(image_data))
            
            # 使用Gemini API分析圖片
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content([
                analysis_prompt or "請詳細分析這張圖片的內容。",
                image
            ])
            
            analysis_result = response.text
            
            # 保存歷史記錄
            await self._save_history(
                user_id=user_id,
                action="analyze",
                prompt=analysis_prompt,
                result=analysis_result[:200]
            )
            
            logger.info(f"✅ 圖片分析完成")
            return analysis_result, "✅ 圖片分析完成"
            
        except Exception as e:
            error_msg = f"❌ 圖片分析失敗: {str(e)}"
            logger.error(error_msg)
            return "", error_msg
    
    async def _save_history(self, user_id: int, action: str, prompt: str, 
                           image_size: int = 0, result: str = ""):
        """保存圖片操作歷史"""
        try:
            history_file = IMAGES_HISTORY_DIR / f"user_{user_id}.json"
            
            # 讀取現有歷史
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            else:
                history = []
            
            # 添加新記錄
            record = {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "prompt": prompt[:200],  # 只保存前200字
                "image_size": image_size,
                "result": result[:200] if result else ""
            }
            history.append(record)
            
            # 只保留最近100筆記錄
            if len(history) > 100:
                history = history[-100:]
            
            # 寫回檔案
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.warning(f"⚠️ 保存歷史失敗: {e}")


class ImageCog(commands.Cog):
    """圖片生成、編輯、分析功能"""
    
    def __init__(self, bot):
        self.bot = bot
        api_key = os.getenv("AI_API_KEY")
        try:
            self.image_handler = ImageHandler(api_key)
            logger.info("✅ 圖片模塊已初始化")
        except Exception as e:
            logger.error(f"❌ 圖片模塊初始化失敗: {e}")
            self.image_handler = None
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """處理圖片相關訊息"""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return
        
        if not self.image_handler:
            await message.reply("⚠️ 圖片功能未初始化。")
            return
        
        user_input = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()
        
        # 檢測圖片請求類型
        request_type = ImageHandler.detect_image_request(user_input)
        
        if not request_type:
            return  # 不是圖片相關請求
        
        user_id = message.author.id
        
        try:
            async with message.channel.typing():
                if request_type == "生圖":
                    await self._handle_generate(message, user_input, user_id)
                elif request_type == "編圖":
                    await self._handle_edit(message, user_input, user_id)
                elif request_type == "看圖":
                    await self._handle_analyze(message, user_input, user_id)
        
        except Exception as e:
            logger.error(f"圖片處理錯誤: {e}")
            await message.reply(f"⚠️ 處理圖片時發生錯誤: {str(e)[:100]}")
    
    async def _handle_generate(self, message: discord.Message, user_input: str, user_id: int):
        """處理生圖請求"""
        # 提取圖片描述（移除生濟詞）
        prompt = user_input
        for keyword in ImageHandler.IMAGE_KEYWORDS["生圖"]:
            prompt = prompt.replace(keyword, "").strip()
        
        if not prompt or len(prompt) < 3:
            await message.reply("📍 描述太短了。給我更詳細的圖片描述。")
            return
        
        # 調用生圖API
        image_data, status_msg = await self.image_handler.generate_image(prompt, user_id)
        
        if image_data:
            # 上傳圖片到Discord
            try:
                file = discord.File(BytesIO(image_data), filename="generated.png")
                await message.reply(
                    content=f"🖼️ 生圖完成！\n**提示詞:** {prompt[:60]}...",
                    file=file
                )
            except Exception as e:
                await message.reply(f"✅ 圖片已生成但上傳失敗: {str(e)[:80]}")
        else:
            await message.reply(status_msg)
    
    async def _handle_edit(self, message: discord.Message, user_input: str, user_id: int):
        """處理編圖請求"""
        # 檢查是否有附檔
        if not message.attachments:
            await message.reply("🖼️ 需要提供圖片檔案才能編輯。請上傳一張圖片。")
            return
        
        # 下載第一張圖片
        attachment = message.attachments[0]
        try:
            image_data = await attachment.read()
        except Exception as e:
            await message.reply(f"❌ 無法下載圖片: {str(e)[:80]}")
            return
        
        # 提取編輯指令（移除編圖詞）
        edit_prompt = user_input
        for keyword in ImageHandler.IMAGE_KEYWORDS["編圖"]:
            edit_prompt = edit_prompt.replace(keyword, "").strip()
        
        if not edit_prompt or len(edit_prompt) < 3:
            await message.reply("📍 編輯指令太短了。告訴我你想怎麼改這張圖片。")
            return
        
        # 呼叫編圖API
        edited_data, status_msg = await self.image_handler.edit_image(image_data, edit_prompt, user_id)
        
        if edited_data:
            try:
                file = discord.File(BytesIO(edited_data), filename="edited.png")
                await message.reply(
                    content=f"🎨 編圖完成！\n**指令:** {edit_prompt[:60]}...",
                    file=file
                )
            except Exception as e:
                await message.reply(f"✅ 圖片已編輯但上傳失敗: {str(e)[:80]}")
        else:
            await message.reply(status_msg)
    
    async def _handle_analyze(self, message: discord.Message, user_input: str, user_id: int):
        """處理看圖/分析請求"""
        # 檢查是否有附檔
        if not message.attachments:
            await message.reply("🖼️ 需要提供圖片檔案才能分析。請上傳一張圖片。")
            return
        
        # 下載第一張圖片
        attachment = message.attachments[0]
        try:
            image_data = await attachment.read()
        except Exception as e:
            await message.reply(f"❌ 無法下載圖片: {str(e)[:80]}")
            return
        
        # 提取分析問題（移除看圖詞）
        analysis_prompt = user_input
        for keyword in ImageHandler.IMAGE_KEYWORDS["看圖"]:
            analysis_prompt = analysis_prompt.replace(keyword, "").strip()
        
        if not analysis_prompt:
            analysis_prompt = "請詳細分析這張圖片的內容。"
        
        # 呼叫分析API
        result, status_msg = await self.image_handler.analyze_image(image_data, analysis_prompt, user_id)
        
        if result:
            # 長文字分多條訊息
            if len(result) > 1900:
                chunks = [result[i:i+1900] for i in range(0, len(result), 1900)]
                await message.reply(f"🔍 圖片分析結果：\n{chunks[0]}")
                for chunk in chunks[1:]:
                    await message.reply(chunk)
            else:
                await message.reply(f"🔍 圖片分析結果：\n{result}")
        else:
            await message.reply(status_msg)


async def setup(bot):
    await bot.add_cog(ImageCog(bot))
