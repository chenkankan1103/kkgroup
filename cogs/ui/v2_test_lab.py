"""V2 遷移測試指令（暫時）：Netflix / bangumi 週榜卡先發測試論壇驗外觀。

Netflix 與 bangumi 週榜推送是獨立 cron 腳本（無按鈕、不需視圖註冊），推送前
先用這兩支指令把 V2 卡發到測試論壇讓人看過；cutover 完成後**整支刪除**
（含 registry 條目）。

腳本模組的匯入刻意放在指令執行時：scheduled_tasks/netflix_weekly_push.py 在
import 當下會 load_dotenv 並對 root logger 掛檔案 handler，不該在 bot 載入
cog 時就發生。
"""

import logging

from discord.ext import commands

logger = logging.getLogger(__name__)

# 測試論壇頻道（ForumChannel）——發測試卡要開討論串，ForumChannel 沒有 .send()
V2_TEST_FORUM_ID = 1504438347974705152


class V2TestLab(commands.Cog):
    """V2 遷移用的暫時測試指令集。"""

    def __init__(self, bot):
        self.bot = bot

    async def _send_to_test_forum(self, thread_name: str, layout):
        """把測試卡開成測試論壇的新討論串，回傳訊息連結（失敗回 None）。"""
        channel = self.bot.get_channel(V2_TEST_FORUM_ID)
        if channel is None or not hasattr(channel, "create_thread"):
            return None
        _thread, message = await channel.create_thread(
            name=thread_name[:100], view=layout, silent=True
        )
        return message.jump_url

    @commands.hybrid_command(
        name="netflix_v2_test",
        description="抓即時 Tudum 榜單，發一張 Netflix 週榜 V2 測試卡到測試論壇",
    )
    @commands.has_permissions(administrator=True)
    async def netflix_v2_test(self, ctx: commands.Context):
        # hybrid 指令統一走 ctx.defer（slash 會 defer、prefix 呼叫是 no-op）；
        # hasattr(ctx, "response") 恆為 False，那種寫法等於從不 defer → 3 秒超時
        await ctx.defer(ephemeral=True)
        try:
            from cogs.ui.netflix_push_v2 import generate_netflix_layout
            from scheduled_tasks.netflix_weekly_push import fetch_tudum_top10

            shows, week_end = await fetch_tudum_top10()
            if not shows:
                await ctx.send("❌ Tudum 抓不到資料", ephemeral=True)
                return
            layout = generate_netflix_layout(shows, week_end)
            url = await self._send_to_test_forum(
                f"V2 測試：Netflix 週榜 {week_end or ''}".strip(), layout
            )
            if url is None:
                await ctx.send("❌ 找不到 V2 測試論壇頻道", ephemeral=True)
                return
            logger.info(f"✅ [netflix_v2_test] 已發測試卡（{len(shows)} 部）")
            await ctx.send(f"✅ Netflix V2 測試卡：{url}", ephemeral=True)
        except Exception as e:
            logger.exception("❌ [netflix_v2_test] 發送失敗")
            await ctx.send(f"❌ 發送失敗: {e!s}", ephemeral=True)

    @commands.hybrid_command(
        name="bangumi_v2_test",
        description="抓即時 bangumi 近期注目，發一張 V2 測試卡到測試論壇",
    )
    @commands.has_permissions(administrator=True)
    async def bangumi_v2_test(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
            from cogs.ui.bangumi_push_v2 import generate_bangumi_layout
            from shared.utils import bangumi_client as bgm

            items = await bgm.get_trending(20)
            if not items:
                await ctx.send("❌ bangumi 抓不到資料", ephemeral=True)
                return
            layout = generate_bangumi_layout(items)
            url = await self._send_to_test_forum(
                f"V2 測試：bangumi 近期注目 TOP{len(items)}", layout
            )
            if url is None:
                await ctx.send("❌ 找不到 V2 測試論壇頻道", ephemeral=True)
                return
            logger.info(f"✅ [bangumi_v2_test] 已發測試卡（{len(items)} 部）")
            await ctx.send(f"✅ bangumi V2 測試卡：{url}", ephemeral=True)
        except Exception as e:
            logger.exception("❌ [bangumi_v2_test] 發送失敗")
            await ctx.send(f"❌ 發送失敗: {e!s}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(V2TestLab(bot))
