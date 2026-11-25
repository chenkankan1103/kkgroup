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

  // 從詞綴池抽 n 條，效果鍵不重複（POE 規則）
  function rollAffixes(pool, n) {
    const out = [], used = new Set();
    let guard = 24;
    while (out.length < n && guard-- > 0) {
      const a = pool[(Math.random() * pool.length) | 0];
      if (used.has(a.k)) continue;
      used.add(a.k);
      const v = a.val[0] + Math.round(Math.random() * (a.val[1] - a.val[0]));
      out.push({ k: a.k, v, fmt: a.fmt, stat: a.stat });
    }
    return out;
  }

  // 生成一件裝備
  function makeItem(elite) {
    const rar = rollRarity(elite);
    const nPre = rar.affixes === 1 ? 1 : rar.affixes === 2 ? 1 : 2;
    const nSuf = rar.affixes === 1 ? 0 : rar.affixes === 2 ? 1 : 2;
    const pre = rollAffixes(PREFIXES, nPre);
    const suf = rollAffixes(SUFFIXES, nSuf);
    const base = BASES[(Math.random() * BASES.length) | 0];
    const name = (pre[0] ? pre[0].label : '') + base + (suf[0] ? suf[0].label : '');
    return { name, rarity: rar, affixes: [...pre, ...suf], t: 0 };  // t=落地壽命計時
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
