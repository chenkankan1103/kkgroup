# -*- coding: utf-8 -*-
"""
全局 Embed 按鈕視圖管理系統
提供可重複使用的 embed 按鈕視圖，支持永久視圖和自定義超時
"""

import discord
from discord.ext import commands
from typing import Optional, Callable, List, Dict, Any
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 按鈕樣式列舉
# ============================================================


class ButtonStyle(str, Enum):
    """按鈕樣式列舉"""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUCCESS = "success"
    DANGER = "danger"
    LINK = "link"


class PersistentEmbedView(discord.ui.View):
    """
    永久 Embed 按鈕視圖（支持 bot 重啟後保留）

    使用方式：
        view = PersistentEmbedView(timeout=10.0)
        view.add_button("按鈕文本", callback_func, style="primary")
        embed = discord.Embed(title="測試", description="點擊按鈕")
        await ctx.send(embed=embed, view=view)
    """

    def __init__(self, timeout: Optional[float] = 10.0):
        """
        初始化永久視圖

        Args:
            timeout: 視圖超時時間（秒），默認 10 秒。
                    設置為 None 表示永久視圖（不過期）
        """
        super().__init__(timeout=timeout)
        self.timeout = timeout
        self.buttons_config: Dict[str, Dict[str, Any]] = {}

    def add_button(
        self,
        label: str,
        callback: Callable,
        style: str = "primary",
        emoji: Optional[str] = None,
        custom_id: Optional[str] = None,
        disabled: bool = False,
        row: Optional[int] = None,
    ) -> "PersistentEmbedView":
        """
        添加按鈕到視圖

        Args:
            label: 按鈕文本
            callback: 按鈕點擊回調函數 (async def callback(interaction: discord.Interaction))
            style: 按鈕樣式 ("primary", "secondary", "success", "danger", "link")
            emoji: 按鈕 emoji
            custom_id: 自定義 ID（用於持久視圖）
            disabled: 是否禁用按鈕
            row: 按鈕所在行（0-4）

        Returns:
            self: 便於鏈式調用
        """
        # 轉換樣式為 discord.ButtonStyle
        try:
            btn_style = getattr(discord.ButtonStyle, style.upper())
        except AttributeError:
            btn_style = discord.ButtonStyle.primary

        # 生成 custom_id
        button_id = custom_id or f"btn_{len(self.buttons_config)}"

        # 保存回調函數
        self.buttons_config[button_id] = {"callback": callback, "label": label}

        # 創建按鈕
        button = discord.ui.Button(
            label=label,
            style=btn_style,
            emoji=emoji,
            custom_id=button_id,
            disabled=disabled,
            row=row,
        )

        # 綁定按鈕回調
        button.callback = lambda interaction: self._button_callback(
            interaction, button_id
        )

        self.add_item(button)
        return self

    async def _button_callback(self, interaction: discord.Interaction, button_id: str):
        """
        內部按鈕回調處理

        Args:
            interaction: Discord 交互對象
            button_id: 按鈕 ID
        """
        if button_id not in self.buttons_config:
            await interaction.response.defer()
            return

        callback = self.buttons_config[button_id]["callback"]

        try:
            # 執行用戶定義的回調
            if asyncio.iscoroutinefunction(callback):
                await callback(interaction)
            else:
                callback(interaction)
        except Exception as e:
            try:
                await interaction.response.defer()
            except:
                pass
            print(f"[EmbedView] 按鈕回調錯誤: {e}")

    def remove_button(self, button_id: str) -> bool:
        """
        移除指定的按鈕

        Args:
            button_id: 按鈕 ID

        Returns:
            bool: 是否成功移除
        """
        # 從配置中移除
        if button_id not in self.buttons_config:
            return False

        del self.buttons_config[button_id]

        # 從視圖中移除按鈕項目
        for item in self.children[:]:
            if isinstance(item, discord.ui.Button) and item.custom_id == button_id:
                self.remove_item(item)
                return True

        return False

    def clear_buttons(self):
        """清除所有按鈕"""
        self.buttons_config.clear()
        for item in self.children[:]:
            if isinstance(item, discord.ui.Button):
                self.remove_item(item)

    async def on_timeout(self):
        """視圖超時後的回調"""
        # 禁用所有按鈕
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class SimpleEmbedButton:
    """
    簡化版本的 Embed 按鈕工廠
    快速創建常見的按鈕操作
    """

    @staticmethod
    def create_confirmation_view(
        on_confirm: Callable, on_cancel: Callable, timeout: float = 10.0
    ) -> PersistentEmbedView:
        """
        創建確認/取消按鈕視圖

        Args:
            on_confirm: 確認回調
            on_cancel: 取消回調
            timeout: 超時時間

        Returns:
            PersistentEmbedView: 配置好的視圖
        """
        view = PersistentEmbedView(timeout=timeout)
        view.add_button("✅ 確認", on_confirm, style="success", custom_id="confirm")
        view.add_button("❌ 取消", on_cancel, style="danger", custom_id="cancel")
        return view

    @staticmethod
    def create_yes_no_view(
        on_yes: Callable, on_no: Callable, timeout: float = 10.0
    ) -> PersistentEmbedView:
        """
        創建是/否按鈕視圖

        Args:
            on_yes: 是回調
            on_no: 否回調
            timeout: 超時時間

        Returns:
            PersistentEmbedView: 配置好的視圖
        """
        view = PersistentEmbedView(timeout=timeout)
        view.add_button("👍 是", on_yes, style="primary", custom_id="yes")
        view.add_button("👎 否", on_no, style="secondary", custom_id="no")
        return view

    @staticmethod
    def create_action_view(
        actions: Dict[str, tuple], timeout: float = 10.0
    ) -> PersistentEmbedView:
        """
        創建自定義操作按鈕視圖

        Args:
            actions: 操作字典 {按鈕標籤: (回調函數, 樣式, emoji)}
                    例: {"刪除": (on_delete, "danger", "🗑️")}
            timeout: 超時時間

        Returns:
            PersistentEmbedView: 配置好的視圖
        """
        view = PersistentEmbedView(timeout=timeout)

        for i, (label, action_config) in enumerate(actions.items()):
            callback = action_config[0]
            style = action_config[1] if len(action_config) > 1 else "primary"
            emoji = action_config[2] if len(action_config) > 2 else None

            view.add_button(
                label, callback, style=style, emoji=emoji, custom_id=f"action_{i}"
            )

        return view


