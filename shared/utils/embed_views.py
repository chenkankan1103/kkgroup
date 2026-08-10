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
