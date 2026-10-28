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
# 動畫投票統計顯示設定
# ============================================================

# 固定顯示順序：embed 生成（cogs/ui/push_embed.py）與按鈕視圖（AnimePushView）
# 共用同一組常數，確保同一則 embed 在兩處重建後欄位格式完全一致。
# 鍵是分數字串（5 最好、1 最差）。2026-10-16 由「神作/佳作/…」改為分數，
# anime_votes.vote_type 也同步遷移成同一組數字鍵 —— 兩邊必須一致，否則
# get_vote_stats 的 `vote_type in vote_stats` 比對不到，票數會全部讀成 0。
VOTE_TYPE_ORDER = ("5", "4", "3", "2", "1")
VOTE_TYPE_LABELS: dict[str, tuple] = {
    "5": ("5分", "🟩"),
    "4": ("4分", "🟦"),
    "3": ("3分", "🟨"),
    "2": ("2分", "🟧"),
    "1": ("1分", "🟥"),
}

# 本集統計、全系列累計、觀眾留言的 embed 欄位名稱（投票後重建欄位時以此比對）
EPISODE_FIELD_NAME = "這集表現得如何?"
CUMULATIVE_FIELD_NAME = "📊 全系列累計"
COMMENTS_FIELD_NAME = "💬 觀眾留言"

# 互動獎勵：每則推播、每人每種一次，且只獎勵「剛推播」的集數。
# 舊訊息在 bot 重啟後會被重新註冊成可投票視圖，不設時窗就等於可以回頭
# 翻訊息逐則投票刷幣。
VOTE_REWARD_AMOUNT = 2000
COMMENT_REWARD_AMOUNT = 10000
REWARD_WINDOW_HOURS = 24
VOTE_REWARD_WINDOW_HOURS = REWARD_WINDOW_HOURS  # 舊名，保留給既有呼叫端

# embed 上的獎勵提示（金額與上面的常數同源，改金額時提示自動跟著變）
REWARD_HINT = f"💰 投票 +{VOTE_REWARD_AMOUNT} KK幣 ・ 💬 留言 +{COMMENT_REWARD_AMOUNT} KK幣"

# 「💬 觀眾留言」顯示設定：欄位值上限 1024 字元，故同時限制則數與單則長度。
# 留言寫入時雖已限制 200 字，多則並列仍會過長，這裡再截一次才讀得下去。
COMMENT_DISPLAY_LIMIT = 3
COMMENT_MAX_LEN = 60


def format_vote_stats(stats: dict[str, int]) -> str:
    """將投票統計字典格式化為 embed 欄位文字（每個分數一行）。

    Args:
        stats: 分數 → 票數的對應；缺少的分數以 0 計。

    Returns:
        以換行分隔的統計文字，例如「🟩 5分: 3」。
    """
    return "\n".join(
        f"{VOTE_TYPE_LABELS[key][1]} {VOTE_TYPE_LABELS[key][0]}: {stats.get(key, 0)}"
        for key in VOTE_TYPE_ORDER
    )


def format_comment_episode(volume) -> str:
    """把 volume（'第14集' / '[14]' / '14'）正規化成「第14集」。

    解析不出數字就回傳空字串，由呼叫端省略集數標註 —— 寧可只寫「匿名」，
    也不要讓使用者看到「第None集」這種半調子的字。
    """
    digits = "".join(ch for ch in str(volume or "") if ch.isdigit())
    return f"第{int(digits)}集" if digits else ""


