# -*- coding: utf-8 -*-
"""
KK 園區堡壘保衛戰 - Discord Cog
玩家透過按鈕參與塔防遊戲，防守 Google Trends 入侵的熱搜大軍
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Button, Modal, TextInput, Select
import json
import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional

from shared.utils.view_registry import PersistentViewBase
from shared.utils import fortress_system as fs
from shared.db.db_adapter import (
    get_user_field, set_user_field, add_user_field, get_all_users
)

log = logging.getLogger("fortress_defense")
TW_TZ = ZoneInfo("Asia/Taipei")

# 從 .env 讀取堡壘頻道 ID（與其他 channel ID 的模式相同）
def _get_fortress_channel_id() -> int:
    return int(os.getenv("FORTRESS_CHANNEL_ID", "0") or 0)


# ─── 興趣標籤 Modal ────────────────────────────────────────

class TagEditModal(Modal, title="🏷️ 設定你的興趣標籤"):
    tags_input = TextInput(
        label="選擇感興趣的話題（用逗號分隔）",
        placeholder="例：科技/AI, 動漫/遊戲, 政治",
        style=discord.TextStyle.short,
        max_length=200,
        required=False,
    )
    hint_input = TextInput(
        label="可選標籤（複製貼上你感興趣的）",
        default=(
            "科技/AI / 動漫/遊戲 / 體育 / "
            "娛樂/明星 / 財經時事 / 健康/美食 / 旅遊/生活 / 政治"
        ),
        style=discord.TextStyle.paragraph,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.tags_input.value.strip()
        tags = [t.strip() for t in raw.replace("、", ",").split(",") if t.strip()]
        valid = [t for t in tags if t in fs.INTEREST_KEYWORDS]

        if not valid and raw:
            await interaction.response.send_message(
                f"❌ 未識別到有效標籤。請從以下選擇：\n"
                + "、".join(fs.INTEREST_KEYWORDS.keys()),
                ephemeral=True
            )
            return

        set_user_field(interaction.user.id, "user_interests", json.dumps(valid, ensure_ascii=False))
        set_user_field(interaction.user.id, "trend_alert_enabled", 1)

        if valid:
            await interaction.response.send_message(
                f"✅ 已設定興趣標籤：**{' / '.join(valid)}**\n"
                "當你感興趣的話題出現在熱搜時，你的攻擊力將會 ×2！",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("✅ 已清空興趣標籤。", ephemeral=True)


# ─── 戰鬥按鈕視圖 ─────────────────────────────────────────

class FortressEnemyView(PersistentViewBase):
    """戰鬥 Embed 下方的互動按鈕"""

    def __init__(self, cog: "FortressDefenseCog"):
        super().__init__()
        self.cog = cog

    @discord.ui.button(
        label="⚔️ 出兵（免費）",
        style=discord.ButtonStyle.success,
        custom_id="fortress:free_attack",
        row=0,
    )
    async def free_attack(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        interests = self._get_user_interests(user_id)

        success, msg, damage = fs.apply_defense_action(
            user_id=user_id,
            action_type="free",
            user_interests=interests,
        )
        if not success:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return

        # 更新全域傷害統計
        add_user_field(user_id, "fortress_total_damage", damage)

        # 更新戰況 Embed
        await self.cog.refresh_battle_embed(interaction)
        await interaction.followup.send(
            f"🗡️ **{interaction.user.display_name}** {msg}", ephemeral=True
        )

    @discord.ui.button(
        label=f"💎 強化防禦（{fs.PAID_COST_KKCOIN} KKCoin）",
        style=discord.ButtonStyle.primary,
        custom_id="fortress:paid_attack",
        row=0,
    )
    async def paid_attack(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        # 扣款
        balance = get_user_field(user_id, "kkcoin", default=0)
        if balance < fs.PAID_COST_KKCOIN:
            await interaction.followup.send(
                f"❌ KKCoin 不足！需要 {fs.PAID_COST_KKCOIN}，你只有 {balance}。",
                ephemeral=True,
            )
            return
        add_user_field(user_id, "kkcoin", -fs.PAID_COST_KKCOIN)

        interests = self._get_user_interests(user_id)
        success, msg, damage = fs.apply_defense_action(
            user_id=user_id,
            action_type="paid",
            user_interests=interests,
        )
        if not success:
            # 退款
            add_user_field(user_id, "kkcoin", fs.PAID_COST_KKCOIN)
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return

        add_user_field(user_id, "fortress_total_damage", damage)
        await self.cog.refresh_battle_embed(interaction)
        await interaction.followup.send(
            f"💥 **{interaction.user.display_name}** {msg}", ephemeral=True
        )

    @discord.ui.button(
        label="📊 查看戰況",
        style=discord.ButtonStyle.secondary,
        custom_id="fortress:status",
        row=1,
    )
    async def show_status(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        state = fs.get_current_battle()
        if not state:
            await interaction.followup.send("目前沒有進行中的戰鬥。", ephemeral=True)
            return
        embed = build_status_embed(state, interaction.user.id)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="🏷️ 設定興趣標籤",
        style=discord.ButtonStyle.secondary,
        custom_id="fortress:set_tags",
        row=1,
    )
    async def set_tags(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TagEditModal())

    @staticmethod
    def _get_user_interests(user_id: int) -> List[str]:
        raw = get_user_field(user_id, "user_interests", default="[]")
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            return []


# ─── Embed 建構函數 ────────────────────────────────────────

def build_battle_embed(state: fs.FortressState) -> discord.Embed:
    """戰鬥 Embed：顯示所有敵人 HP + 堡壘 HP"""
    now = datetime.now(TW_TZ)
    ends = datetime.fromisoformat(state.ends_at)
    # 相容 naive/aware：統一轉為 aware 再比較
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=TW_TZ)
    remaining_min = max(0, int((ends - now).total_seconds() / 60))

    embed = discord.Embed(
        title="⚔️ KK 園區堡壘保衛戰！",
        description=(
            f"熱搜大軍正在入侵！全服玩家聯合防守，守住有獎！\n"
            f"⏱️ 距離結算剩餘 **{remaining_min}** 分鐘"
        ),
        color=0xE74C3C,
        timestamp=now,
    )

    # 敵人列表
    boss_labels = {1: "👑 Boss", 2: "⚡ 精英", 3: "🔥 精英"}
    alive = [e for e in state.enemies if not e.defeated]
    defeated_count = sum(1 for e in state.enemies if e.defeated)

    enemy_lines = []
    for e in sorted(state.enemies, key=lambda x: x.rank):
        prefix = boss_labels.get(e.rank, "👾 雜兵")
        if e.defeated:
            enemy_lines.append(f"~~{prefix} [{e.name}]~~ ✅ 已消滅")
        else:
            enemy_lines.append(f"{prefix} **[{e.name}]**\n`{e.hp_bar()}`")

    embed.add_field(
        name=f"🗡️ 入侵敵軍（{len(alive)}/{len(state.enemies)} 存活）",
        value="\n".join(enemy_lines) or "無",
        inline=False,
    )

    # 堡壘 HP
    embed.add_field(
        name="🏰 KK 詐騙園區堡壘",
        value=f"`{state.fortress_hp_bar()}`",
        inline=False,
    )

    # 參與人數
    embed.add_field(
        name="🛡️ 防守玩家",
        value=f"{len(state.defenders)} 人已出兵",
        inline=True,
    )
    embed.add_field(
        name="🏆 免費出兵",
        value=f"每人每輪 {fs.FREE_ACTIONS_PER_ROUND} 次",
        inline=True,
    )
    embed.add_field(
        name="🏷️ 標籤加乘",
        value="興趣匹配 → 攻擊 ×2",
        inline=True,
    )

    status_map = {"active": "🟢 進行中", "victory": "🎉 勝利", "defeat": "💀 失守"}
    embed.set_footer(text=f"狀態：{status_map.get(state.status, state.status)} | 輪次 {state.round_id}")
    return embed


def build_status_embed(state: fs.FortressState, user_id: int) -> discord.Embed:
    """個人戰況 Embed（ephemeral）"""
    actions = state.defenders.get(user_id, [])
    free_used = sum(1 for a in actions if a.action_type == "free")
    total_dmg = sum(a.damage for a in actions)

    interests_raw = get_user_field(user_id, "user_interests", default="[]")
    try:
        interests = json.loads(interests_raw) if isinstance(interests_raw, str) else []
    except Exception:
        interests = []

    embed = discord.Embed(title="📊 你的戰況", color=0x3498DB)
    embed.add_field(name="免費出兵", value=f"{free_used}/{fs.FREE_ACTIONS_PER_ROUND} 次", inline=True)
    embed.add_field(name="累計傷害", value=f"{total_dmg:,}", inline=True)
    embed.add_field(
        name="興趣標籤",
        value=" / ".join(interests) if interests else "尚未設定",
        inline=False,
    )
    embed.add_field(
        name="堡壘 HP",
        value=f"`{state.fortress_hp_bar()}`",
        inline=False,
    )
    return embed


def build_settlement_embed(result: dict, bot: discord.Client) -> discord.Embed:
    """結算 Embed"""
    won = result["status"] == "victory"
    color = 0x2ECC71 if won else 0x95A5A6

    if won:
        title = "🎉 守城成功！KK 園區安全了！"
        desc = f"全服英雄合力消滅 {result['enemies_defeated']}/{result['enemies_total']} 個敵人！"
    else:
        title = "💀 堡壘失守..."
        desc = (
            f"堡壘剩餘 HP：{result['fortress_hp_remaining']:,}\n"
            + ("（封測期間暫無懲罰，放心繼續試玩！）" if result.get("beta_no_penalty") else "")
        )

    embed = discord.Embed(title=title, description=desc, color=color)

    # 英雄榜
    damage_map: dict = result.get("damage_map", {})
    if damage_map:
        sorted_heroes = sorted(damage_map.items(), key=lambda x: x[1], reverse=True)[:5]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        lines = []
        for i, (uid, dmg) in enumerate(sorted_heroes):
            user = bot.get_user(int(uid))
            name = user.display_name if user else f"玩家 {uid}"
            pct = result["contributions"].get(uid, result["contributions"].get(str(uid), 0))
            lines.append(f"{medals[i]} **{name}** — {dmg:,} 傷害 ({pct}%)")
        embed.add_field(name="🏆 防守英雄榜", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"輪次 {result['round_id']}")
    return embed


# ─── 主 Cog ───────────────────────────────────────────────

class FortressDefenseCog(commands.Cog):
    """KK 園區堡壘保衛戰"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._battle_message_id: Optional[int] = None
        self._battle_channel_id: int = _get_fortress_channel_id()
        self.settle_task.start()
        self.update_trends_scheduled.start()
        log.info("[Fortress] Cog 已初始化")

    def cog_unload(self):
        self.settle_task.cancel()
        self.update_trends_scheduled.cancel()

    # ── 斜線指令 ───────────────────────────────────────────

    @app_commands.command(name="fortress_status", description="查看堡壘保衛戰當前戰況")
    async def fortress_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = fs.get_current_battle()
        if not state:
            await interaction.followup.send("目前沒有進行中的戰鬥。", ephemeral=True)
            return
        embed = build_status_embed(state, interaction.user.id)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="my_interests", description="查看或修改你的興趣標籤（影響塔防加乘）")
    async def my_interests(self, interaction: discord.Interaction):
        raw = get_user_field(interaction.user.id, "user_interests", default="[]")
        try:
            interests = json.loads(raw) if isinstance(raw, str) else []
        except Exception:
            interests = []

        embed = discord.Embed(
            title="🏷️ 我的興趣標籤",
            description=(
                "標籤與熱搜趨勢匹配時，你的攻擊力 **×2**！\n\n"
                "**目前標籤：**\n"
                + (" / ".join(interests) if interests else "尚未設定")
            ),
            color=0x9B59B6,
        )
        embed.add_field(
            name="可用標籤",
            value="、".join(fs.INTEREST_KEYWORDS.keys()),
            inline=False,
        )
        view = InterestManageView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="my_defense_stats", description="查看你的累計防守貢獻")
    async def my_defense_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        total_dmg = get_user_field(uid, "fortress_total_damage", default=0)
        wins = get_user_field(uid, "fortress_wins", default=0)
        embed = discord.Embed(title="🛡️ 我的防守紀錄", color=0x1ABC9C)
        embed.add_field(name="累計造成傷害", value=f"{total_dmg:,}", inline=True)
        embed.add_field(name="累計守城次數", value=str(wins), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── 公開 API（供排程呼叫）─────────────────────────────

    async def start_battle(self, trends: list):
        """開始新一輪戰鬥，發送戰鬥 Embed 到指定頻道"""
        state = fs.start_new_battle(trends)

        channel = self.bot.get_channel(self._battle_channel_id)
        if not channel:
            log.warning(f"[Fortress] 找不到頻道 {self._battle_channel_id}")
            return

        embed = build_battle_embed(state)
        view = FortressEnemyView(self)
        msg = await channel.send(embed=embed, view=view)
        self._battle_message_id = msg.id
        log.info(f"[Fortress] 戰鬥 Embed 發送成功 msg={msg.id}")

    async def refresh_battle_embed(self, interaction: discord.Interaction):
        """在有人出兵後更新戰況 Embed"""
        try:
            if not self._battle_message_id or not self._battle_channel_id:
                return
            channel = self.bot.get_channel(self._battle_channel_id)
            if not channel:
                return
            msg = await channel.fetch_message(self._battle_message_id)
            state = fs.get_current_battle()
            if state:
                await msg.edit(embed=build_battle_embed(state))
        except discord.NotFound:
            pass
        except Exception as e:
            log.warning(f"[Fortress] 更新 Embed 失敗: {e}")

    # ── 結算排程 ──────────────────────────────────────────

    @tasks.loop(minutes=10)
    async def settle_task(self):
        """每 10 分鐘檢查是否到結算時間"""
        try:
            state = fs.get_current_battle()
            if not state or state.status != "active":
                return

            now = datetime.now(TW_TZ)
            ends = datetime.fromisoformat(state.ends_at)

            # 相容 naive/aware datetime
            if ends.tzinfo is None:
                from datetime import timezone
                ends = ends.replace(tzinfo=timezone.utc).astimezone(TW_TZ)

            if now < ends:
                return  # 尚未結算

            # 執行結算
            result = fs.settle_battle()
            if not result.get("success"):
                return

            # 守城成功 → 更新獲勝次數
            if result["status"] == "victory":
                for uid in result["damage_map"]:
                    add_user_field(int(uid), "fortress_wins", 1)

            # 發送結算 Embed
            channel = self.bot.get_channel(self._battle_channel_id)
            if channel:
                embed = build_settlement_embed(result, self.bot)
                await channel.send(embed=embed)

            # 更新舊戰鬥訊息（移除按鈕）
            if self._battle_message_id:
                try:
                    msg = await channel.fetch_message(self._battle_message_id)
                    state_final = fs.get_current_battle()
                    if state_final:
                        await msg.edit(embed=build_battle_embed(state_final), view=None)
                except Exception:
                    pass

            log.info(f"[Fortress] 結算完成: {result['status']}")

        except Exception as e:
            log.error(f"[Fortress] 結算排程出錯: {e}")

    @settle_task.before_loop
    async def before_settle(self):
        await self.bot.wait_until_ready()

    # ── 趨勢排程（每 4 小時抓 Google Trends，開啟新一輪堡壘戰）────

    @tasks.loop(hours=4)
    async def update_trends_scheduled(self):
        """每 4 小時自動抓 Google Trends 並開啟新一輪堡壘保衛戰
        執行時間: 00:00, 08:00, 12:00, 16:00, 20:00 (台灣時間)
        """
        try:
            now = datetime.now(TW_TZ)
            allowed_hours = [0, 8, 12, 16, 20]
            if now.hour not in allowed_hours:
                return
            if now.minute > 5:
                return

            log.info(f"[Fortress] ⏰ 趨勢排程啟動 {now.strftime('%H:%M %Z')}")

            from market_trends_serpapi import get_trending_topics
            trends_data = await get_trending_topics(limit=10)
            if not trends_data:
                log.warning("[Fortress] ⚠️ 取得趨勢資料失敗，跳過本輪")
                return

            await self.start_battle(trends_data)
            log.info(f"[Fortress] ✅ 新一輪堡壘保衛戰已開啟（{len(trends_data)} 個趨勢）")

        except Exception as e:
            log.error(f"[Fortress] 趨勢排程出錯: {e}")

    @update_trends_scheduled.before_loop
    async def before_trends(self):
        await self.bot.wait_until_ready()

    # ── 管理員手動開戰 ────────────────────────────────────

    @app_commands.command(name="fortress_admin_start", description="[管理員] 立即抓取趨勢並開啟新一輪堡壘保衛戰")
    @app_commands.default_permissions(administrator=True)
    async def fortress_admin_start(self, interaction: discord.Interaction):
        """管理員手動觸發堡壘保衛戰（補發用）"""
        await interaction.response.defer(ephemeral=True)
        try:
            from market_trends_serpapi import get_trending_topics
            trends_data = await get_trending_topics(limit=10)
            if not trends_data:
                await interaction.followup.send("❌ 無法取得趨勢資料，請稍後再試", ephemeral=True)
                return
            await self.start_battle(trends_data)
            await interaction.followup.send(
                f"✅ 堡壘保衛戰已手動啟動！共 {len(trends_data)} 個趨勢敵人。",
                ephemeral=True
            )
        except Exception as e:
            log.error(f"[Fortress] 管理員強制開戰失敗: {e}")
            await interaction.followup.send(f"❌ 開戰失敗：{e}", ephemeral=True)


# ─── 興趣管理視圖（/my_interests 用）─────────────────────

class InterestManageView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(label="✏️ 修改標籤", style=discord.ButtonStyle.primary)
    async def edit_tags(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的操作！", ephemeral=True)
            return
        await interaction.response.send_modal(TagEditModal())

    @discord.ui.button(label="🔕 關閉推播通知", style=discord.ButtonStyle.secondary)
    async def toggle_alert(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的操作！", ephemeral=True)
            return
        current = get_user_field(self.user_id, "trend_alert_enabled", default=1)
        new_val = 0 if current else 1
        set_user_field(self.user_id, "trend_alert_enabled", new_val)
        status = "開啟" if new_val else "關閉"
        await interaction.response.send_message(f"✅ 趨勢通知已{status}。", ephemeral=True)


# ─── Cog 載入 ─────────────────────────────────────────────

async def setup(bot: commands.Bot):
    cog = FortressDefenseCog(bot)
    await bot.add_cog(cog)
    bot.add_view(FortressEnemyView(cog))
    log.info("[Fortress] ✅ loaded cogs.ui.fortress_defense")
