# -*- coding: utf-8 -*-
"""守護園區堡壘戰 Components V2 版面。

對應 fortress_defense.py 的 build_battle_embed() / build_settlement_embed()：
戰況卡從 embed（標題 + 8 個 field）換成單一 Container 內的多個 TextDisplay，
塔位下拉與四顆按鈕搬進 ActionRow。custom_id 與舊版 FortressEnemyView 完全
一致，callback 直接借用 legacy view 實例的 bound callback —— 遊戲邏輯只存在
一份，舊版按鈕行為改了這邊自動跟上。

cutover 策略（2026-11-05）：戰役正在進行中，戰場訊息不硬切 ——
- 編輯路徑用 MessageFlags.components_v2 偵測訊息格式：舊訊息維持 classic embed
  更新到當日戰役結束；00:00 結算卡與次日 09:00 新戰場訊息起全部走 V2。
- legacy build_battle_embed / build_settlement_embed 保留在 fortress_defense.py
  當備份，回滾用 git revert cutover commit。

V2 預算：整則訊息所有 TextDisplay 加總 ≤ 4000 字元。敵人戰況表在 legacy 就已
cap 在 1024（_build_enemy_status_field），其餘皆為少量固定文字；本模組另做
總量保護，超過就砍趨勢標題明細（唯一的可壓縮大塊）。
"""

from datetime import datetime

import discord
from discord import ui

from cogs.ui.fortress_defense import (
    TW_TZ,
    FortressEnemyView,
    _build_enemy_status_field,
    _build_td_map,
    _get_map_layout,
    _movement_rule_text,
    _tower_summary_lines,
    _truncate_embed_line,
)
from cogs.ui.utils.embed_utils import create_progress_bar
from shared.utils import fortress_system as fs

# 文字總預算：整則 V2 訊息所有 TextDisplay 加總上限 4000，留一點餘裕
_BUDGET_GUARD = 3950


def _hp_status(state: fs.FortressState) -> tuple[int, str]:
    """堡壘血量 → (accent 色, 狀態文字)，與 legacy build_battle_embed 同一套門檻。"""
    fort_pct = (
        state.fortress_hp / state.fortress_max_hp if state.fortress_max_hp else 1.0
    )
    if fort_pct > 0.6:
        return 0xE74C3C, "🟢 穩固"
    if fort_pct > 0.3:
        return 0xE67E22, "🟡 受損"
    return 0x922B21, "🔴 危急！"


