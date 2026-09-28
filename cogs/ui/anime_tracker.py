# -*- coding: utf-8 -*-
"""
Bahamut 動畫追蹤 Cog - 增強版排程推送系統
- 增強版推送系統：使用 SimpleAnimePushCore (push_core_simple.py) 基於 anime_push.db
  實現精準排程推送與15分鐘輪詢備案機制
- 排程推送：基於 anime_weekly_schedule 表在實際播出時間精確推送
- 備案機制：連續3次失敗後自動切換至15分鐘輪詢，恢復條件為成功推送
- 單一資料庫連線：各組件共用同一 anime_push.db 連線
"""

import logging
import json
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo
import asyncio
import aiohttp
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
    fetch_anime_episodes_with_views,
    EPISODE_SNAPSHOT_CONCURRENCY,
    EPISODE_SNAPSHOT_MAX_ATTEMPTS,
)
from cogs.ui.schedule_tracker import AnimeScheduleTracker

logger = logging.getLogger(__name__)

# 每週成長快照設定
GROWTH_SNAPSHOT_WEEKDAY = 6  # 0=週一 ... 6=週日
GROWTH_SNAPSHOT_HOUR = 22  # 週日 22:00（避開 02:00 週表刷新與 API 尖峰）
GROWTH_CHART_WEEKS = 12  # 折線圖回溯週數
GROWTH_TOP_N = 10  # 成長排行取前 N 名
GROWTH_MOVER_N = 3  # 黑馬卡片取前 N 名
# 只取累計排名前 N 名：擋掉小基數造成的假高成長率（基數 1,000 漲到 2,000 就是
# +100%，但那沒有意義），同時後段番本來就不是使用者關心的範圍
GROWTH_MOVER_RANK_LIMIT = GROWTH_TOP_N * 3
QUICKCHART_URL_LIMIT = 2048  # Discord embed 圖片 URL 上限
GROWTH_VIEW_UNIT = 1000  # 折線圖 Y 值除以一千（成長值動輒 6 位數，不縮放塞不進 URL）
_CHART_COLORS = [
    "#FFD700",
    "#FF6384",
    "#36A2EB",
    "#4BC0C0",
    "#9966FF",
    "#FF9F40",
    "#8BC34A",
    "#E91E63",
    "#00BCD4",
    "#795548",
]

