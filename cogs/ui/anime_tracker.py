# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 增強版排程推送系統
- 增強版推送系統：使用 SimpleAnimePushCore (push_core_simple.py) 基於 anime_push.db
  實現精準排程推送與15分鐘輪詢備案機制
- 排程推送：基於 anime_weekly_schedule 表在實際播出時間精確推送
- 備案機制：連續3次失敗後自動切換至15分鐘輪詢，恢復條件為成功推送
- 單一資料庫連線：各組件共用同一 anime_push.db 連線
"""

import io
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands, tasks
from typing import Optional
import sys
from pathlib import Path

# Add kkgroup directory to sys.path for absolute imports
kkgroup_dir = Path(__file__).resolve().parent.parent.parent
if str(kkgroup_dir) not in sys.path:
    sys.path.insert(0, str(kkgroup_dir))

from cogs.ui.push_core_simple import (
    SimpleAnimePushCore,
    AnimePushDB,
    ANIME_PUSH_DB_PATH,
    ANIME_CHANNEL_ID,
    TW_TZ,
    fetch_all_recent_anime_from_api,
)
from cogs.ui.schedule_tracker import AnimeScheduleTracker
from shared.utils.encoding_handler import setup_utf8_logging

# 這支必須自帶 handler：uibot 用 client.start()，discord.py 的 setup_logging 不會被呼叫，
# root logger 一個 handler 都沒有，記錄會掉進 lastResort 的 WARNING 被吞掉；連
# logging.getLogger(__name__).setLevel(INFO) 也救不回來（2026-10-11 recovery_cog 踩過同一個坑）。
# 實測 journal 7 天 281360 行裡這支只有 12 筆（全是 set_dependencies），推送與投票紀錄全被吞掉。
logger = setup_utf8_logging(__name__, logging.INFO)

# 每週成長快照設定
GROWTH_SNAPSHOT_WEEKDAY = 6  # 0=週一 ... 6=週日
GROWTH_SNAPSHOT_HOUR = 22  # 每天 22:00（避開 02:00 週表刷新與 API 尖峰）
GROWTH_HISTORY_WEEKS = 12  # 回溯週數（算「連續進榜」用）
GROWTH_TOP_N = 10  # 進榜門檻：本週新增前 N 名
GROWTH_BAR_N = 8  # 橫條圖畫幾條
GROWTH_STREAK_MIN = 2  # 連續進榜幾週才標「持續在紅」
GROWTH_STREAK_FIELD_N = 6  # 「持續在紅」欄位最多列幾部
GROWTH_MOVER_N = 3  # 「本週衝最快」卡片取前 N 名
# 只取累計排名前 N 名：擋掉小基數造成的假高成長率（基數 1,000 漲到 2,000 就是
# +100%，但那沒有意義），同時後段番本來就不是使用者關心的範圍
GROWTH_MOVER_RANK_LIMIT = GROWTH_TOP_N * 3

# 人氣走勢折線圖。快照是每天一格、推播只在週日，所以曲線有每日的解析度，
# 但不會每天洗版
GROWTH_TREND_N = 6  # 折線畫幾部（上限受色票槽數限制）
GROWTH_TREND_DAYS = 70  # 折線回溯幾天
GROWTH_WEEK_DAYS = 7  # 「週增量」＝跟幾天前的快照相減

# 橫條圖用色：底色對齊 Discord 深色主題的 embed（#2b2d31）；條身 #3987e5 是
# dataviz 12 色盤第一槽的深色版（單一系列色，已過色盲分離度與對比驗證）。
# 條數固定用同一色——排行已經由長度編碼，顏色再扛辨識只是浪費。
_CHART_BG_HEX = "#2b2d31"
_CHART_BAR_HEX = "#3987e5"
_CHART_TEXT_HEX = "#dbdee1"
# 折線圖色票：dataviz 深色 8 槽裡取 6 槽，跳過 green。已用 validate_palette.py
# 對底色 #2b2d31 驗過亮度帶、彩度、色盲分離度、正常視覺分離度、對比全數 PASS。
# 跳過 green 有兩個理由：它跟 aqua 在折線圖上難以分辨，而且它對底色的對比只有
# 2.79:1。橫條圖可以容忍（長度本身就是第二編碼），折線全靠顏色認人，撞色就完了。
_CHART_SERIES_HEX = (
    "#3987e5",  # blue
    "#d95926",  # orange
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#d55181",  # magenta
    "#9085e9",  # violet
)
_CHART_MUTED_HEX = "#898781"
_CHART_GRID_HEX = "#2c2c2a"
# 從 cogs/ui/ 出發到 repo 根是三層 `../`（與 cogs/common/ 的字型規則相同）
_CJK_FONT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "fonts" / "NotoSansCJKtc-Regular.otf"
)


# V2 版面測試頻道（forum thread）。只給 anime_v2_test 用，cutover 完成後整段移除
ANIME_V2_TEST_CHANNEL_ID = 1504438347974705152


def _iter_dispatchable_items(components):
    """遞迴走訪元件樹，逐一吐出帶 custom_id 的按鈕。

    V2 訊息的按鈕藏在 Container → ActionRow → Button 第三層，embed 時代只有
    ActionRow → Button 兩層。只走兩層對 V2 是全面失效：getattr(ActionRow,
    "custom_id") 恆為 None，於是每則 V2 訊息都被判定成「不是動畫推送」而跳過，
    重啟後所有 V2 按鈕靜默死亡。
    """
    for component in components:
        if getattr(component, "custom_id", None):
            yield component
        children = getattr(component, "children", None)
        if children:
            yield from _iter_dispatchable_items(children)


def _push_mode_of_message(message) -> str:
    """從卡片左側色條回推推送模式。

    V2 訊息沒有其他欄位記得住推送模式，重畫畫面時得照原樣上色 —— 猜錯的話
    使用者一投票，卡片就從排程推送的紫色變成預設灰。
    """
    from cogs.ui.push_embed import _PUSH_MODE_COLORS

    for component in message.components:
        colour = getattr(component, "accent_colour", None)
        if colour is None:
            continue
        value = getattr(colour, "value", colour)
        for name, hex_value in _PUSH_MODE_COLORS.items():
            if hex_value == value:
                return name
    return "unknown"


def _parse_volume_ep(volume) -> Optional[int]:
    """從 volume 字串（'第14集'）解析出集數 14，供標記「本週有新集」"""
    digits = "".join(ch for ch in str(volume or "") if ch.isdigit())
    return int(digits) if digits else None


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤 Cog - 增強版排程推送系統 (含15分鐘輪詢備案)"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logger
        self.polling_core = None
        self.db = None
        self.schedule_tracker = None
        self._running = False
        self._push_tick = 0
        # 監督器重啟次數：loop 名稱 → 次數，用來辨識「啟動後立刻又死」的 loop
        self._loop_restarts: dict[str, int] = {}

    async def set_dependencies(self, db_path: str = None):
        """設置依賴元件 - 初始化增強版推送系統並啟動"""
        if self._running:
            # 已初始化過：僅重新註冊按鈕視圖（冪等）。cog_load 早於 on_ready 的
            # logging 設定，第一次執行的日誌會遺失，此處的日誌可見可驗證
            # 這是整個啟動流程中唯一「看得見」的快照（第一次呼叫的日誌在
            # on_ready 設定 logging 之前，必定遺失）。因此把各 loop 的存活
            # 狀態與 tick 計數一併印出：少了這行就分不出「沒啟動」與
            # 「啟動了但沒跑」——2026-09-28 曾在一個每週迴圈上白等兩輪
            logger.info(
                "[AnimeTracker.set_dependencies] 已運行中，跳過（僅重新註冊視圖）"
                f"｜loop: push={self.push_check_loop.is_running()}"
                f" schedule={self.weekly_schedule_refresh_loop.is_running()}"
                f" growth={self.daily_growth_loop.is_running()}"
                f"｜tick: push={self._push_tick}"
            )
            self._ensure_loops_alive()
            await self.reregister_push_views()
            return

        db_path = db_path or str(ANIME_PUSH_DB_PATH)
        logger.info(
            f"🔧 [AnimeTracker.set_dependencies] 初始化增強版推送系統: {db_path}"
        )

        # 初始化資料庫實例
        self.db = AnimePushDB(db_path)

        # 初始化增強版推送系統 (排程推送 + 15分鐘輪詢備案)
        self.polling_core = SimpleAnimePushCore(self.db)
        self.polling_core.set_bot(self.bot)

        # 啟動推送系統（2026-09-17 修復：改用 tasks.loop 每分鐘檢查。
        # 舊版 start_polling 用 asyncio.create_task 建立循環，task 異常會被困在
        # 無人讀取的 task 物件中（self._task 強引用阻擋 GC），「Task exception
        # was never retrieved」永不觸發 → 推送循環靜默死亡、44 小時零日誌零推送。
        # tasks.loop 每圈接例外、自癒，且錯誤會記入日誌）
        self.polling_core._running = True
        if not self.push_check_loop.is_running():
            self.push_check_loop.start()

        # 初始化週表排程管理器（每天 02:00 刷新 anime_push.db 的 anime_weekly_schedule）
        self.schedule_tracker = AnimeScheduleTracker(str(ANIME_PUSH_DB_PATH))
        self.schedule_tracker.set_dependencies(
            self.bot, self.db, self.polling_core, anime_tracker=self
        )

        # 啟動週表刷新循環（refresh_weekly_schedule 內建 02:00 時間閘門）
        if not self.weekly_schedule_refresh_loop.is_running():
            self.weekly_schedule_refresh_loop.start()

        # 啟動每日觀看數快照循環（內建每天 22:00 閘門 + DB 冪等，可安全重跑）
        if not self.daily_growth_loop.is_running():
            self.daily_growth_loop.start()

        self._running = True
        msg = "✅ [AnimeTracker.set_dependencies] 增強版推送系統啟動完成 (排程+輪詢備案+週表刷新)"
        logger.info(msg)

        # bot 重啟後重新註冊已推送訊息的按鈕視圖。discord.py 的視圖註冊是
        # in-memory 的，重啟後全部清空，而 AnimePushView 的 custom_id 依集數
        # 動態產生、無法在啟動時全域註冊；未重新註冊時，舊訊息的投票/留言
        # 按鈕點擊會被 dispatch_view 直接丟棄（Discord 顯示「應用程式沒有回應」）
        await self.reregister_push_views()

    async def reregister_push_views(self):
        """掃描推送頻道近期歷史，重建已推送訊息的按鈕視圖並依 message_id 綁定"""
        if not self.bot or not self.db:
            return
        # 延遲載入避免循環匯入（與 push_core_simple._check_and_push 相同模式）
        from shared.utils.embed_views import AnimePushView

        try:
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if channel is None:
                logger.warning(
                    f"⚠️ [AnimeTracker.reregister] 找不到推送頻道 {ANIME_CHANNEL_ID}"
                )
                return

            registered = 0
            seen: set[int] = set()
            async for message in channel.history(limit=300, oldest_first=False):
                if message.id in seen or not message.components:
                    continue
                # 從按鈕 custom_id 辨識動畫推送訊息並解析 video_sn
                video_sn = None
                for item in _iter_dispatchable_items(message.components):
                    cid = item.custom_id
                    if cid.startswith("anime_vote_"):
                        try:
                            video_sn = int(cid.rsplit("_", 1)[1])
                        except (ValueError, IndexError):
                            video_sn = None
                        break
                if video_sn is None:
                    continue
                seen.add(message.id)

                # AnimePushView 建構需要 videoSn 與 animeSn 同時存在
                info = self.db.get_notified_info(video_sn)
                if not info:
                    logger.warning(
                        f"⚠️ [AnimeTracker.reregister] videoSn={video_sn} "
                        f"不在 anime_notified，跳過"
                    )
                    continue
                anime_sn, anime_name = info
                episode = {
                    "videoSn": video_sn,
                    "animeSn": anime_sn,
                    "title": anime_name,
                }
                if message.flags.components_v2:
                    # V2 訊息的按鈕長在版面裡，只能用 LayoutView 家族重建
                    # （View.from_message 對 V2 會直接 raise ValueError）。
                    # bot.add_view 內部走 walk_children()，本來就會遞迴註冊巢狀
                    # 按鈕，所以這裡不必自己再拆到第三層。
                    from cogs.ui.push_embed_v2 import AnimePushLayout

                    view = AnimePushLayout(
                        episode,
                        push_mode=_push_mode_of_message(message),
                        db_adapter=self.db,
                        message_id=message.id,
                    )
                else:
                    view = AnimePushView(episode, db_adapter=self.db)
                    view.message_id = message.id  # 讓留言也能精確記錄到該則 embed
                self.bot.add_view(view, message_id=message.id)
                registered += 1

            logger.info(
                f"✅ [AnimeTracker.reregister] 已重新註冊 {registered} 則"
                f"動畫推送訊息的按鈕視圖"
            )
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.reregister] 失敗: {e}", exc_info=True)

    async def cog_load(self):
        """Cog 載入時執行的初始化"""
        self.logger.info("📺 [AnimeTracker.cog_load] 開始載入 Cog")

        # 如果依賴尚未設置，則自行初始化
        if not self._running:
            self.logger.info(
                "🔧 [AnimeTracker.cog_load] 依賴尚未設置，嘗試自行初始化..."
            )
            try:
                await self.set_dependencies(str(ANIME_PUSH_DB_PATH))
                self.logger.info("✅ [AnimeTracker.cog_load] 依賴自行初始化成功")
            except Exception as e:
                self.logger.error(
                    f"❌ [AnimeTracker.cog_load] 依賴自行初始化失敗: {e}", exc_info=True
                )
        else:
            self.logger.info(
                "🚀 [AnimeTracker.cog_load] AnimeTracker Cog 載入完成（依賴已就緒）"
            )

    async def cog_unload(self):
        """Cog 卸載時清理"""
        self.logger.info("🛑 [AnimeTracker.cog_unload] 正在停止推送系統...")
        if self.push_check_loop.is_running():
            self.push_check_loop.cancel()
        if self.weekly_schedule_refresh_loop.is_running():
            self.weekly_schedule_refresh_loop.cancel()
        if self.daily_growth_loop.is_running():
            self.daily_growth_loop.cancel()
        if self._running:
            if self.polling_core:
                await self.polling_core.stop_polling()
            self._running = False
        self.logger.info("🛑 [AnimeTracker.cog_unload] 推送系統已停止")

    # 受監督的 loop。push_check_loop 也在列：從 set_dependencies 呼叫時它若已死
    # 會被救回；從它自己內部呼叫時 is_running() 為 True，自動略過
    _SUPERVISED_LOOPS = (
        "push_check_loop",
        "weekly_schedule_refresh_loop",
        "daily_growth_loop",
    )

    def _ensure_loops_alive(self) -> None:
        """把意外死亡的背景 loop 重新啟動

        discord.py 的 Loop._loop 把 before_loop 放在 try 之外，一旦它拋例外，
        task 就帶例外結束且不留任何日誌（「Task exception was never retrieved」
        只在 GC 時才印）；而 set_dependencies 第二次呼叫在 `if self._running:`
        就 return，永遠不會補救 —— 該 loop 就此永久靜默。
        2026-09-28 曾有一個每週迴圈全程零日誌即屬此類，故用已證實存活的
        分鐘迴圈當監督者，任何死掉的 loop 一分鐘內復活。
        """
        for name in self._SUPERVISED_LOOPS:
            loop = getattr(self, name)
            if loop.is_running():
                continue
            self._loop_restarts[name] = self._loop_restarts.get(name, 0) + 1
            logger.warning(
                f"♻️ [supervisor] {name} 未運行，重新啟動"
                f"（第 {self._loop_restarts[name]} 次）"
            )
            try:
                loop.start()
            except Exception as e:
                logger.error(f"❌ [supervisor] {name} 重啟失敗: {e}", exc_info=True)

    @tasks.loop(minutes=1)
    async def push_check_loop(self):
        """每分鐘檢查排程推送（2026-09-17 修復：取代易無聲死亡的智能睡眠循環）

        tasks.loop 每圈接例外並繼續（自癒），不像 asyncio.create_task 的 task
        異常會被困在無人讀取的 task 物件中導致靜默死亡。
        """
        # 監督：每分鐘檢查所有背景 loop 是否存活。放在 polling_core 檢查之前，
        # 確保就算 polling_core 沒設好也照樣救得回其他 loop
        self._ensure_loops_alive()
        if not self.polling_core:
            return
        self._push_tick += 1
        try:
            # 排程推送：每分鐘檢查（_check_and_push 內建 ±1 分鐘容差與
            # is_notified 防重複，同一時刻只會推送一次）
            await self.polling_core._check_and_push(ANIME_CHANNEL_ID)
            # 備案安全網：每 15 分鐘輪詢 API 最新動畫
            # （排程表遺漏的新集數靠此補推，歷史上 51187 即由此路徑推出）
            if self._push_tick % 15 == 0:
                await self.polling_core._check_and_push_polling(ANIME_CHANNEL_ID)
            # 心跳：每小時一筆 INFO，證明循環存活
            # （2026-09-15~17 靜默失效 44 小時無從診斷的教訓）
            if self._push_tick % 60 == 0:
                logger.info(
                    f"💓 [push_check_loop] 循環存活心跳（第 {self._push_tick} 分鐘）"
                )
        except Exception as e:
            logger.error(f"❌ [push_check_loop] 檢查失敗: {e}", exc_info=True)

    @push_check_loop.before_loop
    async def before_push_check_loop(self):
        """等待 bot 就緒後再開始推送檢查循環"""
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=30)
    async def weekly_schedule_refresh_loop(self):
        """每天 02:00 時段刷新週表（refresh_weekly_schedule 內建時間閘門擋掉非 2 點時段）"""
        try:
            result = await self.schedule_tracker.refresh_weekly_schedule()
            if result.get("success"):
                self.logger.info(
                    f"✅ [weekly_schedule_refresh_loop] 週表刷新完成: {result.get('total_count')} 個時刻"
                )
        except Exception as e:
            self.logger.error(
                f"❌ [weekly_schedule_refresh_loop] 週表刷新失敗: {e}", exc_info=True
            )

    @weekly_schedule_refresh_loop.before_loop
    async def before_weekly_schedule_refresh_loop(self):
        """等待 bot 就緒後再開始刷新循環"""
        await self.bot.wait_until_ready()

    # ==================== 每週觀看數快照與成長推送 ====================

    @tasks.loop(minutes=30)
    async def daily_growth_loop(self):
        """每天 22:00 快照全番觀看數；週日快照完接著推送人氣榜

        一天一次、一次一支請求——index API 一次就回全部番（含每部累計
        popular），不必逐部打。popular 是累計值，任兩天相減就是那段區間的新增
        觀看數，所以每天存一格、要畫週增量時再跟 7 天前那格相減。

        閘門不寫死「必須剛好 22:00」，而是「已過今天 22:00 且今天還沒快照」就
        執行——bot 在觸發時刻重啟也不會漏掉那天。快照與推播共用同一個閘門：
        快照一存檔 has_view_snapshot 就為真，週日的推播因此同樣只會發生一次，
        不需要額外的「已推播」旗標。

        2026-11-02 由「每週日一次」改為「每天一次」：一週一點畫不出曲線，實測
        10 條線裡有 8 條只有 2 個資料點，那種線沒有「趨勢」可言。
        """
        if not self.db:
            return
        try:
            now = datetime.now(TW_TZ)
            if now.hour < GROWTH_SNAPSHOT_HOUR:
                return  # 今天觸發時刻還沒到

            today = now.date().isoformat()
            if self.db.has_view_snapshot(today):
                return  # 今天已快照（週日的推播也在那一次做完了）

            covers = await self._take_daily_snapshot(today)
            if not self.db.has_view_snapshot(today):
                return  # 快照沒成功（API 無資料），下輪重試

            if now.weekday() == GROWTH_SNAPSHOT_WEEKDAY:
                await self._push_growth_embed(today, covers)
        except Exception as e:
            logger.error(f"❌ [daily_growth_loop] 執行失敗: {e}", exc_info=True)

    @daily_growth_loop.before_loop
    async def before_daily_growth_loop(self):
        """等待 bot 就緒後再開始快照循環"""
        await self.bot.wait_until_ready()

    async def _fetch_anime_rows(self) -> tuple[list[dict], dict[int, str]]:
        """從 index API 取得「一部番一列」與封面表

        一支請求就回全部番，所以「取全部」與「取一部」的成本一樣。
        """
        episodes = await fetch_all_recent_anime_from_api()
        if not episodes:
            return [], {}

        # 一部番一列（API 兩個陣列已去重，仍防禦同 animeSn 多集，取觀看數高者）
        # 封面在此順手收進記憶體供卡片用——快照表沒存 cover，而這支 API 已經回傳了，
        # 沒有理由為了縮圖再打一次 API 或改 schema
        covers: dict[int, str] = {}
        anime_map: dict[int, dict] = {}
        for ep in episodes:
            sn = ep.get("animeSn")
            if not sn:
                continue
            if ep.get("cover"):
                covers[int(sn)] = str(ep["cover"])
            views = int(ep.get("popular") or 0)
            prev = anime_map.get(int(sn))
            if prev is not None and views <= prev["total_views"]:
                continue
            anime_map[int(sn)] = {
                "anime_sn": int(sn),
                "anime_name": str(ep.get("title") or f"Anime #{sn}"),
                "total_views": views,
                "volume_ep": _parse_volume_ep(ep.get("volume")),
            }

        rows = sorted(anime_map.values(), key=lambda r: r["total_views"], reverse=True)
        for idx, row in enumerate(rows, 1):
            row["rank"] = idx
        return rows, covers

    async def _take_daily_snapshot(self, snapshot_date: str) -> dict[int, str]:
        """對全番取一次觀看數快照，回傳封面表（供推播卡片縮圖用）

        一支 index API 請求就拿到全部番的累計觀看數，所以「每天全部番」的成本
        跟「每天一部」一樣。失敗時不寫任何東西，呼叫端會在下輪重試同一天。
        """
        rows, covers = await self._fetch_anime_rows()
        if not rows:
            logger.warning("⚠️ [daily_growth] API 無資料，本日快照略過（下輪重試）")
            return {}

        written = self.db.save_view_snapshot(snapshot_date, rows)
        logger.info(f"📸 [daily_growth] 快照完成 {snapshot_date}: {written} 筆")
        return covers

    async def _push_growth_embed(
        self, snapshot_date: str, covers: dict[int, str] = None
    ):
        """推送本週人氣榜：橫條圖 + 人氣走勢折線圖 + 持續在紅 + 本週衝最快

        2026-10-30 把 quickchart 折線圖換成橫條圖：Discord 圖片網址上限 2048
        字元，逼得舊圖把 Y 值除以千、拿掉軸標題與單位，反而更難讀。橫條圖把
        數字直接印在條尾，不必對圖例也不必看座標軸。

        2026-11-02 再把折線圖加回來，但這次是本機產圖、而且資料終於夠了：快照
        從「一週一格」改成「每天一格」之後，每個點都是真的量測值，不再是兩三點
        連成的直線。橫條圖回答「這週誰最熱」，折線圖回答「人氣有沒有維持、誰在
        退燒」——後者才是當初想問的問題。

        也放棄「有沒有新集」當篩選條件：本週 53/54 部都有新集，用它篩等於沒篩
        （只剩 1 部）。改看兩件事——連續進榜（誰一直紅）與成長率（誰在竄紅）。
        """
        covers = covers or {}
        prev_date = (
            date.fromisoformat(snapshot_date) - timedelta(days=GROWTH_WEEK_DAYS)
        ).isoformat()

        if not self.db.has_view_snapshot(prev_date):
            # 首次快照／歷史不足：只有基準，沒有可相減的前一週
            embed = discord.Embed(
                title="📈 本週動畫人氣 — 基準已建立",
                description=(
                    f"已於 **{snapshot_date}** 建立全番觀看數基準。\n"
                    f"下週日起將顯示每週人氣榜與成長名單"
                    f"（要有 **{prev_date}** 那天的快照才比得出來）。"
                ),
                color=discord.Color.blue(),
                timestamp=datetime.now(TW_TZ),
            )
            await self._send_growth_embed([embed])
            return

        # total_views <= 0 是 API 回傳異常（實測每週 1~6 筆），留著會變成負成長，
        # 也會讓下週把它當成「新上架」而在相減時爆出假數字
        growth = [
            g for g in self.db.get_weekly_growth(snapshot_date) if g["total_views"] > 0
        ]
        if not growth:
            logger.warning(f"⚠️ [daily_growth] {snapshot_date} 無可比對的成長資料")
            return

        bar = self._build_growth_bar_chart(growth[:GROWTH_BAR_N])

        embed = discord.Embed(
            title="📈 本週動畫人氣",
            description=(
                f"**{prev_date} → {snapshot_date}**\n"
                "數字＝這週被看的次數（全部集數加總）"
            ),
            color=discord.Color.gold(),
            timestamp=datetime.now(TW_TZ),
        )
        if bar:
            embed.set_image(url=f"attachment://{bar.filename}")

        trend_dates, trend = self._trend_series(snapshot_date)
        trend_chart = self._build_growth_line_chart(trend_dates, trend)

        # 「連續進榜」的單位是「週」，但快照是每天一格，直接丟進去會變成「連續
        # 進前 N 名幾天」，語意完全不同。先抽成每週一格再算。
        streaks = self._growth_streaks(
            self._weekly_spaced(
                self.db.get_snapshot_dates(limit=GROWTH_TREND_DAYS), GROWTH_HISTORY_WEEKS
            )
        )
        hot = sorted(
            (
                (streaks.get(g["anime_sn"], 0), g)
                for g in growth[:GROWTH_TOP_N]
                if streaks.get(g["anime_sn"], 0) >= GROWTH_STREAK_MIN
            ),
            key=lambda t: (-t[0], -t[1]["growth"]),
        )
        if hot:
            embed.add_field(
                name="🔥 持續在紅",
                value="\n".join(
                    f"**{self._short(g['anime_name'], 18)}**"
                    f"　連 {n} 週進前 {GROWTH_TOP_N} 名"
                    for n, g in hot[:GROWTH_STREAK_FIELD_N]
                ),
                inline=False,
            )
        embed.set_footer(
            text=(
                "每天 22:00 自動快照、週日推播"
                f" | 連 N 週＝連續進本週新增前 {GROWTH_TOP_N} 名"
            )
        )

        embeds = [embed]
        if trend_chart:
            embeds.append(
                discord.Embed(
                    title="📉 人氣走勢",
                    description=(
                        f"最近 {GROWTH_TREND_N} 部的**每週新增觀看數**逐日變化。\n"
                        "往下走＝退燒／有人在棄坑，持平或往上＝人氣還撐著"
                    ),
                    color=discord.Color.dark_teal(),
                ).set_image(url=f"attachment://{trend_chart.filename}")
            )

        risers = self._pick_risers(growth)
        if risers:
            embeds.append(
                discord.Embed(
                    title="🚀 本週衝最快",
                    description=(
                        "跟**自己的上週**比，漲幅最大的幾部。\n"
                        "看比例而不是看量——比量永遠是大番贏"
                    ),
                    color=discord.Color.blurple(),
                )
            )
            embeds.extend(self._build_mover_embed(r, covers) for r in risers)
        await self._send_growth_embed(embeds, files=[bar, trend_chart])

    @staticmethod
    def _pick_risers(growth: list[dict]) -> list[dict]:
        """挑出週成長率最高的幾部（本週衝最快）

        用成長率而非成長量：成長量永遠由大番霸榜，看不出「誰在加速」。改用
        累計名次變動也不行——popular 是累計值只增不減，名次天生黏著，實測單週
        只有 ±2 名的雜訊。成長率才是 2 週資料就能算出的竄紅訊號。
        """
        cand = [
            g
            for g in growth
            # rank 為 NULL 時不能直接比大小；給一個排不進去的值而非讓排程爆掉
            if (g["rank"] or 10**9) <= GROWTH_MOVER_RANK_LIMIT and g["prev_views"]
        ]
        cand.sort(key=lambda g: g["growth"] / g["prev_views"], reverse=True)
        return cand[:GROWTH_MOVER_N]

    def _build_mover_embed(self, item: dict, covers: dict[int, str]) -> discord.Embed:
        """單一「衝最快」卡片：標題即漲幅，另附絕對量與名次供對照"""
        pct = item["growth"] / item["prev_views"] * 100
        name = item["anime_name"]
        if len(name) > 30:
            name = name[:30] + "…"
        embed = discord.Embed(
            title=f"🚀 +{pct:.1f}%　{name}",
            color=discord.Color.green(),
        )
        cover = covers.get(item["anime_sn"])
        if cover:
            embed.set_thumbnail(url=cover)
        embed.add_field(name="這週被看", value=f"+{item['growth']:,}", inline=True)
        embed.add_field(name="總觀看數", value=f"{item['total_views']:,}", inline=True)
        embed.add_field(name="人氣排名", value=f"#{item['rank']}", inline=True)
        return embed

    async def _send_growth_embed(
        self, embeds: list[discord.Embed], files: Optional[list[discord.File]] = None
    ):
        """送往動畫推送頻道（Discord 一則訊息上限 10 個 embed）

        files 收清單而非單一檔案：人氣榜同時帶橫條圖與走勢折線圖。產圖失敗時
        傳進來的是 None，這裡先濾掉，免得整則推播被一個空附件拖垮。
        """
        channel = self.bot.get_channel(ANIME_CHANNEL_ID)
        if channel is None:
            logger.warning(f"⚠️ [daily_growth] 找不到頻道 {ANIME_CHANNEL_ID}")
            return
        try:
            files = [f for f in (files or []) if f is not None]
            if files:
                await channel.send(embeds=embeds, files=files)
            else:
                await channel.send(embeds=embeds)
            logger.info(
                f"✅ [daily_growth] 人氣榜已推送"
                f"（{len(embeds)} 個 embed，圖 {len(files)} 張）"
            )
        except Exception as e:
            logger.error(f"❌ [daily_growth] 推送失敗: {e}", exc_info=True)

    @staticmethod
    def _short(name: str, limit: int = 20) -> str:
        """截短番名：Discord 一行放不下完整番名（多數超過 20 字）"""
        name = (name or "").strip()
        return name if len(name) <= limit else name[:limit] + "…"

    @staticmethod
    def _format_views(v: int) -> str:
        """大數字換成「萬」：六位數在手機上讀不出量級（190,220 vs 19.0萬）"""
        if abs(v) >= 10000:
            return f"+{v / 10000:.1f}萬"
        return f"+{v:,}"

    @staticmethod
    def _weekly_spaced(dates_new_to_old: list[str], limit: int) -> list[str]:
        """從每日快照日期裡挑出彼此間隔 7 天的那些，最多 limit 個

        以最新一天為錨往回每 7 天取一點。推播固定在週日，最新一天就是週日，
        所以取出來的剛好是每週推播的那幾天——「連續進榜」的週次因此對得上使用者
        實際看到的那幾則推播，而不是隨便挑的日子。
        """
        if not dates_new_to_old:
            return []
        anchor = date.fromisoformat(dates_new_to_old[0])
        return [
            d
            for d in dates_new_to_old
            if (anchor - date.fromisoformat(d)).days % GROWTH_WEEK_DAYS == 0
        ][:limit]

    def _trend_series(self, snapshot_date: str) -> tuple[list[str], list[dict]]:
        """折線圖的資料：最近 GROWTH_TREND_N 部的逐日週增量

        回傳（日期軸, 每部的點）。點為 None 代表那天算不出來（缺 7 天前那一筆
        快照），matplotlib 會當成缺漏值把線斷開，不會拉一條假線過去。

        挑「最新一天週增量最大的前 N 部」，而不是整段區間累計最大的——後者永遠
        被已經紅很久的番佔滿，看不出最近誰在退燒、誰在往上爬。
        """
        since = (
            date.fromisoformat(snapshot_date) - timedelta(days=GROWTH_TREND_DAYS)
        ).isoformat()
        rows = self.db.get_rolling_weekly_growth(since)
        if not rows:
            return [], []

        latest = max(r["snapshot_date"] for r in rows)
        keep = [
            r["anime_sn"]
            for r in sorted(
                (r for r in rows if r["snapshot_date"] == latest),
                key=lambda r: -r["growth"],
            )[:GROWTH_TREND_N]
        ]
        names = {r["anime_sn"]: r["anime_name"] for r in rows}
        dates = sorted({r["snapshot_date"] for r in rows})

        points: dict[int, dict[str, int]] = {}
        for r in rows:
            if r["anime_sn"] in keep:
                points.setdefault(r["anime_sn"], {})[r["snapshot_date"]] = r["growth"]

        return dates, [
            {
                "anime_sn": sn,
                "anime_name": names.get(sn, f"Anime #{sn}"),
                "points": [points.get(sn, {}).get(d) for d in dates],
            }
            for sn in keep
        ]

    def _growth_streaks(self, dates_new_to_old: list[str]) -> dict[int, int]:
        """每部番「連續幾週進本週新增前 GROWTH_TOP_N 名」

        這是「哪個有持續在成長」唯一站得住的定義：連續正成長沒區分度（實測
        52/54 部符合），有沒有新集也沒區分度（53/54 部都有），只有「一直待在前
        段班」能把長紅的番挑出來（實測 7 部）。

        傳進來的日期必須是「每週一格」（見 _weekly_spaced）：快照雖然是每天一
        格，這裡的單位卻是週，餵每日資料會變成「連續進榜幾天」。
        """
        snaps = self.db.get_snapshots_range(dates_new_to_old)
        ordered = list(reversed(dates_new_to_old))  # 舊 → 新
        by_week: dict[str, dict[int, int]] = {}
        for s in snaps:
            by_week.setdefault(s["snapshot_date"], {})[s["anime_sn"]] = s["total_views"]

        # 逐週排出「本週新增」名次。前值為 0（當週才上架）或當週為 0（API 異常）
        # 都不列入該週比較，否則相減出來的是上架至今累計而非單週新增
        ranks: list[dict[int, int]] = []
        for i in range(1, len(ordered)):
            cur = by_week.get(ordered[i], {})
            prev = by_week.get(ordered[i - 1], {})
            rows = [
                (views - prev[sn], sn)
                for sn, views in cur.items()
                if views > 0 and prev.get(sn)
            ]
            rows.sort(reverse=True)
            ranks.append({sn: rk for rk, (_, sn) in enumerate(rows, 1)})

        # 從最新往回數，斷了就停——只算「一直到本週都還在前段班」的
        streaks: dict[int, int] = {}
        for sn in by_week.get(ordered[-1], {}):
            n = 0
            for rk in reversed(ranks):
                if rk.get(sn, 0) and rk[sn] <= GROWTH_TOP_N:
                    n += 1
                else:
                    break
            if n:
                streaks[sn] = n
        return streaks

    def _build_growth_bar_chart(self, rows: list[dict]) -> Optional[discord.File]:
        """本週最熱橫條圖（matplotlib 本機產 PNG，附加為檔案）

        2026-10-30 換掉 quickchart URL：Discord 圖片網址上限 2048 字元，逼得舊圖
        把 Y 值除以千、拿掉軸標題與單位，圖因此更難讀。本機產圖沒有長度限制，
        數字可以直接印在條尾，資料也不必傳給第三方服務。
        """
        if not rows:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            from matplotlib import font_manager
            from matplotlib import pyplot as plt
        except Exception as e:  # 缺套件時退化成純文字推送，別讓整則推播消失
            logger.warning(f"⚠️ [weekly_growth] matplotlib 不可用，改為純文字：{e}")
            return None

        font = None
        if _CJK_FONT_PATH.exists():
            font = font_manager.FontProperties(fname=str(_CJK_FONT_PATH))
        else:
            logger.warning(f"⚠️ [weekly_growth] 找不到字型 {_CJK_FONT_PATH}，中文恐變方框")

        # 尺寸是照 Discord 的顯示規則反推的：embed 圖最大 550×400，縮放後的字級
        # ≈ 7.6 × fontsize ÷ 圖寬(inch)。圖做寬一點字就變小——9.6 吋寬時只剩 9px，
        # 手機上讀不出來，所以刻意收窄到 6.9 吋（約 13px）並放大字級。
        # 高度取 0.5/列使長寬比 ≥1.375（＝550/400），才不會被高度綁住再縮一次。
        labels = [self._short(r["anime_name"], 16) for r in rows]
        values = [r["growth"] for r in rows]
        fig, ax = plt.subplots(figsize=(6.9, 0.5 * len(rows) + 1.0), dpi=160)
        fig.patch.set_facecolor(_CHART_BG_HEX)
        ax.set_facecolor(_CHART_BG_HEX)
        buf = io.BytesIO()
        try:
            # 由上而下＝由多到少：barh 的 y 軸原點在下方，故把 y 反過來
            y = list(range(len(rows)))[::-1]
            ax.barh(y, values, height=0.72, color=_CHART_BAR_HEX, zorder=3)
            ax.set_yticks(y)
            ax.set_yticklabels(
                labels, fontproperties=font, color=_CHART_TEXT_HEX, fontsize=12
            )
            ax.set_xticks([])
            ax.tick_params(axis="y", length=0)
            for spine in ax.spines.values():
                spine.set_visible(False)
            # 右邊留 16% 給條尾數字，否則最長那條的數字會被裁掉
            ax.margins(x=0.16)
            top = max(values) or 1
            for yi, v in zip(y, values):
                ax.text(
                    v + top * 0.015,
                    yi,
                    self._format_views(v),
                    va="center",
                    ha="left",
                    color=_CHART_TEXT_HEX,
                    fontsize=12.5,
                    fontweight="bold",
                    fontproperties=font,
                )
            fig.savefig(
                buf,
                format="png",
                facecolor=fig.get_facecolor(),
                bbox_inches="tight",
                pad_inches=0.18,
            )
        except Exception as e:  # 產圖失敗不該讓整則推播消失
            logger.error(f"❌ [weekly_growth] 產圖失敗，改為純文字: {e}", exc_info=True)
            return None
        finally:
            plt.close(fig)

        buf.seek(0)
        return discord.File(buf, filename="weekly_growth.png")

    def _build_growth_line_chart(
        self, dates: list[str], series: list[dict]
    ) -> Optional[discord.File]:
        """人氣走勢折線圖（matplotlib 本機產 PNG，附加為檔案）

        6 條線是上限而不是隨手訂的：折線不像橫條圖有長度當第二編碼，全靠顏色
        認人，所以色票只用 dataviz 深色盤裡彼此分得開的 6 槽（已用
        validate_palette.py 對底色 #2b2d31 驗過全數 PASS）。線再多就會開始撞色。
        """
        if not dates or not series:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            from matplotlib import font_manager
            from matplotlib import pyplot as plt
        except Exception as e:  # 缺套件時退化成沒有這張圖，別讓整則推播消失
            logger.warning(f"⚠️ [daily_growth] matplotlib 不可用，略過折線圖：{e}")
            return None

        font = None
        if _CJK_FONT_PATH.exists():
            font = font_manager.FontProperties(fname=str(_CJK_FONT_PATH))
        else:
            logger.warning(f"⚠️ [daily_growth] 找不到字型 {_CJK_FONT_PATH}，中文恐變方框")

        # 長寬比 ≥1.375（＝Discord embed 圖上限 550×400）才不會先被高度綁住再縮一次
        fig, ax = plt.subplots(figsize=(6.9, 4.6), dpi=160)
        fig.patch.set_facecolor(_CHART_BG_HEX)
        ax.set_facecolor(_CHART_BG_HEX)
        buf = io.BytesIO()
        try:
            xi = list(range(len(dates)))
            for i, s in enumerate(series):
                ax.plot(
                    xi,
                    s["points"],
                    color=_CHART_SERIES_HEX[i % len(_CHART_SERIES_HEX)],
                    linewidth=2,
                    zorder=3,
                    label=self._short(s["anime_name"], 12),
                )

            # 點太密就不標日期，否則刻度會疊成一團
            step = max(1, len(dates) // 10)
            ax.set_xticks(xi[::step])
            ax.set_xticklabels([dates[i][5:].replace("-", "/") for i in xi[::step]])
            ax.grid(axis="y", color=_CHART_GRID_HEX, linewidth=0.8, zorder=0)
            ax.set_axisbelow(True)
            for sp in ("top", "right", "left"):
                ax.spines[sp].set_visible(False)
            ax.spines["bottom"].set_color("#383835")
            ax.tick_params(colors=_CHART_MUTED_HEX, length=0, labelsize=9)
            for label in ax.get_xticklabels() + ax.get_yticklabels():
                label.set_fontproperties(font)
            ax.yaxis.set_major_formatter(
                lambda v, _p: f"{v / 10000:.0f}萬" if abs(v) >= 10000 else f"{v:,.0f}"
            )

            legend = ax.legend(
                loc="upper center",
                bbox_to_anchor=(0.5, -0.12),
                ncol=2,
                frameon=False,
                fontsize=9,
                handlelength=1.6,
                columnspacing=1.2,
                labelspacing=0.35,
            )
            for t in legend.get_texts():
                t.set_color(_CHART_TEXT_HEX)
                t.set_fontproperties(font)

            fig.savefig(
                buf,
                format="png",
                facecolor=fig.get_facecolor(),
                bbox_inches="tight",
                pad_inches=0.2,
            )
        except Exception as e:  # 產圖失敗不該讓整則推播消失
            logger.error(f"❌ [daily_growth] 折線圖產圖失敗: {e}", exc_info=True)
            return None
        finally:
            plt.close(fig)

        buf.seek(0)
        return discord.File(buf, filename="anime_trend.png")

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot 就緒事件"""
        self.logger.info(
            "📺 [AnimeTracker.on_ready] AnimeTracker Cog 收到 on_ready 事件"
        )

    # ==================== 指令方法 ====================

    @commands.hybrid_command(name="anime_status", description="查看動畫推送系統狀態")
    @commands.has_permissions(administrator=True)
    async def anime_status(self, ctx: commands.Context):
        """查看動畫推送系統狀態"""
        # hybrid 指令統一走 ctx.defer：slash 會 defer interaction、prefix 呼叫是
        # no-op。舊寫法 hasattr(ctx, "response") 恆為 False（Context 沒這屬性）→
        # 從不 defer → slash 呼叫只要超過 3 秒就跳「應用程式沒有回應」。
        await ctx.defer(ephemeral=True)
        send_response = lambda content, ephemeral=True: ctx.send(
            content, ephemeral=ephemeral
        )

        try:
            status_lines = [
                "📊 **動畫推送系統狀態 (增強版)**",
                f"🔄 總系統狀態: {'✅ 運行中' if self._running else '❌ 已停止'}",
                f"📊 資料庫: anime_push.db",
            ]

            # 推送系統狀態 (現在是增強版：排程推送 + 15分鐘輪詢備案)
            if self.polling_core:
                polling_running = getattr(self.polling_core, "_running", False)
                in_fallback = getattr(self.polling_core, "_in_fallback", False)
                fail_count = getattr(self.polling_core, "_fail_count", 0)
                max_failures = getattr(self.polling_core, "_max_failures", 3)

                if in_fallback:
                    status_lines.append(
                        f"⏰ 推送系統: {'✅ 運行中' if polling_running else '❌ 已停止'} (備案模式: 15分鐘輪詢)"
                    )
                    status_lines.append(f"📉 失敗計數: {fail_count}/{max_failures}")
                else:
                    status_lines.append(
                        f"⏰ 推送系統: {'✅ 運行中' if polling_running else '❌ 已停止'} (排程模式)"
                    )
                    status_lines.append(f"📊 失敗計數: {fail_count}/{max_failures}")

                if polling_running and self.db:
                    try:
                        # 顯示今日待推送數量
                        today_schedule = self.db.get_today_schedule()
                        pending_count = sum(
                            1
                            for item in today_schedule
                            if not item.get("pushed", False)
                        )
                        status_lines.append(f"📋 推程今日待推送: {pending_count} 項")

                        # 顯示已通知的動畫數
                        notified_count = (
                            len(self.db.get_notified_video_sns())
                            if hasattr(self.db, "get_notified_video_sns")
                            else 0
                        )
                        status_lines.append(f"📼 已通知動畫數: {notified_count}")
                    except Exception as e:
                        self.logger.warning(f"無法獲取推送統計: {e}")

            status_lines.extend(
                [
                    f"📋 推送表: anime_weekly_schedule",
                    f"📝 通知記錄: anime_notified 表",
                    f"⏱️ 排程機制: tasks.loop 每分鐘檢查 (±1分鐘容差)",
                    f"⏱️ 備案機制: 每15分鐘輪詢 API 補推排程遺漏的新集數",
                ]
            )

            await send_response("\n".join(status_lines), ephemeral=True)
        except Exception as e:
            self.logger.error(
                f"❌ [AnimeTracker.anime_status] 查詢狀態失敗: {e}", exc_info=True
            )
            await send_response(f"❌ 查詢狀態時發生錯誤: {str(e)}", ephemeral=True)

    @commands.hybrid_command(
        name="anime_manual_check", description="手動觸發一次動畫檢查"
    )
    @commands.has_permissions(administrator=True)
    async def anime_manual_check(self, ctx: commands.Context):
        """手動觸發一次動畫檢查與推送"""
        # hybrid 指令統一走 ctx.defer：slash 會 defer interaction、prefix 呼叫是
        # no-op。舊寫法 hasattr(ctx, "response") 恆為 False（Context 沒這屬性）→
        # 從不 defer → slash 呼叫只要超過 3 秒就跳「應用程式沒有回應」。
        await ctx.defer(ephemeral=True)
        send_response = lambda content, ephemeral=True: ctx.send(
            content, ephemeral=ephemeral
        )

        try:
            self.logger.info(
                f"🔄 [AnimeTracker.anime_manual_check] 手動檢查請求 by {ctx.author}"
            )

            if not self.polling_core:
                await send_response("❌ 推送核心未完全初始化", ephemeral=True)
                return

            # 手動觸發增強版推送系統的檢查 (包含排程推送和輪詢備案)
            await send_response("🔄 正在手動檢查增強版推送系統...", ephemeral=True)
            await self.polling_core._check_and_push(ANIME_CHANNEL_ID)

            await send_response("✅ 手動檢查完成", ephemeral=True)
        except Exception as e:
            self.logger.error(
                f"❌ [AnimeTracker.anime_manual_check] 手動檢查失敗: {e}", exc_info=True
            )
            await send_response(f"❌ 手動檢查失敗: {str(e)}", ephemeral=True)

    @commands.hybrid_command(
        name="anime_v2_test",
        description="發一張 Components V2 測試卡到測試頻道（可帶 video_sn）",
    )
    @commands.has_permissions(administrator=True)
    async def anime_v2_test(self, ctx: commands.Context, video_sn: int = 0):
        """用 bot 本尊發一張 V2 卡，按鈕才會真的接上視圖。

        REST 直發的卡片沒經過 bot 程序，視圖不會被註冊，按鈕按了沒反應；
        這支走 channel.send(view=layout)，discord.py 當場註冊，可實測點擊。
        episode 組法照抄輪詢路徑（index API 打底、detail API 補簡介封面），
        確保測試卡跟生產推送吃同一種資料形狀。
        """
        # hybrid 指令統一走 ctx.defer：slash 會 defer interaction、prefix 呼叫是
        # no-op。舊寫法 hasattr(ctx, "response") 恆為 False（Context 沒這屬性）→
        # 從不 defer → slash 呼叫只要超過 3 秒就跳「應用程式沒有回應」。
        await ctx.defer(ephemeral=True)
        send_response = lambda content, ephemeral=True: ctx.send(
            content, ephemeral=ephemeral
        )

        try:
            from cogs.ui.push_core_simple import (
                fetch_all_recent_anime_from_api,
                fetch_anime_details_from_api,
            )
            from cogs.ui.push_embed_v2 import generate_anime_layout

            channel = self.bot.get_channel(ANIME_V2_TEST_CHANNEL_ID)
            # 1504438347974705152 是論壇頻道本身（ForumChannel），不是 thread ——
            # ForumChannel 沒有 .send()，得用 create_thread 開新討論串放測試卡
            if channel is None or not hasattr(channel, "create_thread"):
                await send_response(
                    "❌ 找不到 V2 測試頻道（或不是論壇頻道）", ephemeral=True
                )
                return

            eps = await fetch_all_recent_anime_from_api() or []
            if video_sn:
                ep = next(
                    (e for e in eps if int(e.get("videoSn") or 0) == video_sn), None
                )
            else:
                ep = next((e for e in eps if e.get("videoSn")), None)
                video_sn = int(ep.get("videoSn")) if ep else 0
            if ep is None:
                if not video_sn:
                    await send_response("❌ API 抓不到動畫資料", ephemeral=True)
                    return
                ep = {"videoSn": video_sn}

            # 詳細資訊合併 —— 與輪詢路徑同一套 key 對應；season_views 先 capture，
            # 因為合併會把 index 的當季總數覆蓋成 detail 的本集數
            season_views = int(ep.get("popular") or 0)
            try:
                details = await fetch_anime_details_from_api(video_sn)
                if details:
                    ep = {
                        **ep,
                        "animeSn": ep.get("animeSn") or details.get("anime_sn", 0),
                        "title": details.get("title") or ep.get("title", ""),
                        "description": details.get("content", ""),
                        "cover": details.get("cover", ""),
                        "total_views": season_views,
                        "episode_count": int(details.get("episode_count") or 0),
                        "popular": details.get("popular", 0),
                        "score": details.get("score", 0),
                    }
            except Exception as e:
                self.logger.debug(f"取得動畫詳細資訊失敗 videoSn={video_sn}: {e}")

            db = self.polling_core.db if self.polling_core else None
            layout = await generate_anime_layout(ep, push_mode="排程推送", db=db)
            if layout is None:
                await send_response("❌ V2 版面生成失敗", ephemeral=True)
                return

            fallback_name = f"videoSn {video_sn}"
            thread_name = f"V2 測試卡：{ep.get('title') or fallback_name}"[:100]
            _thread, message = await channel.create_thread(
                name=thread_name, view=layout, silent=True
            )
            layout.message_id = message.id
            self.bot.add_view(layout, message_id=message.id)
            self.logger.info(
                f"✅ [AnimeTracker.anime_v2_test] 已發 V2 測試卡 videoSn={video_sn}"
            )
            await send_response(f"✅ 已發 V2 測試卡：{message.jump_url}", ephemeral=True)
        except Exception as e:
            self.logger.error(
                f"❌ [AnimeTracker.anime_v2_test] 發送失敗: {e}", exc_info=True
            )
            await send_response(f"❌ 發送失敗: {str(e)}", ephemeral=True)


async def setup(bot):
    """設置 Cog 的入口點"""
    await bot.add_cog(AnimeTracker(bot))