def _battle_blocks(state: fs.FortressState, bot: discord.Client) -> tuple[list, int]:
    """組出戰況卡的全部文字區塊（與 legacy embed 資訊 1:1），回傳 (區塊列表, accent 色)。"""
    now = datetime.now(TW_TZ)
    ends = datetime.fromisoformat(state.ends_at)
    layout = _get_map_layout(state)
    # 相容 naive/aware：統一轉為 aware 再比較
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=TW_TZ)
    remaining_min = max(0, int((ends - now).total_seconds() / 60))

    alive = [e for e in state.enemies if not e.defeated]
    defeated_count = len(state.enemies) - len(alive)
    accent, fort_status = _hp_status(state)

    latest_wave_titles = []
    if state.wave_history:
        latest_wave_titles = state.wave_history[-1].get("titles", [])
    latest_wave_text = (
        "、".join(_truncate_embed_line(t, 40) for t in latest_wave_titles[:10])
        if latest_wave_titles
        else "等待趨勢資料"
    )

    header = (
        f"## ⚔️ KK 園區堡壘戰戰況播報\n"
        f"📡 **戰況播報**｜{state.battle_date} 單日堡壘戰\n"
        f"🏯 **KK 詐騙園區** {fort_status}\n"
        f"🗺️ 本輪地圖：**{layout['name']}**\n"
        f"🌊 目前已進入 **第 {state.current_wave_number} 波**\n"
        f"`{state.fortress_hp_bar()}`"
    )
    status_line = (
        "⬅️ 刑警大隊由左側路線前進，🗼 砲台自動射擊\n"
        f"📏 {_movement_rule_text(layout)}\n"
        f"⏱️ 距結算剩餘 **{remaining_min}** 分鐘　"
        f"💀 已攔截 **{defeated_count}/{len(state.enemies)}** 名刑警"
    )
    map_block = _build_td_map(state)
    waves_block = (
        f"**📰 本波新出兵標題**\n{latest_wave_text}\n"
        f"**🗂️ 今日已出現趨勢**：共 **{len(state.daily_trend_titles)}** 個標題"
    )
    enemy_block = (
        f"**前來執法的刑警大隊（{len(alive)} 在場 / {len(state.enemies)} 總計）**\n"
        f"{_build_enemy_status_field(state) or '所有刑警已撤離！'}"
    )
    frontline_block = (
        f"**🗺️ 戰線說明**\n{layout['name']} 會依輪次自動切換；"
        f"🔲 可蓋塔，🗼 已架設砲台，⚡ 砲台攻擊範圍，🏯 是園區核心。\n"
        f"📏 {_movement_rule_text(layout)}\n"
        f"🔥 砲台每30秒自動攻擊範圍內刑警（2格範圍）"
    )
    towers_block = "**🗼 塔位部署**\n" + "\n".join(_tower_summary_lines(state, bot))
    drafted_block = ""
    if state.drafted_defenders:
        drafted_names = []
        for uid in state.drafted_defenders:
            user = bot.get_user(uid)
            drafted_names.append(user.display_name if user else f"玩家{uid}")
        drafted_block = "**🚨 被抓來防守**\n" + "、".join(drafted_names)
    perks_block = (
        f"**🛡️ 對抗狀況**：**{len(state.defenders)}** 名英雄出兵\n"
        f"每人 {fs.FREE_ACTIONS_PER_ROUND} 次免費出兵\n"
        f"**💎 強化攻擊**：消耗 **{fs.PAID_COST_KKCOIN}** KKCoin\n"
        f"{fs.BASE_DAMAGE_PAID} 傷害（標籤再 ×2）\n"
        f"**🏷️ 加倍獎勵**：前 2 小時勝利 x2\n前 3 小時勝利 x1.5"
    )
    status_map = {"active": "🟢 進行中", "victory": "🎉 勝利", "defeat": "💀 失守"}
    footer = (
        f"-# 狀態：{status_map.get(state.status, state.status)}"
        f" | 單日戰役 {state.round_id} | 目前第 {state.current_wave_number} 波"
        f" | <t:{int(now.timestamp())}:f>"
    )

    blocks = [
        ("header", header),
        ("map", map_block),
        ("status", status_line),
        ("waves", waves_block),
        ("enemy", enemy_block),
        ("frontline", frontline_block),
        ("towers", towers_block),
        ("drafted", drafted_block),
        ("perks", perks_block),
        ("footer", footer),
    ]
    blocks = [(k, t) for k, t in blocks if t]

    # 預算保護：依序折疊可壓縮的大塊（波次標題 → 防守名單 → 戰線說明），
    # 一般情形到不了這裡（標題截 40 字 + 敵軍表自 cap 1024 已夠小）
    def _total() -> int:
        return sum(len(t) for _, t in blocks)

    def _collapse(key: str, replacement: str):
        nonlocal blocks
        rebuilt = []
        for k, t in blocks:
            if k == key:
                if replacement:
                    rebuilt.append((k, replacement))
            else:
                rebuilt.append((k, t))
        blocks = rebuilt

    if _total() > _BUDGET_GUARD:
        _collapse(
            "waves",
            f"**📰 本波新出兵標題**\n（標題過長，共 {len(latest_wave_titles)} 則，略）",
        )
    if _total() > _BUDGET_GUARD and drafted_block:
        _collapse(
            "drafted",
            f"**🚨 被抓來防守**\n共 {len(state.drafted_defenders)} 人（名單過長，略）",
        )
    if _total() > _BUDGET_GUARD:
        _collapse("frontline", "")  # 最後手段：移除與上方重複的說明區
    return [t for _, t in blocks], accent


class FortressBattleLayoutView(ui.LayoutView):
    """戰場互動面板（V2）：戰況 Container + 塔位下拉列 + 按鈕列。

    Select 獨佔一列是 Discord 規則（一條 ActionRow 只能全按鈕或單一 Select）。
    互動元件的 callback 全部借用 legacy FortressEnemyView 實例的 bound
    callback —— custom_id 一致，重啟後 setup() 的 add_view(FortressEnemyView)
    全域註冊也照樣接得到（V2 訊息的 custom_id 相同）。
    """

    def __init__(self, cog, state: fs.FortressState, bot: discord.Client):
        super().__init__(timeout=None)
        self.cog = cog
        legacy = FortressEnemyView(cog)

        blocks, accent = _battle_blocks(state, bot)
        container = ui.Container(accent_colour=discord.Color(accent))
        for text in blocks:
            container.add_item(ui.TextDisplay(text))
        self.add_item(container)

        legacy_select = next(c for c in legacy.children if isinstance(c, ui.Select))
        select = ui.Select(
            placeholder=legacy_select.placeholder,
            options=list(legacy_select.options),
            custom_id=legacy_select.custom_id,
            min_values=1,
            max_values=1,
        )
        select.callback = legacy_select.callback
        self.add_item(ui.ActionRow(select))

        buttons = []
        for legacy_item in legacy.children:
            if isinstance(legacy_item, ui.Button):
                item = ui.Button(
                    label=legacy_item.label,
                    style=legacy_item.style,
                    custom_id=legacy_item.custom_id,
                    disabled=legacy_item.disabled,
                    emoji=legacy_item.emoji,
                )
                item.callback = legacy_item.callback
                buttons.append(item)
        self.add_item(ui.ActionRow(*buttons))


