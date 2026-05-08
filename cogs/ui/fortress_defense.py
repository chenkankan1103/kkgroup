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
from typing import Dict, List, Optional

from shared.utils.view_registry import PersistentViewBase
from shared.utils import fortress_system as fs
from shared.db.db_adapter import (
    get_user_field, set_user_field, add_user_field, get_all_users
)

log = logging.getLogger("fortress_defense")
TW_TZ = ZoneInfo("Asia/Taipei")
FORTRESS_COMMAND_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fortress_command.json")
EMBED_REFRESH_COOLDOWN_SECONDS = 5

_TD_GRID_ROWS = 6
_TD_GRID_COLS = 13
_TD_PATH_COORDS = [
    (0, 0), (0, 1), (0, 2), (0, 3),
    (1, 3), (2, 3),
    (2, 2), (2, 1), (2, 0),
    (3, 0), (4, 0),
    (4, 1), (4, 2), (4, 3), (4, 4),
    (3, 4), (2, 4), (1, 4),
    (1, 5), (1, 6), (1, 7),
    (2, 7), (3, 7), (4, 7), (5, 7),
    (5, 8), (5, 9), (5, 10), (5, 11),
]
_TD_FORT_COORD = (5, 12)
_TD_TOWER_SLOTS: Dict[str, Dict[str, object]] = {
    "north_gate": {"label": "北門入口", "desc": "開局壓制第一波", "coord": (0, 4)},
    "west_corner": {"label": "西側急彎", "desc": "專打轉角卡位", "coord": (1, 1)},
    "mid_choke": {"label": "中央瓶頸", "desc": "火力最密集的彎道", "coord": (3, 2)},
    "inner_curve": {"label": "內圈彎道", "desc": "攔截中段推進", "coord": (2, 5)},
    "east_bridge": {"label": "東側橋頭", "desc": "守住後段長線", "coord": (3, 8)},
    "last_stand": {"label": "園區前哨", "desc": "最後防線", "coord": (4, 11)},
}

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
        self.add_item(TowerPlacementSelect(cog))

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
        state = fs.get_current_battle()
        if state and state.status == "victory":
            await self.cog._finalize_and_announce_battle()
            state = fs.get_current_battle()
        state = fs.get_current_battle()
        tower_label = _get_tower_label_for_user(state, user_id)
        tower_suffix = f"\n🗼 你的砲台【{tower_label}】同步開火" if tower_label else ""
        await interaction.followup.send(
            f"🗡️ **{interaction.user.display_name}** {msg}{tower_suffix}", ephemeral=True
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
        state = fs.get_current_battle()
        if state and state.status == "victory":
            await self.cog._finalize_and_announce_battle()
            state = fs.get_current_battle()
        state = fs.get_current_battle()
        tower_label = _get_tower_label_for_user(state, user_id)
        tower_suffix = f"\n🗼 你的砲台【{tower_label}】同步開火" if tower_label else ""
        await interaction.followup.send(
            f"💥 **{interaction.user.display_name}** {msg}{tower_suffix}", ephemeral=True
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


class TowerPlacementSelect(Select):
    """主戰場下拉選單：選擇本輪塔位"""

    def __init__(self, cog: "FortressDefenseCog"):
        self.cog = cog
        options = [
            discord.SelectOption(
                label=meta["label"],
                value=slot_id,
                description=meta["desc"],
                emoji="🗼",
            )
            for slot_id, meta in _TD_TOWER_SLOTS.items()
        ]
        super().__init__(
            placeholder="🗼 選擇你的砲台架設位置",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="fortress:tower_slot",
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = fs.get_current_battle()
        if not state or state.status != "active":
            await interaction.followup.send("目前沒有進行中的戰鬥。", ephemeral=True)
            return

        slot_id = self.values[0]
        success, result = fs.assign_tower_slot(interaction.user.id, slot_id)
        if not success:
            if result == "occupied":
                owner_name = _find_slot_owner_name(state, slot_id, interaction.client)
                label = _tower_slot_label(slot_id)
                msg = f"❌ 【{label}】已被 {owner_name} 佔用。"
            else:
                msg = f"❌ {result}"
            await interaction.followup.send(msg, ephemeral=True)
            return

        await self.cog.refresh_battle_embed(interaction)
        prev_text = f"（原本在 {_tower_slot_label(result)}）" if result else ""
        await interaction.followup.send(
            f"✅ 已在【{_tower_slot_label(slot_id)}】架設砲台 {prev_text}\n"
            f"這座塔位會直接顯示在主戰場地圖上。",
            ephemeral=True,
        )


# ─── 塔防地圖生成 ─────────────────────────────────────────


def _rank_to_icon(rank: int) -> str:
    """根據敵軍排名回傳戰場 emoji"""
    if rank == 1:   return '👑'
    if rank <= 3:   return '⚡'
    if rank <= 6:   return '🔥'
    return '💀'


def _enemy_path_pos(enemy: fs.EnemyUnit) -> int:
    """計算敵人在路徑上的格子（0=剛入口, 路徑尾端=緊逼堡壘）
    血量越低 → 位置越靠右（越接近 KK 園區）
    """
    if enemy.max_hp == 0:
        return 0
    hp_pct = enemy.current_hp / enemy.max_hp
    path_len = len(_TD_PATH_COORDS)
    return min(int((1 - hp_pct) * path_len), path_len - 1)


def _tower_slot_label(slot_id: str) -> str:
    meta = _TD_TOWER_SLOTS.get(slot_id)
    return str(meta["label"]) if meta else slot_id


def _get_tower_label_for_user(state: Optional[fs.FortressState], user_id: int) -> str:
    if not state:
        return ""
    slot_id = state.tower_slots.get(user_id)
    return _tower_slot_label(slot_id) if slot_id else ""


def _find_slot_owner_name(state: fs.FortressState, slot_id: str, bot: discord.Client) -> str:
    for owner_id, owned_slot in state.tower_slots.items():
        if owned_slot != slot_id:
            continue
        user = bot.get_user(owner_id)
        return user.display_name if user else f"玩家 {owner_id}"
    return "其他玩家"


def _build_td_map(state: fs.FortressState) -> str:
    """建立蛇形塔防地圖。"""
    grid = [["🟩" for _ in range(_TD_GRID_COLS)] for _ in range(_TD_GRID_ROWS)]

    for row, col in _TD_PATH_COORDS:
        grid[row][col] = "🟫"

    occupied_slots = set(state.tower_slots.values())
    for slot_id, meta in _TD_TOWER_SLOTS.items():
        row, col = meta["coord"]
        grid[row][col] = "🗼" if slot_id in occupied_slots else "🔲"

    grid[_TD_FORT_COORD[0]][_TD_FORT_COORD[1]] = "🏯"

    alive = sorted([e for e in state.enemies if not e.defeated], key=lambda enemy: enemy.rank)
    occupied_path_cells = set()
    for enemy in alive:
        icon = _rank_to_icon(enemy.rank)
        target = _enemy_path_pos(enemy)
        chosen_index = None
        for distance in range(len(_TD_PATH_COORDS)):
            for try_index in (target - distance, target + distance):
                if not 0 <= try_index < len(_TD_PATH_COORDS):
                    continue
                coord = _TD_PATH_COORDS[try_index]
                if coord not in occupied_path_cells:
                    chosen_index = try_index
                    occupied_path_cells.add(coord)
                    break
            if chosen_index is not None:
                break
        if chosen_index is None:
            continue
        row, col = _TD_PATH_COORDS[chosen_index]
        grid[row][col] = icon

    return "\n".join("".join(row) for row in grid)


def _tower_summary_lines(state: fs.FortressState) -> List[str]:
    lines = []
    for slot_id, meta in _TD_TOWER_SLOTS.items():
        owner_id = next((uid for uid, owned_slot in state.tower_slots.items() if owned_slot == slot_id), None)
        if owner_id is None:
            lines.append(f"▫️ {_tower_slot_label(slot_id)}：空位")
            continue
        lines.append(f"🗼 {_tower_slot_label(slot_id)}：玩家 {owner_id}")
    return lines


# ─── Embed 建構函數 ────────────────────────────────────────

def build_battle_embed(state: fs.FortressState) -> discord.Embed:
    """塔防風格戰鬥 Embed"""
    now = datetime.now(TW_TZ)
    ends = datetime.fromisoformat(state.ends_at)
    # 相容 naive/aware：統一轉為 aware 再比較
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=TW_TZ)
    remaining_min = max(0, int((ends - now).total_seconds() / 60))

    alive         = [e for e in state.enemies if not e.defeated]
    defeated_count = len(state.enemies) - len(alive)

    # 堡壘狀態 → 動態顏色與警示
    fort_pct = state.fortress_hp / state.fortress_max_hp if state.fortress_max_hp else 1.0
    if fort_pct > 0.6:
        embed_color = 0xE74C3C
        fort_status = "🟢 穩固"
    elif fort_pct > 0.3:
        embed_color = 0xE67E22
        fort_status = "🟡 受損"
    else:
        embed_color = 0x922B21
        fort_status = "🔴 危急！"

    td_map = _build_td_map(state)

    description = (
        f"🏯 **KK 詐騙園區** {fort_status}\n"
        f"`{state.fortress_hp_bar()}`\n\n"
        f"{td_map}\n\n"
        f"⬅️ 敵軍由左側入侵路線前進，🗼 砲台自動射擊\n"
        f"⏱️ 距結算剩餘 **{remaining_min}** 分鐘　"
        f"💀 已殲滅 **{defeated_count}/{len(state.enemies)}** 敵"
    )

    embed = discord.Embed(
        title="⚔️ KK 園區堡壘保衛戰！",
        description=description,
        color=embed_color,
        timestamp=now,
    )

    # 敵軍詳細列表（含推進進度）
    rank_labels = {1: "👑 BOSS", 2: "⚡ 精英", 3: "⚡ 精英"}
    enemy_lines = []
    for e in sorted(state.enemies, key=lambda x: x.rank):
        label = rank_labels.get(e.rank, f"💀 #{e.rank}")
        if e.defeated:
            enemy_lines.append(f"~~{label} · {e.name}~~ ✅ 已消滅")
        else:
            advance = int((1 - e.current_hp / e.max_hp) * 100) if e.max_hp else 100
            warn    = "‼️" if advance >= 80 else ("⚠️" if advance >= 50 else "")
            enemy_lines.append(
                f"{warn}{label} **{e.name}**（推進 {advance}%）\n"
                f"└ `{e.hp_bar(8)}`"
            )

    embed.add_field(
        name=f"🗡️ 入侵敵軍（{len(alive)} 存活 / {len(state.enemies)} 總計）",
        value="\n".join(enemy_lines) or "所有敵軍已消滅！",
        inline=False,
    )
    embed.add_field(
        name="🗺️ 戰線說明",
        value="蛇形戰線會一路彎進 KK 園區；🔲 可蓋塔，🗼 已架設砲台，🏯 是園區核心。",
        inline=False,
    )
    embed.add_field(
        name="🗼 塔位部署",
        value="\n".join(_tower_summary_lines(state)),
        inline=False,
    )

    embed.add_field(
        name="🛡️ 防守狀況",
        value=f"**{len(state.defenders)}** 名英雄出兵\n每人 {fs.FREE_ACTIONS_PER_ROUND} 次免費出兵",
        inline=True,
    )
    embed.add_field(
        name="💎 強化攻擊",
        value=f"消耗 **{fs.PAID_COST_KKCOIN}** KKCoin\n{fs.BASE_DAMAGE_PAID} 傷害（標籤再 ×2）",
        inline=True,
    )
    embed.add_field(
        name="🏷️ 加倍獎勵",
        value="前 2 小時勝利 x2\n前 3 小時勝利 x1.5",
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
    tower_label = _get_tower_label_for_user(state, user_id)
    embed.add_field(
        name="砲台位置",
        value=tower_label if tower_label else "尚未架設（可直接用下拉選單選塔位）",
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
        reward_text = ""
        if result.get("total_reward_kkcoin", 0) > 0:
            reward_text = (
                f"\n💰 本輪獎勵：{result['total_reward_kkcoin']:,} KKCoin"
                f"（x{result.get('reward_multiplier', 1.0):.1f}）"
            )
        desc = (
            f"全服英雄合力消滅 {result['enemies_defeated']}/{result['enemies_total']} 個敵人！"
            f"\n⏱️ 提前完成：剩餘 {result.get('remaining_minutes', 0)} 分鐘"
            f"{reward_text}"
        )
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
            reward = result.get("reward_map", {}).get(str(uid), 0)
            reward_suffix = f" | +{reward:,} KKCoin" if reward else ""
            lines.append(f"{medals[i]} **{name}** — {dmg:,} 傷害 ({pct}%){reward_suffix}")
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
        self._settled_round_ids: set[str] = set()
        self._last_embed_refresh_at: Optional[datetime] = None
        self.settle_task.start()
        self.update_trends_scheduled.start()
        self.command_poll_task.start()
        log.info("[Fortress] Cog 已初始化")

    def cog_unload(self):
        self.settle_task.cancel()
        self.update_trends_scheduled.cancel()
        self.command_poll_task.cancel()

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

    async def _start_battle_from_trends(self) -> tuple[bool, str, int]:
        """抓取趨勢並啟動戰鬥，供 slash 與文字指令共用。"""
        log.info("[Fortress] 手動開戰流程開始")
        try:
            from market_trends_serpapi import get_trending_topics

            trends_data = await asyncio.wait_for(get_trending_topics(limit=10), timeout=25)
            if not trends_data:
                log.warning("[Fortress] 手動開戰失敗：趨勢資料為空")
                return False, "無法取得趨勢資料，請稍後再試", 0

            await self.start_battle(trends_data)
            log.info(f"[Fortress] 手動開戰成功，敵人數={len(trends_data)}")
            return True, "堡壘保衛戰已手動啟動！", len(trends_data)
        except asyncio.TimeoutError:
            log.error("[Fortress] 手動開戰逾時：SerpApi 超過 25 秒未返回")
            return False, "取得趨勢資料逾時，請稍後再試", 0
        except Exception as e:
            log.exception(f"[Fortress] 手動開戰失敗: {e}")
            return False, f"開戰失敗：{e}", 0

    async def _finalize_and_announce_battle(self):
        """統一處理戰鬥結算、獎勵發放與公告。"""
        state_before = fs.get_current_battle()
        if not state_before or state_before.round_id in self._settled_round_ids:
            return

        result = fs.settle_battle()
        if not result.get("success"):
            return

        self._settled_round_ids.add(result["round_id"])

        if result["status"] == "victory":
            for uid in result["damage_map"]:
                add_user_field(int(uid), "fortress_wins", 1)
            for uid, reward in result.get("reward_map", {}).items():
                if reward > 0:
                    add_user_field(int(uid), "kkcoin", reward)

        channel = self.bot.get_channel(self._battle_channel_id)
        if channel:
            embed = build_settlement_embed(result, self.bot)
            await channel.send(embed=embed)

            if self._battle_message_id:
                try:
                    msg = await channel.fetch_message(self._battle_message_id)
                    state_final = fs.get_current_battle()
                    if state_final:
                        await msg.edit(embed=build_battle_embed(state_final), view=None)
                except Exception:
                    pass

        log.info(f"[Fortress] 結算完成: {result['status']}")

    async def refresh_battle_embed(self, interaction: discord.Interaction):
        """在有人出兵後更新戰況 Embed"""
        try:
            if not self._battle_message_id or not self._battle_channel_id:
                return

            state = fs.get_current_battle()
            if not state:
                return

            now = datetime.now(TW_TZ)
            if state.status == "active" and self._last_embed_refresh_at:
                elapsed = (now - self._last_embed_refresh_at).total_seconds()
                if elapsed < EMBED_REFRESH_COOLDOWN_SECONDS:
                    return

            channel = self.bot.get_channel(self._battle_channel_id)
            if not channel:
                return
            msg = await channel.fetch_message(self._battle_message_id)
            if state:
                view = None if state.status != "active" else FortressEnemyView(self)
                await msg.edit(embed=build_battle_embed(state), view=view)
                self._last_embed_refresh_at = now
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
            await self._finalize_and_announce_battle()

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

    @tasks.loop(seconds=15)
    async def command_poll_task(self):
        """輪詢伺服器端命令檔，作為 Discord slash 故障時的 fallback。"""
        try:
            if not os.path.exists(FORTRESS_COMMAND_FILE):
                return

            with open(FORTRESS_COMMAND_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)

            os.remove(FORTRESS_COMMAND_FILE)
            if payload.get("command") != "start":
                return

            log.info("[Fortress] 接收到伺服器端手動開戰命令")
            success, msg, count = await self._start_battle_from_trends()
            if success:
                log.info(f"[Fortress] 伺服器端手動開戰成功，敵人數={count}")
            else:
                log.warning(f"[Fortress] 伺服器端手動開戰失敗: {msg}")
        except FileNotFoundError:
            return
        except Exception as e:
            log.error(f"[Fortress] 命令輪詢失敗: {e}")

    @command_poll_task.before_loop
    async def before_command_poll(self):
        await self.bot.wait_until_ready()

    # ── 管理員手動開戰 ────────────────────────────────────

    @app_commands.command(name="fortress_admin_start", description="[管理員] 立即抓取趨勢並開啟新一輪堡壘保衛戰")
    @app_commands.default_permissions(administrator=True)
    async def fortress_admin_start(self, interaction: discord.Interaction):
        """管理員手動觸發堡壘保衛戰（補發用）"""
        log.info(f"[Fortress] slash /fortress_admin_start invoked by {interaction.user.id}")
        await interaction.response.defer(ephemeral=True)
        success, msg, count = await self._start_battle_from_trends()
        if not success:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ {msg} 共 {count} 個趨勢敵人。",
            ephemeral=True
        )

    @fortress_admin_start.error
    async def fortress_admin_start_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        log.exception(f"[Fortress] slash /fortress_admin_start error: {error}")
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ 開戰失敗：{error}", ephemeral=True)
            return
        await interaction.response.send_message(f"❌ 開戰失敗：{error}", ephemeral=True)

    @commands.command(name="fortress_start")
    @commands.has_permissions(administrator=True)
    async def fortress_start_text(self, ctx: commands.Context):
        """文字指令 fallback：!fortress_start"""
        log.info(f"[Fortress] text !fortress_start invoked by {ctx.author.id}")
        success, msg, count = await self._start_battle_from_trends()
        if not success:
            await ctx.send(f"❌ {msg}")
            return
        await ctx.send(f"✅ {msg} 共 {count} 個趨勢敵人。")


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