def format_comments(
    comments: list,
    limit: int = COMMENT_DISPLAY_LIMIT,
    max_len: int = COMMENT_MAX_LEN,
) -> str:
    """將留言列表格式化為 embed 欄位文字（每則一行、匿名、標註出自第幾集）。

    留言以 animeSn 跨集數聚合（見 AnimePushDB.get_comments_by_anime），同一系列
    的新一集也看得到先前集數的留言，故每則都得標出集數，才讀得出「這是哪一集的
    人在說」。刻意不顯示 user_hash：embed 上是匿名呈現。

    Args:
        comments: 每筆含 comment 與選填 volume 的字典列表。
        limit: 最多顯示幾則（欄位值有 1024 字元上限）。
        max_len: 單則留言截斷長度。

    Returns:
        以換行分隔的留言文字；沒有可顯示的留言時回傳空字串。
    """
    lines = []
    for item in comments[:limit]:
        text = " ".join(str(item.get("comment") or "").split())
        if not text:
            continue
        if len(text) > max_len:
            text = text[: max_len - 1].rstrip() + "…"
        episode = format_comment_episode(item.get("volume"))
        suffix = f"匿名 · {episode}" if episode else "匿名"
        lines.append(f"> {text} — {suffix}")
    return "\n".join(lines)


