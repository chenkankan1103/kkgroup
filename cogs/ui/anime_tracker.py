"""
Bahamut ?•ç•«è¿½è¹¤ Cog - ?ªå??šçŸ¥?°ä??¶é???
å·²é?æ§‹ç‚ºä¸‰å€‹æ¨¡çµ„ï?Push/Core?Schedule Tracker?Ranking Stats
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import aiohttp
import sqlite3
import json
import re
import html
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from zoneinfo import ZoneInfo  # Python 3.9+, æ­?¢º?„æ??€?•ç?
import time
from urllib.parse import quote  # ?¨æ–¼?Ÿæ? QuickChart URL
from shared.utils.view_registry import PersistentViewBase

# ?°ç£?‚å?
TW_TZ = ZoneInfo('Asia/Taipei')

# ?ç½®
ANIME_DB_PATH = Path(__file__).resolve().parent.parent.parent / "user_data.db"  # çµ±ä?ä½¿ç”¨ä¸»æ•¸?šåº«ï¼Œæ??‰è¡¨?¨å?ä¸€??user_data.db ä¸?
API_ENDPOINT = "https://api.gamer.com.tw/mobile_app/anime/v3/index.php"
API_TIMEOUT = 15  # ç§?

# è¡¨å??‡æ?ä½?
NOTIFIED_TABLE = "anime_notified"
BOOTSTRAP_FLAG_TABLE = "anime_bootstrap"
ANIME_DETAILS_TABLE = "anime_details"  # æ°¸æ?å¿«å??•ç•«è©³ç´°ä¿¡æ¯
ANIME_STATS_TABLE = "anime_statistics"  # ?•ç•«çµ±è??¸æ?ï¼ˆè??‹äºº?¸ã€è??†è¶¨?¢ç?ï¼?
EPISODE_STATS_TABLE = "episode_statistics"  # æ¯é?çµ±è??¸æ?
ANIME_MESSAGES_TABLE = "anime_messages"  # æ¶ˆæ¯ ID è¿½è¹¤ï¼ˆç”¨??bot ?å??‚æ¢å¾?viewï¼?
ANIME_VOTES_TABLE = "anime_votes"  # ?¿å??•ç¥¨çµæ?
ANIME_REWARDS_TABLE = "anime_rewards"  # KKå¹???µè¿½è¸ªï??²æ­¢?è??¼æ”¾ï¼?
ANIME_CHECK_HISTORY_TABLE = "anime_check_history"  # æ¯æ—¥?‚åˆ»æª¢æŸ¥æ­·å²ï¼ˆé˜²æ­¢é?è¤‡æª¢?¥ï?è§?±º Bot ?å??é?ï¼?
ANIME_WEEKLY_SCHEDULE_TABLE = "anime_weekly_schedule"  # ?±è¡¨ï¼šæ??±ä??ªå??‰å??„å??´æ?ç¨‹è¡¨ï¼ˆæ?å°?API èª¿ç”¨ï¼?

# å°å…¥?ªå?ç¾©æ¨¡çµ?
from .push_core import AnimePushCore, AnimeDatabase, ANIME_CHANNEL_ID, find_unpushed_items
from .schedule_tracker import AnimeScheduleTracker
from .ranking_stats import RankingStats

# Logger
logger = logging.getLogger(__name__)


class AnimeTracker(commands.Cog):
    """Bahamut ?•ç•«è¿½è¹¤ä¸?Cog"""

    def __init__(self, bot: commands.Bot):
        print("[ANIME_INIT_START] ?¬ AnimeTracker.__init__ ?‹å??·è?")
        import sys
        sys.stdout.flush()

        import logging
        logger = logging.getLogger(__name__)
        logger.info("=" * 50)
        logger.info("?“º [AnimeTracker.__init__] ?‹å??å???)
        self.bot = bot
        try:
            self.db = AnimeDatabase(ANIME_DB_PATH)
            logger.info(f"??[AnimeTracker.__init__] ?¸æ?åº«å·²?å??? {ANIME_DB_PATH}")
        except Exception as e:
            logger.error(f"??[AnimeTracker.__init__] ?¸æ?åº«å?å§‹å?å¤±æ?: {e}", exc_info=True)
            raise

        # ?å??–ä??‹æ¨¡çµ?
        self.push_core = AnimePushCore(ANIME_DB_PATH)
        self.schedule_tracker = AnimeScheduleTracker(ANIME_DB_PATH)
        self.ranking_stats = RankingStats(ANIME_DB_PATH)

        # è¨­ç½®?¸ä?ä¾è³´
        self.push_core.set_bot_and_db(bot, self.db)
        self.schedule_tracker.set_dependencies(bot, self.db, self.push_core)
        self.ranking_stats.set_dependencies(bot, self.db)

        # è¨­å? View ?Ÿæ?å·¥å?ï¼ˆè§£æ±ºå¾ª?°å??¥å?é¡Œï?
        self.push_core.set_view_factory(self.generate_anime_view)

        self.task_started = False
        self.bootstrap_completed = False
        self.last_weekly_stats_sent = None

    def __getattr__(self, name):
        """Delegate attribute access to sub-modules (push_core, db, schedule_tracker, ranking_stats)."""
        # Use __dict__ to avoid recursive __getattr__ calls
        for attr in ('push_core', 'db', 'schedule_tracker', 'ranking_stats'):
            obj = self.__dict__.get(attr)
            if obj is not None and hasattr(obj, name):
                return getattr(obj, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    # ==================== CULC ?Ÿå‘½?±æ??¹æ? ====================

    async def cog_load(self):
        """Cog ? è??‚å??•ä»»??""
        import sys
        import time
        start_time = time.perf_counter()
        print("[COG_LOAD_START] ?¬ cog_load() ?‹å??·è?", flush=True)
        sys.stdout.flush()

        import logging
        logger = logging.getLogger(__name__)

        logger.info("=" * 50)
        logger.info("?¬ [AnimeTracker.cog_load] cog_load() è¢«èª¿??)

        try:
            # ?¢å¾©?Šæ??¯ç?è¦–å? - ??bot ?å??‚é??°è¨»?Šæ??‰æ°¸ä¹…è???
            print("[COG_LOAD] ?—è©¦?¢å¾©?Šæ???view...", flush=True)
            await self._restore_old_message_views()
            print("[COG_LOAD] ???Šæ???view ?¢å¾©å®Œæ?", flush=True)

            # å¦‚æ??±è¡¨?ºç©ºï¼Œç??³æ??–ï?è§?±ºé¦–æ¬¡?¨ç½²/?ç¦®?œå¤©?å??é?ï¼?
            print("[COG_LOAD] æª¢æŸ¥?±è¡¨?¯å¦?€è¦å?å§‹å?...", flush=True)
            await self._init_weekly_schedule_if_empty()
            print("[COG_LOAD] ???±è¡¨?å??–æª¢?¥å???, flush=True)

            # è£œæ¨ï¼šè‹¥ bot ?å??æ??ªæ¨?ç??•ç•«ï¼Œå??•æ?è£œç™¼
            print("[COG_LOAD] æª¢æŸ¥?¯å¦?‰éŒ¯?ç??•ç•«?¨é€?..", flush=True)
            await self._catchup_missed_pushes()
            print("[COG_LOAD] ??è£œæ¨æª¢æŸ¥å®Œæ?", flush=True)

            # ?Ÿå??±è¡¨?·æ–°ä»»å?
            print("[COG_LOAD] æª¢æŸ¥ refresh_weekly_schedule ä»»å??€??, flush=True)
            if not self.refresh_weekly_schedule.is_running():
                print("[COG_LOAD] ???Ÿå? refresh_weekly_schedule ä»»å?", flush=True)
                logger.info("?? [AnimeTracker.cog_load] ?Ÿå? refresh_weekly_schedule ä»»å?")
                try:
                    self.refresh_weekly_schedule.start()
                    logger.info(f"??[AnimeTracker.cog_load] refresh_weekly_schedule å·²å???(is_running={self.refresh_weekly_schedule.is_running()})")
                    print("[COG_LOAD] ??refresh_weekly_schedule å·²å???, flush=True)
                except Exception as start_err:
                    logger.error(f"??[AnimeTracker.cog_load] ?Ÿå? refresh_weekly_schedule å¤±æ?: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ???Ÿå? refresh_weekly_schedule å¤±æ?: {start_err}", flush=True)
                    # ?è©¦ä¸€æ¬?
                    try:
                        await asyncio.sleep(1)
                        logger.info("?? [AnimeTracker.cog_load] ?è©¦?Ÿå? refresh_weekly_schedule...")
                        self.refresh_weekly_schedule.start()
                        logger.info("??[AnimeTracker.cog_load] ?è©¦?å?ï¼Œrefresh_weekly_schedule å·²å???)
                        print("[COG_LOAD] ???è©¦?å?ï¼Œrefresh_weekly_schedule å·²å???, flush=True)
                    except Exception as retry_err:
                        logger.error(f"??[AnimeTracker.cog_load] ?è©¦å¤±æ?: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ???è©¦å¤±æ?: {retry_err}", flush=True)
            else:
                logger.info(f"?­ï?  [AnimeTracker.cog_load] refresh_weekly_schedule å·²åœ¨?‹è? (is_running=True)")
                print("[COG_LOAD] ? ï? refresh_weekly_schedule å·²åœ¨?‹è?", flush=True)

            # ?? é©—è??±è¡¨?·æ–°ä»»å??Ÿæ­£?Ÿå?ï¼ˆbefore_loop ?¯èƒ½å¤±æ?ä½†ä??‹å‡º?°å¸¸ï¼?
            await asyncio.sleep(0.5)
            if self.refresh_weekly_schedule.is_running():
                logger.info("??[AnimeTracker.cog_load] ç¢ºè? refresh_weekly_schedule æ­?œ¨?‹è?")
                print("[COG_LOAD] ??ç¢ºè? refresh_weekly_schedule æ­?œ¨?‹è?", flush=True)
            else:
                logger.error("??[AnimeTracker.cog_load] refresh_weekly_schedule ?Ÿå?å¾Œç??‹ç•°å¸?(is_running=False)ï¼Œå?è©¦é???..")
                print("[COG_LOAD_ERROR] ??refresh_weekly_schedule ?Ÿå?å¾Œç??‹ç•°å¸¸ï??—è©¦?å?...", flush=True)
                try:
                    self.refresh_weekly_schedule.start()
                    await asyncio.sleep(0.5)
                    if self.refresh_weekly_schedule.is_running():
                        logger.info("??[AnimeTracker.cog_load] ?å??å?")
                        print("[COG_LOAD] ???å??å?", flush=True)
                    else:
                        logger.critical("?’¥ [AnimeTracker.cog_load] ?å?ä»å¤±?—ï?ä»»å??¡æ??Ÿå?ï¼?)
                        print("[COG_LOAD_CRITICAL] ?’¥ ?å?ä»å¤±?—ï?ä»»å??¡æ??Ÿå?ï¼?, flush=True)
                except Exception as e:
                    logger.critical(f"?’¥ [AnimeTracker.cog_load] ?å??°å¸¸: {e}", exc_info=True)
                    print(f"[COG_LOAD_CRITICAL] ?’¥ ?å??°å¸¸: {e}", flush=True)

            # ?Ÿå?ç²¾å?æ´¾ç™¼?¨ï??Œæ™¯ä»»å?ï¼Œé? tasks.loopï¼?
            print("[COG_LOAD] ?Ÿå?ç²¾æ??’ç?æ´¾ç™¼??, flush=True)
            logger.info("?? [AnimeTracker.cog_load] ?Ÿå?ç²¾æ??’ç?æ´¾ç™¼??)
            self._dispatcher_task = asyncio.create_task(
                self._wrap_task_with_restart("_schedule_dispatcher", self._schedule_dispatcher))
            # çµ¦ä»»?™ä?é»æ??“å??•ï?æª¢æŸ¥?¯å¦?‰ç•°å¸?
            await asyncio.sleep(0.1)
            if self._dispatcher_task.done():
                exc = self._dispatcher_task.exception()
                if exc:
                    logger.error(f"??[AnimeTracker.cog_load] _schedule_dispatcher ä»»å?ç«‹å³å¤±æ?: {exc}", exc_info=True)
                    print(f"[COG_LOAD_ERROR] _schedule_dispatcher ä»»å?ç«‹å³å¤±æ?: {exc}", flush=True)
                    raise exc
                else:
                    logger.warning(f"? ï? [AnimeTracker.cog_load] _schedule_dispatcher ä»»å??å?çµæ?ï¼ˆç„¡?°å¸¸ï¼?)
                    print("[COG_LOAD_WARN] _schedule_dispatcher ä»»å??å?çµæ?", flush=True)
            else:
                logger.info("??[AnimeTracker.cog_load] ç²¾æ??’ç?æ´¾ç™¼?¨å·²?Ÿå?ä¸¦é?è¡Œä¸­")
                print("[COG_LOAD] ??ç²¾æ??’ç?æ´¾ç™¼?¨å·²?Ÿå?ä¸¦é?è¡Œä¸­", flush=True)

            # ?Ÿå?å®šæ?è£œæ¨ä»»å?ï¼ˆæ? 5 ?†é?æª¢æŸ¥?€è¿?10 ?†é??§æ??¨é??®ä¸¦?Ÿæ­£?¼é€ï?
            print("[COG_LOAD] ?Ÿå?å®šæ?è£œæ¨æª¢æŸ¥ä»»å?", flush=True)
            logger.info("?? [AnimeTracker.cog_load] ?Ÿå?å®šæ?è£œæ¨æª¢æŸ¥ä»»å?")
            try:
                self._catchup_check_task = asyncio.create_task(
                    self._wrap_task_with_restart("_periodic_catchup_check", self._periodic_catchup_check))
                # çµ¦ä»»?™ä?é»æ??“å??•ï?æª¢æŸ¥?¯å¦?‰ç•°å¸?
                await asyncio.sleep(0.1)
                if self._catchup_check_task.done():
                    exc = self._catchup_check_task.exception()
                    if exc:
                        logger.error(f"??[AnimeTracker.cog_load] _periodic_catchup_check ä»»å?ç«‹å³å¤±æ?: {exc}", exc_info=True)
                        print(f"[COG_LOAD_ERROR] _periodic_catchup_check ä»»å?ç«‹å³å¤±æ?: {exc}", flush=True)
                    else:
                        logger.warning(f"? ï? [AnimeTracker.cog_load] _periodic_catchup_check ä»»å??å?çµæ?")
                else:
                    logger.info("??[AnimeTracker.cog_load] å®šæ?è£œæ¨æª¢æŸ¥ä»»å?å·²å??•ä¸¦?‹è?ä¸?)
                    print("[COG_LOAD] ??å®šæ?è£œæ¨æª¢æŸ¥ä»»å?å·²å??•ä¸¦?‹è?ä¸?, flush=True)
            except Exception as e:
                logger.error(f"??[AnimeTracker.cog_load] ?µå»º _periodic_catchup_check ä»»å?å¤±æ?: {e}", exc_info=True)
                print(f"[COG_LOAD_ERROR] ?µå»º _periodic_catchup_check ä»»å?å¤±æ?: {e}", flush=True)
                raise

            # ?Ÿå??±æ?çµ±è??Œæ­¥ä»»å?
            print("[COG_LOAD] æª¢æŸ¥ sync_episode_stats ä»»å??€??, flush=True)
            if not self.sync_episode_stats.is_running():
                print("[COG_LOAD] ???Ÿå? sync_episode_stats ä»»å?", flush=True)
                logger.info("?? [AnimeTracker.cog_load] ?Ÿå? sync_episode_stats ä»»å?")
                try:
                    self.sync_episode_stats.start()
                    logger.info(f"??[AnimeTracker.cog_load] sync_episode_stats å·²å???(is_running={self.sync_episode_stats.is_running()})")
                    print("[COG_LOAD] ??sync_episode_stats å·²å???, flush=True)
                except Exception as start_err:
                    logger.error(f"??[AnimeTracker.cog_load] ?¨å? sync_episode_stats å¤±æ?: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ???¨å? sync_episode_stats å¤±æ?: {start_err}", flush=True)
                    # ?è©¦ä¸€æ¬?
                    try:
                        await asyncio.sleep(1)
                        logger.info("?? [AnimeTracker.cog_load] ?è©¦?Ÿå? sync_episode_stats...")
                        self.sync_episode_stats.start()
                        logger.info("??[AnimeTracker.cog_load] ?è©¦?å?ï¼Œsync_episode_stats å·²å???)
                        print("[COG_LOAD] ???è©¦?å?ï¼Œsync_episode_stats å·²å???, flush=True)
                    except Exception as retry_err:
                        logger.error(f"??[AnimeTracker.cog_load] ?è©¦å¤±æ?: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ???è©¦å¤±æ?: {retry_err}", flush=True)
            else:
                logger.info(f"?­ï?  [AnimeTracker.cog_load] sync_episode_stats å·²åœ¨?‹è? (is_running=True)")
                print("[COG_LOAD] ? ï? sync_episode_stats å·²åœ¨?‹è?", flush=True)

            print("[COG_LOAD_END] ??cog_load() ?·è?å®Œæ?", flush=True)
            sys.stdout.flush()
            logger.info("??[AnimeTracker.cog_load] ä»»å??Ÿå?å®Œæ?")

        except Exception as e:
            import traceback
            error_msg = f"??[cog_load] ?·è?å¤±æ?: {e}"
            print(f"[COG_LOAD_ERROR] {error_msg}", flush=True)
            print(f"[COG_LOAD_ERROR] Traceback:\n{traceback.format_exc()}", flush=True)
            logger.error(error_msg, exc_info=True)
            raise
        elapsed = time.perf_counter() - start_time
        logger.info(f"?±ï? [AnimeTracker.cog_load] ç¸½è€—æ?: {elapsed:.2f} ç§?)
        print(f"[COG_LOAD_TIMING] ç¸½è€—æ?: {elapsed:.2f} ç§?, flush=True)
        logger.info("=" * 50)

    def cog_unload(self):
        """Cog ?¸è??‚å?æ­¢ä»»??""
        logger = logging.getLogger(__name__)
        logger.info("=" * 50)
        logger.info("?? [AnimeTracker.cog_unload] cog_unload() è¢«èª¿??)
        try:
            # ??check_new_anime å·²ç§»??

            if self.refresh_weekly_schedule.is_running():
                self.refresh_weekly_schedule.cancel()
                logger.info("??[AnimeTracker.cog_unload] refresh_weekly_schedule å·²å?æ­?)

            # ?œæ­¢ç²¾æ??’ç?æ´¾ç™¼?¨ï??Œæ™¯ä»»å?ï¼Œé? tasks.loopï¼?
            if hasattr(self, '_dispatcher_task') and not self._dispatcher_task.done():
                self._dispatcher_task.cancel()
                logger.info("??[AnimeTracker.cog_unload] ç²¾æ??’ç?æ´¾ç™¼?¨å·²?œæ­¢")

            # ?œæ­¢å®šæ?è£œæ¨æª¢æŸ¥ä»»å?
            if hasattr(self, '_catchup_check_task') and not self._catchup_check_task.done():
                self._catchup_check_task.cancel()
                logger.info("??[AnimeTracker.cog_unload] å®šæ?è£œæ¨æª¢æŸ¥ä»»å?å·²å?æ­?)

            if self.sync_episode_stats.is_running():
                self.sync_episode_stats.cancel()
                logger.info("??[AnimeTracker.cog_unload] sync_episode_stats å·²å?æ­?)

        except Exception as e:
            logger.error(f"??[AnimeTracker.cog_unload] ä»»å??œæ­¢å¤±æ?: {e}", exc_info=True)
        logger.info("=" * 50)

    # ==================== ?¸å??Ÿèƒ½?¹æ? ====================

    async def generate_anime_view(self, episode: dict) -> Optional[discord.ui.View]:
        """?Ÿæ??•ç•«è¦–å? - ?µå»º?•ç¥¨?Œè?è«–æ???+ ?•ç•«??è§€?‹é€??"""
        try:
            video_sn = episode.get("videoSn")
            anime_sn = episode.get("animeSn")
            if not video_sn or not anime_sn:
                return None

            vote_view = self.AnimeVoteView(episode, self)
            anime_url = f"https://ani.gamer.com.tw/animeRef.php?sn={anime_sn}"
            vote_view.add_item(discord.ui.Button(label="?? ?•ç•«??, url=anime_url, style=discord.ButtonStyle.link))
            video_url = f"https://ani.gamer.com.tw/animeVideo.php?sn={video_sn}"
            vote_view.add_item(discord.ui.Button(label="?¶ï? è§€??, url=video_url, style=discord.ButtonStyle.link))
            return vote_view
        except Exception as e:
            logger.error(f"??[generate_anime_view] Failed to generate view: {e}", exc_info=True)
            return None

    # ==================== è¦–å??¢å¾©?Œå??•æ–¹æ³?====================

    async def _restore_old_message_views(self):
        """Bot ?å??‚æ¢å¾©è?æ¶ˆæ¯?„è???""
        try:
            # ?²å??€?‰ä?å­˜ç?æ¶ˆæ¯è³‡è?
            messages = self.get_unviewed_messages()

            for msg_info in messages:
                try:
                    # ?æ–°?Ÿæ?è¦–å?ä¸¦è¨»?Šåˆ° bot
                    # æ³¨æ?ï¼šé€™è£¡?€è¦é??°å? API ?²å? episode ?¸æ?ä¾†ç??æ­£ç¢ºç?è¦–å?
                    # ?ºç°¡?–èµ·è¦‹ï??‘å€‘å?è¨»å?ä¸€?‹åŸº?¬ç?è¦–å?ï¼Œå¯¦?›å…§å®¹æ??¨ç”¨?¶ä??•æ??´æ–°
                    # ?‚é??°ç???
                    # get_unviewed_messages è¿”å? snake_case keys (video_sn, anime_sn, etc.)
                    video_sn = msg_info.get('video_sn') or msg_info.get('videoSn')

                    # å¾è??™åº«?²å??•ç•«è³‡è?
                    anime_info = self.db.get_anime_details_by_videosn(video_sn)
                    if anime_info:
                        # ?µå»ºä¸€?‹å???episode å­—å…¸?¨æ–¼?Ÿæ?è¦–å?
                        episode = {
                            'videoSn': video_sn,
                            'animeSn': anime_info.get('animeSn'),
                            'title': anime_info.get('title', 'Unknown'),
                            'volume': anime_info.get('volume', ''),
                            'cover': anime_info.get('cover_url', '')
                        }

                        # ?Ÿæ?è¦–å?
                        view = await self.generate_anime_view(episode)
                        if view:
                            # ?œéµï¼šå??ˆå‚³??message_id ?èƒ½è®“æ°¸ä¹…è??–åœ¨?å?å¾Œæ­£å¸¸å·¥ä½?
                            message_id = msg_info.get('messageId') or msg_info.get('message_id')
                            if message_id:
                                self.bot.add_view(view, message_id=int(message_id))
                                logger.info(f"??[_restore_old_message_views] å·²è¨»?Šæ°¸ä¹…è???message_id={message_id}")
                            else:
                                logger.warning(f"? ï? [_restore_old_message_views] ç¼ºå? message_idï¼Œç„¡æ³•è¨»?Šæ°¸ä¹…è???)

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"??[_restore_old_message_views] å¾©å?è¦–å?å¤±æ? for message {msg_info.get('messageId')}: {e}")
                    continue

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"??[_restore_old_message_views] å¤±æ?: {e}")

    async def _catchup_missed_pushes(self):
        """Bot ?å??‚è??¨ä??¥å·²?æ??»ä?å°šæœª?¨é€ç??•ç•«ï¼ˆç?æ­?™¼?ï?ä¸å??ªæ?è¨˜ï?

        ä¿®å¾©ï¼šå?å¯¦ä??ªåœ¨?å??‚æ??æ??»æ?è¨˜ç‚º pushed=1 ?»ä?å¯¦é??¼é€ï?å°è‡´
        ?å??Ÿé??¯é??„å??«æ°¸ä¹…éºå¤±ã€‚ç¾?¨æ”¹?ºå¯¦?›å‘¼??send_anime_push è£œç™¼??
        send_anime_push ?§éƒ¨å·²æ???API ?å?å¾Œæ?è¨?pushed=1ï¼Œæ?æ­¤è?ä¸é?è¤‡æ?è¨˜ã€?
        """
        logger = logging.getLogger(__name__)
        try:
            await self.bot.wait_until_ready()
            now = datetime.now(TW_TZ)
            week_start_str = self.get_week_start_date(now)
            day_of_week = (now.weekday() + 1) % 7 or 7
            today_schedule = self.get_today_schedule()
            if not today_schedule:
                logger.warning("? ï? [_catchup_missed_pushes] ä»Šæ—¥?±è¡¨?ºç©ºï¼Œå?è©¦å? API ?å??–é€±è¡¨...")
                # ?—è©¦?å??–é€±è¡¨ï¼ˆè§£æ±ºé?æ¬¡éƒ¨ç½??é€±æ—¥?å?/DB æ¸…ç©º?é?ï¼?
                await self._init_weekly_schedule_if_empty()
                # ?æ–°?²å?
                today_schedule = self.get_today_schedule()
                if not today_schedule:
                    logger.warning("? ï? [_catchup_missed_pushes] ?±è¡¨?å??–å?ä»ç‚ºç©ºï??¡æ?è£œæ¨")
                    return
                logger.info(f"??[_catchup_missed_pushes] ?±è¡¨?å??–æ??Ÿï??–å? {len(today_schedule)} ç­†ä??¥æ?ç¨?)

            # ?¾å‡ºä»Šå¤©å·²é??‚åˆ»ä½†å??ªæ?è¨˜ç‚ºå·²æ¨?ç??…ç›®
            missed = find_unpushed_items(today_schedule, now, future_only=False)
            logger.info(f"?? [_catchup_missed_pushes] ?¼ç¾ {len(missed)} ?‹é??Ÿå?æ¼æ¨?…ç›®ï¼Œé?å§‹è???)
            for item in missed:
                scheduled_time = item['scheduled_time']
                try:
                    sched_dt = datetime.strptime(scheduled_time, "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                    )
                    diff_seconds = (now - sched_dt).total_seconds()
                    logger.info(f"?“º [_catchup_missed_pushes] è£œæ¨?‚åˆ»: {scheduled_time} (è·ä? {diff_seconds:.0f} ç§’å?)")

                    success = await self.send_anime_push(
                        scheduled_time, ANIME_CHANNEL_ID,
                        week_start_date=week_start_str,
                        day_of_week=day_of_week
                    )
                    if success:
                        logger.info(f"??[_catchup_missed_pushes] è£œæ¨?å?: {scheduled_time}")
                    else:
                        logger.warning(f"? ï? [_catchup_missed_pushes] è£œæ¨?¡æ–°?ªæ?å¤±æ?: {scheduled_time}")
                except Exception as e:
                    logger.error(f"??[_catchup_missed_pushes] è£œæ¨?°å¸¸ {scheduled_time}: {e}", exc_info=True)
                await asyncio.sleep(2)  # ?¿å??­æ??“å…§????¼é€å¤ªå¤šè???
        except Exception as e:
            logger.error(f"??[_catchup_missed_pushes] å¤±æ?: {e}", exc_info=True)

    async def _periodic_catchup_check(self):
        """
        å®šæ?è£œæ¨æª¢æŸ¥ï¼šæ? 15 ?†é??·è?ä¸€æ¬¡ï?æª¢æŸ¥ä»Šæ—¥?€?‰ã€Œå·²?æ?ä½†æœª?¨é€ã€ç??…ç›®ä¸¦ç?æ­?™¼??
        è§?±º dispatcher ?¯é??‚åˆ»?bot ?å?å¾Œæ??¨ç??é?
        ï¼ˆé »?‡å? 5 ?†é??ç‚º 15 ?†é?ä»¥æ?å°?API ?¼å«ï¼Œé¿?è¢«å·´å? ban IPï¼?
        """
        logger = logging.getLogger(__name__)
        print("[DEBUG_CATCHUP] _periodic_catchup_check function entered", flush=True)
        logger.info("?? [_periodic_catchup_check] å®šæ?è£œæ¨æª¢æŸ¥ä»»å??Ÿå?ï¼ˆæ? 5 ?†é?ï¼?)

        # ç­‰å? bot readyï¼Œä?è¨?timeout ?²æ­¢?¡æ­»
        try:
            await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
            print("[DEBUG_CATCHUP] bot.wait_until_ready() completed", flush=True)
            logger.info("??[_periodic_catchup_check] bot readyï¼Œé?å§‹åŸ·è¡Œè??¨æª¢??)
        except asyncio.TimeoutError:
            logger.error("??[_periodic_catchup_check] wait_until_ready() timeout 60sï¼Œç?æ­¢ä»»??)
            print("[DEBUG_CATCHUP] wait_until_ready() TIMEOUT!", flush=True)
            return

        while not self.bot.is_closed():
            try:
                now = datetime.now(TW_TZ)
                week_start_str = self.get_week_start_date(now)
                day_of_week = (now.weekday() + 1) % 7 or 7
                today_schedule = self.get_today_schedule()

                if not today_schedule:
                    logger.warning("? ï? [_periodic_catchup_check] today_schedule ?ºç©ºï¼Œå?è©¦å? API ?‰å??±è¡¨...")
                    # ?—è©¦?å??–é€±è¡¨ï¼ˆé?ä¼?cog_load ?‚ç??è¼¯ï¼?
                    await self._init_weekly_schedule_if_empty()
                    # ?æ–°?²å?
                    today_schedule = self.get_today_schedule()
                    if not today_schedule:
                        logger.warning("? ï? [_periodic_catchup_check] ?±è¡¨?å??–å?ä»ç‚ºç©ºï?è·³é??¬æ¬¡æª¢æŸ¥")
                        await asyncio.sleep(300)  # 5 ?†é?
                        continue

                # Debug: log today's schedule status
                pending_count = sum(1 for item in today_schedule if not item['pushed'])
                logger.info(f"?? [_periodic_catchup_check] ä»Šæ—¥?‚ç? {len(today_schedule)} ç­†ï?å¾…è???{pending_count} ç­?)
                for item in today_schedule:
                    status = "?…å·²?? if item['pushed'] else "?³å?è£?
                    anime_data = item['anime_data']
                    title = (anime_data.get('title', 'N/A') if isinstance(anime_data, dict)
                            else json.loads(anime_data).get('title', 'N/A'))
                    logger.debug(f"   {item['scheduled_time']} {status} - {title[:30]}")

                # ?¾å‡ºï¼špushed=0 ä¸?scheduled_time <= ?¶å??‚é?ï¼ˆä??¥æ??‰å·²?æ??ªæ¨?é??®ï?
                catchup_items = find_unpushed_items(today_schedule, now, future_only=False)

                if catchup_items:
                    logger.info(f"?? [_periodic_catchup_check] ?¼ç¾ {len(catchup_items)} ?‹ä??¥æ??¨é??®ï??‹å?è£œæ¨")
                    # å·²ç???find_unpushed_items ?’å?

                    for item in catchup_items:
                        scheduled_time = item['scheduled_time']
                        try:
                            sched_dt = datetime.strptime(scheduled_time, "%H:%M").replace(
                                year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                            )
                            diff_seconds = (now - sched_dt).total_seconds()
                            logger.info(f"?“º [_periodic_catchup_check] è£œæ¨?‚åˆ»: {scheduled_time} (è·ä? {diff_seconds:.0f} ç§’å?)")

                            success = await self.send_anime_push(
                                scheduled_time,
                                ANIME_CHANNEL_ID,
                                day_of_week=day_of_week,
                                week_start_date=week_start_str
                            )
                            if success:
                                logger.info(f"??[_periodic_catchup_check] è£œæ¨?å?: {scheduled_time}")
                            else:
                                logger.warning(f"? ï? [_periodic_catchup_check] è£œæ¨?¡æ–°?ªæ?å¤±æ?: {scheduled_time}")
                        except Exception as e:
                            logger.error(f"??[_periodic_catchup_check] è£œæ¨?°å¸¸ {scheduled_time}: {e}")
                else:
                    logger.info("?˜´ [_periodic_catchup_check] ?¬æ¬¡æª¢æŸ¥?¡é?è£œæ¨?…ç›®")

                # æ¯?15 ?†é?æª¢æŸ¥ä¸€æ¬?
                await asyncio.sleep(900)

            except asyncio.CancelledError:
                logger.info("?? [_periodic_catchup_check] ä»»å?è¢«å?æ¶?)
                break
            except Exception as e:
                logger.error(f"??[_periodic_catchup_check] ?°å¸¸: {e}", exc_info=True)
                await asyncio.sleep(60)  # ?¯èª¤?‚ç? 1 ?†é??¿å??‚è¿´??

    async def _init_weekly_schedule_if_empty(self):
        """å¦‚æ??¬é€±ç??±è¡¨?ºç©ºï¼Œç??³å? API ?‰å?ï¼ˆè§£æ±ºé?æ¬¡éƒ¨ç½??ç¦®?œå¤©?å??é?ï¼?""
        try:
            await self.bot.wait_until_ready()
            today_schedule = self.get_today_schedule()
            if today_schedule:
                logger = logging.getLogger(__name__)
                logger.info(f"??[_init_weekly_schedule_if_empty] ?±è¡¨å·²æ? {len(today_schedule)} ç­†ï?è·³é?")
                return

            logger = logging.getLogger(__name__)
            logger.info("?? [_init_weekly_schedule_if_empty] ?±è¡¨?ºç©ºï¼Œç??³å? API ?‰å?...")
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("? ï? [_init_weekly_schedule_if_empty] ?¡æ??‰å??‚ç?è¡?API")
                return

            now = datetime.now(TW_TZ)
            week_start_str = self.get_week_start_date(now, api_week=True)

            schedule_data = []
            for day_offset in range(7):
                day_of_week = (day_offset + 1) % 7 or 7  # 1=Mon, 7=Sun
                day_key = str(day_of_week)
                if day_key in schedule:
                    for anime in schedule[day_key]:
                        scheduled_time = anime.get('scheduleTime', '')
                        if scheduled_time:
                            schedule_data.append({
                                'day_of_week': day_of_week,
                                'scheduled_time': scheduled_time,
                                'anime_data': anime
                            })

            if schedule_data:
                self.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(f"??[_init_weekly_schedule_if_empty] ?±è¡¨?å??–å??? {len(schedule_data)} ç­?)

                # æ¸…ç?å­¤å?è¨˜é?
                if hasattr(self.db, 'clean_orphaned_records'):
                    orphan_stats = self.db.clean_orphaned_records(week_start_str)
                    if orphan_stats.get('messages', 0) > 0 or orphan_stats.get('notified', 0) > 0:
                        logger.info(f"?§¹ [_init_weekly_schedule_if_empty] æ¸…ç?å­¤å?è¨˜é?: messages={orphan_stats.get('messages')}, notified={orphan_stats.get('notified')}")
            else:
                logger.warning("? ï? [_init_weekly_schedule_if_empty] API è¿”å?ç©ºæ?ç¨‹è¡¨")
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"??[_init_weekly_schedule_if_empty] å¤±æ?: {e}", exc_info=True)

    # ==================== API ?¸é??¹æ? ====================

    async def fetch_new_anime_from_api(self) -> List[Dict]:
        """å¾?API ?²å??€è¿‘æ›´?°ç??•ç•«"""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

                    # API ?æ?çµæ?: { "data": { "newAnime": { "date": [...], ... } } }
                    new_anime = data.get('data', {}).get('newAnime')
                    if not new_anime or 'date' not in new_anime:
                        return None

                    return new_anime['date']
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"??Error fetching new anime from API: {e}")
            return None

    async def fetch_all_recent_anime_from_api(self) -> List[Dict]:
        """?²å??€?‰æ?è¿‘æ›´?°ç??•ç•«ï¼ˆç”¨?¼æ?è¡Œæ?ï¼?""
        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(API_ENDPOINT) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

                    if 'newAnime' not in data:
                        return None

                    return data['newAnime']
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"??Error fetching all recent anime from API: {e}")
            return None

    async def fetch_anime_details_from_api(self, video_sn: int) -> Optional[Dict]:
        """å¾?API ?²å??®é??•ç•«è©³ç´°ä¿¡æ¯"""
        try:
            url = f"https://api.gamer.com.tw/mobile_app/anime/v2/video.php?vsn={video_sn}"
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return data
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"??Error fetching anime details from API: {e}")
            return None

    # ==================== ?’ç?ä»»å? ====================

    # ?’ç??†ç™¼?¨ï??¨ã€Œä?ä¸€?‹å??¨é€æ??»ã€ç²¾ç¢ºå??’ï??¼å« API ???¨é€????¡åˆ°ä¸‹ä??‹æ???
    # ?–ä»£?Ÿæ??†é?è¼ªè©¢ï¼Œå¤§å¹…æ?å°?API ?¼å«
    async def _schedule_dispatcher(self):
        """?Œæ™¯ä»»å?ï¼šç²¾ç¢ºåœ¨æ¯å€?scheduled_time ?šé?ä¸¦æ¨??""
        logger = logging.getLogger(__name__)
        logger.info("?? [_schedule_dispatcher] ?’ç??†ç™¼?¨å???)

        # ç­‰å? bot readyï¼Œä?è¨?timeout ?²æ­¢?¡æ­»ï¼ˆå???_periodic_catchup_checkï¼?
        try:
            await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
            logger.info("??[_schedule_dispatcher] bot readyï¼Œé?å§‹åŸ·è¡Œæ?ç¨‹å???)
        except asyncio.TimeoutError:
            logger.error("??[_schedule_dispatcher] wait_until_ready() timeout 60sï¼Œç?æ­¢ä»»??)
            return

        # ?Ÿå??‚æª¢??week_start_date ?¯å¦?ºæœ¬?±ï??²æ­¢è·¨é€±é??Ÿå¸¶?Šè??™ï?
        now = datetime.now(TW_TZ)
        expected_week_start = self.get_week_start_date(now, api_week=True)
        logger.info(f"?? [_schedule_dispatcher] ?Ÿå?é©—è?ï¼šæ??›é€±èµ·å§‹æ—¥??{expected_week_start}ï¼Œä???{now.strftime('%Y-%m-%d %a')}")

        while not self.bot.is_closed():
            try:
                now = datetime.now(TW_TZ)
                today_schedule = self.get_today_schedule()

                # Debug: log today's schedule status
                pending_count = sum(1 for item in today_schedule if not item['pushed'])
                logger.info(f"?? [_schedule_dispatcher] ä»Šæ—¥?‚ç? {len(today_schedule)} ç­†ï?å¾…æ¨??{pending_count} ç­?)
                for item in today_schedule:
                    status = "?…å·²?? if item['pushed'] else "?³å???
                    anime_data = item['anime_data']
                    title = (anime_data.get('title', 'N/A') if isinstance(anime_data, dict)
                            else json.loads(anime_data).get('title', 'N/A'))
                    logger.info(f"   {item['scheduled_time']} {status} - {title[:30]}")

                # å¦‚æ? today_schedule ?ºç©ºï¼Œå?è©¦å? API ?‰å??±è¡¨
                if not today_schedule:
                    logger.warning("? ï? [_schedule_dispatcher] today_schedule ?ºç©ºï¼Œå?è©¦å? API ?‰å??±è¡¨...")
                    await self._init_weekly_schedule_if_empty()
                    today_schedule = self.get_today_schedule()
                    if not today_schedule:
                        logger.warning("? ï? [_schedule_dispatcher] ?±è¡¨?å??–å?ä»ç‚ºç©ºï??¡åˆ°?å¤© 00:00 ?è©¦")
                        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                        sleep_seconds = (tomorrow - now).total_seconds()
                        await asyncio.sleep(sleep_seconds)
                        continue

                # ?¾å‡ºä»Šå¤©?Œå??ªæ¨?ã€ä??Œæ???>= ?¾åœ¨?ç??€?©ä?ç­?
                next_item = None
                for item in today_schedule:
                    if item['pushed']:
                        continue
                    scheduled = item['scheduled_time']
                    try:
                        datetime.strptime(scheduled, "%H:%M")  # é©—è??¼å?
                        next_item = item
                        break
                    except ValueError as e:
                        logger.warning(f"??[{self.__class__.__name__}] ?¡æ?è§???’ç??‚é? '{scheduled}': {e}")
                    except Exception as e:
                        logger.error(f"??[{self.__class__.__name__}] ?•ç??’ç??‚é??‚ç™¼?Ÿæœª?æ??¯èª¤ '{scheduled}': {e}", exc_info=True)

                if next_item:
                    scheduled = next_item['scheduled_time']
                    # è¨ˆç?è¦ç¡å¤šä?ï¼ˆç?ï¼?
                    try:
                        sched_dt = datetime.strptime(scheduled, "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                        )
                    except ValueError as e:
                        logger.warning(f"??[{self.__class__.__name__}] ?¡æ?è§???’ç??‚é? '{scheduled}' è¨ˆç??¡ç??‚é?: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"??[{self.__class__.__name__}] ?•ç??’ç??‚é??‚ç™¼?Ÿæœª?æ??¯èª¤ '{scheduled}' è¨ˆç??¡ç??‚é?: {e}", exc_info=True)
                        continue
                    sleep_seconds = (sched_dt - now).total_seconds()

                    # ?? ?¹æ?ï¼šæ???30 ç§’å??’é???APIï¼Œç??°æ?é»å??¼é€?
                    # ?¿å??å??¨é€ï?API ?¯èƒ½?„æ??´æ–°ï¼‰ï?ä¹Ÿé¿?å»¶??
                    preheat_seconds = max(0, sleep_seconds - 30)

                    # ?¡åˆ°?ç†±?‚é?ï¼ˆæ?å¤šç¡ 24 å°æ??²å?ï¼?
                    if preheat_seconds > 0:
                        logger.info(f"?˜´ [_schedule_dispatcher] ä¸‹ä?æª?{scheduled}ï¼Œç¡ {preheat_seconds:.0f} ç§’ï??å? 30s ?ç†±ï¼?)
                        await asyncio.sleep(min(preheat_seconds, 86400))

                    # ?ç†±ï¼šæ???fetch APIï¼Œè?å·´å??‰æ??“å???
                    logger.info(f"?”¥ [_schedule_dispatcher] ?ç†± {scheduled}ï¼Œæ???fetch API...")
                    preheat_episodes = await self.fetch_new_anime_from_api()
                    if preheat_episodes:
                        logger.info(f"?”¥ [_schedule_dispatcher] ?ç†±å®Œæ?ï¼ŒAPI ?å‚³ {len(preheat_episodes)} ç­?)
                    else:
                        logger.warning(f"? ï? [_schedule_dispatcher] ?ç†± API ?¡å??‰ï?ç¨å??¨é€æ??ƒé?è©?)

                    # ç­‰åˆ°æº–é?ï¼ˆå‰©é¤˜ç? 30 ç§’ï?
                    now = datetime.now(TW_TZ)
                    remaining = (sched_dt - now).total_seconds()
                    if remaining > 0:
                        logger.info(f"??[_schedule_dispatcher] ç­‰å? {remaining:.0f} ç§’åˆ°æº–é? {scheduled}")
                        await asyncio.sleep(remaining)

                    # æº–é??¨é€?
                    now = datetime.now(TW_TZ)
                    logger.info(f"??[_schedule_dispatcher] æº–é? {scheduled}ï¼Œæ¨?ï??¶å? {now.strftime('%H:%M:%S')}ï¼?)

                    # ?³å…¥?ç†±çµæ?ï¼Œé¿??send_anime_push ?è??¼å« API
                    success = await self.send_anime_push(
                        scheduled, ANIME_CHANNEL_ID,
                        prefetched_episodes=preheat_episodes
                    )
                    if success:
                        logger.info(f"??[_schedule_dispatcher] {scheduled} ?¨é€æ???)
                    else:
                        # API å°šæœª?´æ–°?–æ?æ®µç„¡?¹é? ???­æš«ç­‰å?å¾Œé?è©¦ç•¶?æ???
                        logger.warning(f"? ï? [_schedule_dispatcher] {scheduled} ?¨é€æœªå®Œæ?ï¼?0s å¾Œé?è©?..")
                        await asyncio.sleep(30)
                        # ?è©¦?‚ä?ä½¿ç”¨?ç†±è³‡æ?ï¼Œè? send_anime_push ?æ–° fetch API
                        success = await self.send_anime_push(scheduled, ANIME_CHANNEL_ID)
                        if success:
                            logger.info(f"??[_schedule_dispatcher] {scheduled} ?è©¦?å?")
                        else:
                            logger.warning(f"? ï? [_schedule_dispatcher] {scheduled} ?è©¦ä»å¤±?—ï??™çµ¦ catchup ?•ç?")
                        # ??5 ?†é??¿å??¡é??è©¦ï¼Œè? catchup ?¨ä?ä¸€è¼ªè???
                        await asyncio.sleep(300)
                else:
                    # ä»Šå¤©æ²’æ?å¾…æ¨?é??????¡åˆ°?å¤© 00:00 ?æ–°è¼‰å…¥?‚ç?
                    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    sleep_seconds = (tomorrow - now).total_seconds()
                    logger.info(f"?˜´ [_schedule_dispatcher] ä»Šæ—¥?¡å??¨é??®ï??¡åˆ°?å¤© 00:00 ({sleep_seconds:.0f} ç§?")
                    await asyncio.sleep(sleep_seconds)

            except asyncio.CancelledError:
                logger.info("?? [_schedule_dispatcher] ä»»å?è¢«å?æ¶?)
                break
            except Exception as e:
                logger.error(f"??[_schedule_dispatcher] ?°å¸¸: {e}", exc_info=True)
                await asyncio.sleep(60)  # ?¯èª¤?‚ä???1 ?†é??¿å??‚è¿´??

    @tasks.loop(hours=24)
    async def refresh_weekly_schedule(self):
        """æ¯å¤©?šä? 22:00 ?‰å?å®Œæ•´?±è¡¨?¨é?è¦†è?ï¼Œä¸¦æª¢æŸ¥ä»Šæ—¥ <=22:00 ?„æ??¨é??®é€²è?è£œæ¨"""
        result = await self.schedule_tracker.refresh_weekly_schedule()

        if not result.get('success'):
            if result.get('skipped'):
                return  # ??22:00 ?œé?è·³é?
            logger = logging.getLogger(__name__)
            logger.error(f"??[refresh_weekly_schedule] ?±è¡¨?·æ–°å¤±æ?: {result.get('error')}")
            return

        # ?±è¡¨?·æ–°?å?ï¼Œæª¢?¥ä??¥å·²?å»/?¶å??‚åˆ»(<=22:00)ä¸”æœª?¨é€ç??…ç›®?²è?è£œæ¨
        today_schedule = result.get('today_schedule', [])
        now = datetime.now(TW_TZ)
        current_time_str = now.strftime("%H:%M")

        logger = logging.getLogger(__name__)
        logger.info(f"??[refresh_weekly_schedule] ?±è¡¨?·æ–°å®Œæ?ï¼Œæª¢?¥è??¨é??®ï??¾åœ¨ {current_time_str}ï¼?)

        # ç¯©é¸ï¼špushed=0 ä¸?scheduled_time <= 22:00ï¼ˆä?å¤©ç??¨é€æ?æ®µå·²çµæ?ï¼?
        missed = []
        for item in today_schedule:
            if item['pushed']:
                continue
            scheduled = item['scheduled_time']
            try:
                # ?…è???<= ?¶å??‚é?ï¼?2:00 ?·è??‚ï??¶å??³ç‚º 22:xxï¼Œæ?ä»?<=22:00 ?³ç‚ºä»Šæ—¥å·²é??»æ?æ®µï?
                if scheduled <= current_time_str:
                    missed.append(item)
            except Exception as e:
                logger.error(f"??[refresh_weekly_schedule] ?•ç??‚åˆ»?‚ç™¼?ŸéŒ¯èª?'{scheduled}': {e}", exc_info=True)

        if missed:
            missed_sorted = sorted(missed, key=lambda x: x['scheduled_time'])
            logger.info(f"?“º [refresh_weekly_schedule] ?¼ç¾ {len(missed_sorted)} ?‹æ??¨æ??»ï??‹å?è£œæ¨")
            for item in missed_sorted:
                await self.send_anime_push(item['scheduled_time'], ANIME_CHANNEL_ID)
                await asyncio.sleep(2)
        else:
            logger.info(f"?¹ï? [refresh_weekly_schedule] ä»Šæ—¥?¡æ??¨é???)

    @tasks.loop(hours=6)
    async def sync_episode_stats(self):
        """?ªå??¼é€é€±çµ±è¨?- æ¯é€±å¤© ?°ç£?‚é? 23:00 ?¼é€?- å·²å??¨ï?è¢«æ??¥æª¢?¥å?ä»?""
        # æ­¤å??½å·²è¢?daily_anime_check ?–ä»£
        pass

    # ==================== ä»»å??Ÿå??ŒéŒ¯èª¤è???====================

    @refresh_weekly_schedule.before_loop
    async def before_refresh_weekly_schedule(self):
        """ç­‰å? bot å°±ç?ï¼Œä¸¦å°é??°æ?å¤©æ?ä¸?22:00 ?·è?"""
        logger = logging.getLogger(__name__)
        max_retries = 3
        retry_delay = 10  # ç§?

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"?? [before_refresh_weekly_schedule] ?—è©¦?Ÿå? (ç¬?{attempt}/{max_retries} æ¬?")

                # ç­‰å? bot readyï¼Œè¨­ timeout ?²æ­¢æ°¸é??¡ä?
                try:
                    await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
                    logger.info("??[before_refresh_weekly_schedule] bot ready")
                except asyncio.TimeoutError:
                    logger.error("??[before_refresh_weekly_schedule] wait_until_ready() timeout 60s")
                    raise

                # è¨ˆç?è·é›¢ä¸‹ä?æ¬?22:00 ?„ç???
                now = datetime.now(TW_TZ)
                next_run = now.replace(hour=22, minute=0, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)

                sleep_seconds = (next_run - now).total_seconds()
                logger.info(f"??[refresh_weekly_schedule] é¦–æ¬¡?·è?å°‡åœ¨ {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({sleep_seconds:.0f} ç§’å?)")

                # ?¡ç??´åˆ°?®æ??‚é?ï¼Œå¯è¢«å?æ¶?
                await asyncio.sleep(sleep_seconds)
                logger.info("??[before_refresh_weekly_schedule] å°é?å®Œæ?ï¼Œä»»?™å³å°‡é?å§?)
                return  # ?å??Ÿå?ï¼Œé›¢?‹é?è©¦è¿´??

            except asyncio.CancelledError:
                logger.info("?? [before_refresh_weekly_schedule] ä»»å?è¢«å?æ¶?)
                raise
            except Exception as e:
                logger.error(f"??[before_refresh_weekly_schedule] ç¬?{attempt} æ¬¡å?è©¦å¤±?? {e}", exc_info=True)
                if attempt < max_retries:
                    logger.info(f"??[before_refresh_weekly_schedule] {retry_delay} ç§’å??è©¦...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.critical(f"?’¥ [before_refresh_weekly_schedule] ?è©¦ {max_retries} æ¬¡å?å¤±æ?ï¼Œä»»?™å?ä¸æ??Ÿå?ï¼?)
                    raise

    @refresh_weekly_schedule.error
    async def refresh_weekly_schedule_error(self, error):
        """?•ç?ä»»å??°å¸¸"""
        logger = logging.getLogger(__name__)
        logger.error(f"??[refresh_weekly_schedule] ä»»å??°å¸¸: {error}", exc_info=True)

    @sync_episode_stats.before_loop
    async def before_sync_episode_stats(self):
        """ç­‰å? bot å°±ç?"""
        logger = logging.getLogger(__name__)
        max_retries = 3
        retry_delay = 10

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"?? [before_sync_episode_stats] ?—è©¦?Ÿå? (ç¬?{attempt}/{max_retries} æ¬?")
                await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
                logger.info("??[before_sync_episode_stats] bot ready")
                return
            except asyncio.CancelledError:
                logger.info("?? [before_sync_episode_stats] ä»»å?è¢«å?æ¶?)
                raise
            except asyncio.TimeoutError:
                logger.error(f"??[before_sync_episode_stats] ç¬?{attempt} æ¬?wait_until_ready() timeout")
            except Exception as e:
                logger.error(f"??[before_sync_episode_stats] ç¬?{attempt} æ¬¡å?è©¦å¤±?? {e}", exc_info=True)

            if attempt < max_retries:
                logger.info(f"??[before_sync_episode_stats] {retry_delay} ç§’å??è©¦...")
                await asyncio.sleep(retry_delay)
            else:
                logger.critical(f"?’¥ [before_sync_episode_stats] ?è©¦ {max_retries} æ¬¡å?å¤±æ?ï¼Œä»»?™å?ä¸æ??Ÿå?ï¼?)
                raise

    @sync_episode_stats.error
    async def sync_episode_stats_error(self, error):
        """?•ç?ä»»å??°å¸¸"""
        logger = logging.getLogger(__name__)
        logger.error(f"??[sync_episode_stats] ä»»å??°å¸¸: {error}", exc_info=True)

    # ==================== è¼”åŠ©?¹æ? ====================

    async def _sync_episode_stats_from_api(self):
        """å¾?API ?Œæ­¥?‡é?çµ±è??¸æ?"""
        try:
            # ?²å??€è¿‘ç??•ç•«?¸æ?
            episodes = await self.fetch_all_recent_anime_from_api()
            if not episodes:
                logger = logging.getLogger(__name__)
                logger.warning("? ï? [_sync_episode_stats_from_api] ?¡æ??²å??•ç•«?¸æ?")
                return

            # ?•ç?æ¯é??¸æ?
            processed_count = 0
            for episode in episodes:
                video_sn = episode.get('videoSn')
                anime_sn = episode.get('animeSn')
                episode_num = episode.get('episodeNum', '')
                views = self._extract_view_count_from_episode(episode)
                score = episode.get('score', 0.0)

                if video_sn and anime_sn:
                    self.record_episode_stats(video_sn, anime_sn, episode_num, views, score)
                    processed_count += 1

            logger = logging.getLogger(__name__)
            logger.info(f"?? [_sync_episode_stats_from_api] ?Œæ­¥äº?{processed_count} ç­†å??†çµ±è¨ˆæ•¸??)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"??[_sync_episode_stats_from_api] ?Œæ­¥å¤±æ?: {e}", exc_info=True)

    # ==================== è¼”åŠ©é¡ï?AnimeVoteView (ä¿æ??¨ä¸»é¡ä¸­ï¼Œå??ºå??€è¦å??¨ä¸»é¡? ====================

    class AnimeVoteView(PersistentViewBase):
        """?•ç•«?•ç¥¨è¦–å? - 6 ?‹æ?ç¥¨æ???+ è©•è??‰é? (æ°¸ä?è¦–å?)

        ç¹¼æ‰¿ PersistentViewBase ç¢ºä? timeout=None ä¸”ç¬¦?ˆå?æ¡ˆæ°¸ä¹…è??–è?ç¯„ã€?
        """

        # ?•ç¥¨é¡å??ç½®
        VOTE_TYPES = {
            "masterpiece": ("ç¥ä?", "?Ÿ©"),     # ç¶?
            "great": ("ä½³ä?", "?Ÿ¦"),          # ??
            "darkhorse": ("é»‘é¦¬", "?Ÿª"),      # ç´?
            "decent": ("?®ä?/å°å?", "?Ÿ¨"),    # é»?
            "controversial": ("?­è­°ä½?, "?Ÿ§"), # æ©?
            "disaster": ("?·ä?/ç³ä?", "?Ÿ¥"),   # ç´?
        }

        def __init__(self, episode: Dict, anime_tracker: "AnimeTracker"):
            # æ°¸ä?è¦–å?è¨­ç½®ï¼štimeout=None ??PersistentViewBase ?ªå??•ç?
            super().__init__()
            self.episode = episode
            self.tracker = anime_tracker
            self.video_sn = episode.get("videoSn")
            self.anime_sn = episode.get("animeSn")
            self.message.id if self.message else None = None
            self.last_interaction_time = None  # ?¨æ–¼è¿½è¹¤?€å¾Œä??•æ???

            logger = logging.getLogger(__name__)
            logger.info(f"?? [AnimeVoteView.__init__] ?‹å??µå»ºè¦–å?ï¼Œvideo_sn={self.video_sn}")

            # æ·»å??•ç¥¨?‰é?
            button_count = 0
            for vote_key, (vote_label, color_emoji) in self.VOTE_TYPES.items():
                # ?€?‰æ?ç¥¨æ??•éƒ½?¨ç°??
                button_style = discord.ButtonStyle.secondary  # ?°è‰²

                button = discord.ui.Button(
                    label=f"{color_emoji} {vote_label}",
                    custom_id=f"anime_vote_{vote_key}_{self.video_sn}",
                    style=button_style
                )
                button.callback = self._vote_callback
                self.add_item(button)
                button_count += 1

            logger.info(f"??[AnimeVoteView.__init__] æ·»å?äº?{button_count} ?‹æ?ç¥¨æ???)

            # æ·»å?è©•è??‰é?
            comment_button = discord.ui.Button(
                label="?’¬ ?™è?",
                custom_id=f"anime_comment_{self.video_sn}",
                style=discord.ButtonStyle.secondary  # ?°è‰²
            )
            comment_button.callback = self._comment_callback
            self.add_item(comment_button)

            logger.info(f"??[AnimeVoteView.__init__] æ·»å?äº†è?è«–æ??•ï??®å??±æ? {len(self.children)} ?‹é???)

        async def _vote_callback(self, interaction: discord.Interaction):
            """?•ç??•ç¥¨?‰é?é»æ? - ?•ç¥¨ +2000 KKå¹??æ¯å€‹ç”¨?¶æ?æ¢æ??¯åª?©ç”¨ä¸€æ¬¡ï?"""
            try:
                logger = logging.getLogger(__name__)
                logger.info(f"?¯ [_vote_callback] ?¨æˆ¶ {interaction.user.name}({interaction.user.id}) é»æ??•ç¥¨?‰é?")
                logger.info(f"   custom_id={interaction.custom_id}, message_id={interaction.message.id}")

                # ?? ?œéµï¼šç???defer() ?æ? Discordï¼Œé¿??3 ç§’è???
                await interaction.response.defer()
                logger.info(f"??[_vote_callback] defer() å·²åŸ·è¡?)

                # è¨˜é?äº’å??‚é?
                self.last_interaction_time = datetime.now(TW_TZ)

                # è§???•ç¥¨é¡å?
                vote_key = interaction.custom_id.replace(f"anime_vote_", "").rsplit("_", 1)[0]
                vote_label, _ = self.VOTE_TYPES.get(vote_key, ("?ªçŸ¥", None))

                # ?²å??¨æˆ¶?„åŒ¿?é?æ¹Šï??¨ä??²æ­¢?Œä??¨æˆ¶å¤šæ¬¡?•ç¥¨ï¼?
                user_hash = str(hash(interaction.user.id))[:10]

                # è¨˜é??•ç¥¨ - ä½¿ç”¨ message.id ?ä??–è??–é??Ÿå??€è¦å? storage ?²å?
                message_id = interaction.message.id if interaction.message else None
                vote_recorded = self.tracker.record_vote(
                    video_sn=self.video_sn,
                    anime_sn=self.anime_sn,
                    message_id=message_id,
                    vote_type=vote_key,
                    user_hash=user_hash
                )

                if not vote_recorded:
                    logger.error(f"??[_vote_callback] ?•ç¥¨è¨˜é?å¤±æ? (resource ?å‚³ False): user={interaction.user.name}, vote_key={vote_key}")
                else:
                    logger.info(f"??[_vote_callback] ?•ç¥¨å·²è??? {interaction.user.name} ?•ç¥¨äº?{vote_label}")

                # === KKå¹???µé?è¼?(?•ç¥¨ +2000) ===
                reward_given = False
                try:
                    from db_adapter import set_user_field, get_user_field

                    # æª¢æŸ¥?¯å¦å·²ç™¼?¾é??å‹µ - ä½¿ç”¨ message_id
                    reward_message_id = interaction.message.id if interaction.message else None
                    if reward_message_id and not self.tracker.db.is_reward_already_given(interaction.user.id, reward_message_id, "vote"):
                        # ?²å??¶å? KKå¹?
                        current_kkcoin = get_user_field(interaction.user.id, "kkcoin") or 0
                        new_kkcoin = int(current_kkcoin) + 2000

                        # ?´æ–° KKå¹?
                        set_user_field(interaction.user.id, "kkcoin", new_kkcoin)

                        # è¨˜é??å‹µ?¼æ”¾
                        self.tracker.db.record_reward(
                            user_id=interaction.user.id,
                            message_id=reward_message_id,
                            reward_type="vote",
                            reward_amount=2000
                        )

                        logger.info(f"?’° [_vote_callback] {interaction.user.name} ?•ç¥¨?²å? 2000 KKå¹???¾åœ¨?±æ? {new_kkcoin} KKå¹?)
                        reward_given = True
                    else:
                        logger.info(f"?­ï? [_vote_callback] {interaction.user.name} å·²ç²å¾—é?è©²æ??¯ç??•ç¥¨?å‹µ")
                except ImportError:
                    logger.warning("? ï? [_vote_callback] db_adapter ?ªæ‰¾?°ï??¡æ??å‹µ KKå¹?)
                except Exception as e:
                    logger.error(f"??[_vote_callback] ?å‹µ KKå¹?¤±?? {e}", exc_info=True)

                # ?? ?ˆç™¼??follow-up ç¢ºè?çµ¦ç”¨?¶ï??ªå??æ?ï¼Œé¿?å»¶?²ï?
                try:
                    reward_text = "?’° +2000 KKå¹???µå·²?¼æ”¾ï¼? if reward_given else "?­ï? ?¨å·²?˜å??æ­¤?¨é€ç??•ç¥¨?å‹µ"
                    await interaction.followup.send(
                        f"???•ç¥¨?å?ï¼{vote_label}\n{reward_text}",
                        ephemeral=True
                    )
                    logger.info(f"??[_vote_callback] å·²ç™¼??follow-up ç¢ºè?çµ?{interaction.user.name}")
                except Exception as followup_error:
                    logger.error(f"??[_vote_callback] ?¼é€?follow-up å¤±æ?: {followup_error}")

                # ?´æ–°?Ÿå?æ¶ˆæ¯??embedï¼ˆé??œéµè·¯å?ï¼Œå¤±?—ä?å½±éŸ¿?¨æˆ¶é«”é?ï¼?
                try:
                    message_id = interaction.message.id if interaction.message else None
                    if message_id:
                        await self._update_message_stats(message_id=message_id, channel=interaction.channel)
                    logger.info(f"??[_vote_callback] {interaction.user.name} ?„æ?ç¥¨å·²è¨˜é?ä¸¦æ›´?°æ??¯çµ±è¨?)
                except Exception as update_error:
                    logger.error(f"??[_vote_callback] ?´æ–°æ¶ˆæ¯çµ±è?å¤±æ?: {update_error}", exc_info=True)

            except Exception as e:
                logger.error(f"??[_vote_callback] ?•ç¥¨å¤±æ?: {e}", exc_info=True)
                try:
                    # å¦‚æ?å·²ç? defer ?ä?ï¼Œç”¨ followupï¼›å¦?‡ç”¨ response
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            f"???•ç¥¨å¤±æ?: {str(e)[:50]}", ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"???•ç¥¨å¤±æ?: {str(e)[:50]}", ephemeral=True
                        )
                except:
                    pass

        async def _comment_callback(self, interaction: discord.Interaction):
            """?•ç?è©•è??‰é?é»æ? - å½ˆå‡ºè©•è?è¼¸å…¥æ¡?""
            try:
                logger = logging.getLogger(__name__)
                # è¨˜é?äº’å??‚é?
                self.last_interaction_time = datetime.now(TW_TZ)

                # ?•ç²å¤–éƒ¨ self (AnimeVoteView) ä¾›å…§?¨é??¥ä½¿??
                outer_self = self

                # ?µå»ºç°¡å–®?„æ??¬è¼¸?¥æ¨¡?‹æ?
                class CommentModal(discord.ui.Modal, title="?™ä??¿å?è©•è?"):
                    comment_input = discord.ui.TextInput(
                        label="è©•è??§å®¹",
                        placeholder="å¯«ä?ä½ å??™éƒ¨?•ç•«?„ç?æ³?..",
                        max_length=200,
                        required=False
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        try:
                            comment = str(self.comment_input).strip()
                            if not comment:
                                await modal_interaction.response.send_message("è©•è?ä¸èƒ½?ºç©º", ephemeral=True)
                                return

                            # ?²å??¨æˆ¶?¿å??œæ?
                            user_hash = str(hash(modal_interaction.user.id))[:10]

                            # è¨˜é?è©•è?ï¼ˆvote_type ?ºç©ºè¡¨ç¤º?ªæ˜¯è©•è?ï¼?- ä½¿ç”¨ message_id
                            message_id = modal_interaction.message.id if modal_interaction.message else None
                            vote_recorded = outer_self.tracker.record_vote(
                                video_sn=outer_self.video_sn,
                                anime_sn=outer_self.anime_sn,
                                message_id=message_id,
                                vote_type="comment",
                                comment=comment,
                                user_hash=user_hash
                            )

                            if not vote_recorded:
                                logger.error(f"??[comment_submit] è©•è?è¨˜é?å¤±æ? (resource ?å‚³ False): user={modal_interaction.user}")
                            else:
                                logger.info(f"?’¬ [comment] {modal_interaction.user} ?™è?: {comment[:30]}...")

                            # === KKå¹???µé?è¼?(è©•è? +3000) ===
                            reward_message = "??è©•è?å·²ä?å­˜ï??Ÿè?ä½ ç??è?"
                            try:
                                from db_adapter import set_user_field, get_user_field

                                # æª¢æŸ¥?¯å¦å·²ç™¼?¾é??å‹µ
                                if not outer_self.tracker.db.is_reward_already_given(modal_interaction.user.id, modal_interaction.message.id, "comment"):
                                    # ?²å??¶å? KKå¹?
                                    current_kkcoin = get_user_field(modal_interaction.user.id, "kkcoin") or 0
                                    new_kkcoin = int(current_kkcoin) + 3000

                                    # ?´æ–° KKå¹?- ä½¿ç”¨ message_id
                                    message_id_for_reward = modal_interaction.message.id if modal_interaction.message else None
                                    set_user_field(modal_interaction.user.id, "kkcoin", new_kkcoin)

                                    # è¨˜é??å‹µ?¼æ”¾
                                    outer_self.tracker.db.record_reward(
                                        user_id=modal_interaction.user.id,
                                        message_id=message_id_for_reward,
                                        reward_type="comment",
                                        reward_amount=3000
                                    )

                                    logger.info(f"?’° [comment_submit] {modal_interaction.user} è©•è??²å? 3000 KKå¹???¾åœ¨?±æ? {new_kkcoin} KKå¹?)
                                    reward_message = "??è©•è?å·²ä?å­˜ï?\n?’° +3000 KKå¹???µå·²?¼æ”¾"
                                else:
                                    logger.info(f"?­ï? [comment_submit] {modal_interaction.user} å·²ç²å¾—é?è©²æ??¯ç?è©•è??å‹µ")
                                    reward_message = "??è©•è?å·²ä?å­˜ï?"
                            except ImportError:
                                logger.warning("? ï? [comment_submit] db_adapter ?ªæ‰¾?°ï??¡æ??å‹µ KKå¹?)
                            except Exception as e:
                                logger.error(f"??[comment_submit] ?å‹µ KKå¹?¤±?? {e}", exc_info=True)

                            await modal_interaction.response.send_message(reward_message, ephemeral=True)

                            # ?´æ–°?Ÿå?æ¶ˆæ¯çµ±è?
                            try:
                                message_id_for_update = modal_interaction.message.id if modal_interaction.message else None
                                if message_id_for_update:
                                    await outer_self._update_message_stats(message_id=message_id_for_update, channel=modal_interaction.channel)
                                logger.info(f"??[comment_submit] {modal_interaction.user} ?„è?è«–å·²ä¿å?ä¸¦æ›´?°æ??¯çµ±è¨?)
                            except Exception as update_error:
                                logger.error(f"??[comment_submit] ?´æ–°æ¶ˆæ¯çµ±è?å¤±æ?: {update_error}", exc_info=True)
                        except Exception as e:
                            logger.error(f"??[comment_submit] ä¿å?è©•è?å¤±æ?: {e}", exc_info=True)
                            try:
                                await modal_interaction.response.send_message(
                                    f"??è©•è?å¤±æ?: {str(e)[:50]}", ephemeral=True
                                )
                            except:
                                pass

                # ?¼é€?Modalï¼ˆåœ¨ _comment_callback ä¸­ï?ä¸åœ¨ on_submit ä¸­ï?
                await interaction.response.send_modal(CommentModal())

            except Exception as e:
                logger.error(f"??[_comment_callback] è©•è?å¤±æ?: {e}", exc_info=True)
                try:
                    await interaction.response.send_message(
                        f"???¡æ??‹å?è©•è?: {str(e)[:50]}", ephemeral=True
                    )
                except:
                    pass

        async def _update_message_stats(self, message_id: int, channel: discord.abc.Messageable = None):
            """?´æ–°æ¶ˆæ¯ä¸­ç??•ç¥¨çµ±è? - ?¯æ??šé? message_id ?²å?æ¶ˆæ¯ï¼ˆæ?ä¹…å?è¦–å??å?å¾Œé?è¦ï?"""
            try:
                logger = logging.getLogger(__name__)

                # ?²å?æ¶ˆæ¯å°è±¡
                message = None
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        logger.info(f"?? [_update_message_stats] å¾é »?“ç²?–æ???ID={message_id}")
                    except discord.NotFound:
                        logger.warning(f"? ï? [_update_message_stats] æ¶ˆæ¯ä¸å???ID={message_id}")
                        return
                    except discord.Forbidden:
                        logger.error(f"??[_update_message_stats] ?¡æ??ç²?–æ???ID={message_id}")
                        return
                    except Exception as e:
                        logger.error(f"??[_update_message_stats] ?²å?æ¶ˆæ¯å¤±æ?: {e}", exc_info=True)
                        return

                if not message:
                    logger.warning(f"? ï? [_update_message_stats] ?¡æ??²å?æ¶ˆæ¯ ID={message_id}")
                    return

                logger.info(f"?? [_update_message_stats] ?‹å??´æ–°æ¶ˆæ¯ ID={message.id}, ?»é? ID={message.channel.id}")

                if not message.embeds:
                    logger.warning(f"? ï? [_update_message_stats] æ¶ˆæ¯æ²’æ? embed, message_id={message.id}")
                    return

                original_embed = message.embeds[0]
                logger.info(f"??[_update_message_stats] ?¾åˆ° embed, æ¨™é?={original_embed.title}")

                # ?²å??•ç¥¨çµ±è??Œè?è«?- ä½¿ç”¨ message_id ?¥è©¢ DB
                stats = self.tracker.get_vote_stats(message_id)
                comments = self.tracker.get_vote_comments(message_id, limit=3)
                logger.info(f"?? [_update_message_stats] ?•ç¥¨çµ±è?: {stats}, è©•è??? {len(comments)}")

                # å»ºç?çµ±è??§å®¹
                stats_content = ""
                if stats and any(stats.values()):
                    stat_lines = []
                    for vote_key, (vote_label, color_block) in self.VOTE_TYPES.items():
                        count = stats.get(vote_key, 0)
                        if count > 0:
                            stat_lines.append(f"{color_block} {vote_label}: {count} ç¥?)
                    stats_content = "\n".join(stat_lines) if stat_lines else ""

                # å»ºç?è©•è??§å®¹
                comments_content = ""
                if comments:
                    comments_content = "\n".join([f"??{c}" for c in comments])

                # ä½¿ç”¨ embeds ?ƒæ•¸?´æ¥ç·¨è¼¯ï¼Œä?ä¿®æ”¹ embed ?©ä»¶?¬èº«
                # ?ˆé??°æ?å»ºå??´ç? embedï¼Œé¿??EmbedProxy åºå??–å?é¡?
                new_embed = discord.Embed(
                    title=original_embed.title,
                    description=original_embed.description,
                    color=original_embed.color,
                    timestamp=original_embed.timestamp
                )

                # è¤‡è£½?Ÿæ??„å?æ®µï??¤ä?çµ±è??Œè?è«?
                for field in original_embed.fields:
                    if field.name not in ["?? ?•ç¥¨çµ±è?", "?’¬ ?¿å?è©•è?"]:
                        new_embed.add_field(name=field.name, value=field.value, inline=field.inline)

                # æ·»å??´æ–°å¾Œç?çµ±è?
                if stats_content:
                    new_embed.add_field(name="?? ?•ç¥¨çµ±è?", value=stats_content, inline=False)

                # æ·»å??´æ–°å¾Œç?è©•è?
                if comments_content:
                    new_embed.add_field(name="?’¬ ?¿å?è©•è?", value=comments_content, inline=False)

                # è¤‡è£½ footer?author ç­‰å…¶ä»–å±¬??
                if original_embed.footer:
                    new_embed.set_footer(text=original_embed.footer.text, icon_url=original_embed.footer.icon_url)
                if original_embed.author:
                    new_embed.set_author(name=original_embed.author.name, url=original_embed.author.url, icon_url=original_embed.author.icon_url)
                if original_embed.image:
                    new_embed.set_image(url=original_embed.image.url)
                if original_embed.thumbnail:
                    new_embed.set_thumbnail(url=original_embed.thumbnail.url)

                # ç·¨è¼¯æ¶ˆæ¯
                logger.info(f"?? [_update_message_stats] æº–å?ç·¨è¼¯æ¶ˆæ¯ ID={message.id}, ?»é?={message.channel.id}, æ¬Šé?={message.channel.permissions_for(message.guild.me) if message.guild else 'DM'}")
                await message.edit(embed=new_embed)
                logger.info(f"??[_update_message_stats] æ¶ˆæ¯å·²æ??Ÿç·¨è¼?ID={message.id}")

            except discord.Forbidden as e:
                logger.error(f"??[_update_message_stats] æ¬Šé?ä¸è¶³ï¼ˆå¯?½ç¼ºå°?MANAGE_MESSAGESï¼? {e}", exc_info=True)
            except discord.NotFound as e:
                logger.error(f"??[_update_message_stats] æ¶ˆæ¯ä¸å??¨æ?å·²è¢«?ªé™¤: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"??[_update_message_stats] ?´æ–°çµ±è?å¤±æ?: {e}", exc_info=True)


    @app_commands.command(name="anime_refresh", description="?? ?‹å??·æ–°?•ç•«?±è¡¨ï¼ˆç??¥è??¨ç”¨ï¼?)
    @app_commands.default_permissions(administrator=True)
    async def anime_refresh(self, interaction: discord.Interaction):
        """?‹å?è§¸ç™¼?±è¡¨?·æ–°ï¼Œè§£æ±ºè‡ª?•åˆ·?°å¤±?—æ?ç·Šæ€¥è??¨é?æ±?""
        await interaction.response.defer(ephemeral=True)
        logger = logging.getLogger(__name__)
        logger.info(f"?? [/anime_refresh] ç®¡ç???{interaction.user} è§¸ç™¼?‹å??±è¡¨?·æ–°")

        try:
            result = await self.refresh_weekly_schedule()

            if result.get('success'):
                embed = discord.Embed(
                    title="???±è¡¨?·æ–°?å?",
                    description=f"?±èµ·å§‹æ—¥?? {result['week_start_date']}\nä»Šæ—¥?‚ç?: {len(result['today_schedule'])} ç­†\nç¸½è?: {result['total_count']} ç­?,
                    color=discord.Color.green()
                )
                # æª¢æŸ¥?¯å¦?‰å??¨é€é???
                pending = sum(1 for item in result['today_schedule'] if not item.get('pushed'))
                if pending > 0:
                    embed.add_field(name="??å¾…è??¨é???, value=f"{pending} ?‹æ??»æœª?¨é€?, inline=False)
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"??[/anime_refresh] ?‹å??·æ–°å®Œæ?: {result['total_count']} ç­?)
            else:
                error = result.get('error', '?ªçŸ¥?¯èª¤')
                skipped = result.get('skipped', False)
                if skipped:
                    await interaction.followup.send("?­ï? è·³é??·æ–°ï¼šé??·è??‚é?ï¼ˆæ?å¤?22:00-22:59ï¼?, ephemeral=True)
                else:
                    await interaction.followup.send(f"???·æ–°å¤±æ?: {error}", ephemeral=True)
                logger.warning(f"? ï? [/anime_refresh] ?‹å??·æ–°å¤±æ?: {error}")
        except Exception as e:
            logger.error(f"??[/anime_refresh] ?°å¸¸: {e}", exc_info=True)
            await interaction.followup.send(f"???·è??°å¸¸: {e}", ephemeral=True)


# ==================== ä»»å??å??…è??½æ•¸ ====================

    async def _wrap_task_with_restart(self, name: str, coro_func):
        """?šç”¨ä»»å??…è??¨ï??°å¸¸?‚è‡ª?•è??„ä¸¦??5 ç§’å??å?"""
        logger = logging.getLogger(__name__)
        while not self.bot.is_closed():
            try:
                await coro_func()
            except asyncio.CancelledError:
                logger.info(f"?? [{name}] ä»»å?è¢«å?æ¶?)
                break
            except Exception as e:
                logger.error(f"??[{name}] ä»»å??°å¸¸çµ‚æ­¢ï¼? ç§’å??å?: {e}", exc_info=True)
                await asyncio.sleep(5)
                if not self.bot.is_closed():
                    logger.info(f"?? [{name}] ?å?ä»»å?...")


async def setup(bot: commands.Bot):
    """Setup ?½æ•¸ä¾?Discord.py ? è? Cog"""
    await bot.add_cog(AnimeTracker(bot))




