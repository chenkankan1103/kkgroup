)
                conn.commit()
                logger.info(f"📈 Updated stats for {anime_name}: {total_ep} eps, avg_views={avg_views:.0f}, avg_score={avg_score:.1f}")
        except Exception as e:
            logger.error(f"❌ Error updating anime statistics: {e}")

    def get_top_anime_by_views(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """獲取觀看次數最多的動畫排行（直接從 episode_statistics 聚合）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                where_clauses = []
                params = []

                if start_time:
                    where_clauses.append("recorded_at >= ?")
                    params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

                if end_time:
                    where_clauses.append("recorded_at < ?")
                    params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                # 直接從 episode_statistics 聚合，而不是等待 anime_statistics 更新
                cursor.execute(f"""
                    SELECT
                        animeSn,
                        COUNT(*) as total_episodes,
                        SUM(views) as total_views,
                        AVG(views) as avg_views,
                        AVG(score) as avg_score
                    FROM {EPISODE_STATS_TABLE}
                    {where_sql}
                    GROUP BY animeSn
                    ORDER BY total_views DESC LIMIT ?
                """, (*params, limit))

                results = []
                for row in cursor.fetchall():
                    anime_sn = row[0]
                    # 先從 anime_details 查詢名稱（最新數據），再從 anime_notified 查詢
                    anime_name = None

                    cursor.execute(f"""
                        SELECT title FROM {ANIME_DETAILS_TABLE}
                        WHERE animeSn = ? ORDER BY cached_at DESC LIMIT 1
                    """, (anime_sn,))
                    detail_row = cursor.fetchone()
                    if detail_row:
                        anime_name = detail_row[0]

                    # 如果 anime_details 沒有，再從 anime_notified 查詢
                    if not anime_name:
                        cursor.execute(f"""
                            SELECT anime_name FROM {NOTIFIED_TABLE}
                            WHERE animeSn = ? LIMIT 1
                        """, (anime_sn,))
                        notified_row = cursor.fetchone()
                        anime_name = notified_row[0] if notified_row else None

                    # 最後還是沒有就用預設名稱
                    if not anime_name:
                        anime_name = f"Anime #{anime_sn}"

                    results.append({
                        "anime_sn": anime_sn,
                        "name": anime_name,
                        "total_views": row[2] or 0,
                        "avg_views": row[3] or 0,
                        "avg_score": row[4] or 0,
                        "total_episodes": row[1] or 0
                    })

                return results
        except Exception as e:
            logger.error(f"❌ Error getting top anime: {e}")
            return []

    def get_multi_episode_anime_for_chart(
        self,
        limit: int = 10,
        min_episodes: int = 1,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """獲取有多集數據的動畫（用於多線坐標圖），按總觀看次數排序
        改進：降低 min_episodes 預設值為 1，讓更多動畫能納入統計

        Returns:
            [{
                "anime_sn": int,
                "name": str,
                "cover_url": str,  # 新增：動畫封面 URL
                "short_name": str,  # 新增：動畫簡稱（前 2 個字符）
                "episodes": [{"num": str, "views": int}, ...],
                "total_views": int,
                "total_episodes": int
            }, ...]
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                where_clauses = []
                params = []

                if start_time:
                    where_clauses.append("recorded_at >= ?")
                    params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

                if end_time:
                    where_clauses.append("recorded_at < ?")
                    params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                # 確保表存在
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {EPISODE_STATS_TABLE} (
                        videoSn INTEGER PRIMARY KEY,
                        animeSn INTEGER NOT NULL,
                        episode_num TEXT,
                        views INTEGER,
                        score REAL,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 先獲取所有有多於 min_episodes 的動畫
                cursor.execute(f"""
                    SELECT
                        animeSn,
                        COUNT(*) as total_episodes,
                        SUM(views) as total_views
                    FROM {EPISODE_STATS_TABLE}
                    {where_sql}
                    GROUP BY animeSn
                    HAVING COUNT(*) >= ?
                    ORDER BY total_views DESC LIMIT ?
                """, (*params, min_episodes, limit))

                results = []
                for row in cursor.fetchall():
                    anime_sn = row[0]
                    total_episodes = row[1]
                    total_views = row[2] or 0

                    # 獲取動畫名稱和封面 URL
                    anime_name = None
                    cover_url = None

                    cursor.execute(f"""
                        SELECT title FROM {ANIME_DETAILS_TABLE}
                        WHERE animeSn = ? ORDER BY cached_at DESC LIMIT 1
                    """, (anime_sn,))
                    detail_row = cursor.fetchone()
                    if detail_row:
                        anime_name = detail_row[0]

                    if not anime_name:
                        cursor.execute(f"""
                            SELECT anime_name, cover_url FROM {NOTIFIED_TABLE}
                            WHERE animeSn = ? LIMIT 1
                        """, (anime_sn,))
                        notified_row = cursor.fetchone()
                        if notified_row:
                            anime_name = notified_row[0]
                            cover_url = notified_row[1] if len(notified_row[2] if len(notified_row) > 2 else None
                        else:
                            anime_name = f"Anime #{anime_sn}"

                    # 如果還沒有 cover_url，嘗試從 NOTIFIED_TABLE 獲取
                    if not cover_url:
                        cursor.execute(f"""
                            SELECT cover_url FROM {NOTIFIED_TABLE}
                            WHERE animeSn = ? ORDER BY notified_at DESC LIMIT 1
                        """, (anime_sn,))
                        cover_row = cursor.fetchone()
                        if cover_row and cover_row[0]:
                            cover_url = cover_row[0]

                    # 生成動畫簡稱（前 2 個字符）
                    short_name = anime_name[:2] if len(anime_name) >= 2 else anime_name

                    # 獲取該動畫的所有集集數據（按集數排序）
                    episode_where = ["animeSn = ?"]
                    episode_params = [anime_sn]

                    if start_time:
                        episode_where.append("recorded_at >= ?")
                        episode_params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

                    if end_time:
                        episode_where.append("recorded_at < ?")
                        episode_params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

                    cursor.execute(f"""
                        SELECT episode_num, views FROM {EPISODE_STATS_TABLE}
                        WHERE {' AND '.join(episode_where)}
                        ORDER BY episode_num ASC
                    """, tuple(episode_params))

                    episodes = []
                    for ep_row in cursor.fetchall():
                        ep_num = ep_row[0] or "?"
                        views = ep_row[1] or 0
                        episodes.append({"num": ep_num, "views": views})

                    results.append({
                        "anime_sn": anime_sn,
                        "name": anime_name,
                        "cover_url": cover_url,
                        "short_name": short_name,
                        "episodes": episodes,
                        "total_views": total_views,
                        "total_episodes": total_episodes
                    })

                logger.info(f"📊 [get_multi_episode_anime_for_chart] 找到 {len(results)} 部有多集數據的動畫")
                return results
        except Exception as e:
            logger.error(f"❌ Error getting multi-episode anime for chart: {e}", exc_info=True)
            return []

    def record_vote(self, video_sn: int, anime_sn: int, message_id: int, vote_type: str, comment: str = None, user_hash: str = None):
        """記錄匿名投票"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT INTO {ANIME_VOTES_TABLE}
                    (videoSn, animeSn, message_id, vote_type, comment, user_hash, voted_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (video_sn, anime_sn, message_id, vote_type, comment, user_hash))
                conn.commit()
                logger.info(f"📊 [record_vote] 記錄投票: videoSn={video_sn}, vote_type={vote_type}")
        except Exception as e:
            logger.error(f"❌ Error recording vote: {e}", exc_info=True)

    def get_vote_stats(self, message_id: int) -> Dict:
        """獲取某條消息的投票統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT vote_type, COUNT(*) as count FROM {ANIME_VOTES_TABLE}
                    WHERE message_id = ?
                    GROUP BY vote_type
                    ORDER BY count DESC
                """, (message_id,))

                stats = {}
                for row in cursor.fetchall():
                    stats[row[0]] = row[1]

                return stats
        except Exception as e:
            logger.error(f"❌ Error getting vote stats: {e}")
            return {}

    def get_vote_comments(self, message_id: int, limit: int = 5) -> List[str]:
        """獲取某條消息的匿名評論"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT comment FROM {ANIME_VOTES_TABLE}
                    WHERE message_id = ? AND comment IS NOT NULL
                    ORDER BY voted_at DESC
                    LIMIT ?
                """, (message_id, limit))

                comments = [row[0] for row in cursor.fetchall() if row[0]]
                return comments
        except Exception as e:
            logger.error(f"❌ Error getting vote comments: {e}")
            return []

    def get_weekly_vote_stats(self) -> Dict[int, Dict]:
        """獲取本週的投票統計（按動畫分組）

        Returns:
            {
                animeSn: {
                    'anime_name': 'xxx',
                    'total_votes': 10,
                    'votes': {'masterpiece': 3, 'great': 2, ...},
                    'episodes': set([videoSn1, videoSn2, ...])
                },
                ...
            }
        """
        try:
            from datetime import datetime, timedelta

            # 計算本週一零時（台灣時區）
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())  # 週一
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 獲取本週的投票
                cursor.execute(f"""
                    SELECT animeSn, videoSn, vote_type, COUNT(*) as count
                    FROM {ANIME_VOTES_TABLE}
                    WHERE voted_at >= ?
                    GROUP BY animeSn, videoSn, vote_type
                    ORDER BY animeSn, count DESC
                """, (week_start.isoformat(),))

                # 組織數據
                stats = {}
                for anime_sn, video_sn, vote_type, count in cursor.fetchall():
                    if anime_sn not in stats:
                        stats[anime_sn] = {
                            'votes': {},
                            'episodes': set(),
                            'total_votes': 0
                        }

                    stats[anime_sn]['votes'][vote_type] = stats[anime_sn]['votes'].get(vote_type, 0) + count
                    stats[anime_sn]['episodes'].add(video_sn)
                    stats[anime_sn]['total_votes'] += count

                # 補充動畫名稱
                for anime_sn in stats:
                    anime_details = self.get_anime_details(anime_sn)
                    if anime_details:
                        stats[anime_sn]['anime_name'] = anime_details.get('title', f'動畫 {anime_sn}')
                    else:
                        stats[anime_sn]['anime_name'] = f'動畫 {anime_sn}'

                return stats
        except Exception as e:
            logger.error(f"❌ Error getting weekly vote stats: {e}", exc_info=True)
            return {}

    def record_reward(self, user_id: int, message_id: int, reward_type: str, reward_amount: int) -> bool:
        """記錄 KK幣獎勵 - 防止重複發放"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT INTO {ANIME_REWARDS_TABLE}
                    (user_id, message_id, reward_type, reward_amount, awarded_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, message_id, reward_type, reward_amount))
                conn.commit()
                logger.info(f"💰 [record_reward] user_id={user_id}, message_id={message_id}, type={reward_type}, amount={reward_amount}")
                return True
        except sqlite3.IntegrityError:
            # 該用戶在該消息上已獲得過此類型的獎勵
            logger.info(f"⏭️ [record_reward] user_id={user_id} 已獲得過 {reward_type} 獎勵")
            return False
        except Exception as e:
            logger.error(f"❌ Error recording reward: {e}")
            return False

    def is_reward_already_given(self, user_id: int, message_id: int, reward_type: str) -> bool:
        """檢查是否已發放過獎勵"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {ANIME_REWARDS_TABLE}
                    WHERE user_id = ? AND message_id = ? AND reward_type = ?
                """, (user_id, message_id, reward_type))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Error checking reward: {e}")
            return False

    def is_time_checked_today(self, scheduled_time: str, check_date=None) -> bool:
        """檢查某個時刻在指定日期是否已檢查過（防止重複檢查）

        Args:
            scheduled_time: 預定時刻, 格式 "HH:MM"
            check_date: 檢查日期, 如果為 None 使用今天（台灣時區）

        Returns:
            bool: 如果已檢查過則返回 True，否則返回 False
        """
        try:
            if check_date is None:
                check_date = datetime.now(TW_TZ).date()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {ANIME_CHECK_HISTORY_TABLE}
                    WHERE check_date = ? AND scheduled_time = ?
                """, (check_date, scheduled_time))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Error checking time history: {e}")
            return False

    def mark_time_checked(self, scheduled_time: str, check_date=None) -> bool:
        """標記某個時刻已檢查過（用於防止重複檢查）

        Args:
            scheduled_time: 預定時刻, 格式 "HH:MM"
            check_date: 檢查日期, 如果為 None 使用今天（台灣時區）

        Returns:
            bool: 如果成功標記則返回 True，否則返回 False
        """
        try:
            if check_date is None:
                check_date = datetime.now(TW_TZ).date()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR IGNORE INTO {ANIME_CHECK_HISTORY_TABLE}
                    (check_date, scheduled_time, checked_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (check_date, scheduled_time))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error marking time checked: {e}")
            return False

    def save_message_info(self, message_id: int, video_sn: int, anime_sn: int, anime_name: str, channel_id: int) -> bool:
        """保存消息 ID 以用於 bot 重啟時恢復 view"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {ANIME_MESSAGES_TABLE}
                    (message_id, videoSn, animeSn, anime_name, channel_id, sent_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (message_id, video_sn, anime_sn, anime_name, channel_id))
                conn.commit()
                logger.info(f"💾 [save_message_info] message_id={message_id}, video_sn={video_sn}, anime_name={anime_name}")
                return True
        except Exception as e:
            logger.error(f"❌ Error saving message info: {e}")
            return False

    def get_all_message_infos(self) -> List[Dict]:
        """獲取所有已保存的消息 ID，用於 bot 重啟時恢復"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT message_id, videoSn, animeSn, anime_name, channel_id
                    FROM {ANIME_MESSAGES_TABLE}
                    ORDER BY sent_at DESC
                """)
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "message_id": row[0],
                        "video_sn": row[1],
                        "anime_sn": row[2],
                        "anime_name": row[3],
                        "channel_id": row[4]
                    })
                return results
        except Exception as e:
            logger.error(f"❌ Error getting message infos: {e}")
            return []

    def save_weekly_schedule(self, week_start_date: str, schedule_data: List[Dict]) -> bool:
        """儲存每週的完整時程表

        Args:
            week_start_date: 週一日期 (YYYY-MM-DD)
            schedule_data: 每日時程表 [{day_of_week: 1-7, scheduled_time: "HH:MM", anime_data: {...}}]
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                saved_count = 0
                for entry in schedule_data:
                    # 提取 animeSn 作為組合唯一鍵的一部分（允許同一時刻多部動畫）
                    anime_sn = entry['anime_data'].get('animeSn', 0) or 0
                    cursor.execute(f"""
                        INSERT OR REPLACE INTO {ANIME_WEEKLY_SCHEDULE_TABLE}
                        (week_start_date, day_of_week, scheduled_time, anime_sn, anime_data, pushed)
                        VALUES (?, ?, ?, ?, ?, 0)
                    """, (
                        week_start_date,
                        entry['day_of_week'],
                        entry['scheduled_time'],
                        anime_sn,
                        json.dumps(entry['anime_data'], ensure_ascii=False)
                    ))
                    saved_count += 1
                conn.commit()
                logger.info(f"✅ [save_weekly_schedule] 週表已保存: {week_start_date}, {saved_count} 筆")
                return True
        except Exception as e:
            logger.error(f"❌ Error saving weekly schedule: {e}", exc_info=True)
            return False

    def get_today_schedule(self) -> List[Dict]:
        """獲取今天的時程表（從週表中）"""
        try:
            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())  # 取得本週一的日期
            day_of_week = (now.weekday() + 1) % 7 or 7  # 1=Mon, 7=Sun

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT scheduled_time, anime_data, pushed FROM {ANIME_WEEKLY_SCHEDULE_TABLE}
                    WHERE week_start_date = ? AND day_of_week = ?
                    ORDER BY scheduled_time ASC
                """, (week_start.strftime("%Y-%m-%d"), day_of_week))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'scheduled_time': row[0],
                        'anime_data': json.loads(row[1]),
                        'pushed': bool(row[2])
                    })
                return results
        except Exception as e:
            logger.error(f"❌ Error getting today schedule: {e}")
            return []

    def mark_time_pushed(self, week_start_date: str, day_of_week: int, scheduled_time: str) -> bool:
        """標記某個時刻已推送過"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE {ANIME_WEEKLY_SCHEDULE_TABLE}
                    SET pushed = 1
                    WHERE week_start_date = ? AND day_of_week = ? AND scheduled_time = ?
                """, (week_start_date, day_of_week, scheduled_time))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error marking time pushed: {e}")
            return False


