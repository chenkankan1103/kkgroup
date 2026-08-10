import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import random
import asyncio
import json
import io
from PIL import Image
from typing import Optional
from pathlib import Path
import time
from datetime import datetime
from db_adapter import get_user, set_user, get_user_field, set_user_field
from cogs.ui.utils import paperdoll_manager

load_dotenv()

# ─── 入園後興趣標籤選擇 ──────────────────────────────────────


class InterestOnboardingView(discord.ui.View):
    """入園成功後顯示的興趣標籤選擇（不強制，可跳過）"""

    _INTEREST_OPTS = [
        discord.SelectOption(label="科技/AI", emoji="🤖"),
        discord.SelectOption(label="動漫/遊戲", emoji="🎮"),
        discord.SelectOption(label="體育", emoji="⚽"),
        discord.SelectOption(label="娛樂/明星", emoji="🌟"),
        discord.SelectOption(label="財經時事", emoji="📈"),
        discord.SelectOption(label="健康/美食", emoji="🍜"),
        discord.SelectOption(label="旅遊/生活", emoji="✈️"),
        discord.SelectOption(label="政治", emoji="🏛️"),
    ]

    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.select(
        placeholder="選擇你感興趣的話題（可複選，最多 5 個）",
        min_values=0,
        max_values=5,
        options=[
            discord.SelectOption(label="科技/AI", emoji="🤖"),
            discord.SelectOption(label="動漫/遊戲", emoji="🎮"),
            discord.SelectOption(label="體育", emoji="⚽"),
            discord.SelectOption(label="娛樂/明星", emoji="🌟"),
            discord.SelectOption(label="財經時事", emoji="📈"),
            discord.SelectOption(label="健康/美食", emoji="🍜"),
            discord.SelectOption(label="旅遊/生活", emoji="✈️"),
            discord.SelectOption(label="政治", emoji="🏛️"),
        ],
    )
    async def interest_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ 這不是你的選項！", ephemeral=True
            )
            return
        selected = select.values
        set_user_field(
            self.user_id, "user_interests", json.dumps(selected, ensure_ascii=False)
        )
        set_user_field(self.user_id, "trend_alert_enabled", 1)
        tags_text = " / ".join(selected) if selected else "（跳過）"
        await interaction.response.send_message(
            f"✅ 興趣標籤已設定：**{tags_text}**\n"
            "🏰 當你的標籤話題出現在熱搜時，堡壘保衛戰攻擊力將 **×2**！",
            ephemeral=True,
        )
        self.stop()

    @discord.ui.button(label="跳過", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ 這不是你的按鈕！", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "已跳過。你可以隨時使用 `/my_interests` 設定標籤。", ephemeral=True
        )
        self.stop()


# ─────────────────────────────────────────────────────────


class GenderSelectView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.select(
        placeholder="選擇你的性別...",
        options=[
            discord.SelectOption(label="男性", value="male", emoji="♂️"),
            discord.SelectOption(label="女性", value="female", emoji="♀️"),
        ],
    )
    async def gender_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的選項！")
            return

        # 使用隨機紙娃娃配置，保持性別不變
        selected_gender = select.values[0]
        appearance = paperdoll_manager.get_random(preserve_gender=selected_gender)

        try:
            await self.cog.update_user_data(self.user_id, appearance)
            await self.cog.update_welcome_message(interaction, self.user_id)
        except Exception as e:
            print(f"❌ 更新用戶性別失敗: {e}")

        gender_text = "男性" if selected_gender == "male" else "女性"
        await interaction.followup.send(f"✅ 已設定為{gender_text}！")