# 深色主題：對齊 Discord 預設深色主題的 embed 底色 #2b2d31（# 在 query 中須編碼）
_CHART_BG = "%232b2d31"
# Chart.js v3 起 options.color 是全域文字色，一個鍵就覆蓋圖例與兩軸刻度；
# v2 得逐軸寫 fontColor（且 scales 是陣列），成本高到塞不進 2048 字元。
# 格線預設是 rgba(0,0,0,.1)，在深底上等於消失，故補上微亮格線。
_DARK_CHART_OPTIONS = {
    "color": "#dddddd",
    "scales": {
        "x": {"grid": {"color": "#3a3d42"}},
        "y": {"grid": {"color": "#3a3d42"}},
    },
}


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
        self._episode_tick = 0
        # 單集快照的重試計數：week_start → 已嘗試次數。整批失敗時靠它避免
        # 每 30 分鐘無限重打；成功寫入後即清除
        self._episode_attempts: dict[str, int] = {}

    async def set_dependencies(self, db_path: str = None):
        """設置依賴元件 - 初始化增強版推送系統並啟動"""
        if self._running:
            # 已初始化過：僅重新註冊按鈕視圖（冪等）。cog_load 早於 on_ready 的
            # logging 設定，第一次執行的日誌會遺失，此處的日誌可見可驗證
            logger.info(
                "[AnimeTracker.set_dependencies] 已運行中，跳過（僅重新註冊視圖）"
            )
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

        # 啟動每週觀看數快照循環（內建週日 22:00 閘門 + DB 冪等，可安全重跑）
        if not self.weekly_growth_loop.is_running():
            self.weekly_growth_loop.start()

        # 啟動單集快照循環（與上面同一時點，但獨立重試，避免整批失敗就永久遺失該週）
        if not self.episode_snapshot_loop.is_running():
            self.episode_snapshot_loop.start()

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
                for row in message.components:
                    for child in row.children:
                        cid = getattr(child, "custom_id", None)
                        if cid and cid.startswith("anime_vote_"):
                            try:
                                video_sn = int(cid.rsplit("_", 1)[1])
                            except (ValueError, IndexError):
                                video_sn = None
                            break
                    if video_sn is not None:
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
                view = AnimePushView(
                    {"videoSn": video_sn, "animeSn": anime_sn, "title": anime_name},
                    db_adapter=self.db,
                )
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
        if self.weekly_growth_loop.is_running():
            self.weekly_growth_loop.cancel()
        if self.episode_snapshot_loop.is_running():
            self.episode_snapshot_loop.cancel()
        if self._running:
            if self.polling_core:
                await self.polling_core.stop_polling()
            self._running = False
        self.logger.info("🛑 [AnimeTracker.cog_unload] 推送系統已停止")

    @tasks.loop(minutes=1)
    async def push_check_loop(self):
        """每分鐘檢查排程推送（2026-09-17 修復：取代易無聲死亡的智能睡眠循環）

        tasks.loop 每圈接例外並繼續（自癒），不像 asyncio.create_task 的 task
        異常會被困在無人讀取的 task 物件中導致靜默死亡。
        """
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
    async def weekly_growth_loop(self):
        """每週日 22:00 快照全番觀看數，並推送成長折線圖

        閘門不寫死「必須剛好 22:00」，而是「已過本週的週日 22:00 且本週尚未
        快照」就執行——bot 在觸發時刻重啟也不會漏掉該週，且 has_view_snapshot
        保證重跑不產生重複快照。
        """
        if not self.db:
            return
        try:
            now = datetime.now(TW_TZ)
            days_since_sunday = (now.weekday() + 1) % 7
            sunday = (now - timedelta(days=days_since_sunday)).replace(
                hour=GROWTH_SNAPSHOT_HOUR, minute=0, second=0, microsecond=0
            )
            if now < sunday:
                return  # 本週觸發時刻還沒到

            week_start = (sunday - timedelta(days=6)).date().isoformat()
            if self.db.has_view_snapshot(week_start):
                return  # 本週已快照

            await self._run_weekly_growth(week_start)
        except Exception as e:
            logger.error(f"❌ [weekly_growth_loop] 執行失敗: {e}", exc_info=True)

    @weekly_growth_loop.before_loop
    async def before_weekly_growth_loop(self):
        """等待 bot 就緒後再開始快照循環"""
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=30)
    async def episode_snapshot_loop(self):
        """每週單集觀看數快照（與週成長快照同時點，但獨立重試）

        獨立成一個 loop 而非掛在 _run_weekly_growth 之後：系列快照一存檔，
        weekly_growth_loop 的閘門就會擋掉後續執行，若單集抓取整批失敗，那一週
        就永久遺失（巴哈 API 不提供歷史，補不回來）。這裡只認 has_episode_snapshot，
        整批失敗時下一輪（30 分鐘後）自動重試。
        """
        if not self.db:
            logger.warning("⚠️ [episode_snapshot] db 未初始化，略過本輪")
            return
        try:
            self._episode_tick += 1
            # 心跳：重啟後第一輪就印，之後每天一筆。這個 loop 曾整批靜默失敗卻
            # 不留痕跡，沒有心跳就分不出「迴圈已死」與「閘門沒過」
            if self._episode_tick == 1 or self._episode_tick % 48 == 0:
                logger.info(
                    f"💓 [episode_snapshot] 循環存活心跳（第 {self._episode_tick} 輪）"
                )
            now = datetime.now(TW_TZ)
            days_since_sunday = (now.weekday() + 1) % 7
            sunday = (now - timedelta(days=days_since_sunday)).replace(
                hour=GROWTH_SNAPSHOT_HOUR, minute=0, second=0, microsecond=0
            )
            if now < sunday:
                logger.debug(f"⏳ [episode_snapshot] 本週觸發時刻未到（{sunday}）")
                return  # 本週觸發時刻還沒到

            week_start = (sunday - timedelta(days=6)).date().isoformat()
            if self.db.has_episode_snapshot(week_start):
                logger.debug(f"✅ [episode_snapshot] {week_start} 已有快照，略過")
                return  # 本週已完整快照

            logger.info(f"🚀 [episode_snapshot] 開始抓取 {week_start} 的單集觀看數")
            await self._run_episode_snapshot(week_start)
        except Exception as e:
            logger.error(f"❌ [episode_snapshot_loop] 執行失敗: {e}", exc_info=True)

    @episode_snapshot_loop.before_loop
    async def before_episode_snapshot_loop(self):
        """等待 bot 就緒後再開始快照循環"""
        await self.bot.wait_until_ready()

    async def _fetch_anime_rows(self) -> tuple[list[dict], dict[int, str]]:
        """從 index API 取得「一部番一列」與封面表

        系列快照與單集快照都需要這份清單（單集快照要的是每部的最新集 videoSn），
        故抽成共用方法讓兩個 loop 各自取用。
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
                # 最新一集的 videoSn：單集快照的入口（該支 API 會一併回傳集數清單）
                "video_sn": int(ep["videoSn"]) if ep.get("videoSn") else None,
            }

        rows = sorted(anime_map.values(), key=lambda r: r["total_views"], reverse=True)
        for idx, row in enumerate(rows, 1):
            row["rank"] = idx
        return rows, covers

    async def _run_weekly_growth(self, week_start: str):
        """對全番取一次觀看數快照，接著推送成長圖"""
        rows, covers = await self._fetch_anime_rows()
        if not rows:
            logger.warning("⚠️ [weekly_growth] API 無資料，本週快照略過")
            return

        written = self.db.save_view_snapshot(week_start, rows)
        logger.info(f"📸 [weekly_growth] 快照完成 {week_start}: {written} 筆")

        await self._push_growth_embed(week_start, covers)

    async def _run_episode_snapshot(self, week_start: str):
        """抓取並落地某週的單集觀看數

        獨立於 weekly_growth_loop：系列快照一存檔，那支 loop 的閘門就會擋掉後續
        執行，若單集抓取整批失敗（例如被巴哈限流），該週就永久遺失。這裡只認
        has_episode_snapshot，整批失敗（0 筆）時下一輪會自動重試。
        """
        attempts = self._episode_attempts.get(week_start, 0)
        if attempts >= EPISODE_SNAPSHOT_MAX_ATTEMPTS:
            logger.info(
                f"⏹️ [episode_snapshot] {week_start} 已達重試上限"
                f"（{attempts}/{EPISODE_SNAPSHOT_MAX_ATTEMPTS}），本週不再嘗試"
            )
            return  # 已達重試上限，避免持續失敗時每半小時重打一次全量請求

        rows, _ = await self._fetch_anime_rows()
        if not rows:
            logger.warning("⚠️ [episode_snapshot] API 無資料，本輪略過（下輪重試）")
            return

        self._episode_attempts[week_start] = attempts + 1
        written = await self._snapshot_episodes(week_start, rows)
        if written:
            self._episode_attempts.pop(week_start, None)
        else:
            logger.warning(
                f"⚠️ [episode_snapshot] {week_start} 本輪 0 筆，"
                f"第 {attempts + 1}/{EPISODE_SNAPSHOT_MAX_ATTEMPTS} 次嘗試"
            )

    async def _snapshot_episodes(self, week_start: str, rows: list[dict]) -> int:
        """對每部番逐集抓觀看數並落地，回傳寫入筆數

        這份資料有時效性：巴哈 API 不提供歷史，漏掉一週就永久少一週。口碑發酵
        曲線（ep1 逐週增量）需要連續數週才看得出形狀，故圖表尚未實作也先存。

        部分失敗時仍寫入已取得的列——留下部分資料遠優於全數丟棄，失敗部數記在
        log 供事後判讀該週是否完整；整批失敗回傳 0，由呼叫端決定是否重試。
        """
        targets = [(r["anime_sn"], r["video_sn"]) for r in rows if r.get("video_sn")]
        if not targets:
            logger.warning("⚠️ [episode_snapshot] 無可用 videoSn，略過")
            return 0

        sem = asyncio.Semaphore(EPISODE_SNAPSHOT_CONCURRENCY)
        try:
            async with aiohttp.ClientSession() as session:
                results = await asyncio.gather(
                    *(
                        fetch_anime_episodes_with_views(session, sn, vsn, sem)
                        for sn, vsn in targets
                    )
                )
        except Exception as e:
            logger.error(f"❌ [episode_snapshot] 抓取失敗: {e}", exc_info=True)
            return 0

        ep_rows = [r for group in results for r in group]
        failed = sum(1 for g in results if not g)
        written = self.db.save_episode_snapshot(week_start, ep_rows)
        logger.info(
            f"📸 [episode_snapshot] 完成 {week_start}: {written} 筆"
            f"（{len(targets)} 部，失敗 {failed} 部）"
        )
        return written

    async def _push_growth_embed(self, week_start: str, covers: dict[int, str] = None):
        """推送本週成長排行與折線圖，並附上名次變動最大的卡片"""
        covers = covers or {}
        weeks = self.db.get_snapshot_weeks(limit=GROWTH_CHART_WEEKS)
        if week_start not in weeks:
            return
        idx = weeks.index(week_start)

        if idx + 1 >= len(weeks):
            # 首次快照：只有基準，沒有可相減的前一週
            embed = discord.Embed(
                title="📈 新番週成長排行 — 基準已建立",
                description=(
                    f"已於 **{week_start}** 建立全番觀看數基準。\n"
                    "下週日起將顯示每週新增觀看數折線圖。"
                ),
                color=discord.Color.blue(),
                timestamp=datetime.now(TW_TZ),
            )
            await self._send_growth_embed([embed])
            return

        prev_week = weeks[idx + 1]
        growth = self.db.get_weekly_growth(week_start, prev_week)
        if not growth:
            logger.warning(f"⚠️ [weekly_growth] {week_start} 無可比對的成長資料")
            return

        top = growth[:GROWTH_TOP_N]
        chart_url = self._build_growth_chart(weeks, [t["anime_sn"] for t in top])

        # 圖表 Y 軸已被 GROWTH_VIEW_UNIT 縮放，且為了省 URL 長度拿掉了 options 區塊，
        # 軸上不會再出現單位——改在這裡說明，否則數字會被誤讀成實際觀看數
        unit_note = "（圖表單位：千）" if chart_url else ""
        embed = discord.Embed(
            title="📈 新番週成長排行",
            description=f"**{prev_week} → {week_start}** 每週新增觀看數{unit_note}",
            color=discord.Color.gold(),
            timestamp=datetime.now(TW_TZ),
        )
        if chart_url:
            embed.set_image(url=chart_url)

        lines = []
        for rank, item in enumerate(top, 1):
            medal = ["🥇", "🥈", "🥉"][rank - 1] if rank <= 3 else f"#{rank}"
            name = item["anime_name"]
            if len(name) > 20:
                name = name[:20] + "…"
            mark = " 🆕" if item["is_new_ep"] else ""
            lines.append(
                f"{medal} **{name}**{mark} `+{item['growth']:,}`"
                f"（累計 {item['total_views']:,}）"
            )
        embed.add_field(name="📋 成長名單", value="\n".join(lines), inline=False)
        embed.set_footer(
            text="每週日 22:00 自動快照 | 成長 = 本週累計 − 上週累計 | 🆕 本週有新集"
        )
        embeds = [embed]
        risers = self._pick_risers(growth)
        if risers:
            embeds.append(
                discord.Embed(
                    title="🚀 本週成長率最高",
                    description=(
                        "不看絕對量，看**相對自己基底的漲幅**——"
                        "成長量永遠由大番霸榜，成長率才看得出誰在加速"
                    ),
                    color=discord.Color.blurple(),
                )
            )
            embeds.extend(self._build_mover_embed(r, covers) for r in risers)
        await self._send_growth_embed(embeds)

    @staticmethod
    def _pick_risers(growth: list[dict]) -> list[dict]:
        """挑出週成長率最高的幾部（黑馬）

        用成長率而非成長量：成長量永遠由大番霸榜，看不出「誰在加速」。改用
        累計名次變動也不行——popular 是累計值只增不減，名次天生黏著，實測單週
        只有 ±2 名的雜訊。成長率才是 2 週資料就能算出的黑馬訊號。
        """
        cand = [
            g
            for g in growth
            if g["rank"] <= GROWTH_MOVER_RANK_LIMIT and g["prev_views"]
        ]
        cand.sort(key=lambda g: g["growth"] / g["prev_views"], reverse=True)
        return cand[:GROWTH_MOVER_N]

    def _build_mover_embed(self, item: dict, covers: dict[int, str]) -> discord.Embed:
        """單一黑馬卡片：標題即成長率，另附絕對量與名次供對照"""
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
        embed.add_field(name="本週新增", value=f"{item['growth']:,}", inline=True)
        embed.add_field(name="累計觀看", value=f"{item['total_views']:,}", inline=True)
        embed.add_field(name="累計排名", value=f"#{item['rank']}", inline=True)
        return embed

    async def _send_growth_embed(self, embeds: list[discord.Embed]):
        """送往動畫推送頻道（Discord 一則訊息上限 10 個 embed）"""
        channel = self.bot.get_channel(ANIME_CHANNEL_ID)
        if channel is None:
            logger.warning(f"⚠️ [weekly_growth] 找不到頻道 {ANIME_CHANNEL_ID}")
            return
        try:
            await channel.send(embeds=embeds)
            logger.info(f"✅ [weekly_growth] 成長排行已推送（{len(embeds)} 個 embed）")
        except Exception as e:
            logger.error(f"❌ [weekly_growth] 推送失敗: {e}", exc_info=True)

    @staticmethod
    def _short_name(name: str, limit: int = 4) -> str:
        """圖例用的短名（中文經 URL 編碼後每字 9 字元，是 URL 長度的最大單一成本）

        4 字是量測出來的上限：10 條線 × 11 週時，5 字名會讓 URL 超過 2048。
        完整番名在 embed 的成長名單裡，圖例只求認得出是哪條線。
        """
        name = (name or "").strip()
        return name if len(name) <= limit else name[:limit] + "…"

    def _build_growth_chart(
        self, weeks_new_to_old: list[str], top_sns: list[int]
    ) -> Optional[str]:
        """組 quickchart 折線圖 URL：X 軸為週次，每部番一條線，Y 軸為每週新增

        兩個壓縮關鍵（少了任一項，10 線 × 11 週會爆 2048 字元上限）：
        1. Y 值除以 GROWTH_VIEW_UNIT——成長值動輒 6 位數，10 條線 × 11 點光數字
           就吃掉近千字元。
        2. quote(safe=",:")——預設會把 JSON 的 `,` 與 `:` 編成 %2C/%3A，讓結構
           字元成本三倍；這兩者在 query string 中本就可原樣傳遞。

        仍保留由大而小的降級階梯（先減線數、再減週數）作為保險。
        """
        # 每條線的點數 = 週數 - 1（首週是相減的基準，不產生點）。要連成線至少
        # 需要 2 點，也就是 3 週；只有 2 週時每條線僅 1 點，畫出來是一排孤立的
        # 圓點而非趨勢，不如不畫，改由文字排行呈現。
        if len(weeks_new_to_old) < 3 or not top_sns:
            return None

        snaps = self.db.get_snapshots_range(weeks_new_to_old)
        by_week: dict[str, dict[int, int]] = {}
        names: dict[int, str] = {}
        for s in snaps:
            by_week.setdefault(s["week_start"], {})[s["anime_sn"]] = s["total_views"]
            names.setdefault(s["anime_sn"], s["anime_name"])

        ordered = list(reversed(weeks_new_to_old))  # 舊 → 新
        # 'MM-DD'：'-' 是 URL 免編碼字元，比 '/'（→ %2F）每個標籤省 2 字元
        all_labels = [w[5:] for w in ordered[1:]]

        def series_for(sn: int) -> list[Optional[int]]:
            """每週新增觀看數，已除以 GROWTH_VIEW_UNIT（圖表單位：千）"""
            pts: list[Optional[int]] = []
            for i in range(1, len(ordered)):
                cur = by_week.get(ordered[i], {}).get(sn)
                prev = by_week.get(ordered[i - 1], {}).get(sn)
                # 前值為 0 代表該番當週才上架，相減是上架至今累計而非單週新增
                pts.append(
                    round((cur - prev) / GROWTH_VIEW_UNIT)
                    if (cur is not None and prev)
                    else None
                )
            return pts

        for max_lines, max_weeks in (
            (GROWTH_TOP_N, 12),
            (8, 12),
            (6, 10),
            (5, 8),
            (4, 6),
        ):
            cut = min(len(all_labels), max_weeks - 1)
            if cut <= 0:
                continue
            # 只留必要鍵：quickchart 的 Chart.js 預設值已足夠（圖例顯示），逐鍵寫出來
            # 會讓每條線多約 90 字元。刻意不設 spanGaps——新番上架前的 null 本就該讓
            # 線從首週才開始，硬連會畫出它不存在的歷史。
            # 顯式指定 Chart.js v3（url 的 v=3）：v2 的 line 圖預設 fill=true，10 條
            # 半透明填色會疊成一片混濁；v3 預設 fill=false，同時省下每條線 13 字元的
            # "fill":false——這筆省下的額度正好拿來付深色主題的 options。
            datasets = []
            for i, sn in enumerate(top_sns[:max_lines]):
                datasets.append(
                    {
                        "label": self._short_name(names.get(sn, str(sn))),
                        "data": series_for(sn)[-cut:],
                        "borderColor": _CHART_COLORS[i % len(_CHART_COLORS)],
                    }
                )
            config = {
                "type": "line",
                "data": {"labels": all_labels[-cut:], "datasets": datasets},
                "options": _DARK_CHART_OPTIONS,
            }
            encoded = quote(
                json.dumps(config, separators=(",", ":"), ensure_ascii=False),
                safe=",:",
            )
            url = (
                f"https://quickchart.io/chart?v=3&bkg={_CHART_BG}"
                f"&w=900&h=400&c={encoded}"
            )
            if len(url) <= QUICKCHART_URL_LIMIT:
                return url
            logger.warning(
                f"⚠️ [weekly_growth] 圖表 URL {len(url)} 字元超限，降級重試"
                f"（{max_lines} 線 / {max_weeks} 週）"
            )
        logger.warning("⚠️ [weekly_growth] 圖表 URL 無法壓進 2048 字元，改為純文字推送")
        return None

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
        if hasattr(ctx, "response"):
            await ctx.response.defer(ephemeral=True)
            send_response = lambda content, ephemeral=True: ctx.followup.send(
                content, ephemeral=ephemeral
            )
        else:
            send_response = lambda content: ctx.send(content)

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
        if hasattr(ctx, "response"):
            await ctx.response.defer(ephemeral=True)
            send_response = lambda content, ephemeral=True: ctx.followup.send(
                content, ephemeral=ephemeral
            )
        else:
            send_response = lambda content: ctx.send(content)

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


async def setup(bot):
    """設置 Cog 的入口點"""
    await bot.add_cog(AnimeTracker(bot))
