# 📌 關鍵：註冊永久視圖到 bot，否則按鈕點擊不會被識別
                    logger.info(f"🔗 [_check_and_send_anime] 註冊視圖到 bot (video_sn={ep.get('videoSn')})")

                    # 發送訊息
                    message = await channel.send(embed=embed, view=view)
                    self.tracker.db.save_message_info(
                        message_id=message.id,
                        video_sn=ep.get('videoSn'),
                        anime_sn=ep.get('animeSn'),
                        anime_name=ep.get('title', '未知動畫'),
                        channel_id=channel.id
                    )
                    self.tracker.db.add_notified(ep.get('videoSn'))

                    logger.info(f"✅ [_check_and_send_anime] 消息已發送 (message_id={message.id}, video_sn={ep.get('videoSn')})")
                    sent_count += 1
                except Exception as send_err:
                    logger.error(f"❌ [_check_and_send_anime] 發送失敗 (video_sn={ep.get('videoSn')}): {send_err}", exc_info=True)
                    continue

            logger.info(f"✅ [_check_and_send_anime] 完成推播，成功發送 {sent_count} 個通知")
            return sent_count > 0
        except Exception as e:
            logger.error(f"❌ [_check_and_send_anime] 執行失敗: {e}", exc_info=True)
            return False

    async def daily_anime_check(self):
        """每日直接從 API 檢查新番（取代週表模式）"""
        try:
            # 防止重複執行（同一天內只執行一次）
            today = datetime.now(TW_TZ).date()
            if self.last_daily_check_date == today:
                return

            # 檢查是否在檢查時間內（每天 9:00-9:59 執行）
            now = datetime.now(TW_TZ)
            is_check_time = now.hour == 9  # 現在是 9:00-9:59

            if not is_check_time:
                return

            self.last_daily_check_date = today
            logger.info(f"🚀 [daily_anime_check] 開始每日動畫檢查 (時間: {now.strftime('%Y-%m-%d %H:%M:%S')})")

            # 獲取頻道
            channel = self.bot.get_channel(ANIME_CHANNEL_ID)
            if not channel:
                logger.error(f"❌ [daily_anime_check] 找不到頻道 ID: {ANIME_CHANNEL_ID}")
                return

            # 檢查並發送新番
            found_new = await self._check_and_send_anime("DAILY_CHECK", channel)

            if found_new:
                logger.info(f"✅ [daily_anime_check] 每日檢查完成，發現並發送了新番通知")
            else:
                logger.info(f"ℹ️ [daily_anime_check] 每日檢查完成，今日無新番")

        except Exception as e:
            logger.error(f"❌ [daily_anime_check] 每日檢查失敗: {e}", exc_info=True)

    # ==================== 已移除的週表相關任務 ====================
    # ✅ check_new_anime 任務已移除（改為 daily_anime_check）
    # ✅ 週表模式已替換為直接每日 API 檢查

async def setup(bot: commands.Bot):
    """Discord.py 2.0+ 加載方式 - cog_load() 會自動被調用"""
    import sys
    print("[SETUP_START] 🎬 AnimeTracker setup() 開始", flush=True)
    sys.stdout.flush()

    try:
        cog = AnimeTracker(bot)
        await bot.add_cog(cog)
        logger.info("✅ AnimeTracker Cog 已加載（任務將在 cog_load() 中啟動）")
        print("[SETUP_END] 🎬 AnimeTracker setup() 完成 - cog_load() 將自動被調用", flush=True)
        sys.stdout.flush()
    except Exception as setup_err:
        import traceback
        error_msg = f"❌ [setup] AnimeTracker setup() 失敗: {setup_err}"
        print(f"[SETUP_ERROR] {error_msg}", flush=True)
        print(f"[SETUP_ERROR] Traceback:\n{traceback.format_exc()}", flush=True)
        logger.error(error_msg, exc_info=True)
        raise