# -*- coding: utf-8 -*-
"""Netflix 每日排行（JustWatch GraphQL）測試。

歷史沿革（為何本檔與舊版不同）：
舊版測試打的是已刪除的實作 —— 該版本走 Streaming Availability API 並用 PIL
自行拼貼海報，故有 `_get_best_image_url` / `_get_poster_url` /
`_translate_genres_to_chinese` / `_create_collage_file` 四個方法與對應 5 個測試。
現行版本改用 JustWatch GraphQL（無需 API Key），海報直接以 URL 縮圖呈現，
上述方法皆不存在。`_fetch_top_shows()` 亦不再接受 country / show_type 參數，
回傳值由 (shows, country) 元組改為 list。
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.ui.netflix_top10 import (
    _cache,
    CACHE_TTL,
    MAX_EMBEDS_PER_MESSAGE,
    NetflixTop10Cog,
)

POSTER_TEMPLATE = "/poster/{profile}/{format}"
EXPECTED_POSTER = "https://images.justwatch.com/poster/s718/jpg"


@pytest.fixture(autouse=True)
def clear_cache():
    """每個測試前後清空模組層快取（避免跨測試污染）"""
    _cache.clear()
    yield
    _cache.clear()


@pytest.fixture
def netflix_cog():
    return NetflixTop10Cog(MagicMock())


def _node(title, object_type="SHOW", show_id="ts1", poster=POSTER_TEMPLATE, year=2026):
    """組出 JustWatch GraphQL 的 edge.node 結構"""
    return {
        "__typename": "MovieOrShow",
        "id": show_id,
        "objectType": object_type,
        "content": {
            "title": title,
            "originalReleaseYear": year,
            "posterUrl": poster,
        },
    }


def _payload(*nodes):
    return {"data": {"popularTitles": {"edges": [{"node": n} for n in nodes]}}}


def _mock_http(status=200, json_data=None, text_data=""):
    """組出 `async with ClientSession() as s: async with s.post(...) as r:` 的替身。

    回傳 (session_cm, session)，session_cm 供 patch aiohttp.ClientSession 使用。
    """
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=text_data)

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return session_cm, session


class TestFetchPopularNetflix:
    """JustWatch GraphQL 抓取、過濾與快取"""

    @pytest.mark.asyncio
    async def test_parses_and_filters_out_movies(self, netflix_cog):
        """熱門榜含電影條目，必須只保留 SHOW 並組出完整海報 URL"""
        session_cm, session = _mock_http(
            json_data=_payload(
                _node("影集甲", object_type="SHOW", show_id="ts1"),
                _node("電影乙", object_type="MOVIE", show_id="tm1"),
            )
        )
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession", return_value=session_cm
        ):
            results = await netflix_cog._fetch_popular_netflix()

        assert len(results) == 1, f"電影應被過濾掉，實際 {results}"
        show = results[0]
        assert show["title"] == "影集甲"
        assert show["object_type"] == "SHOW"
        assert show["id"] == "ts1"
        assert show["poster_url"] == EXPECTED_POSTER
        assert show["release_year"] == 2026
        session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_poster_template_without_placeholders_yields_empty_url(
        self, netflix_cog
    ):
        """posterUrl 若不含 {profile}/{format} 佔位符，不應硬拼出壞 URL"""
        session_cm, _ = _mock_http(
            json_data=_payload(_node("影集甲", poster="https://example.com/plain.jpg"))
        )
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession", return_value=session_cm
        ):
            results = await netflix_cog._fetch_popular_netflix()

        assert results[0]["poster_url"] == ""

    @pytest.mark.asyncio
    async def test_missing_year_becomes_na(self, netflix_cog):
        """originalReleaseYear 非整數時回傳 'N/A'（避免 None 流入 embed）"""
        node = _node("影集甲")
        node["content"]["originalReleaseYear"] = None
        session_cm, _ = _mock_http(json_data=_payload(node))
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession", return_value=session_cm
        ):
            results = await netflix_cog._fetch_popular_netflix()

        assert results[0]["release_year"] == "N/A"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_http(self, netflix_cog):
        """TTL 內第二次呼叫不得再打 API（避免觸發速率限制）"""
        session_cm, session = _mock_http(json_data=_payload(_node("影集甲")))
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession", return_value=session_cm
        ):
            first = await netflix_cog._fetch_popular_netflix()
            second = await netflix_cog._fetch_popular_netflix()

        assert first == second
        session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_expired_cache_refetches(self, netflix_cog):
        """快取過期後必須重新抓取"""
        _cache["TW_show"] = ([{"title": "舊資料"}], time.time() - CACHE_TTL - 1)
        session_cm, session = _mock_http(json_data=_payload(_node("新資料")))
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession", return_value=session_cm
        ):
            results = await netflix_cog._fetch_popular_netflix()

        assert results[0]["title"] == "新資料"
        session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_error_falls_back_to_stale_cache(self, netflix_cog):
        """API 非 200 時回退到過期快取，而非回傳空列表（用戶仍看得到榜單）"""
        _cache["TW_show"] = ([{"title": "舊資料"}], time.time() - CACHE_TTL - 1)
        session_cm, _ = _mock_http(status=500, text_data="boom")
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession", return_value=session_cm
        ):
            results = await netflix_cog._fetch_popular_netflix()

        assert results == [{"title": "舊資料"}]

    @pytest.mark.asyncio
    async def test_429_falls_back_to_cache(self, netflix_cog):
        """429 速率限制時回退快取"""
        _cache["TW_show"] = ([{"title": "舊資料"}], time.time() - CACHE_TTL - 1)
        session_cm, _ = _mock_http(status=429)
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession", return_value=session_cm
        ):
            results = await netflix_cog._fetch_popular_netflix()

        assert results == [{"title": "舊資料"}]

    @pytest.mark.asyncio
    async def test_request_exception_returns_empty_without_cache(self, netflix_cog):
        """無快取且請求拋錯 → 空列表（不得讓例外冒泡到指令層）"""
        with patch(
            "cogs.ui.netflix_top10.aiohttp.ClientSession",
            side_effect=RuntimeError("network down"),
        ):
            results = await netflix_cog._fetch_popular_netflix()

        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_top_shows_requests_larger_pool(self, netflix_cog):
        """_fetch_top_shows 必須放大候選池到 50：熱門榜含電影，過濾後才夠湊 TOP 10"""
        with patch.object(
            netflix_cog, "_fetch_popular_netflix", AsyncMock(return_value=[])
        ) as mock_fetch:
            await netflix_cog._fetch_top_shows()

        mock_fetch.assert_awaited_once_with(page_size=50)


class TestCreateShowEmbeds:
    """排行榜 Embed 生成"""

    @pytest.mark.asyncio
    async def test_header_then_ranked_cards(self, netflix_cog):
        shows = [
            {
                "title": "甲",
                "object_type": "SHOW",
                "poster_url": "http://x/1.jpg",
                "release_year": 2026,
            },
            {
                "title": "乙",
                "object_type": "SHOW",
                "poster_url": "http://x/2.jpg",
                "release_year": 2020,
            },
            {
                "title": "丙",
                "object_type": "SHOW",
                "poster_url": "",
                "release_year": "N/A",
            },
            {
                "title": "丁",
                "object_type": "SHOW",
                "poster_url": "",
                "release_year": "N/A",
            },
        ]
        embeds = await netflix_cog._create_show_embeds(shows, max_shows=10)

        assert len(embeds) == len(shows) + 1, "應為 1 張標題卡 + 每部作品 1 張"
        assert "TOP 10" in embeds[0].title

        titles = [e.title for e in embeds[1:]]
        assert titles[0].startswith("🥇 #1 甲")
        assert titles[1].startswith("🥈 #2 乙")
        assert titles[2].startswith("🥉 #3 丙")
        assert titles[3].startswith("4. #4 丁"), "第 4 名起改用數字"

    @pytest.mark.asyncio
    async def test_truncates_to_max_shows(self, netflix_cog):
        shows = [{"title": f"第{i}名", "release_year": "N/A"} for i in range(1, 21)]
        embeds = await netflix_cog._create_show_embeds(shows, max_shows=10)
        assert len(embeds) == 11, "1 張標題卡 + 10 張作品卡"

    @pytest.mark.asyncio
    async def test_missing_poster_notes_failure(self, netflix_cog):
        """無海報時要在 description 說明，而非留白讓用戶困惑"""
        embeds = await netflix_cog._create_show_embeds(
            [{"title": "甲", "poster_url": "", "release_year": 2026}], max_shows=10
        )
        assert "海報圖片載入失敗" in embeds[1].description

    @pytest.mark.asyncio
    async def test_empty_shows_returns_placeholder(self, netflix_cog):
        embeds = await netflix_cog._create_show_embeds([], max_shows=10)
        assert len(embeds) == 1
        assert embeds[0].title == "無法取得資料"


class TestSendSilent:
    """靜音推播分批（供未來每日排程使用）"""

    @pytest.mark.asyncio
    async def test_batches_at_discord_embed_limit(self, netflix_cog):
        """Discord 單訊息上限 10 個 embeds，25 個應拆成 10/10/5 三批且全靜音"""
        channel = MagicMock()
        channel.send = AsyncMock()
        embeds = [discord.Embed(title=f"#{i}") for i in range(25)]

        await netflix_cog._send_silent(channel, embeds)

        assert channel.send.await_count == 3
        sizes = [len(call.kwargs["embeds"]) for call in channel.send.await_args_list]
        assert sizes == [MAX_EMBEDS_PER_MESSAGE, MAX_EMBEDS_PER_MESSAGE, 5]
        assert all(
            call.kwargs["silent"] is True for call in channel.send.await_args_list
        )


class TestNetflixTop10Command:
    """斜線指令流程"""

    @pytest.fixture
    def interaction(self):
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_defers_before_fetch_and_sends_embeds(self, netflix_cog, interaction):
        """defer 必須先於抓取（Discord 3 秒超時），再以 followup 送出榜單"""
        shows = [{"title": "甲", "poster_url": "http://x/1.jpg", "release_year": 2026}]
        with patch.object(
            netflix_cog, "_fetch_top_shows", AsyncMock(return_value=shows)
        ):
            await netflix_cog.netflix_top10.callback(netflix_cog, interaction)

        interaction.response.defer.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()
        sent = interaction.followup.send.await_args.kwargs["embeds"]
        assert len(sent) == 2  # 標題卡 + 1 部作品

    @pytest.mark.asyncio
    async def test_empty_result_replies_ephemeral(self, netflix_cog, interaction):
        """取不到資料時給 ephemeral 提示，不發空榜單"""
        with patch.object(netflix_cog, "_fetch_top_shows", AsyncMock(return_value=[])):
            await netflix_cog.netflix_top10.callback(netflix_cog, interaction)

        interaction.followup.send.assert_awaited_once()
        assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True
        assert "embeds" not in interaction.followup.send.await_args.kwargs

    @pytest.mark.asyncio
    async def test_fetch_exception_replies_ephemeral(self, netflix_cog, interaction):
        """抓取拋錯時吞掉例外並回覆錯誤訊息，不得讓例外冒泡"""
        with patch.object(
            netflix_cog, "_fetch_top_shows", AsyncMock(side_effect=RuntimeError("boom"))
        ):
            await netflix_cog.netflix_top10.callback(netflix_cog, interaction)

        interaction.followup.send.assert_awaited_once()
        assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True
        assert "❌" in interaction.followup.send.await_args.args[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