class EmbedViewManager:
    """
    全局 Embed 視圖管理器
    用於在 bot 啟動時註冊持久視圖
    """

    def __init__(self, bot: commands.Bot):
        """
        初始化視圖管理器

        Args:
            bot: Discord bot 實例
        """
        self.bot = bot
        self.persistent_views: Dict[str, PersistentEmbedView] = {}

    def register_persistent_view(self, view_id: str, view: PersistentEmbedView):
        """
        註冊持久視圖（bot 重啟後仍然有效）

        Args:
            view_id: 視圖唯一識別碼
            view: PersistentEmbedView 實例
        """
        self.persistent_views[view_id] = view
        self.bot.add_view(view)

    def get_persistent_view(self, view_id: str) -> Optional[PersistentEmbedView]:
        """
        獲取已註冊的持久視圖

        Args:
            view_id: 視圖唯一識別碼

        Returns:
            PersistentEmbedView 或 None
        """
        return self.persistent_views.get(view_id)

    def unregister_view(self, view_id: str) -> bool:
        """
        移除已註冊的視圖

        Args:
            view_id: 視圖唯一識別碼

        Returns:
            bool: 是否成功移除
        """
        if view_id in self.persistent_views:
            del self.persistent_views[view_id]
            return True
        return False


# ============================================================
# 便捷函數
# ============================================================


