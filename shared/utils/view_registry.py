# -*- coding: utf-8 -*-
"""
永久視圖管理系統
- PersistentViewBase: 所有永久視圖的基類
- register_all_permanent_views: 視圖註冊中樞

重要: 
- 視圖需要 timeout=None 才能在機器人重啟後保持有效
- 必須在 cog 的 setup() 時通過 bot.add_view() 預先註冊
- 使用 PersistentViewBase 基類自動設置 timeout=None
"""

import discord
from typing import Optional, Callable, Any
import asyncio


def _is_expired_interaction_error(error: Exception) -> bool:
    if isinstance(error, discord.NotFound):
        if getattr(error, "code", None) == 10062:
            return True
        if "Unknown interaction" in str(error):
            return True
    return False


async def _safe_defer(interaction: discord.Interaction) -> bool:
    if interaction.response.is_done():
        return True

    try:
        await interaction.response.defer()
        return True
    except Exception as error:
        if _is_expired_interaction_error(error):
            return False
        raise


class PersistentViewBase(discord.ui.View):
    """
    永久視圖基類 - 自動設置 timeout=None
    
    所有需要在機器人重啟後仍然有效的視圖應該繼承此類。
    支持通過 add_button 動態添加按鈕。
    
    使用方式：
        from shared.utils.view_registry import PersistentViewBase
        
        class MyPersistentView(PersistentViewBase):
            def __init__(self):
                super().__init__()
                # 你的初始化邏輯...
    
    關鍵特性：
    - ✅ timeout=None: 按鈕永不過期
    - ✅ 自動註冊: cog 在 setup() 時調用 bot.add_view(instance)
    - ✅ 跨重啟有效: 機器人重啟後按鈕仍然可用
    - ✅ add_button: 動態添加按鈕，支持鏈式調用
    """
    
    def __init__(self):
        """初始化永久視圖，自動設置 timeout=None"""
        super().__init__(timeout=None)
        self.buttons_config = {}
    
    def add_button(
        self,
        label: str,
        callback: Callable,
        style: str = "primary",
        emoji: Optional[str] = None,
        custom_id: Optional[str] = None,
        disabled: bool = False,
        row: Optional[int] = None
    ) -> "PersistentViewBase":
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
        self.buttons_config[button_id] = {
            "callback": callback,
            "label": label
        }
        
        # 創建按鈕
        button = discord.ui.Button(
            label=label,
            style=btn_style,
            emoji=emoji,
            custom_id=button_id,
            disabled=disabled,
            row=row
        )
        
        # 綁定按鈕回調
        button.callback = lambda interaction: self._button_callback(interaction, button_id)
        
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
            try:
                await _safe_defer(interaction)
            except Exception as error:
                print(f"[PersistentViewBase] 無法回應未知按鈕 {button_id}: {error}")
            return
        
        callback = self.buttons_config[button_id]["callback"]
        
        try:
            # 執行用戶定義的回調
            if asyncio.iscoroutinefunction(callback):
                await callback(interaction)
            else:
                callback(interaction)
        except Exception as e:
            if _is_expired_interaction_error(e):
                print(f"[PersistentViewBase] 忽略過期互動: {button_id}")
                return

            try:
                await _safe_defer(interaction)
            except Exception:
                pass
            print(f"[PersistentViewBase] 按鈕回調錯誤: {e}")


def register_all_permanent_views(client):
    """
    註冊所有永久視圖到 Discord Bot
    在 bot.on_ready() 中呼叫此函數
    
    Args:
        client: Discord Bot 客戶端
    """
    
    print("[VIEW_REGISTRY] ✅ 視圖註冊系統初始化完成")
    print("[VIEW_REGISTRY] 💡 所有視圖由各 cog 在 setup() 時自行管理")
    return 0
