'use strict';
/* loot.js — POE 掉落：稀有度 roll → 詞綴 roll（不重複效果鍵）→ 裝備物件＋光柱 */

const Loot = (() => {
  // 權重抽稀有度
  function rollRarity(elite) {
    if (elite) return RARITY[2];                     // 精英必掉稀有
    const total = RARITY.reduce((s, r) => s + r.w, 0);
    let x = Math.random() * total;
    for (const r of RARITY) { x -= r.w; if (x <= 0) return r; }
    return RARITY[0];
  }

  // 從詞綴池抽 n 條，效果鍵不重複（POE 規則）；w=槽位加權表（可省）
  function rollAffixes(pool, n, w) {
    const out = [], used = new Set();
    let guard = 24;
    const wt = a => 1 + ((w && w[a.k]) || 0);
    while (out.length < n && guard-- > 0) {
      const total = pool.reduce((s, a) => s + (used.has(a.k) ? 0 : wt(a)), 0);
      let x = Math.random() * total;
      let pick = pool[pool.length - 1];
      for (const a of pool) {
        if (used.has(a.k)) continue;
        x -= wt(a);
        if (x <= 0) { pick = a; break; }
      }
      used.add(pick.k);
      const v = pick.val[0] + Math.round(Math.random() * (pick.val[1] - pick.val[0]));
      out.push({ k: pick.k, v, fmt: pick.fmt, stat: pick.stat, label: pick.label });
    }
    return out;
  }

  // 生成一件裝備：先 roll 槽位 → 該槽底裝 → 詞綴照槽位加權
  function makeItem(elite) {
    const rar = rollRarity(elite);
    const nPre = rar.affixes === 1 ? 1 : rar.affixes === 2 ? 1 : 2;
    const nSuf = rar.affixes === 1 ? 0 : rar.affixes === 2 ? 1 : 2;
    const slot = GEAR_SLOTS[(Math.random() * GEAR_SLOTS.length) | 0];
    const pre = rollAffixes(PREFIXES, nPre, slot.affixW);
    const suf = rollAffixes(SUFFIXES, nSuf, slot.affixW);
    const base = slot.bases[(Math.random() * slot.bases.length) | 0];
    const name = (pre[0] ? pre[0].label : '') + base + (suf[0] ? suf[0].label : '');
    return { name, slot: slot.id, slotLabel: slot.label, rarity: rar, affixes: [...pre, ...suf], t: 0 };
  }

  // 詞綴 → 玩家統計（裝備即時生效）
  function applyToStats(stats, item) {
    for (const a of item.affixes) {
      switch (a.k) {
        case 'dmg':    stats.dmgPct += a.v; break;
        case 'aspd':   stats.aspdPct += a.v; break;
        case 'bullet': stats.bullets += a.v; break;
        case 'pierce': stats.pierce += a.v; break;
        case 'mspd':   stats.mspdPct += a.v; break;
        case 'hp':     stats.maxHp += a.v; stats.hp += a.v; break;
        case 'magnet': stats.magnetPct += a.v; break;
        case 'xp':     stats.xpPct += a.v; break;
      }
    }
  }

  // 一行詞綴文字（面板/分享卡共用）
  function affixLine(a) { return a.fmt(a.v); }

  return { makeItem, applyToStats, affixLine };
})();