def _set_embed_field(embed: discord.Embed, name: str, value: Optional[str]) -> None:
    """就地覆蓋 embed 上的同名欄位（原位置換掉）；value 為空則整個欄位移除。

    統計與留言都是「同一則 embed 由不同人陸續更新」的欄位，不覆蓋就會出現兩個
    同名欄位各說各話。刻意寫回原位置而非移除後追加（那樣留言欄位會被擠到統計
    上面），欄位順序與 generate_anime_embed 產出的一致。
    """
    for i, field in enumerate(embed.fields):
        if field.name == name:
            if value:
                embed.set_field_at(i, name=name, value=value, inline=False)
            else:
                embed.remove_field(i)
            return
    if value:
        embed.add_field(name=name, value=value, inline=False)


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
    包含 5 個投票按鈕、1 個評論按鈕、動畫頁連結、觀看連結。
    """

    # 投票類型配置 (與 AnimeVoteView 保持一致；實際定義見模組頂端 VOTE_TYPE_LABELS)
    VOTE_TYPES = VOTE_TYPE_LABELS

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
                label="▶️ 觀看第一集", url=anime_url, style=discord.ButtonStyle.link
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
            self.message_id = message_id  # 供後續統計依「同一則 embed」精確查詢
            vote_recorded = False
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

            # 投票成功且原訊息存在 → 更新「本集」與「全系列累計」兩個統計欄位
            if vote_recorded and interaction.message:
                try:
                    if interaction.message.embeds:
                        embed = interaction.message.embeds[0].copy()
                        # 兩個欄位都要重建：若只重建本集欄位，全系列累計會停留在
                        # 投票前的數字，與本集欄位互相矛盾。
                        _set_embed_field(
                            embed, EPISODE_FIELD_NAME, self._build_vote_stats_text()
                        )
                        _set_embed_field(
                            embed,
                            CUMULATIVE_FIELD_NAME,
                            self._build_cumulative_stats_text(),
                        )
                        await interaction.message.edit(embed=embed)
                except Exception as e:
                    logger.error(f"❌ 更新投票統計欄位失敗: {e}")

            # 發放投票獎勵（每人每則一次；已領過或超過時窗則不發）
            rewarded = False
            if vote_recorded and message_id:
                rewarded = await self._grant_reward(
                    interaction, message_id, "vote", VOTE_REWARD_AMOUNT
                )

            # 先發送 follow-up 確認給用戶
            try:
                reply = f"✅ 投票成功！{vote_label}"
                if rewarded:
                    reply += f"\n💰 獲得 {VOTE_REWARD_AMOUNT} KK幣"
                await interaction.followup.send(reply, ephemeral=True)
            except Exception as e:
                logger.error(f"發送 follow-up 失敗: {e}")

        except Exception as e:
            logger.error(f"❌ [AnimePushView._vote_callback] 投票失敗: {e}", exc_info=True)

    async def _grant_reward(
        self,
        interaction: discord.Interaction,
        message_id: int,
        reward_type: str,
        amount: int,
    ) -> bool:
        """發放互動 KK幣獎勵，回傳這次是否真的發出去了。

        先向 DB 認領（原子寫入）再發幣，順序不能顛倒：反過來的話，發幣成功
        但認領失敗就會重複發放。寧可極少數情況下使用者領不到，也不要多發。

        兩道閘門對投票與留言一體適用：`anime_rewards` 的
        UNIQUE(user_id, message_id, reward_type) 擋同人同則重複領，
        is_recently_pushed 擋回頭翻舊訊息刷幣。留言可以無限重送，
        沒有第一道閘門就是無限印鈔。
        """
        if not self.db or not hasattr(self.db, "record_reward"):
            return False

        if hasattr(self.db, "is_recently_pushed") and not self.db.is_recently_pushed(
            self.video_sn, REWARD_WINDOW_HOURS
        ):
            logger.info(
                f"⏭️ [AnimePushView] videoSn={self.video_sn} 已超過 "
                f"{REWARD_WINDOW_HOURS}h 獎勵時窗，不發放 {reward_type} 獎勵"
            )
            return False

        try:
            claimed = self.db.record_reward(
                interaction.user.id, message_id, reward_type, amount
            )
        except Exception as e:
            logger.error(f"❌ [AnimePushView] 認領 {reward_type} 獎勵失敗: {e}")
            return False

        if not claimed:
            return False

        try:
            # 區域匯入：embed_views 被多個 cog 匯入，模組層就載入 user_data.db
            # 會拖慢啟動並增加循環匯入風險
            from shared.db.async_adapter import update_user_kkcoin

            await update_user_kkcoin(interaction.user.id, amount)
        except Exception as e:
            logger.error(
                f"❌ [AnimePushView] 發放 {reward_type} 獎勵失敗 "
                f"(user={interaction.user.id}): {e}"
            )
            return False
        return True

    def _build_vote_stats_text(self) -> Optional[str]:
        """從資料庫重建「這集表現得如何?」欄位文字（與 push_embed.generate_anime_embed 格式一致）。

        以 self.message_id（該則 embed）精確查詢；尚未設定 message_id 時退回以 videoSn 查詢。
        """
        try:
            if not self.db or not hasattr(self.db, "get_vote_stats") or not self.video_sn:
                return None
            vote_stats = self.db.get_vote_stats(int(self.video_sn), self.message_id)
            return format_vote_stats(vote_stats)
        except Exception as e:
            logger.error(f"❌ 重建投票統計失敗: {e}")
            return None

    def _build_cumulative_stats_text(self) -> Optional[str]:
        """從資料庫重建「全系列累計」欄位文字。

        以 self.anime_sn 跨集數加總，讓最新一集的 embed 也能看到先前集數的累積表現。
        """
        try:
            if (
                not self.db
                or not hasattr(self.db, "get_vote_stats_by_anime")
                or not self.anime_sn
            ):
                return None
            return format_vote_stats(
                self.db.get_vote_stats_by_anime(int(self.anime_sn))
            )
        except Exception as e:
            logger.error(f"❌ 重建全系列累計統計失敗: {e}")
            return None

    def _build_comments_text(self) -> Optional[str]:
        """從資料庫重建「💬 觀眾留言」欄位文字（與 push_embed 的格式同源）。

        以 self.anime_sn 跨集數取最新幾則，語意與「全系列累計」一致：同一系列
        共用一塊留言板，新一集的推播也看得到先前集數的留言（各自標註集數）。
        """
        try:
            if (
                not self.db
                or not hasattr(self.db, "get_comments_by_anime")
                or not self.anime_sn
            ):
                return None
            return format_comments(self.db.get_comments_by_anime(int(self.anime_sn)))
        except Exception as e:
            logger.error(f"❌ 重建觀眾留言失敗: {e}")
            return None

    async def _refresh_comments_field(
        self,
        interaction: discord.Interaction,
        message: Optional[discord.Message],
    ) -> None:
        """把「💬 觀眾留言」欄位重建到原推播 embed 上（沒有留言就整欄移除）。

        留言只寫進 DB 是不夠的：使用者按了留言、幣也發了，畫面上卻什麼都沒變，
        看起來就像「話被吃掉了」。投票在同一則訊息上是即時更新欄位的，留言必須一致。

        Args:
            interaction: 用來在拿不到 message 物件時回頭抓訊息（有 channel 即可）。
            message: 原推播訊息；Modal 不一定帶得到 message 物件，故由按鈕當下傳入。
        """
        try:
            if message is None and self.message_id and interaction.channel:
                message = await interaction.channel.fetch_message(self.message_id)
            if not message or not message.embeds:
                return

            # None 代表查不到（db 不可用），此時不要動 embed，免得把既有留言欄位誤刪
            comments_text = self._build_comments_text()
            if comments_text is None:
                return

            embed = message.embeds[0].copy()
            _set_embed_field(embed, COMMENTS_FIELD_NAME, comments_text)
            await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"❌ 更新觀眾留言欄位失敗: {e}")

    async def _comment_callback(self, interaction: discord.Interaction):
        """處理評論按鈕點擊 - 彈出評論輸入框"""
        try:
            logger.info(f"💬 [AnimePushView._comment_callback] 用戶 {interaction.user.name} 點擊評論")

            outer_self = self
            # 按鈕當下的推播訊息：Modal 有時拿不到 message 物件，先在這裡抓下來，
            # 留言存檔後才能把那則 embed 的留言欄位一起更新
            source_message = interaction.message

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
                            # 空留言不必動用 DB，直接回掉，也就無須 defer
                            await modal_interaction.response.send_message(
                                "評論不能為空", ephemeral=True
                            )
                            return

                        # 🔑 先 defer：發幣要寫 user_data.db，超過 3 秒會被 Discord
                        # 判定「應用程式沒有回應」
                        await modal_interaction.response.defer(ephemeral=True)

                        user_hash = str(hash(modal_interaction.user.id))[:10]
                        # 優先用 modal 來源訊息，未重新投票也能精確記錄到該則 embed
                        message = modal_interaction.message or source_message
                        message_id = (
                            message.id if message else outer_self.message_id
                        )
                        anime_name = outer_self.episode.get("title", "") if outer_self.episode else ""

                        # 記錄評論
                        if outer_self.db and hasattr(outer_self.db, 'record_vote'):
                            outer_self.db.record_vote(
                                video_sn=outer_self.video_sn,
                                anime_sn=outer_self.anime_sn,
                                message_id=message_id,
                                vote_type="comment",
                                comment=comment,
                                user_hash=user_hash,
                                anime_name=anime_name,
                            )

                        # 存檔後立刻把留言欄位貼回原推播 embed（與投票即時更新欄位一致），
                        # 排在發幣之前：發幣要寫 user_data.db，先讓畫面更新才不會卡在等幣
                        await outer_self._refresh_comments_field(
                            modal_interaction, message
                        )

                        # 留言獎勵：留言可以重複送出，防重複全靠 anime_rewards 的
                        # UNIQUE(user_id, message_id, reward_type)
                        rewarded = False
                        if message_id:
                            rewarded = await outer_self._grant_reward(
                                modal_interaction,
                                message_id,
                                "comment",
                                COMMENT_REWARD_AMOUNT,
                            )

                        reply = "✅ 評論已保存！感謝你的意見"
                        if rewarded:
                            reply += f"\n💰 獲得 {COMMENT_REWARD_AMOUNT} KK幣"
                        await modal_interaction.followup.send(reply, ephemeral=True)

                    except Exception as e:
                        logger.error(f"❌ [CommentModal.on_submit] 失敗: {e}")
                        try:
                            # 上面可能已經 defer 過，用錯管道會再噴一次互動失敗
                            if modal_interaction.response.is_done():
                                await modal_interaction.followup.send(
                                    f"❌ 評論失敗: {str(e)[:50]}", ephemeral=True
                                )
                            else:
                                await modal_interaction.response.send_message(
                                    f"❌ 評論失敗: {str(e)[:50]}", ephemeral=True
                                )
                        except Exception:
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