# ==================== 匿名投票 View 類 ====================

class AnimeVoteView(discord.ui.View):
    """動畫投票視圖 - 6 個投票按鈕 + 評論按鈕 (永久視圖)"""

    # 投票類型配置
    VOTE_TYPES = {
        "masterpiece": ("神作", "🟩"),     # 綠
        "great": ("佳作", "🟦"),          # 藍
        "darkhorse": ("黑馬", "🟪"),      # 紫
        "decent": ("普作/小品", "🟨"),    # 黃
        "controversial": ("爭議作", "🟧"), # 橙
        "disaster": ("雷作/糞作", "🟥"),   # 紅
    }

    def __init__(self, episode: Dict, anime_tracker: "AnimeTracker"):
        # 永久視圖設置：timeout=None 表示永不超時，persistent=True 表示重啟後依然有效
        super().__init__(timeout=None)
        self.episode = episode
        self.tracker = anime_tracker
        self.video_sn = episode.get("videoSn")
        self.anime_sn = episode.get("animeSn")
        self.message_id = None
        self.last_interaction_time = None  # 用於追蹤最後互動時間

        logger.info(f"📌 [AnimeVoteView.__init__] 開始創建視圖，video_sn={self.video_sn}")

        # 添加投票按鈕
        button_count = 0
        for vote_key, (vote_label, color_emoji) in self.VOTE_TYPES.items():
            # 所有投票按鈕都用灰色
            button_style = discord.ButtonStyle.secondary  # 灰色

            button = discord.ui.Button(
                label=f"{color_emoji} {vote_label}",
                custom_id=f"anime_vote_{vote_key}_{self.video_sn}",
                style=button_style
            )
            button.callback = self._vote_callback
            self.add_item(button)
            button_count += 1

        logger.info(f"✅ [AnimeVoteView.__init__] 添加了 {button_count} 個投票按鈕")

        # 添加評論按鈕
        comment_button = discord.ui.Button(
            label="💬 留言",
            custom_id=f"anime_comment_{self.video_sn}",
            style=discord.ButtonStyle.secondary  # 灰色
        )
        comment_button.callback = self._comment_callback
        self.add_item(comment_button)

        logger.info(f"✅ [AnimeVoteView.__init__] 添加了評論按鈕，目前共有 {len(self.children)} 個項目")

    async def _vote_callback(self, interaction: discord.Interaction):
        """處理投票按鈕點擊 - 投票 +2000 KK幣（每個用戶每條消息只適用一次）"""
        try:
            logger.info(f"🎯 [_vote_callback] 用戶 {interaction.user.name}({interaction.user.id}) 點擊投票按鈕")
            logger.info(f"   custom_id={interaction.custom_id}, message_id={interaction.message.id}")

            # 記錄互動時間
            self.last_interaction_time = datetime.now(TW_TZ)

            # 解析投票類型
            vote_key = interaction.custom_id.replace(f"anime_vote_", "").rsplit("_", 1)[0]
            vote_label, _ = self.VOTE_TYPES.get(vote_key, ("未知", None))

            # 獲取用戶的匿名雜湊（用來防止同一用戶多次投票）
            user_hash = str(hash(interaction.user.id))[:10]

            # 記錄投票
            self.tracker.db.record_vote(
                video_sn=self.video_sn,
                anime_sn=self.anime_sn,
                message_id=interaction.message.id,
                vote_type=vote_key,
                user_hash=user_hash
            )

            logger.info(f"✅ [_vote_callback] 投票已記錄: {interaction.user.name} 投票了 {vote_label}")

            # 立即回應用戶
            logger.info(f"⏳ [_vote_callback] 準備 defer() 響應...")
            await interaction.response.defer()
            logger.info(f"✅ [_vote_callback] defer() 已執行")

            # === KK幣獎勵邏輯 (投票 +2000) ===
            reward_given = False
            try:
                from db_adapter import set_user_field, get_user_field

                # 檢查是否已發放過獎勵
                if not self.tracker.db.is_reward_already_given(interaction.user.id, interaction.message.id, "vote"):
                    # 獲取當前 KK幣
                    current_kkcoin = get_user_field(interaction.user.id, "kkcoin") or 0
                    new_kkcoin = int(current_kkcoin) + 2000

                    # 更新 KK幣
                    set_user_field(interaction.user.id, "kkcoin", new_kkcoin)

                    # 記錄獎勵發放
                    self.tracker.db.record_reward(
                        user_id=interaction.user.id,
                        message_id=interaction.message.id,
                        reward_type="vote",
                        reward_amount=2000
                    )

                    logger.info(f"💰 [vote_callback] {interaction.user} 投票獲得 2000 KK幣，現在共有 {new_kkcoin} KK幣")
                    reward_given = True

                    # 發送獎勵通知
                    try:
                        reward_embed = discord.Embed(
                            title="🎯 投票獎勵",
                            description="感謝你的投票！",
                            color=discord.Color.gold()
                        )
                        reward_embed.add_field(
                            name="獲得獎勵",
                            value="💰 +2000 KK幣",
                            inline=False
                        )
                        reward_embed.add_field(
                            name="目前餘額",
                            value=f"💵 {new_kkcoin} KK幣",
                            inline=False
                        )
                        await interaction.followup.send(embed=reward_ephemeral=True)
                    except:
                        pass
                else:
                    logger.info(f"⏭️ [vote_callback] {interaction.user} 已獲得過該消息的投票獎勵")
            except ImportError:
                logger.warning("⚠️ [vote_callback] db_adapter 未找到，無法獎勵 KK幣")
            except Exception as e:
                logger.error(f"❌ [vote_callback] 獎勵 KK幣失敗: {e}", exc_info=True)

            # 更新原始消息的 embed（添加統計信息）
            try:
                await self._update_message_stats(interaction.message)
                logger.info(f"✅ [_vote_callback] {interaction.user} 的投票已記錄並更新消息統計")
            except Exception as update_error:
                logger.error(f"❌ [_vote_callback] 更新消息統計失敗: {update_error}", exc_info=True)

        except Exception as e:
            logger.error(f"❌ [_vote_callback] 投票失敗: {e}", exc_info=True)
            try:
                await interaction.response.send_message(f"❌ 投票失敗: {str(e)[:50]}", ephemeral=True)
            except:
                pass

    async def _comment_callback(self, interaction: discord.Interaction):
        """處理評論按鈕點擊 - 彈出評論輸入框"""
        try:
            # 記錄互動時間
            self.last_interaction_time = datetime.now(TW_TZ)

            # 創建簡單的文本輸入模態框
            class CommentModal(discord.ui.Modal, title="留下匿名評論"):
                comment_input = discord.ui.TextInput(
                    label="評論內容",
                    placeholder="寫下你對這部動畫的看法...",
                    max_length=200,
                    required=False
                )

                async def on_submit(self, modal_interaction: discord.Interaction):
                    try:
                        comment = str(self.comment_input).strip()
                        if not comment:
                            await modal_interaction.response.send_message("評論不能為空", ephemeral=True)
                            return

                        # 獲取用戶匿名雜湊
                        user_hash = str(hash(modal_interaction.user.id))[:10]

                        # 記錄評論（vote_type 為空表示只是評論）
                        self.modal_tracker.db.record_vote(
                            video_sn=self.modal_video_sn,
                            anime_sn=self.modal_anime_sn,
                            message_id=modal_interaction.message.id,
                            vote_type="comment",
                            comment=comment,
                            user_hash=user_hash
                        )

                        logger.info(f"💬 [comment] {modal_interaction.user} 留言: {comment[:30]}...")

                        # === KK幣獎勵邏輯 (評論 +3000) ===
                        reward_message = "✅ 評論已保存！感謝你的意見"
                        try:
                            from db_adapter import set_user_field, get_user_field

                            # 檢查是否已發放過獎勵
                            if not self.modal_tracker.db.is_reward_already_given(modal_interaction.user.id, modal_interaction.message.id, "comment"):
                                # 獲取當前 KK幣
                                current_kkcoin = get_user_field(modal_interaction.user.id, "kkcoin") or 0
                                new_kkcoin = int(current_kkcoin) + 3000

                                # 更新 KK幣
                                set_user_field(modal_interaction.user.id, "kkcoin", new_kkcoin)

                                # 記錄獎勵發放
                                self.modal_tracker.db.record_reward(
                                    user_id=modal_interaction.user.id,
                                    message_id=modal_interaction.message.id,
                                    reward_type="comment",
                                    reward_amount=3000
                                )

                                logger.info(f"💰 [comment_submit] {modal_interaction.user} 評論獲得 3000 KK幣，現在共有 {new_kkcoin} KK幣")
                                reward_message = "✅ 評論已保存！\n💰 +3000 KK幣獎勵已發放"
                            else:
                                logger.info(f"⏭️ [comment_submit] {modal_interaction.user} 已獲得過該消息的評論獎勵")
                                reward_message = "✅ 評論已保存！"
                        except ImportError:
                            logger.warning("⚠️ [comment_submit] db_adapter 未找到，無法獎勵 KK幣")
                        except Exception as e:
                            logger.error(f"❌ [comment_submit] 獎勵 KK幣失敗: {e}", exc_info=True)

                        await modal_interaction.response.send_message(reward_message, ephemeral=True)

                        # 更新原始消息統計
                        try:
                            await self.modal_update_stats(modal_interaction.message)
                            logger.info(f"✅ [comment_submit] {modal_interaction.user} 的評論已保存並更新消息統計")
                        except Exception as update_error:
                            logger.error(f"❌ [comment_submit] 更新消息統計失敗: {update_error}", exc_info=True)
                    except Exception as e:
                        logger.error(f"❌ [comment_submit] 保存評論失敗: {e}", exc_info=True)

                # 將追蹤和更新函數保存到模態框實例
                modal = CommentModal()
                modal.modal_tracker = self.tracker
                modal.modal_video_sn = self.video_sn
                modal.modal_anime_sn = self.anime_sn
                modal.modal_update_stats = self._update_message_stats

                await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"❌ [_comment_callback] 評論失敗: {e}", exc_info=True)

    async def _update_message_stats(self, message: discord.Message):
        """更新消息中的投票統計"""
        try:
            logger.info(f"📝 [_update_message_stats] 開始更新消息 ID={message.id}, 頻道 ID={message.channel.id}")

            if not message.embeds:
                logger.warning(f"⚠️ [_update_message_stats] 消息沒有 embed, message_id={message.id}")
                return

            original_embed = message.embeds[0]
            logger.info(f"✅ [_update_message_stats] 找到 embed, 標題={original_embed.title}")

            # 獲取投票統計和評論
            stats = self.tracker.db.get_vote_stats(message.id)
            comments = self.tracker.db.get_vote_comments(message.id, limit=3)
            logger.info(f"📊 [_update_message_stats] 投票統計: {stats}, 評論數: {len(comments)}")

            # 建立統計內容
            stats_content = ""
            if stats and any(stats.values()):
                stat_lines = []
                for vote_key, (vote_label, color_block) in self.VOTE_TYPES.items():
                    count = stats.get(vote_key, 0)
                    if count > 0:
                        stat_lines.append(f"{color_block} {vote_label}: {count} 票")
                stats_content = "\n".join(stat_lines) if stat_lines else ""

            # 建立評論內容
            comments_content = ""
            if comments:
                comments_content = "\n".join([f"• {c}" for c in comments])

            # 使用 embeds 參數直接編輯，不修改 embed 物件本身
            # 先重新構建完整的 embed，避免 EmbedProxy 序列化問題
            new_embed = discord.Embed(
                title=original_embed.title,
                description=original_embed.description,
                color=original_embed.color,
                timestamp=original_embed.timestamp
            )

            # 複製原有的字段，除了統計和評論
            for field in original_embed.fields:
                if field.name not in ["📊 投票統計", "💬 匿名評論"]:
                    new_embed.add_field(name=field.name, value=field.value, inline=field.inline)

            # 添加更新後的統計
            if stats_content:
                new_embed.add_field(name="📊 投票統計", value=stats_content, inline=False)

            # 添加更新後的評論
            if comments_content:
                new_embed.add_field(name="💬 匿名評論", value=comments_content, inline=False)

            # 複製 footer、author 等其他屬性
            if original_embed.footer:
                new_embed.set_footer(text=original_embed.footer.text, icon_url=original_embed.footer.icon_url)
            if original_embed.author:
                new_embed.set_author(name=original_embed.author.name, url=original_embed.author.url, icon_url=original_embed.author.icon_url)
            if original_embed.image:
                new_embed.set_image(url=original_embed.image.url)
            if original_embed.thumbnail:
                new_embed.set_thumbnail(url=original_embed.thumbnail.url)

            # 編輯消息
            logger.info(f"🔄 [_update_message_stats] 準備編輯消息 ID={message.id}")
            await message.edit(embed=new_embed)
            logger.info(f"✅ [_update_message_stats] 消息已成功編輯 ID={message.id}")

        except discord.Forbidden as e:
            logger.error(f"❌ [_update_message_stats] 權限不足（可能缺少 MANAGE_MESSAGES）: {e}", exc_info=True)
        except discord.NotFound as e:
            logger.error(f"❌ [_update_message_stats] 消息不存在或已被刪除: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ [_update_message_stats] 更新統計失敗: {e}", exc_info=True)