def build_battle_layout(
    cog, state: fs.FortressState, bot: discord.Client
) -> FortressBattleLayoutView:
    """生成戰場面板的 V2 版面（含互動元件）。"""
    return FortressBattleLayoutView(cog=cog, state=state, bot=bot)


def build_settlement_layout(result: dict, bot: discord.Client) -> ui.LayoutView:
    """生成結算卡的 V2 版面（單向公告，無互動元件）。"""
    won = result["status"] == "victory"
    accent = 0x2ECC71 if won else 0x95A5A6
    battle_date = result.get("battle_date", result["round_id"])
    defeated, total = result["enemies_defeated"], result["enemies_total"]
    remaining = result.get("remaining_minutes", 0)

    if won:
        header = (
            f"## 🎉 {battle_date} 守城成功！\n"
            f"全服英雄合力消滅 **{defeated} / {total}** 名敵軍！"
        )
    else:
        header = f"## 💀 {battle_date} 堡壘失守\n堡壘被攻破了，刑警大隊突破防線。"
        if result.get("beta_no_penalty"):
            header += "\n（封測期間暫無懲罰，放心繼續試玩！）"

    stats_lines = [f"**⚔️ 殲滅敵軍**：**{defeated} / {total}**"]
    if won:
        reward = result.get("total_reward_kkcoin", 0)
        mult = result.get("reward_multiplier", 1.0)
        stats_lines.append(f"**⏱️ 剩餘時間**：**{remaining} 分**")
        stats_lines.append(f"**💰 本日獎勵**：**{reward:,}** KKCoin ×{mult:.1f}")
    else:
        stats_lines.insert(
            0, f"**🏯 堡壘剩餘 HP**：**{result['fortress_hp_remaining']:,}**"
        )
        stats_lines.append(f"**⏱️ 剩餘時間**：**{remaining} 分**")
    stats_block = "\n".join(stats_lines)

    heroes_block = ""
    damage_map: dict = result.get("damage_map", {})
    if damage_map:
        sorted_heroes = sorted(
            damage_map.items(), key=lambda x: x[1], reverse=True
        )[:10]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        hero_lines = []
        for i, (uid, dmg) in enumerate(sorted_heroes):
            user = bot.get_user(int(uid))
            raw_name = user.display_name if user else f"玩家 {uid}"
            name = _truncate_embed_line(raw_name, 24)
            pct = result["contributions"].get(
                uid, result["contributions"].get(str(uid), 0)
            )
            bar = create_progress_bar(pct, 100, 10)
            detail = f"　　{int(dmg):,} 傷害"
            reward = result.get("reward_map", {}).get(str(uid), 0)
            if reward:
                detail += f" · +{reward:,} KKCoin"
            hero_lines.append(f"{medals[i]} **{name}** `{bar}` {pct}%\n{detail}")
        heroes_block = "**🏆 對抗英雄榜**\n" + "\n".join(hero_lines)

    waves_block = ""
    wave_history = result.get("wave_history", [])
    if wave_history:
        wave_lines = []
        for wave in wave_history:
            titles = wave.get("titles", [])
            title_text = (
                "、".join(_truncate_embed_line(t, 40) for t in titles)
                if titles
                else "無資料"
            )
            wave_lines.append(f"• 第 {wave.get('wave_number', '?')} 波 · {title_text}")
        waves_block = (
            f"**📰 當天趨勢（共 {len(wave_history)} 波）**\n" + "\n".join(wave_lines)
        )

    footer = f"-# 單日戰役 {result['round_id']}"

    blocks = [b for b in (header, stats_block, heroes_block, waves_block, footer) if b]
    # 預算保護：趨勢明細是唯一大塊，超了就折疊
    total = sum(len(b) for b in blocks)
    if total > _BUDGET_GUARD:
        collapsed = f"**📰 當天趨勢（共 {len(wave_history)} 波）**\n（標題過長，略）"
        blocks = [collapsed if b is waves_block else b for b in blocks]

    view = ui.LayoutView()
    container = ui.Container(accent_colour=discord.Color(accent))
    for text in blocks:
        container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


async def setup(bot):
    """本檔是版面模組不是 cog；uibot 會掃 cogs/ui/ 全載，補空 setup 防噴載入失敗。"""
