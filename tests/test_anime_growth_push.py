# -*- coding: utf-8 -*-
"""每週人氣榜測試 —— 2026-10-30 改版（折線圖 → 橫條圖 + 連續進榜）

改版理由：舊版 quickchart 折線圖對一般觀眾讀不出東西（10 條線、Y 值除以千、
沒有軸單位），而且「有沒有新集」當篩選條件等於沒篩（實測 53/54 部都有新集）。
現在只回答一個問題：哪部是**一直在紅**的（連續進前 10 名）。

這裡測的是判定邏輯（連續進榜的週數、資料異常的處理）與推送組裝，圖檔本身
由 VM 的 venv 產（本機 .venv 的 numpy 是壞的，見 requires_matplotlib）。
"""

import io
import sys
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.ui.anime_tracker import AnimeTracker
from cogs.ui.push_core_simple import AnimePushDB

# 四個快照週次（新 → 舊），兩個測試類別共用
WEEKS = ["2026-10-19", "2026-10-12", "2026-10-05", "2026-09-28"]


def _matplotlib_renders() -> bool:
    """本機 matplotlib 能不能真的產圖（判斷失敗只影響圖檔測試，不影響其他）"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        fig, _ = plt.subplots(figsize=(1, 1))
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        return buf.tell() > 0
    except Exception:  # noqa: BLE001 - 任何失敗都只代表「本機畫不出來」
        return False


requires_matplotlib = pytest.mark.skipif(
    not _matplotlib_renders(),
    reason="本機 matplotlib 無法產圖（.venv 的 numpy 是 cp310 wheel，跑在 3.11 上）；"
    "VM 的 venv/matplotlib 正常，該處會執行",
)


@pytest.fixture
def tracker(temp_db_path):
    """生產同款：AnimeTracker + AnimePushDB（bot 用 mock，只需要 get_channel）"""
    cog = AnimeTracker(MagicMock())
    cog.db = AnimePushDB(temp_db_path)
    return cog


@pytest.fixture
def channel(tracker):
    """接住推送的假頻道"""
    ch = MagicMock()
    ch.send = AsyncMock()
    tracker.bot.get_channel.return_value = ch
    return ch


def _seed(db: AnimePushDB, week: str, rows: list[tuple]) -> None:
    """rows: (anime_sn, anime_name, total_views, rank)"""
    db.save_view_snapshot(
        week,
        [
            {
                "anime_sn": sn,
                "anime_name": name,
                "total_views": views,
                "volume_ep": 1,
                "rank": rank,
            }
            for sn, name, views, rank in rows
        ],
    )


# ==================== 連續進榜 ====================


class TestGrowthStreaks:
    """「持續在紅」＝連續進本週新增前 GROWTH_TOP_N 名"""

    def _seed_twelve(self, db: AnimePushDB) -> None:
        """12 部：長紅番每週稱王、中段番最後兩週才衝上來、其餘固定成長

        固定成長那 10 部數值完全相同，排序以 anime_sn 遞減決勝，所以 sn 最小的
        兩部（200/201）在最新一週必定落到 11、12 名，用來驗證「斷了就停」。
        """
        old_to_new = list(reversed(WEEKS))
        long_run = [1000, 6000, 11000, 16000]  # 每週 +5000
        mid_run = [100000, 100100, 106100, 112100]  # +100 / +6000 / +6000
        for i, week in enumerate(old_to_new):
            rows = [(1, "長紅番", long_run[i], 1), (2, "中段番", mid_run[i], 2)]
            rows += [(200 + k, f"固定番{k}", 10000 + 3000 * i, 10) for k in range(10)]
            _seed(db, week, rows)

    def test_counts_consecutive_top10_weeks(self, tracker):
        self._seed_twelve(tracker.db)
        streaks = tracker._growth_streaks(WEEKS)

        assert streaks[1] == 3, "每週都稱王 → 三週全算"
        assert streaks[2] == 2, "最舊的那週只有 +100（第 12 名）→ 從那裡斷"
        assert 200 not in streaks and 201 not in streaks, "最新一週落到 11、12 名"
        assert len(streaks) == 10, "1 + 1 + 8 部"

    def test_zero_view_week_breaks_streak(self, tracker):
        """total_views=0 是 API 異常：不能拿它跟下一週相減，也不能算進榜"""
        old_to_new = list(reversed(WEEKS))
        # 乾淨番每週 +100，必定每週在榜
        clean = [100, 200, 300, 400]
        # 異常番第三週回 0，第四週又正常
        broken = [500, 1000, 0, 2000]
        for i, week in enumerate(old_to_new):
            _seed(
                tracker.db,
                week,
                [(1, "乾淨番", clean[i], 1), (2, "異常番", broken[i], 2)],
            )

        streaks = tracker._growth_streaks(WEEKS)

        assert streaks[1] == 3, "乾淨番不受別人異常影響"
        assert streaks.get(2, 0) == 0, "0 當週與其後一週都不可比 → 不算連續進榜"


# ==================== 推送組裝 ====================


class TestPushGrowthEmbed:
    def _seed_three(self, db: AnimePushDB) -> None:
        """長紅番：連 3 週；新竄番：第三週才上架 → 連 2 週"""
        _seed(db, "2026-09-28", [(101, "長紅番", 1000, 1)])
        _seed(db, "2026-10-05", [(101, "長紅番", 1500, 1), (102, "新竄番", 1000, 2)])
        _seed(db, "2026-10-12", [(101, "長紅番", 2000, 1), (102, "新竄番", 1400, 2)])
        _seed(db, "2026-10-19", [(101, "長紅番", 2500, 1), (102, "新竄番", 2000, 2)])

    async def test_embed_has_chart_and_streak_field(self, tracker, channel, monkeypatch):
        self._seed_three(tracker.db)
        file = discord.File(io.BytesIO(b"fake-png"), filename="weekly_growth.png")
        monkeypatch.setattr(
            tracker, "_build_growth_bar_chart", lambda rows: file
        )

        await tracker._push_growth_embed(WEEKS[0], {})

        channel.send.assert_awaited_once()
        kwargs = channel.send.await_args.kwargs
        assert kwargs.get("file") is file, "圖要以附件送出，不是網址"

        embeds = kwargs["embeds"]
        main = embeds[0]
        assert main.title == "📈 本週動畫人氣"
        assert "2026-10-12 → 2026-10-19" in main.description
        assert main.image.url == "attachment://weekly_growth.png"

        hot = [f for f in main.fields if f.name == "🔥 持續在紅"]
        assert len(hot) == 1, "連續進榜要單獨一欄"
        assert "**長紅番**　連 3 週進前 10 名" in hot[0].value
        assert "**新竄番**　連 2 週進前 10 名" in hot[0].value

        # 黑馬卡片：本週成長率＝新竄番 +42.9%、長紅番 +25%
        assert embeds[1].title == "🚀 本週衝最快"
        assert embeds[2].title.startswith("🚀 +42.9%")
        assert embeds[3].title.startswith("🚀 +25.0%")

    async def test_no_streak_field_with_one_week_history(
        self, tracker, channel, monkeypatch
    ):
        """只有兩週快照 → 最多只能連續 1 週，未達門檻就不該出現空欄位"""
        monkeypatch.setattr(tracker, "_build_growth_bar_chart", lambda rows: None)
        _seed(tracker.db, "2026-10-12", [(101, "舊番", 1000, 1)])
        _seed(tracker.db, "2026-10-19", [(101, "舊番", 1500, 1), (102, "新番", 900, 2)])

        await tracker._push_growth_embed(WEEKS[0], {})

        main = channel.send.await_args.kwargs["embeds"][0]
        assert [f.name for f in main.fields] == [], "只有一週歷史 → 沒有連續進榜"
        assert "file" not in channel.send.await_args.kwargs
        assert not main.image.url, "沒有圖時不該掛 attachment://"

    async def test_first_snapshot_is_baseline_only(self, tracker, channel):
        """只有一週快照時沒有可相減的前一週，只發基準說明"""
        _seed(tracker.db, "2026-10-19", [(101, "長紅番", 1000, 1)])

        await tracker._push_growth_embed("2026-10-19", {})

        embeds = channel.send.await_args.kwargs["embeds"]
        assert len(embeds) == 1
        assert "基準已建立" in embeds[0].title


# ==================== 圖檔 ====================


class TestBarChart:
    def _rows(self) -> list[dict]:
        return [
            {"anime_sn": 1, "anime_name": "學生會也有洞！", "growth": 190220},
            {"anime_sn": 2, "anime_name": "被放逐的作弊賦予魔術師", "growth": 124221},
            {"anime_sn": 3, "anime_name": "BLEACH 死神 千年血戰篇", "growth": 115395},
        ]

    def test_empty_rows_returns_none(self, tracker):
        assert tracker._build_growth_bar_chart([]) is None

    def test_degrades_to_none_without_matplotlib(self, tracker, monkeypatch):
        """沒有 matplotlib 時要回 None（純文字推送），不能讓整則推播爆掉"""
        monkeypatch.setitem(sys.modules, "matplotlib", None)
        assert tracker._build_growth_bar_chart(self._rows()) is None

    @requires_matplotlib
    def test_renders_valid_png(self, tracker):
        file = tracker._build_growth_bar_chart(self._rows())
        assert file is not None
        assert file.filename == "weekly_growth.png"
        head = file.fp.read(8)
        assert head == b"\x89PNG\r\n\x1a\n", "要是真的 PNG"
        assert file.fp.seek(0, io.SEEK_END) > 5000, "不該是空白圖"


# ==================== 本週衝最快 ====================


class TestRisers:
    @staticmethod
    def _item(sn: int, rank, prev: int, growth: int) -> dict:
        return {
            "anime_sn": sn,
            "anime_name": f"番{sn}",
            "rank": rank,
            "prev_views": prev,
            "growth": growth,
            "total_views": prev + growth,
        }

    def test_excludes_out_of_range_and_missing_rank(self, tracker):
        growth = [
            self._item(1, 100, 10, 90),  # +900% 但排 100 名 → 小基數假黑馬
            self._item(2, None, 10, 90),  # rank 為 NULL 不能比大小
            self._item(3, 5, 100, 50),  # +50%
            self._item(4, 2, 100, 20),  # +20%
        ]
        picked = tracker._pick_risers(growth)
        assert [g["anime_sn"] for g in picked] == [3, 4]

    def test_excludes_anime_without_prev_views(self, tracker):
        """前值為 0 是當週才上架，相減會變成上架至今累計"""
        growth = [self._item(1, 100, 0, 999)]
        assert tracker._pick_risers(growth) == []