def create_embed_with_view(
    title: str = "",
    description: str = "",
    color: Optional[discord.Color] = None,
    buttons: Optional[List[tuple]] = None,
    timeout: float = 10.0,
) -> tuple[discord.Embed, PersistentEmbedView]:
    """
    快速創建 Embed 和按鈕視圖

    Args:
        title: Embed 標題
        description: Embed 描述
        color: Embed 顏色
        buttons: 按鈕列表 [(標籤, 回調, 樣式, emoji), ...]
        timeout: 視圖超時時間

    Returns:
        tuple: (embed, view)
    """
    embed = discord.Embed(
        title=title, description=description, color=color or discord.Color.blue()
    )

    view = PersistentEmbedView(timeout=timeout)

    if buttons:
        for i, button_config in enumerate(buttons):
            label = button_config[0]
            callback = button_config[1]
            style = button_config[2] if len(button_config) > 2 else "primary"
            emoji = button_config[3] if len(button_config) > 3 else None

            view.add_button(
                label, callback, style=style, emoji=emoji, custom_id=f"btn_{i}"
            )

    return embed, view


class AnimePushView(discord.ui.View):
    """
    動畫推送視圖 - 投票按鈕 + 評論按鈕 + 動畫頁/觀看連結 (永久視圖)

    用於動畫推送的簡化版視圖，不依賴 AnimeTracker 類別。
    包含 6 個投票按鈕、1 個評論按鈕、動畫頁連結、觀看連結。
    """

    # 投票類型配置 (與 AnimeVoteView 保持一致)
    VOTE_TYPES = {
        "masterpiece": ("神作", "🟩"),
        "great": ("佳作", "🟦"),
        "darkhorse": ("黑馬", "🟪"),
        "decent": ("普作/小品", "🟨"),
        "controversial": ("爭議作", "🟧"),
        "disaster": ("雷作/糞作", "🟥"),
    }

    def __init__(self, episode: dict, db_adapter=None):
        # 永久視圖：timeout=None
        super().__init__(timeout=None)
        self.episode = episode
        self.db = db_adapter
        self.video_sn = episode.get("videoSn")
        self.anime_sn = episode.get("animeSn")
        self.message_id = None

        if not self.video_sn or not self.anime_sn:
            logger.warning("AnimePushView: 缺少 videoSn 或 animeSn")
            return

        # 添加投票按鈕
        for vote_key, (vote_label, color_emoji) in self.VOTE_TYPES.items():
            button = discord.ui.Button(
                label=f"{color_emoji} {vote_label}",
                custom_id=f"anime_vote_{vote_key}_{self.video_sn}",
                style=discord.ButtonStyle.secondary,  # 灰色
            )
            button.callback = self._vote_callback
            self.add_item(button)

        # 添加評論按鈕
        comment_button = discord.ui.Button(
            label="💬 留言",
            custom_id=f"anime_comment_{self.video_sn}",
            style=discord.ButtonStyle.secondary,
        )
        comment_button.callback = self._comment_callback
        self.add_item(comment_button)

        # 添加動畫頁連結
        anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={self.anime_sn}"
        self.add_item(
            discord.ui.Button(
                label="🔗 動畫頁", url=anime_url, style=discord.ButtonStyle.link
            )
        )

        # 添加觀看連結
        video_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={self.video_sn}"
        self.add_item(
            discord.ui.Button(
                label="▶️ 觀看", url=video_url, style=discord.ButtonStyle.link
            )
        )

    async def _vote_callback(self, interaction: discord.Interaction):
        """處理投票按鈕點擊"""
        try:
            logger.info(f"🎯 [AnimePushView._vote_callback] 用戶 {interaction.user.name}({interaction.user.id}) 點擊投票")

            # 🔑 關鍵：立即 defer() 回應 Discord，避免 3 秒超時
            await interaction.response.defer()

            # 解析投票類型
            vote_key = interaction.custom_id.replace("anime_vote_", "").rsplit("_", 1)[0]
            vote_label, _ = self.VOTE_TYPES.get(vote_key, ("未知", None))

            # 獲取用戶的匿名雜湊
            user_hash = str(hash(interaction.user.id))[:10]

            # 取得動畫名稱
            anime_name = self.episode.get("title", "") if self.episode else ""

            # 記錄投票 (需要 db adapter 有 record_vote 方法)
            message_id = interaction.message.id if interaction.message else None
            if self.db and hasattr(self.db, 'record_vote'):
                vote_recorded = self.db.record_vote(
                    video_sn=self.video_sn,
                    anime_sn=self.anime_sn,
                    message_id=message_id,
                    vote_type=vote_key,
                    user_hash=user_hash,
                    anime_name=anime_name,
                )
                if not vote_recorded:
                    logger.error(f"❌ 投票記錄失敗")

            # 先發送 follow-up 確認給用戶
            try:
                await interaction.followup.send(
                    f"✅ 投票成功！{vote_label}", ephemeral=True
                )
            except Exception as e:
                logger.error(f"發送 follow-up 失敗: {e}")

        except Exception as e:
            logger.error(f"❌ [AnimePushView._vote_callback] 投票失敗: {e}", exc_info=True)

    async def _comment_callback(self, interaction: discord.Interaction):
        """處理評論按鈕點擊 - 彈出評論輸入框"""
        try:
            logger.info(f"💬 [AnimePushView._comment_callback] 用戶 {interaction.user.name} 點擊評論")

            outer_self = self

            class CommentModal(discord.ui.Modal, title="留下匿名評論"):
                comment_input = discord.ui.TextInput(
                    label="評論內容",
                    placeholder="寫下你對這部動畫的看法...",
                    max_length=200,
                    required=False,
                )

                async def on_submit(self, modal_interaction: discord.Interaction):
                    try:
                        comment = str(self.comment_input).strip()
                        if not comment:
                            await modal_interaction.response.send_message(
                                "評論不能為空", ephemeral=True
                            )
                            return

                        user_hash = str(hash(modal_interaction.user.id))[:10]
                        message_id = outer_self.message_id
                        anime_name = outer_self.episode.get("title", "") if outer_self.episode else ""

                        # 記錄評論
                        if outer_self.db and hasattr(outer_self.db, 'record_vote'):
                            vote_recorded = outer_self.db.record_vote(
                                video_sn=outer_self.video_sn,
                                anime_sn=outer_self.anime_sn,
                                message_id=message_id,
                                vote_type="comment",
                                comment=comment,
                                user_hash=user_hash,
                                anime_name=anime_name,
                            )

                        await modal_interaction.response.send_message(
                            "✅ 評論已保存！感謝你的意見", ephemeral=True
                        )

                    except Exception as e:
                        logger.error(f"❌ [CommentModal.on_submit] 失敗: {e}")
                        try:
                            await modal_interaction.response.send_message(
                                f"❌ 評論失敗: {str(e)[:50]}", ephemeral=True
                            )
                        except:
                            pass

            # 發送 Modal
            await interaction.response.send_modal(CommentModal())

        except Exception as e:
            logger.error(f"❌ [AnimePushView._comment_callback] 評論失敗: {e}")
            try:
                await interaction.response.send_message(
                    f"❌ 無法開啟評論: {str(e)[:50]}", ephemeral=True
                )
            except:
                pass


def create_anime_push_view(episode: dict, db_adapter=None) -> Optional[AnimePushView]:
    """
    創建動畫推送視圖

    Args:
        episode: 動畫集數資料字典 (需包含 videoSn, animeSn 等)
        db_adapter: 可選的資料庫適配器，用於記錄投票/評論

    Returns:
        AnimePushView 實例，或 None (如果資料不完整)
    """
    try:
        video_sn = episode.get("videoSn")
        anime_sn = episode.get("animeSn")
        if not video_sn or not anime_sn:
            logger.warning("create_anime_push_view: 缺少 videoSn 或 animeSn")
            return None
        return AnimePushView(episode, db_adapter)
    except Exception as e:
        logger.error(f"create_anime_push_view 失敗: {e}")
        return None