class AnimeTracker(commands.Cog):
    """Bahamut 動畫追蹤主 Cog"""

    def __init__(self, bot: commands.Bot):
        import sys
        print("[ANIME_INIT_START] 🎬 AnimeTracker.__init__ 開始執行", flush=True)
        sys.stdout.flush()

        logger.info("=" * 50)
        logger.info("📺 [AnimeTracker.__init__] 開始初始化")
        self.bot = bot
        try:
            self.db = AnimeDatabase(ANIME_DB_PATH)
            logger.info(f"✅ [AnimeTracker.__init__] 數據庫已初始化: {ANIME_DB_PATH}")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.__init__] 數據庫初始化失敗: {e}, exc_info=True)
            raise

        self.task_started = False
        self.bootstrap_completed = False
        self.scheduler = None  # APScheduler 實例（可選）

        # 跟踪動畫的檢查狀態（單一窗口檢查）
        # 格式: {"HH:MM": {"checked": bool, "found": bool, "start_time": datetime}}
        self.anime_retry_queue = {}

        # 週統計發送追蹤（防止重複發送）
        self.last_weekly_stats_sent = None  # 上次發送週統計的日期
        # 單次推送最多處理的新集數量，避免阻塞事件循環
        self.MAX_NEW_EPISODES_PER_PUSH = 20
        # 用於週表為空時的API回退節流（避免頻繁呼叫API）
        self._last_fallback_check = None
        # 用於週表為空時的排程取得節流
        self._last_schedule_fallback = None

        # 每日檢查追蹤（防止重複執行）
        self.last_daily_check_date = None  # 上次執行每日檢查的日期

        # 注意：任務將在 cog_load 中由 @tasks.loop 自動啟動
        logger.info("📺 [AnimeTracker.__init__] 任務將在 cog_load 中由 @tasks.loop 啟動")

        logger.info("📺 [AnimeTracker.__init__] AnimeTracker Cog 初始化完成")
        logger.info(f"📺 Bot 已就緒? {bot.is_ready()}")
        logger.info(f"📺 頻道 ID: {ANIME_CHANNEL_ID}")
        logger.info(f"📺 數據庫路徑: {ANIME_DB_PATH}")
        print("[ANIME_INIT_COMPLETE] ✅ AnimeTracker.__init__ 執行完成", flush=True)
        sys.stdout.flush()
        logger.info("=" * 50)

    async def cog_load(self):
        """Cog 加載時啟動任務"""
        import sys
        import time
        start_time = time.perf_counter()
        print("[COG_LOAD_START] 🎬 cog_load() 開始執行", flush=True)
        sys.stdout.flush()

        logger.info("=" * 50)
        logger.info("🎬 [AnimeTracker.cog_load] cog_load() 被調用")

        try:
            # 恢復舊消息的視圖 - 在 bot 重啟時重新註冊所有永久視圖
            print("[COG_LOAD] 嘗試恢復舊消息 view...", flush=True)
            await self._restore_old_message_views()
            print("[COG_LOAD] ✅ 舊消息 view 恢復完成", flush=True)

            # 如果週表為空，立即拉取（解決首次部署/非禮拜天重啟問題）
            print("[COG_LOAD] 檢查週表是否需要初始化...", flush=True)
            await self._init_weekly_schedule_if_empty()
            print("[COG_LOAD] ✅ 週表初始化檢查完成", flush=True)

            # 補推：若 bot 重啟前有未推送的動畫，啟動時補發
            print("[COG_LOAD] 檢查是否有錯過的動畫推送...", flush=True)
            await self._catchup_missed_pushes()
            print("[COG_LOAD] ✅ 補推檢查完成", flush=True)

            # 啟動週統計任務
            print("[COG_LOAD] 檢查 send_weekly_stats 任務狀態", flush=True)
            if not self.send_weekly_stats.is_running():
                print("[COG_LOAD] ✅ 啟動 send_weekly_stats 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 send_weekly_stats 任務")
                try:
                    self.send_weekly_stats.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] send_weekly_stats 已啟動 (is_running={self.send_weekly_stats.is_running()})")
                    print("[COG_LOAD] ✅ send_weekly_stats 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 send_weekly_stats 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 send_weekly_stats 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 send_weekly_stats...")
                        self.send_weekly_stats.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，send_weekly_stats 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，send_weekly_stats 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] send_weekly_stats 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ send_weekly_stats 已在運行", flush=True)

            # 啟動週表刷新任務
            print("[COG_LOAD] 檢查 refresh_weekly_schedule 任務狀態", flush=True)
            if not self.refresh_weekly_schedule.is_running():
                print("[COG_LOAD] ✅ 啟動 refresh_weekly_schedule 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 任務")
                try:
                    self.refresh_weekly_schedule.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] refresh_weekly_schedule 已啟動 (is_running={self.refresh_weekly_schedule.is_running()})")
                    print("[COG_LOAD] ✅ refresh_weekly_schedule 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 refresh_weekly_schedule 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 refresh_weekly_schedule 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 refresh_weekly_schedule...")
                        self.refresh_weekly_schedule.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，refresh_weekly_schedule 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，refresh_weekly_schedule 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] refresh_weekly_schedule 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ refresh_weekly_schedule 已在運行", flush=True)

            # 啟動推送檢查任務（週表模式）
            print("[COG_LOAD] 檢查 check_scheduled_push 任務狀態", flush=True)
            if not self.check_scheduled_push.is_running():
                print("[COG_LOAD] ✅ 啟動 check_scheduled_push 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 check_scheduled_push 任務")
                try:
                    self.check_scheduled_push.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] check_scheduled_push 已啟動 (is_running={self.check_scheduled_push.is_running()})")
                    print("[COG_LOAD] ✅ check_scheduled_push 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 check_scheduled_push 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 check_scheduled_push 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 check_scheduled_push...")
                        self.check_scheduled_push.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，check_scheduled_push 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，check_scheduled_push 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] check_scheduled_push 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ check_scheduled_push 已在運行", flush=True)

            # 啟動週期統計同步任務
            print("[COG_LOAD] 檢查 sync_episode_stats 任務狀態", flush=True)
            if not self.sync_episode_stats.is_running():
                print("[COG_LOAD] ✅ 啦動 sync_episode_stats 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 sync_episode_stats 任務")
                try:
                    self.sync_episode_stats.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] sync_episode_stats 已啟動 (is_running={self.sync_episode_stats.is_running()})")
                    print("[COG_LOAD] ✅ sync_episode_stats 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 sync_episode_stats 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啦動 sync_episode_stats 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 sync_episode_stats...")
                        self.sync_episode_stats.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，sync_episode_stats 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，sync_episode_stats 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] sync_episode_stats 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ sync_episode_stats 已在運行", flush=True)

            # 🆕 啟動每日動畫檢查任務（新增：直接每日API檢查）
            print("[COG_LOAD] 檢查 daily_anime_check 任務狀態", flush=True)
            if not self.daily_anime_check.is_running():
                print("[COG_LOAD] ✅ 啟動 daily_anime_check 任務", flush=True)
                logger.info("🚀 [AnimeTracker.cog_load] 啟動 daily_anime_check 任務（每日直接API檢查）")
                try:
                    self.daily_anime_check.start()
                    logger.info(f"✅ [AnimeTracker.cog_load] daily_anime_check 已啟動 (is_running={self.daily_anime_check.is_running()})")
                    print("[COG_LOAD] ✅ daily_anime_check 已啟動", flush=True)
                except Exception as start_err:
                    logger.error(f"❌ [AnimeTracker.cog_load] 啟動 daily_anime_check 失敗: {start_err}", exc_info=True)
                    print(f"[COG_LOAD] ❌ 啟動 daily_anime_check 失敗: {start_err}", flush=True)
                    # 重試一次
                    try:
                        await asyncio.sleep(1)
                        logger.info("🔄 [AnimeTracker.cog_load] 重試啟動 daily_anime_check...")
                        self.daily_anime_check.start()
                        logger.info("✅ [AnimeTracker.cog_load] 重試成功，daily_anime_check 已啟動")
                        print("[COG_LOAD] ✅ 重試成功，daily_anime_check 已啟動", flush=True)
                    except Exception as retry_err:
                        logger.error(f"❌ [AnimeTracker.cog_load] 重試失敗: {retry_err}", exc_info=True)
                        print(f"[COG_LOAD] ❌ 重試失敗: {retry_err}", flush=True)
            else:
                logger.info(f"⏭️  [AnimeTracker.cog_load] daily_anime_check 已在運行 (is_running=True)")
                print("[COG_LOAD] ⚠️ daily_anime_check 已在運行", flush=True)

            print("[COG_LOAD_END] ✅ cog_load() 執行完成", flush=True)
            sys.stdout.flush()
            logger.info("✅ [AnimeTracker.cog_load] 任務啟動完成")

        except Exception as e:
            import traceback
            error_msg = f"❌ [cog_load] 執行失敗: {e}"
            print(f"[COG_LOAD_ERROR] {error_msg}", flush=True)
            print(f"[COG_LOAD_ERROR] Traceback:\n{traceback.format_exc()}", flush=True)
            logger.error(error_msg, exc_info=True)
            raise
        elapsed = time.perf_counter() - start_time
        logger.info(f"⏱️ [AnimeTracker.cog_load] 總耗時: {elapsed:.2f} 秒")
        print(f"[COG_LOAD_TIMING] 總耗時: {elapsed:.2f} 秒", flush=True)
        logger.info("=" * 50)

    def cog_unload(self):
        """Cog 卸載時停止任務"""
        logger.info("=" * 50)
        logger.info("🛑 [AnimeTracker.cog_unload] cog_unload() 被調用")
        try:
            # ✅ check_new_anime 已移除

            if self.send_weekly_stats.is_running():
                self.send_weekly_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] send_weekly_stats 已停止")

            if self.refresh_weekly_schedule.is_running():
                self.refresh_weekly_schedule.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] refresh_weekly_schedule 已停止")

            if self.check_scheduled_push.is_running():
                self.check_scheduled_push.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] check_scheduled_push 已停止")

            if self.sync_episode_stats.is_running():
                self.sync_episode_stats.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] sync_episode_stats 已停止")

            if self.daily_anime_check.is_running():
                self.daily_anime_check.cancel()
                logger.info("✅ [AnimeTracker.cog_unload] daily_anime_check 已停止")
        except Exception as e:
            logger.error(f"❌ [AnimeTracker.cog_unload] 任務停止失敗: {e}", exc_info=True)
        logger.info("=" * 50)

    async def _catchup_missed_pushes(self):
        """Bot 重啟時標記今日已過時刻為已推送（不進行實際推送），避免重複嘗試"""
        try:
            await self.bot.wait_until_ready()
            now = datetime.now(TW_TZ)
            today_schedule = self.db.get_today_schedule()
            if not today_schedule:
                return

            # 找出今天已過時刻但尚未標記為已推送的項目
            to_mark = []
            for item in today_schedule:
                if item['pushed']:
                    continue
                try:
                    sched_dt = datetime.strptime(item['scheduled_time'], "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day, tzinfo=TW_TZ
                    )
                    if (now - sched_dt).total_seconds() >= 0:  # 已過或當前時刻
                        to_mark.append(item)
                except Exception:
                    pass

            if not to_mark:
                return

            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%Y-%m-%d")
            day_of_week = (now.weekday() + 1) % 7 or 7
            marked_times = []
            for item in to_mark:
                self.db.mark_time_pushed(week_start_str, day_of_week, item['scheduled_time'])
                marked_times.append(item['scheduled_time'])

            logger.info(f"✅ [_catchup_missed_pushes] 已標記 {len(marked_times)} 個過時時刻為已推送：{sorted(set(marked_times))}")
        except Exception as e:
            logger.error(f"❌ [_catchup_missed_pushes] 失敗: {e}", exc_info=True)

    async def _init_weekly_schedule_if_empty(self):
        """如果本週的週表為空，立即從 API 拉取（解決首次部署/非禮拜天重啟問題）"""
        try:
            await self.bot.wait_until_ready()
            today_schedule = self.db.get_today_schedule()
            if today_schedule:
                logger.info(f"✅ [_init_weekly_schedule_if_empty] 週表已有 {len(today_schedule)} 筆，跳過")
                return

            logger.info("🔄 [_init_weekly_schedule_if_empty] 週表為空，立即從 API 拉取...")
            schedule = await self._get_anime_schedule()
            if not schedule:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] 無法拉取時程表 API")
                return

            now = datetime.now(TW_TZ)
            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%Y-%m-%d")

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
                self.db.save_weekly_schedule(week_start_str, schedule_data)
                logger.info(f"✅ [_init_weekly_schedule_if_empty] 週表初始化完成: {len(schedule_data)} 筆")
            else:
                logger.warning("⚠️ [_init_weekly_schedule_if_empty] API 返回空時程表")
        except Exception as e:
            logger.error(f"❌ [_init_weekly_schedule_if_empty] 失敗: {e}", exc_info=True)

    async def _restore_old_message_views(self):
        """用於 bot 重啟時恢復永久視圖"""
        try:
            await self.bot.wait_until_ready()
            message_infos = self.db.get_all_message_infos()
            for info in message_infos:
                # 重新創建視圖並註冊到 bot
                episode = {
                    "videoSn": info['video_sn'],
                    "animeSn": info['anime_sn'],
                    "title": info['anime_name']
                }
                view = await self.generate_anime_view(episode)
                if view:
                    self.bot.add_view(view)
                    logger.info(f"🔄 [_restore_old_message_views] 恢復視圖: message_id={info['message_id']}, video_sn={info['video_sn']}")
            logger.info(f"✅ [_restore_old_message_views] 已恢復 {len(message_infos)} 個永久視圖")
        except Exception as e:
            logger.error(f"❌ [_restore_old_message_views] 失敗: {e}", exc_info=True)

    async def _get_anime_schedule(self) -> dict:
        """從 API 獲取日程表 (newAnimeSchedule)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_ENDPOINT, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as response:
                    if response.status != 200:
                        logger.error(f"❌ API returned status {response.status}")
                        return {}

                    data = await response.json()
                    schedule = data.get("data", {}).get("newAnimeSchedule", {})
                    return schedule
        except Exception as e:
            logger.error(f"❌ Error fetching schedule: {e}")
            return {}

    def _get_expected_check_times(self, schedule: dict, now: datetime) -> list:
        """取得今天和明天的所有預期檢查時刻

        修復: 移除 1 小時過濾，改用日期過濾，防止凌晨時同日時刻被篩除
        例如: 凌晨 03:59 時 01:00 不應被過濾
        """
        check_times = []
        weekday_today = (now.weekday() + 1) % 7 or 7
        weekday_tomorrow = (weekday_today % 7) + 1

        for day_offset, weekday in [(0, str(weekday_today)), (1, str(weekday_tomorrow))]:
            target_date = (now + timedelta(days=day_offset)).date()
            for anime_info in schedule.get(weekday, []):
                schedule_time = anime_info.get("scheduleTime", "")
                if schedule_time:
                    try:
                        scheduled_time = datetime.strptime(schedule_time, "%H:%M").time()
                        scheduled_dt = datetime.combine(target_date, scheduled_time, tzinfo=TW_TZ)
                        # ✅ 改用日期過濾：超過 1 天的時刻才篩除，同日所有時刻都保留
                        # 這防止凌晨時早晨時刻被篩除（例如: 凌晨 03:59 時 01:00 不應被篩除）
                        if scheduled_dt.date() >= (now - timedelta(days=1)).date():
                            check_times.append(scheduled_dt)
                    except:
                        pass

        return sorted(check_times)

    async def _check_and_send_anime(self, scheduled_time_str: str, channel) -> bool:
        """
        檢查新番集並發送通知（用於多窗口檢查）

        Args:
            scheduled_time_str: 預定時刻字符串, 例如 "14:30"
            channel: Discord 頻道物件

        Returns:
            bool: 是否找到並發送了新集
        """
        try:
            # 獲取最新動畫數據
            episodes = await self.fetch_new_anime_from_api()
            if not episodes:
                logger.warning(f"⚠️ [_check_and_send_anime] 無法從 API 獲取數據 (時刻: {scheduled_time_str})")
                return False

            # 檢查新集
            new_episodes = []
            for ep in episodes:
                try:
                    video_sn = ep.get("videoSn")
                    if video_sn and not self.db.is_notified(video_sn):
                        new_episodes.append(ep)
                except Exception as check_err:
                    logger.error(f"❌ [_check_and_send_anime] 檢查集 {ep.get('videoSn')} 時異常: {check_err}", exc_info=True)
                    continue

            if not new_episodes:
                logger.info(f"⏭️  [{scheduled_time_str}] 沒有新集")
                return False

            # 發送新集通知
            logger.info(f"🆕 [{scheduled_time_str}] 發現 {len(new_episodes)} 個新集，開始推播...")
            sent_count = 0

            for ep in new_episodes:
                try:
                    embed = await self.generate_anime_embed(ep)
                    view = await self.generate_anime_view(ep)

                    if view is None:
                        logger.warning(f"⚠️ [_check_and_send_anime] 視圖為 None，無法發送消息 (video_sn={ep.get('videoSn')})")
                        continue

                    # 📌 關鍵：註冊永久視圖到 bot，否則按鈕點擊不會被識別
                    logger.info(f"🔗 [_check_and_send_anime] 註冊視圖到 bot (video_sn={ep.get('videoSn')})