class WelcomeActionView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(
        label="繳交手機身分證", style=discord.ButtonStyle.secondary, emoji="📱"
    )
    async def submit_items(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！")
            return

        try:
            await self.cog.remove_items_from_inventory(self.user_id, ["手機", "身分證"])
            await self.cog.update_welcome_message(interaction, self.user_id)
        except Exception as e:
            print(f"❌ 繳交物品失敗: {e}")

        await interaction.followup.send("✅ 已繳交手機和身分證！")

    @discord.ui.button(label="隨機造型", style=discord.ButtonStyle.primary, emoji="🎲")
    async def random_appearance(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！")
            return

        # 獲取當前用戶資料以保持性別
        user_data = self.cog.get_user_data(self.user_id)
        current_gender = user_data.get("gender") if user_data else None

        # 生成新的隨機造型（保持性別）
        new_appearance = paperdoll_manager.get_random(preserve_gender=current_gender)

        # 更新用戶資料
        try:
            await self.cog.update_user_data(self.user_id, new_appearance)
            await self.cog.update_welcome_message(interaction, self.user_id)
        except Exception as e:
            print(f"❌ 更新隨機造型失敗: {e}")

        gender_text = "男性" if new_appearance["gender"] == "male" else "女性"
        await interaction.followup.send(
            f"🎲 已重新生成{gender_text}造型！\n"
            f"臉型: {new_appearance['face']} | 髮型: {new_appearance['hair']} | 上衣: {new_appearance['top']}"
        )

    @discord.ui.button(
        label="確認進入園區", style=discord.ButtonStyle.danger, emoji="🚪"
    )
    async def confirm_entry(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

        if interaction.user.id != self.user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        await self.cog.handle_final_verification(interaction, interaction.user)


class PersistentWelcomeView(discord.ui.View):
    """Persistent view for welcome interactions (cross-restart)."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    def _extract_target_user_id(self, message: discord.Message) -> Optional[int]:
        """從 embed 中解析被歡迎的 user id（fallback: None）"""
        try:
            import re

            if not message or not getattr(message, "embeds", None):
                return None
            for embed in message.embeds:
                desc = getattr(embed, "description", "") or ""
                m = re.search(r"<@!?(?P<id>\d+)>", desc)
                if m:
                    return int(m.group("id"))
                # 檢查欄位
                for field in getattr(embed, "fields", []):
                    m = re.search(r"<@!?(?P<id>\d+)>", field.value or "")
                    if m:
                        return int(m.group("id"))
        except Exception:
            return None
        return None

    @discord.ui.select(
        custom_id="welcome_gender_select",
        placeholder="選擇你的性別...",
        options=[
            discord.SelectOption(label="男性", value="male", emoji="♂️"),
            discord.SelectOption(label="女性", value="female", emoji="♀️"),
        ],
    )
    async def gender_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        await interaction.response.defer(ephemeral=True)
        target_user_id = (
            self._extract_target_user_id(interaction.message) or interaction.user.id
        )

        if interaction.user.id != target_user_id:
            await interaction.followup.send("❌ 這不是你的選項！", ephemeral=True)
            return

        # 使用隨機紙娃娃配置，保持性別不變
        selected_gender = select.values[0]
        appearance = paperdoll_manager.get_random(preserve_gender=selected_gender)

        await self.cog.update_user_data(target_user_id, appearance)
        await self.cog.update_welcome_message(interaction, target_user_id)

        gender_text = "男性" if selected_gender == "male" else "女性"
        await interaction.followup.send(f"✅ 已設定為{gender_text}！", ephemeral=True)

    @discord.ui.button(
        custom_id="welcome_submit_items",
        label="繳交手機身分證",
        style=discord.ButtonStyle.secondary,
        emoji="📱",
    )
    async def submit_items(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        target_user_id = (
            self._extract_target_user_id(interaction.message) or interaction.user.id
        )

        if interaction.user.id != target_user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        await self.cog.remove_items_from_inventory(target_user_id, ["手機", "身分證"])
        await self.cog.update_welcome_message(interaction, target_user_id)
        await interaction.followup.send("✅ 已繳交手機和身分證！", ephemeral=True)

    @discord.ui.button(
        custom_id="welcome_random_appearance",
        label="隨機造型",
        style=discord.ButtonStyle.primary,
        emoji="🎲",
    )
    async def random_appearance(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        target_user_id = (
            self._extract_target_user_id(interaction.message) or interaction.user.id
        )

        if interaction.user.id != target_user_id:
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        # 獲取當前用戶資料以保持性別
        user_data = self.cog.get_user_data(target_user_id)
        current_gender = user_data.get("gender") if user_data else None

        # 生成新的隨機造型（保持性別）
        new_appearance = paperdoll_manager.get_random(preserve_gender=current_gender)

        # 更新用戶資料
        await self.cog.update_user_data(target_user_id, new_appearance)
        await self.cog.update_welcome_message(interaction, target_user_id)

        gender_text = "男性" if new_appearance["gender"] == "male" else "女性"
        await interaction.followup.send(
            f"🎲 已重新生成{gender_text}造型！\n"
            f"臉型: {new_appearance['face']} | 髮型: {new_appearance['hair']} | 上衣: {new_appearance['top']}",
            ephemeral=True,
        )

    @discord.ui.button(
        custom_id="welcome_confirm_entry",
        label="確認進入園區",
        style=discord.ButtonStyle.danger,
        emoji="🚪",
    )
    async def confirm_entry(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        target_user_id = (
            self._extract_target_user_id(interaction.message) or interaction.user.id
        )

        print(
            f"🔘 【入園按鈕】按下者: {interaction.user.id} ({interaction.user.name}), 目標用戶: {target_user_id}"
        )

        if interaction.user.id != target_user_id:
            print(
                f"❌ 【入園按鈕】權限檢查失敗：{interaction.user.id} != {target_user_id}"
            )
            await interaction.followup.send("❌ 這不是你的按鈕！", ephemeral=True)
            return

        if not interaction.guild:
            print("❌ 【入園按鈕】交互不在伺服器中")
            await interaction.followup.send("❌ 無法在此上下文中處理", ephemeral=True)
            return

        member = interaction.guild.get_member(target_user_id)
        if not member:
            print(f"❌ 【入園按鈕】找不到成員: {target_user_id}")
            await interaction.followup.send("❌ 無法找到用戶，請重試", ephemeral=True)
            return

        print(f"✅ 【入園按鈕】權限檢查通過，開始處理 {member.name} 的入園流程...")
        await self.cog.handle_final_verification(interaction, member)


class TestWelcomeView(discord.ui.View):
    """安全測試用歡迎視圖，只在記憶體中模擬，不寫入資料庫。"""

    def __init__(self, cog, preview_user: discord.abc.User, preview_user_data: dict):
        super().__init__(timeout=900)
        self.cog = cog
        self.preview_user = preview_user
        self.preview_user_data = dict(preview_user_data)

    def _get_inventory_items(self) -> list[str]:
        inventory_raw = self.preview_user_data.get("inventory", "[]")
        if isinstance(inventory_raw, list):
            return list(inventory_raw)
        if isinstance(inventory_raw, str):
            try:
                return json.loads(inventory_raw) if inventory_raw else []
            except json.JSONDecodeError:
                return []
        return []

    def _set_inventory_items(self, items: list[str]) -> None:
        self.preview_user_data["inventory"] = json.dumps(items, ensure_ascii=False)

    async def _refresh_preview(
        self, interaction: discord.Interaction, notice: str, *, clear_view: bool = False
    ):
        embed = await self.cog.create_welcome_embed(
            self.preview_user_data, self.preview_user
        )
        await interaction.response.edit_message(
            embed=embed, view=None if clear_view else self
        )
        await interaction.followup.send(notice, ephemeral=True)

    @discord.ui.select(
        placeholder="選擇你的性別...",
        options=[
            discord.SelectOption(label="男性", value="male", emoji="♂️"),
            discord.SelectOption(label="女性", value="female", emoji="♀️"),
        ],
    )
    async def gender_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        selected_gender = select.values[0]
        appearance = paperdoll_manager.get_random(preserve_gender=selected_gender)

        for field in ("face", "hair", "skin", "top", "bottom", "shoes", "gender"):
            self.preview_user_data[field] = appearance[field]

        gender_text = "男性" if selected_gender == "male" else "女性"
        appearance_text = (
            f"已套用 {gender_text} 測試造型（僅預覽，未保存）。\n"
            f"臉：{appearance['face']}｜髮：{appearance['hair']}｜上衣：{appearance['top']}"
        )
        await self._refresh_preview(interaction, appearance_text)

    @discord.ui.button(
        label="繳交手機身分證", style=discord.ButtonStyle.secondary, emoji="📱"
    )
    async def submit_items(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        inventory = self._get_inventory_items()
        inventory = [item for item in inventory if item not in {"手機", "身分證"}]
        self._set_inventory_items(inventory)
        await self._refresh_preview(
            interaction, "（模擬）已繳交手機與身分證，僅更新這次預覽。"
        )

    @discord.ui.button(label="隨機造型", style=discord.ButtonStyle.primary, emoji="🎲")
    async def random_appearance(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        current_gender = self.preview_user_data.get("gender")
        appearance = paperdoll_manager.get_random(preserve_gender=current_gender)

        for field in ("face", "hair", "skin", "top", "bottom", "shoes", "gender"):
            self.preview_user_data[field] = appearance[field]

        gender_text = "男性" if appearance["gender"] == "male" else "女性"
        await self._refresh_preview(
            interaction, f"（模擬）已重新生成 {gender_text} 造型，結果未寫入資料庫。"
        )

    @discord.ui.button(
        label="確認進入園區", style=discord.ButtonStyle.danger, emoji="🚪"
    )
    async def confirm_entry(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        inventory = self._get_inventory_items()
        inventory = [item for item in inventory if item not in {"手機", "身分證"}]
        self._set_inventory_items(inventory)
        self.preview_user_data["is_stunned"] = 1
        self.preview_user_data["hp"] = 10
        self.preview_user_data["stamina"] = 10
        await self._refresh_preview(
            interaction,
            "（模擬）已走完入園流程預覽；身分組、暱稱與資料庫都沒有修改。",
            clear_view=True,
        )


class WelcomeFlow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.welcome_channel_id = int(os.getenv("WELCOME_CHANNEL_ID", 0))
        self.image_storage_channel_id = int(os.getenv("IMAGE_STORAGE_CHANNEL_ID", 0))
        self.temp_role1_id = int(os.getenv("TEMP_ROLE1_ID", 0))
        self.member_role_id = int(os.getenv("MEMBER_ROLE_ID", 0))
        self.db_path = "./user_data.db"
        self.welcome_messages = {}
        self.stunned_users = {}

        # 預設角色圖片配置 (4種固定組合)
        self.preset_characters = {
            "male_normal": {
                "skin": 12000,
                "face": 20005,
                "hair": 30120,
                "top": 1040014,
                "bottom": 1060096,
                "shoes": 1072005,
                "pose": "stand1",
                "stunned": 0,
            },
            "male_stunned": {
                "skin": 12000,
                "face": 20005,
                "hair": 30120,
                "top": 1040014,
                "bottom": 1060096,
                "shoes": 1072005,
                "pose": "prone",
                "stunned": 1,
            },
            "female_normal": {
                "skin": 12000,
                "face": 21731,
                "hair": 34410,
                "top": 1041004,
                "bottom": 1061008,
                "shoes": 1072005,
                "pose": "stand1",
                "stunned": 0,
            },
            "female_stunned": {
                "skin": 12000,
                "face": 21731,
                "hair": 34410,
                "top": 1041004,
                "bottom": 1061008,
                "shoes": 1072005,
                "pose": "prone",
                "stunned": 1,
            },
        }

        # 圖片緩存
        self.cache_dir = Path("./character_images")
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = Path("./character_images/discord_url_cache.json")

        self.init_database()
        # 啟動時加載持久化緩存
        self.load_persistent_cache()
        # 啟動時預載入圖片 - 延遲啟動避免阻塞
        self.bot.loop.create_task(self.delayed_preload())

        # 註冊跨重啟的 persistent view（處理 welcome 的按鈕/選單）
        try:
            self.persistent_view = PersistentWelcomeView(self)
            self.bot.add_view(self.persistent_view)
            print("✅ 已註冊 PersistentWelcomeView (跨重啟互動)")
        except Exception as e:
            print(f"⚠️ 註冊 PersistentWelcomeView 失敗: {e}")

    def load_persistent_cache(self):
        """從文件加載持久化的 Discord URL 緩存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    # 轉換回內存格式
                    for cache_key, url_data in cache_data.items():
                        if isinstance(url_data, dict) and "discord_url" in url_data:
                            self.image_cache[cache_key] = url_data
                print(f"✅ 已加載 {len(self.image_cache)} 個圖片緩存 (從文件)")
        except Exception as e:
            print(f"⚠️ 加載持久化緩存失敗: {e}")

    def save_persistent_cache(self):
        """保存 Discord URL 緩存到文件"""
        try:
            self.cache_dir.mkdir(exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.image_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存持久化緩存失敗: {e}")

    async def delayed_preload(self):
        """延遲預載入以避免阻塞機器人啟動"""
        try:
            print("⏳ 等待機器人完全啟動...")
            await asyncio.sleep(5)  # 等待機器人完全啟動
            print("🚀 機器人已啟動，開始預載入角色圖片...")
            await self.preload_preset_images()
            print(f"✅ 角色圖片預載入完成！(共 {len(self.image_cache)} 個預設圖片)")
        except Exception as e:
            print(f"⚠️ 預載入圖片時發生錯誤（不影響主功能）: {e}")
            import traceback

            traceback.print_exc()

    def init_database(self):
        """
        Initialize database using new sheet-driven architecture.
        Schema is automatically managed by db_adapter via SHEET Row 1.
        """
        try:
            # Initialize in-memory image cache (replaces SQLite table)
            # Format: {cache_key: {'discord_url': str, 'created_at': int, 'message_id': int}}
            if not hasattr(self, "image_cache"):
                self.image_cache = {}
            print("✅ 資料庫初始化完成 (使用 Sheet-Driven 架構)")

        except Exception as e:
            print(f"❌ 資料庫初始化錯誤: {e}")
            import traceback

            traceback.print_exc()

    async def preload_preset_images(self):
        """預載入 4 張預設角色圖片（如果緩存不存在）"""
        print("🖼️ 開始檢查並預載入角色圖片...")
        print(f"   預設角色配置: {list(self.preset_characters.keys())}")
        print(f"   當前記憶體緩存: {len(self.image_cache)} 個圖片")

        success_count = 0
        fail_count = 0

        for preset_name, config in self.preset_characters.items():
            try:
                # 檢查是否已有緩存（優先從文件快取）
                cached_url = self.get_cached_discord_url(preset_name)
                if cached_url:
                    print(f"   ✅ {preset_name} 使用已存在的緩存 (跳過上傳)")
                    success_count += 1
                    continue

                # 檢查本地緩存
                cache_path = self.cache_dir / f"{preset_name}.png"
                if cache_path.exists():
                    try:
                        with open(cache_path, "rb") as f:
                            image_data = f.read()

                        print(
                            f"   📁 {preset_name} 找到本地緩存: {len(image_data)} bytes"
                        )
                        discord_url = await self.upload_image_to_discord_storage(
                            image_data, preset_name
                        )
                        if discord_url:
                            print(f"   ✅ {preset_name} 從本地緩存上傳到 Discord")
                            success_count += 1
                            continue
                        else:
                            print(f"   ⚠️ {preset_name} 本地緩存上傳失敗，嘗試重新生成")
                    except Exception as e:
                        print(f"   ⚠️ 讀取本地緩存 {preset_name} 失敗: {e}")

                # 從 API 獲取圖片
                print(f"   🌐 {preset_name} 正在從 API 生成...")
                discord_url = await self.generate_and_cache_preset_image(
                    preset_name, config
                )
                if discord_url:
                    print(f"   ✅ {preset_name} 從 API 獲取並緩存成功")
                    success_count += 1
                else:
                    print(f"   ❌ {preset_name} 預載入失敗（API 無法生成）")
                    fail_count += 1

                # 避免請求過於頻繁
                await asyncio.sleep(1)

            except Exception as e:
                print(f"   ❌ {preset_name} 預載入異常: {type(e).__name__}: {e}")
                fail_count += 1

        print(
            f"📊 預載入完成: ✅ {success_count} 成功 | ❌ {fail_count} 失敗 | 📦 {len(self.image_cache)} 總計"
        )
        if fail_count > 0:
            print(
                "⚠️ 提示: 如果圖片無法顯示，請檢查 MapleStory API (maplestory.io) 是否可訪問"
            )

    async def generate_and_cache_preset_image(
        self, preset_name: str, config: dict
    ) -> Optional[str]:
        """生成並返回預設角色圖片 API URL（不保存本地文件）"""
        try:
            items = [
                {"itemId": 2000, "region": "TWMS", "version": "256"},
                {"itemId": config["skin"], "region": "TWMS", "version": "256"},
            ]

            if config["stunned"] == 1:
                items.append(
                    {
                        "itemId": config["face"],
                        "animationName": "stunned",
                        "region": "TWMS",
                        "version": "256",
                    }
                )
            else:
                items.append(
                    {
                        "itemId": config["face"],
                        "animationName": "default",
                        "region": "TWMS",
                        "version": "256",
                    }
                )

            items.extend(
                [
                    {"itemId": config["hair"], "region": "TWMS", "version": "256"},
                    {"itemId": config["top"], "region": "TWMS", "version": "256"},
                    {"itemId": config["bottom"], "region": "TWMS", "version": "256"},
                    {"itemId": config["shoes"], "region": "TWMS", "version": "256"},
                ]
            )

            item_path = ",".join(
                [json.dumps(item, separators=(",", ":")) for item in items]
            )
            api_url = f"https://maplestory.io/api/character/{item_path}/{config['pose']}/animated?showears=false&showLefEars=false&showHighLefEars=false&resize=3&flipX=true"

            print(f"🎨 【{preset_name}】API URL: {api_url[:80]}...")
            print("   ✅ 已生成 API URL")
            return api_url

        except Exception as e:
            print(f"❌ 【{preset_name}】生成失敗: {type(e).__name__}: {e}")

        return None

    def get_user_data(self, user_id: int) -> Optional[dict]:
        """Get user data from sheet-driven database"""
        try:
            user_data = get_user(user_id)
            if not user_data:
                return None
            return self._resolve_user_data(user_id, user_data, persist_repairs=True)
        except Exception as e:
            print(f"❌ 獲取用戶資料錯誤: {e}")
            return None

    def _resolve_user_data(
        self, user_id: int, user_data: dict, persist_repairs: bool
    ) -> dict:
        resolved_user_data = dict(user_data)
        appearance_fields = ("face", "hair", "skin", "top", "bottom", "shoes")
        missing_fields = []

        for field in appearance_fields:
            value = resolved_user_data.get(field)
            if value in (None, "", 0, "0"):
                missing_fields.append(field)

        gender = resolved_user_data.get("gender")
        inferred_gender = None
        if gender not in ("male", "female"):
            missing_fields.append("gender")
            inferred_gender = paperdoll_manager.infer_gender_from_appearance(
                resolved_user_data
            )
            gender = inferred_gender

        if missing_fields:
            random_appearance = paperdoll_manager.get_random(preserve_gender=gender)
            repaired_fields = {}

            for field in appearance_fields:
                if field in missing_fields:
                    repaired_fields[field] = int(random_appearance[field])

            if "gender" in missing_fields:
                repaired_fields["gender"] = (
                    inferred_gender or random_appearance["gender"]
                )

            for field, value in repaired_fields.items():
                resolved_user_data[field] = value
                if persist_repairs:
                    set_user_field(user_id, field, value)

            if persist_repairs:
                print(f"⚠️ 用戶 {user_id} 紙娃娃欄位缺失 {missing_fields}，已補齊資料")
            else:
                print(
                    f"ℹ️ 用戶 {user_id} 紙娃娃欄位缺失 {missing_fields}，僅用於預覽補齊"
                )

        return resolved_user_data

    def get_preview_user_data(self, user_id: int) -> dict:
        user_data = get_user(user_id)
        if user_data:
            resolved_user_data = self._resolve_user_data(
                user_id, user_data, persist_repairs=False
            )
        else:
            random_appearance = paperdoll_manager.get_random()
            resolved_user_data = {
                "user_id": user_id,
                "inventory": json.dumps(["手機", "身分證"], ensure_ascii=False),
                "character_config": "{}",
                "face": int(random_appearance["face"]),
                "hair": int(random_appearance["hair"]),
                "skin": int(random_appearance["skin"]),
                "top": int(random_appearance["top"]),
                "bottom": int(random_appearance["bottom"]),
                "shoes": int(random_appearance["shoes"]),
                "gender": random_appearance["gender"],
                "level": 1,
                "xp": 0,
                "kkcoin": 0,
                "title": "新手",
                "hp": 100,
                "stamina": 100,
                "is_stunned": 0,
            }

        default_values = {
            "user_id": user_id,
            "inventory": json.dumps(["手機", "身分證"], ensure_ascii=False),
            "character_config": "{}",
            "level": 1,
            "xp": 0,
            "kkcoin": 0,
            "title": "新手",
            "hp": 100,
            "stamina": 100,
            "is_stunned": 0,
        }

        for field, default_value in default_values.items():
            if resolved_user_data.get(field) is None:
                resolved_user_data[field] = default_value

        if not resolved_user_data.get("inventory"):
            resolved_user_data["inventory"] = default_values["inventory"]

        return resolved_user_data

    def create_user_data(self, user_id: int) -> bool:
        """Create new user data with random appearance and default values. Returns True if successful. Includes retry logic."""
        max_retries = 3
        default_inventory = json.dumps(["手機", "身分證"])

        # 🎭 為新用戶生成隨機造型（男/女各占 50%）
        random_appearance = paperdoll_manager.get_random()

        user_data = {
            "user_id": user_id,
            "inventory": default_inventory,
            "character_config": "{}",
            "face": int(random_appearance["face"]),
            "hair": int(random_appearance["hair"]),
            "skin": int(random_appearance["skin"]),
            "top": int(random_appearance["top"]),
            "bottom": int(random_appearance["bottom"]),
            "shoes": int(random_appearance["shoes"]),
            "gender": random_appearance["gender"],
            "level": 1,
            "xp": 0,
            "kkcoin": 0,
            "title": "新手",
            "hp": 100,
            "stamina": 100,
            "is_stunned": 0,
            "thread_id": 0,
            "last_kkcoin_snapshot": 0,
            "last_xp_snapshot": 0,
            "last_level_snapshot": 1,
        }

        for attempt in range(1, max_retries + 1):
            try:
                # 先檢查用戶是否已存在
                existing = get_user(user_id)
                if existing:
                    print(f"⚠️ 用戶資料已存在: {user_id}（略過創建）")
                    return True

                result = set_user(user_id, user_data)
                if result:
                    print(f"✅ 創建用戶資料: {user_id} (嘗試 {attempt}/{max_retries})")
                    return True
                else:
                    print(
                        f"⚠️ set_user 返回 False: {user_id} (嘗試 {attempt}/{max_retries})"
                    )
                    if attempt < max_retries:
                        import time

                        time.sleep(0.5)
                        continue
                    return False

            except Exception as e:
                print(
                    f"❌ 創建用戶資料錯誤 (嘗試 {attempt}/{max_retries}): {type(e).__name__}: {e}"
                )
                if attempt < max_retries:
                    import time

                    time.sleep(0.5)
                    continue
                else:
                    import traceback

                    traceback.print_exc()
                    return False

        return False

    async def update_user_data(self, user_id: int, data: dict):
        """Update user data fields in sheet-driven database"""
        try:
            allowed_fields = {
                "face",
                "hair",
                "skin",
                "top",
                "bottom",
                "shoes",
                "gender",
                "hp",
                "stamina",
                "is_stunned",
                "thread_id",
                "inventory",
                "character_config",
                "injury_recovery_time",
                "last_recovery",
            }

            for key, value in data.items():
                if key in allowed_fields:
                    set_user_field(user_id, key, value)

            # ✅ 新增備份邏輯：如果 hp 和 stamina 都是 100，自動清除 is_stunned
            # 這是 recovery_cog 的備份邏輯，確保昏倒狀態被正確清除
            hp = data.get("hp") or get_user_field(user_id, "hp", default=0)
            stamina = data.get("stamina") or get_user_field(
                user_id, "stamina", default=0
            )
            is_stunned = get_user_field(user_id, "is_stunned", default=0)

            if hp == 100 and stamina == 100 and is_stunned == 1:
                set_user_field(user_id, "is_stunned", 0)
                print(f"✅ 用戶 {user_id} 已完全恢復，清除昏倒狀態")

        except Exception as e:
            print(f"❌ 更新用戶資料錯誤: {e}")

    async def remove_items_from_inventory(self, user_id: int, items_to_remove: list):
        """Remove items from user inventory"""
        try:
            user_data = self.get_user_data(user_id)
            if not user_data:
                return

            # db_adapter 可能已自動反序列化，需要檢查類型
            inventory_raw = user_data.get("inventory", "[]")
            if isinstance(inventory_raw, str):
                inventory = json.loads(inventory_raw) if inventory_raw else []
            else:
                inventory = inventory_raw if isinstance(inventory_raw, list) else []

            for item in items_to_remove:
                if item in inventory:
                    inventory.remove(item)

            set_user_field(user_id, "inventory", json.dumps(inventory))
            print(f"✅ 已移除物品: {items_to_remove}，剩餘: {inventory}")

        except Exception as e:
            print(f"❌ 移除物品錯誤: {e}")

    def create_progress_bar(self, current: int, maximum: int, length: int = 10) -> str:
        percentage = max(0, min(1, current / maximum)) if maximum > 0 else 0
        filled = int(length * percentage)
        return "█" * filled + "░" * (length - filled)

    def get_preset_key_for_user(self, user_data: dict) -> str:
        """根據用戶數據獲取對應的預設角色鍵值"""
        gender = user_data.get("gender", "male")
        is_stunned = user_data.get("is_stunned", 0)

        if is_stunned == 1:
            return f"{gender}_stunned"
        else:
            return f"{gender}_normal"

    async def save_image_to_cache(self, image_data: bytes, cache_key: str) -> bool:
        """將圖片數據保存到本地緩存"""
        try:
            cache_path = self.cache_dir / f"{cache_key}.png"

            if len(image_data) < 100:
                return False

            with io.BytesIO(image_data) as image_buffer:
                try:
                    img = Image.open(image_buffer)
                    img.verify()

                    image_buffer.seek(0)
                    img = Image.open(image_buffer)
                    img.save(cache_path, "PNG", optimize=True)
                    return True

                except Exception:
                    return False

        except Exception as e:
            print(f"❌ 保存本地緩存錯誤: {e}")
            return False

    def get_cached_discord_url(self, cache_key: str) -> Optional[str]:
        """從記憶體獲取 Discord URL 緩存"""
        try:
            # 清理過期的緩存 (超過30天)
            thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
            expired_keys = [
                key
                for key, data in self.image_cache.items()
                if data.get("created_at", 0) < thirty_days_ago
            ]
            for key in expired_keys:
                del self.image_cache[key]

            # 獲取緩存
            if cache_key in self.image_cache:
                return self.image_cache[cache_key].get("discord_url")
            return None

        except Exception as e:
            print(f"❌ 獲取 Discord URL 緩存錯誤: {e}")
            return None

    def save_discord_url_cache(
        self, cache_key: str, discord_url: str, message_id: int = None
    ):
        """保存 Discord URL 到記憶體緩存並持久化到文件"""
        try:
            current_time = int(time.time())
            self.image_cache[cache_key] = {
                "discord_url": discord_url,
                "created_at": current_time,
                "message_id": message_id,
            }
            # 同時保存到文件實現持久化
            self.save_persistent_cache()

        except Exception as e:
            print(f"❌ 保存 Discord URL 緩存錯誤: {e}")

    async def upload_image_to_discord_storage(
        self, image_data: bytes, cache_key: str
    ) -> Optional[str]:
        """改為直接返回 MapleStory API URL（不保存本地文件）"""
        try:
            # 構建 API URL
            preset_config = self.preset_characters.get(cache_key)
            if not preset_config:
                print(f"   ⚠️ 未找到預設配置: {cache_key}")
                return None

            # 直接返回 API URL
            items = [
                {"itemId": 2000, "region": "TWMS", "version": "256"},
                {"itemId": preset_config["skin"], "region": "TWMS", "version": "256"},
            ]

            if preset_config["stunned"] == 1:
                items.append(
                    {
                        "itemId": preset_config["face"],
                        "animationName": "stunned",
                        "region": "TWMS",
                        "version": "256",
                    }
                )
            else:
                items.append(
                    {
                        "itemId": preset_config["face"],
                        "animationName": "default",
                        "region": "TWMS",
                        "version": "256",
                    }
                )

            items.extend(
                [
                    {
                        "itemId": preset_config["hair"],
                        "region": "TWMS",
                        "version": "256",
                    },
                    {
                        "itemId": preset_config["top"],
                        "region": "TWMS",
                        "version": "256",
                    },
                    {
                        "itemId": preset_config["bottom"],
                        "region": "TWMS",
                        "version": "256",
                    },
                    {
                        "itemId": preset_config["shoes"],
                        "region": "TWMS",
                        "version": "256",
                    },
                ]
            )

            item_path = ",".join(
                [json.dumps(item, separators=(",", ":")) for item in items]
            )
            api_url = f"https://maplestory.io/api/character/{item_path}/{preset_config['pose']}/animated?showears=false&showLefEars=false&showHighLefEars=false&resize=3&flipX=true"
            return api_url

        except Exception as e:
            print(f"   ❌ 構建 API URL 錯誤: {type(e).__name__}: {e}")

        return None

    async def get_character_image_url(self, user_data: dict) -> Optional[str]:
        """
        使用用戶的實際紙娃娃配置生成圖片 API URL。
        委派給 paperdoll_manager.build_api_url() 統一處理。
        """
        url = paperdoll_manager.build_api_url(user_data)
        if url:
            print(
                f"🎭 【get_character_image_url】face={user_data.get('face')}, hair={user_data.get('hair')}, top={user_data.get('top')}"
            )
        else:
            print("❌ 【get_character_image_url】build_api_url 回傳 None")
        return url

    async def create_welcome_embed(
        self, user_data: dict, user: discord.User
    ) -> discord.Embed:
        try:
            if user_data.get("is_stunned", 0) == 1:
                embed = discord.Embed(
                    title="💫 一陣天旋地轉...",
                    description=(
                        f"💫 **{user.mention}** 一陣天旋地轉，你已倒在地上。\n\n"
                        "😵 你被擊暈了！\n"
                        "🏥 血量和體力大幅下降\n"
                        "💤 正在恢復中...\n\n"
                        "⏰ 請等待恢復，或聯繫管理員協助"
                    ),
                    color=0xFF6B6B,
                )
            else:
                embed = discord.Embed(
                    title="🎉 歡迎光臨 KK 園區™",
                    description=(
                        f"🎉 歡迎 **{user.mention}** 蒞臨 KK 園區™ — 一個讓人留連忘返的樂園。\n\n"
                        "🏠 食宿無憂，大通鋪讓你夜夜安穩；\n"
                        "🤝 不怕孤單，因為你永遠有人作伴；\n"
                        "🎭 娛樂充足，幹部們會「適時」安排你的休閒時光。\n\n"
                        "📜 **入園流程如下：**\n"
                        "1️⃣ 選擇你的性別\n"
                        "2️⃣ 繳交不必要的物品\n"
                        "3️⃣ 點擊確認，即刻入住\n\n"
                        "📌 每日表現將自動記錄為積分，影響分配與待遇。\n"
                        "🎁 定期將物品上繳以獲得特別回饋。\n"
                        "🚪 出口目前維護中，開放時間未定。\n"
                        "📷 園區全程監控中，請放心生活。"
                    ),
                    color=0x8B0000,
                )

            # 添加用戶資訊欄位
            embed.add_field(name="⭐ 等級", value=f"{user_data['level']}", inline=True)
            embed.add_field(
                name="💰 金錢", value=f"{user_data['kkcoin']} KKCoin", inline=True
            )
            embed.add_field(name="🏆 職位", value=user_data["title"], inline=True)

            hp_bar = self.create_progress_bar(user_data["hp"], 100)
            stamina_bar = self.create_progress_bar(user_data["stamina"], 100)
            embed.add_field(
                name="❤️ 血量", value=f"{hp_bar} {user_data['hp']}/100", inline=False
            )
            embed.add_field(
                name="⚡ 體力",
                value=f"{stamina_bar} {user_data['stamina']}/100",
                inline=False,
            )

            gender_display = "男性 ♂️" if user_data.get("gender") == "male" else "女性 ♀️"
            embed.add_field(name="👤 性別", value=gender_display, inline=True)
            embed.add_field(
                name="👔 上衣", value=f"ID: {user_data['top']}", inline=True
            )
            embed.add_field(
                name="👖 下裝", value=f"ID: {user_data['bottom']}", inline=True
            )

            # 處理物品欄顯示
            inventory = "空的"
            if user_data["inventory"]:
                try:
                    inv_raw = user_data["inventory"]
                    if isinstance(inv_raw, list):
                        items = inv_raw
                    elif isinstance(inv_raw, str):
                        items = json.loads(inv_raw) if inv_raw else []
                    else:
                        items = []
                    if items:
                        inventory = ", ".join(str(item) for item in items[:3])
                        if len(items) > 3:
                            inventory += f"... 等{len(items)}項"
                except:
                    pass
            embed.add_field(name="🎒 物品欄", value=inventory, inline=False)

            embed.set_thumbnail(url=user.display_avatar.url)

            # 獲取並設置角色圖片 API URL
            try:
                print(
                    f"📸 【create_welcome_embed】開始獲取角色圖片 (User: {user.name}, ID: {user.id})"
                )
                character_image_url = await self.get_character_image_url(user_data)
                if character_image_url:
                    embed.set_image(url=character_image_url)
                    print("✅ 【create_welcome_embed】紙娃娃已設置")
                else:
                    print("⚠️ 【create_welcome_embed】無法獲取紙娃娃圖片。")
            except Exception as e:
                print(
                    f"❌ 【create_welcome_embed】獲取紙娃娃失敗: {type(e).__name__}: {e}"
                )

            if user_data.get("is_stunned", 0) == 1:
                embed.set_footer(text="💫 你目前處於擊暈狀態，請等待恢復...")
            else:
                embed.set_footer(text="⚠️ 園區已自動為你關閉離開選項，安心享受吧。")

            return embed

        except Exception as e:
            print(f"⚠️ create_welcome_embed 發生錯誤: {e}")
            import traceback

            traceback.print_exc()

            fallback = discord.Embed(
                title="🎉 歡迎光臨 KK 園區™",
                description=(
                    f"🎉 歡迎 **{user.mention}**！\n\n"
                    "發生了一點小問題，但你仍可以按下確認進入園區。"
                ),
                color=0x8B0000,
            )
            fallback.add_field(
                name="📌 提示", value="若按鈕無法顯示，可稍後再嘗試。", inline=False
            )
            return fallback

    async def update_welcome_message(
        self, interaction: discord.Interaction, user_id: int
    ):
        """更新歡迎頻道中用戶的歡迎 embed。"""
        try:
            if not interaction.guild:
                print("⚠️ 交互不在伺服器中，無法更新訊息")
                return

            user_data = self.get_user_data(user_id)
            if not user_data:
                print(f"⚠️ 無法獲取用戶資料: {user_id}")
                return

            user = interaction.guild.get_member(user_id)
            if not user:
                print(f"⚠️ 無法獲取成員資料: {user_id}")
                return

            embed = await self.create_welcome_embed(user_data, user)

            # 獲取角色圖片路徑（本地緩存）
            # 注: 本地路徑不能直接用作 Embed URL，已改為本地文件存儲
            character_image_path = await self.get_character_image_url(user_data)
            if character_image_path:
                print(f"📁 本地圖片快取: {character_image_path}")

            # 更新歡迎頻道的原始訊息（如果有紀錄）
            try:
                msg_id = self.welcome_messages.get(interaction.guild.id, {}).get(
                    user_id
                )
                if msg_id:
                    channel = self.bot.get_channel(self.welcome_channel_id)
                    if channel:
                        msg = await channel.fetch_message(msg_id)
                        if user_data.get("is_stunned", 0) == 1:
                            await msg.edit(embed=embed, view=None)
                            print(f"✅ 已更新歡迎訊息為擊暈狀態: {user_id}")
                        else:
                            await msg.edit(embed=embed, view=self.persistent_view)
                            print(f"✅ 已更新歡迎訊息: {user_id}")
                    else:
                        print(f"⚠️ 找不到歡迎頻道: {self.welcome_channel_id}")
                else:
                    print(f"⚠️ 未找到歡迎訊息 ID for {user_id}")
            except discord.NotFound:
                print(f"⚠️ 歡迎訊息已被刪除: {user_id}")
            except Exception as e:
                print(f"⚠️ 編輯歡迎訊息失敗: {e}")

        except Exception as e:
            print(f"❌ 更新歡迎訊息錯誤: {e}")
            import traceback

            traceback.print_exc()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            print(f"🎯 檢測到新成員加入: {member.name} (ID: {member.id})")

            # 檢查環境變數 - 如果缺失，日誌警告但繼續（稍後會有動態檢查）
            if (
                not self.welcome_channel_id
                or not self.temp_role1_id
                or not self.member_role_id
            ):
                print("⚠️ 環境變數不完整（將繼續嘗試）:")
                print(f"   WELCOME_CHANNEL_ID={self.welcome_channel_id}")
                print(f"   TEMP_ROLE1_ID={self.temp_role1_id}")
                print(f"   MEMBER_ROLE_ID={self.member_role_id}")

            guild = member.guild

            # 添加臨時身分組（失敗時繼續，不中斷流程）
            if self.temp_role1_id:
                temp_role1 = guild.get_role(self.temp_role1_id)
                if temp_role1:
                    try:
                        await member.add_roles(temp_role1, reason="初步驗證角色")
                        print(f"✅ 已添加臨時身分組給 {member.name}")
                    except discord.Forbidden:
                        print("⚠️ 權限不足，無法添加身分組 (將繼續)")
                    except Exception as e:
                        print(f"⚠️ 添加身分組失敗: {type(e).__name__} (將繼續)")
                else:
                    print("⚠️ 找不到臨時身分組 (將繼續)")
            else:
                print("⚠️ TEMP_ROLE1_ID 未設置 (將繼續)")

            # 創建用戶資料（帶重試）
            user_created = self.create_user_data(member.id)
            if not user_created:
                print("⚠️ 創建用戶資料失敗，但嘗試繼續...")

            # 獲取用戶資料（重試機制）
            user_data = None
            for attempt in range(1, 4):
                user_data = self.get_user_data(member.id)
                if user_data:
                    print(f"✅ 成功獲取用戶資料 (嘗試 {attempt}/3)")
                    break
                else:
                    print(f"⚠️ 第 {attempt}/3 次獲取用戶資料失敗，重試...")
                    await asyncio.sleep(0.3)

            # 如果仍然無法獲取，使用隨機造型而非預設男性
            if not user_data:
                print("❌ 無法獲取用戶資料，生成隨機造型")
                # 🎭 生成隨機造型（男/女各占 50%）
                random_appearance = paperdoll_manager.get_random()
                user_data = {
                    "user_id": member.id,
                    "inventory": '["手機", "身分證"]',
                    "character_config": "{}",
                    "face": int(random_appearance["face"]),
                    "hair": int(random_appearance["hair"]),
                    "skin": int(random_appearance["skin"]),
                    "top": int(random_appearance["top"]),
                    "bottom": int(random_appearance["bottom"]),
                    "shoes": int(random_appearance["shoes"]),
                    "gender": random_appearance["gender"],
                    "level": 1,
                    "xp": 0,
                    "kkcoin": 0,
                    "title": "新手",
                    "hp": 100,
                    "stamina": 100,
                    "is_stunned": 0,
                    "thread_id": 0,
                    "last_kkcoin_snapshot": 0,
                    "last_xp_snapshot": 0,
                    "last_level_snapshot": 1,
                }
                print(
                    f"✅ 已生成隨機造型: {random_appearance['gender']} - face:{random_appearance['face']} hair:{random_appearance['hair']}"
                )

            # 發送歡迎訊息
            channel = None
            if self.welcome_channel_id:
                channel = self.bot.get_channel(self.welcome_channel_id)

            if not channel:
                print(f"❌ 找不到歡迎頻道 ID: {self.welcome_channel_id})")
                try:
                    await member.send(
                        "⚠️ 無法在歡迎頻道發送訊息，但你已被記錄。請聯繫管理員。"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

            print(f"📢 準備發送歡迎訊息到頻道: {channel.name}")

            embed = None
            try:
                embed = await self.create_welcome_embed(user_data, member)
                # 獲取角色圖片本地快取（非關鍵錯誤，可以失敗）
                try:
                    character_image_path = await self.get_character_image_url(user_data)
                    if character_image_path:
                        print(
                            f"✅ 【on_member_join】已準備角色圖片本地快取: {character_image_path}"
                        )
                    else:
                        print("⚠️ 【on_member_join】無法獲取角色圖片，將跳過")
                except Exception as img_err:
                    print(
                        f"⚠️ 【on_member_join】獲取圖片異常: {type(img_err).__name__} (將繼續)"
                    )

            except Exception as inner_err:
                # 生成歡迎 embed 或獲取圖片失敗，仍需發送基本歡迎訊息
                print(
                    f"⚠️ 【on_member_join】生成 embed 失敗，改用簡化版本: {type(inner_err).__name__}"
                )

                embed = discord.Embed(
                    title="🎉 歡迎光臨 KK 園區™",
                    description=(
                        f"🎉 歡迎 **{member.mention}** 來到 KK 園區！\n\n"
                        "發生了一些問題，但你仍然可以按下按鈕進入園區。"
                    ),
                    color=0x8B0000,
                )
                embed.add_field(
                    name="📌 提示",
                    value="如果按鈕無法顯示，請稍後重新進入此頻道。",
                    inline=False,
                )
                embed.set_thumbnail(url=member.display_avatar.url)

            # 發送訊息到頻道（最多重試 2 次）
            welcome_msg = None
            for attempt in range(1, 3):
                try:
                    # 確保 embed 存在
                    if not embed:
                        embed = discord.Embed(
                            title="🎉 歡迎光臨",
                            description=f"歡迎 {member.mention}！",
                            color=0x8B0000,
                        )

                    # 使用跨重啟的 persistent view（已註冊）
                    welcome_msg = await channel.send(
                        embed=embed, view=self.persistent_view
                    )
                    self.welcome_messages.setdefault(guild.id, {})[member.id] = (
                        welcome_msg.id
                    )

                    print(f"✅ 成功發送歡迎訊息給 {member.name} (嘗試 {attempt}/2)")
                    break

                except discord.Forbidden as perm_err:
                    print(f"❌ 發送訊息權限不足 (嘗試 {attempt}/2): {perm_err}")
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    try:
                        await member.send(
                            f"⚠️ {channel.name} 頻道發送失敗 (權限不足)，但你已被記錄。"
                        )
                    except:
                        pass

                except discord.HTTPException as http_err:
                    print(f"❌ HTTP 錯誤 (嘗試 {attempt}/2): {http_err}")
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    try:
                        await member.send("⚠️ 發送歡迎訊息失敗，但你已被記錄。")
                    except:
                        pass

                except Exception as msg_err:
                    print(
                        f"❌ 發送訊息異常 (嘗試 {attempt}/2): {type(msg_err).__name__}: {msg_err}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    import traceback

                    traceback.print_exc()
                    try:
                        await member.send("⚠️ 發送歡迎訊息異常，但你已被記錄。")
                    except:
                        pass

        except Exception as e:
            print(f"❌ on_member_join 外層異常: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()

    async def handle_final_verification(
        self, interaction: discord.Interaction, member: discord.Member
    ):
        try:
            print(f"🚪 開始入園流程: {member.name} (ID: {member.id})")

            # 檢查是否已繳交手機和身分證
            user_data = self.get_user_data(member.id)
            if not user_data:
                print(f"❌ 無法獲取用戶資料: {member.id}")
                await interaction.followup.send(
                    "❌ 無法獲取用戶資料，請聯繫管理員", ephemeral=True
                )
                return

            inventory_raw = user_data.get("inventory", "[]")
            if isinstance(inventory_raw, list):
                inventory = inventory_raw
            elif isinstance(inventory_raw, str):
                inventory = json.loads(inventory_raw) if inventory_raw else []
            else:
                inventory = []

            if "手機" in inventory or "身分證" in inventory:
                # 使用者尚未手動上繳，先警告並自動沒收
                print(f"⚠️ {member.name} 未上繳物品，系統自動沒收")
                await interaction.followup.send(
                    "⚠️ 你尚未上繳手機或身分證，系統已自動強制沒收並繼續入園流程。",
                    ephemeral=False,
                )
                await self.remove_items_from_inventory(member.id, ["手機", "身分證"])
                inventory = []

            guild = member.guild
            temp_role1 = guild.get_role(self.temp_role1_id)
            member_role = guild.get_role(self.member_role_id)

            if not member_role:
                print(f"❌ 正式成員身分組不存在: {self.member_role_id}")
                await interaction.followup.send(
                    "❌ 正式成員身分組配置錯誤，請聯繫管理員", ephemeral=True
                )
                return

            # 設置擊暈狀態
            print(f"💫 設置 {member.name} 為擊暈狀態")
            current_timestamp = int(datetime.now().timestamp())
            await self.update_user_data(
                member.id,
                {
                    "is_stunned": 1,
                    "hp": 10,
                    "stamina": 10,
                    "injury_recovery_time": current_timestamp,
                    "last_recovery": current_timestamp,
                },
            )

            # 立即添加正式成員身分
            try:
                print(f"🎯 嘗試添加正式成員身分給 {member.name}...")
                await member.add_roles(member_role, reason="進入園區成為正式成員")
                print(f"✅ 成功添加正式成員身分給 {member.name}")
            except discord.Forbidden as e:
                print(f"❌ 權限不足，無法添加身分組: {e}")
                await interaction.followup.send(
                    "❌ 無法添加身分組，可能是權限問題。請檢查機器人角色位置。",
                    ephemeral=True,
                )
                return
            except discord.HTTPException as e:
                print(f"❌ 添加身分組時出現 HTTP 錯誤: {e}")
                await interaction.followup.send(
                    "❌ 添加身分組失敗，請聯繫管理員。", ephemeral=True
                )
                return

            scam_id = f"{random.randint(1, 99999):05d}"
            nickname = f"NO.{scam_id} {member.display_name}"
            try:
                print(f"📝 設定昵稱: {nickname}")
                await member.edit(nick=nickname, reason="設定園編")
            except discord.Forbidden:
                print("⚠️ 權限不足，無法修改昵稱")
            except Exception as e:
                print(f"⚠️ 修改昵稱失敗: {e}")

            # 更新歡迎訊息
            print("📢 更新歡迎訊息...")
            await self.update_welcome_message(interaction, member.id)

            # 記錄擊暈用戶資訊
            self.stunned_users[member.id] = {
                "guild_id": guild.id,
                "temp_role1": temp_role1,
                "message_id": self.welcome_messages.get(guild.id, {}).get(member.id),
            }

            embed_response = discord.Embed(
                title="💫 擊暈成功！",
                description=(
                    f"園編：**{nickname}**\n"
                    "💫 已被成功擊暈！\n"
                    "✅ 已獲得正式成員身分\n"
                    "⏰ 5分鐘後將移除臨時身分組\n"
                    "🏥 血量和體力已降至10"
                ),
                color=0x696969,
            )
            embed_response.set_thumbnail(url=member.display_avatar.url)

            print(f"✅ 發送入園成功訊息給 {member.name}")
            await interaction.followup.send(embed=embed_response, ephemeral=True)

            # 🏷️ 發送興趣標籤選擇（堡壘保衛戰用，不強制）
            try:
                interest_embed = discord.Embed(
                    title="🏰 KK 園區對抗刑警大隊 — 選擇你的興趣標籤",
                    description=(
                        "每 4 小時，Google 熱搜話題會化為**刑警大隊**前來 KK 園區執法！\n\n"
                        "選擇你感興趣的話題，當相關趨勢入侵時：\n"
                        "⚔️ 你的攻擊力將會 **×2**！\n\n"
                        "選擇後即生效，也可隨時用 `/my_interests` 修改。"
                    ),
                    color=0xE74C3C,
                )
                interest_view = InterestOnboardingView(member.id)
                await interaction.followup.send(
                    embed=interest_embed, view=interest_view, ephemeral=True
                )
            except Exception as ie:
                print(f"⚠️ 發送興趣選擇失敗（不影響入園）: {ie}")

            # 📌 置物櫃將由 on_member_update 事件自動建立（當獲得正式會員角色時）

            # 5分鐘後移除臨時身分組並完成處理（後台執行，不阻塞交互）
            async def cleanup_after_delay():
                try:
                    await asyncio.sleep(300)
                    await self.remove_temp_role_and_cleanup(member.id)
                except Exception as cleanup_err:
                    print(f"❌ 後台清理任務錯誤: {cleanup_err}")

            print("⏱️ 排隊 5 分鐘後的清理任務")
            self.bot.loop.create_task(cleanup_after_delay())

        except Exception as e:
            print(f"❌ handle_final_verification 錯誤: {e}")
            import traceback

            traceback.print_exc()
            try:
                await interaction.followup.send(
                    f"❌ 入園流程發生錯誤: {str(e)[:100]}\n請聯繫管理員", ephemeral=True
                )
            except:
                pass

    async def remove_temp_role_and_cleanup(self, user_id: int):
        """5分鐘後移除臨時身分組並清理歡迎訊息"""
        try:
            if user_id not in self.stunned_users:
                return

            stun_data = self.stunned_users[user_id]
            guild = self.bot.get_guild(stun_data["guild_id"])
            if not guild:
                return

            member = guild.get_member(user_id)
            if not member:
                return

            # 移除臨時身分組
            if stun_data["temp_role1"] and stun_data["temp_role1"] in member.roles:
                await member.remove_roles(
                    stun_data["temp_role1"], reason="5分鐘後移除臨時身分組"
                )

            # 🏥 **保持傷病狀態**（`is_stunned: 1`）讓 recovery_cog 自動恢復
            # ✅ 傷病狀態恢復速度更快：每小時 +25 體力，約 4 小時後自動出院
            # 🔑 更新 injury_recovery_time 讓恢復循環能正確追蹤
            current_timestamp = int(datetime.now().timestamp())
            await self.update_user_data(
                user_id,
                {
                    "injury_recovery_time": current_timestamp,
                    "last_recovery": current_timestamp,
                    # ⚠️ **不**設置 is_stunned: 0，讓它保持為 1，由 recovery_cog 在體力達 100 時自動設為 0
                },
            )

            # 🔄 刷新紙娃娃顯示狀態（重新渲染歡迎訊息頂部，顯示恢復中的狀態）
            try:
                user_data = self.get_user_data(user_id)
                if user_data and member:
                    embed = None
                    try:
                        embed = await self.create_welcome_embed(user_data, member)
                        # 嘗試獲取角色圖片本地快取
                        character_image_path = await self.get_character_image_url(
                            user_data
                        )
                        if character_image_path and embed:
                            print(f"✅ 已準備角色圖片本地快取: {character_image_path}")
                    except Exception as embed_err:
                        print(f"⚠️ 生成歡迎 embed 失敗: {embed_err}")

                    # 👤 發送恢復說明給用戶（私訊）
                    try:
                        if embed:
                            recovery_message = (
                                f"✅ 5 分鐘清理完成！\n\n"
                                f"**📊 當前狀態：**\n"
                                f"• ❤️ 血量：{user_data.get('hp', 10)}/100\n"
                                f"• ⚡ 體力：{user_data.get('stamina', 10)}/100\n"
                                f"• 💤 傷病狀態：恢復中\n\n"
                                f"**⏱️ 自動恢復進度：**\n"
                                f"• 每小時恢復 +25 體力\n"
                                f"• 預計 4 小時內自動出院\n"
                                f"• 系統會自動通知你出院\n\n"
                                f"**💊 快速恢復選項：**\n"
                                f"• 如需立即恢復，可前往醫院購買恢復產品\n"
                                f"• 紙娃娃狀態見下方 ↓\n"
                            )
                            await member.send(recovery_message, embed=embed)
                    except Exception as msg_err:
                        print(f"⚠️ 發送恢復訊息失敗: {msg_err}")
            except Exception as refresh_err:
                print(f"⚠️ 刷新紙娃娃失敗（非關鍵）: {refresh_err}")

            # 獲取歡迎頻道（共用於清理訊息和發送完成通知）
            channel = self.bot.get_channel(self.welcome_channel_id)

            # 清理歡迎訊息
            if channel and stun_data["message_id"]:
                try:
                    msg = await channel.fetch_message(stun_data["message_id"])
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

            # 發送完成通知
            if channel:
                embed = discord.Embed(
                    title="✨ 入園完成！",
                    description=(
                        f"🎊 **{member.mention}** 已完成入園程序！\n"
                        "✅ 正式成員身分已確認\n"
                        "🗑️ 臨時身分組已移除\n"
                        "💤 已從擊暈狀態恢復\n"
                        "⚠️ 血量和體力仍處於虛弱狀態\n"
                        "🏥 請尋求治療或使用道具恢復\n"
                        "🎯 歡迎正式加入園區大家庭！"
                    ),
                    color=0x32CD32,
                )
                embed.set_thumbnail(url=member.display_avatar.url)

                completion_msg = await channel.send(embed=embed)

                # 5分鐘後刪除完成訊息（使用後台任務避免阻塞）
                async def delete_completion_msg():
                    try:
                        await asyncio.sleep(300)
                        await completion_msg.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass

                self.bot.loop.create_task(delete_completion_msg())

            # 清理記錄
            if user_id in self.stunned_users:
                del self.stunned_users[user_id]

            guild_messages = self.welcome_messages.get(stun_data["guild_id"], {})
            if user_id in guild_messages:
                del guild_messages[user_id]

        except Exception as e:
            print(f"❌ 移除臨時身分組錯誤: {e}")

    # ---------- debug helpers (slash commands) ----------
    @app_commands.command(name="debug_welcome")
    @app_commands.describe(member="目標成員（預設自己）")
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_welcome(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ):
        """單一唯讀歡迎流程預覽，不會修改資料庫或角色狀態。"""
        target = member or interaction.user
        user_data = self.get_preview_user_data(target.id)
        embed = await self.create_welcome_embed(user_data, target)
        view = TestWelcomeView(self, target, user_data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(WelcomeFlow(bot))
