'use strict';
/* engine.js — 寫手 A 側模組（v0.2.0：Faction 推拉＋踩點／Dice 真 d20／Base 點擊機／Save 日結＋localStorage）
   仍 mock：BlockMap（8 街區手擺，Voronoi=A1 待做）、Star（恆 0 星，A4 待做）。
   契約見 design/api-signatures.md。本版新增：BlockMap.blockAt／Faction.scout／
   Save.dayEnd report 形狀／Bus 'money' 由引擎在收帳時 emit。 */

const Bus = {
  L: {},
  on(k, f) { (this.L[k] = this.L[k] || []).push(f); },
  emit(k, a) { (this.L[k] || []).forEach((f) => { try { f(a); } catch (e) { console.error(e); } }); },
};

/* ===== S：唯一資料中心（簽名 §0 形狀） ===== */
window.S = {
  ver: 1, seed: 20261124, day: 1, phase: 'street',
  money: 3000, goods: 0, faction: 'park', stars: 0, heat: 0,
  attrs: { talk: 1, agility: 1, brain: 1, guts: 1 },
  attrExp: { talk: 0, agility: 0, brain: 0, guts: 0 },
  blocks: [], bases: [], suspects: [],
  skills: { bait: 0, smoke: 0, bot: 0 },
  police: 0, switchCooldown: 0,
};

/* ===== BlockMap（簽名 §1）：8 街區 mock 圖＋blockAt 點測（Voronoi=A1 待做） ===== */
const BlockMap = {
  W: 1440, H: 960, TILE: 32,
  generate(seed) {
    void seed;
    const raw = [
      { type: 'biz',     ctrl: 85,  polygon: [[30, 40], [300, 25], [360, 200], [330, 400], [120, 430], [20, 260]] },
      { type: 'biz',     ctrl: 40,  polygon: [[380, 30], [640, 45], [700, 240], [620, 420], [390, 400], [370, 220]] },
      { type: 'neutral', ctrl: 12,  polygon: [[30, 460], [330, 440], [380, 620], [350, 900], [120, 930], [25, 700]] },
      { type: 'neutral', ctrl: -5,  polygon: [[400, 440], [660, 430], [710, 640], [640, 910], [400, 920], [385, 640]] },
      { type: 'watch',   ctrl: -30, polygon: [[740, 40], [1020, 30], [1080, 220], [1040, 430], [760, 420], [730, 230]] },
      { type: 'watch',   ctrl: -60, polygon: [[740, 450], [1060, 440], [1110, 650], [1050, 920], [750, 910], [725, 660]] },
      { type: 'neutral', ctrl: 25,  polygon: [[1110, 30], [1400, 45], [1420, 240], [1380, 420], [1120, 430], [1095, 220]] },
      { type: 'biz',     ctrl: -95, polygon: [[1130, 450], [1410, 460], [1425, 660], [1390, 920], [1140, 910], [1108, 650]] },
    ];
    const blocks = raw.map((r, i) => ({
      id: i, polygon: r.polygon, center: BlockMap.centroid(r.polygon),
      ctrl: r.ctrl, locked: null, lockStreak: 0, type: r.type, yieldRate: 1.0, watch: 0,
    }));
    S.blocks = blocks;
    const gw = Math.ceil(BlockMap.W / BlockMap.TILE), gh = Math.ceil(BlockMap.H / BlockMap.TILE);
    return { blocks, obstacles: new Uint8Array(gw * gh) };   // mock 無障礙
  },
  centroid(poly) {
    let a = 0, cx = 0, cy = 0;
    for (let i = 0; i < poly.length; i++) {
      const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length];
      const cr = x1 * y2 - x2 * y1;
      a += cr; cx += (x1 + x2) * cr; cy += (y1 + y2) * cr;
    }
    a /= 2;
    return a ? [cx / (6 * a), cy / (6 * a)] : [poly[0][0], poly[0][1]];
  },
  blockAt(S, x, y) {
    for (const b of S.blocks) {
      let inside = false;
      const p = b.polygon;
      for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
        const [xi, yi] = p[i], [xj, yj] = p[j];
        if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
      }
      if (inside) return b;
    }
    return null;
  },
};

/* ===== Faction（簽名 §2）：推拉引擎真實作（spec §2.2）＋踩點 ===== */
const Faction = (() => {
  const NEIGHBOR_R = 460;   // mock 街區網格的相鄰判定：中心距（Voronoi 真圖改共用邊）
  const SCOUT_CD = 5000;    // 踩點冷卻（spec §2.2 未定值，v1 取 5s）
  const SCOUT_GAIN = 8;     // 踩點 +8（spec §2.2）
  let lastScout = 0;

  function adjacency(S) {
    const adj = S.blocks.map(() => []);
    for (let i = 0; i < S.blocks.length; i++) {
      for (let j = i + 1; j < S.blocks.length; j++) {
        const a = S.blocks[i].center, b = S.blocks[j].center;
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) <= NEIGHBOR_R) { adj[i].push(j); adj[j].push(i); }
      }
    }
    return adj;
  }

  // 每日結算（睡覺段呼叫）：ctrl[blk] += parkPush - policePush + neighborFlow（spec §2.2）
  function push(S) {
    const adj = adjacency(S);
    const events = [], locks = [];
    S.blocks.forEach((b, i) => {
      const parkUnits = S.bases.filter((base) => base.blk === i).length;
      const greenAdj = adj[i].map((j) => S.blocks[j].ctrl).filter((c) => c > 0);
      const greenMean = greenAdj.length ? greenAdj.reduce((a, c) => a + c, 0) / greenAdj.length : 0;
      const parkPush = parkUnits * 0.8 + greenMean * 0.15 - (b.watch || 0) * 0.5;
      // 巡查哨輻射：哨所所在 3.0、相鄰 1.2，×進度係數（S.police 0 → 0.5）
      const factor = 0.5 + (S.police || 0) / 100;
      let radiance = 0;
      S.blocks.forEach((w, j) => {
        if (w.type !== 'watch') return;
        if (j === i || adj[i].includes(j)) radiance += j === i ? 3.0 : 1.2;
      });
      const policePush = radiance * factor;
      const flow = adj[i].reduce((a, j) => a + (S.blocks[j].ctrl - b.ctrl) * 0.1, 0);
      const from = b.ctrl;
      b.ctrl = Math.max(-100, Math.min(100, b.ctrl + parkPush - policePush + flow));
      if (from !== 0 && (from > 0) !== (b.ctrl > 0)) events.push({ blk: i, from: Math.round(from), to: Math.round(b.ctrl) });
      // 定色：|ctrl|==100 連續 3 天（spec §2.2）；綠定色 產出+25%
      if (Math.abs(b.ctrl) >= 100) {
        b.lockStreak += 1;
        if (b.lockStreak >= 3 && !b.locked) {
          b.locked = b.ctrl > 0 ? 'park' : 'police';
          if (b.locked === 'park') b.yieldRate = 1.25;
          locks.push({ blk: i, side: b.locked });
        }
      } else {
        b.lockStreak = 0;
      }
    });
    return { events, locks };
  }

  // 踩點（spec §2.2 玩家主動手段）：站進街區 +8，冷卻 5s
  function scout(S, blk) {
    const now = Date.now();
    if (now - lastScout < SCOUT_CD) return { ok: false, reason: 'cd' };
    lastScout = now;
    blk.ctrl = Math.max(-100, Math.min(100, blk.ctrl + SCOUT_GAIN));
    return { ok: true, blk: blk.id, ctrl: Math.round(blk.ctrl) };
  }

  function flip(S) {
    S.faction = S.faction === 'park' ? 'police' : 'park';
    Bus.emit('flip', S.faction);
    return S;
  }

  function sideOf(S, block) {
    const mineGreen = block.ctrl > 0;
    return (S.faction === 'park') === mineGreen ? 'mine' : 'foe';
  }

  return { push, scout, flip, sideOf };
})();

/* ===== Dice（簽名 §3）：真 d20（spec §5 公式：d20+屬性+修正 vs 難度） ===== */
const Dice = {
  roll(attrKey, dc, opts) {
    const bonus = (opts && opts.bonus) || 0;
    const d20 = 1 + ((Math.random() * 20) | 0);
    const attr = S.attrs[attrKey] || 0;
    const total = d20 + attr + bonus;
    return { d20, attr, bonus, total, dc, ok: total >= dc, crit: d20 === 20, fumble: d20 === 1 };
  },
  consequence(kind, roll) {
    void kind; void roll;
    return { text: '（後果表 v0.3 落地）', effects: {} };
  },
};

/* ===== Star（簽名 §4）：仍 mock——恆 0 星、無追擊、無怪潮（A4 待做） ===== */
const Star = {
  update(dt, ctx) {
    void dt; void ctx;
    return { stars: S.stars, chasers: [], wave: null };
  },
  useSkill(skill) { void skill; return false; },
};

/* ===== Base（簽名 §5）：點擊機真實作（貨→錢匯率在日結算，GOODS_RATE） ===== */
const Base = {
  click(base) {
    S.goods += 1;
    return { goods: S.goods };
  },
  tick() {}, hire() {}, upgrade() {},
  offline(S, hoursAway) { return { gain: 0, backlog: [] }; },
  resolveSuspect(S, idx, choice) { void idx; void choice; return { text: '' }; },
};

/* ===== Save（簽名 §6）：localStorage＋日結流水線（spec §1④／§2.2） ===== */
const Save = (() => {
  const KEY = 'kkpark_block_save';
  const GOODS_RATE = 3;   // 貨→錢匯率 v1（升級鏈後調）

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      const s = JSON.parse(raw);
      return s && s.ver === 1 ? s : null;
    } catch (e) { return null; }
  }

  function save(S) {
    try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* 私密模式容錯 */ }
  }

  function newGame() {
    S.seed = (Date.now() % 1e9) | 0;
    const gen = BlockMap.generate(S.seed);
    S.blocks = gen.blocks;
    S.bases = [{ blk: 0, level: 1, hires: [], goodsRate: 1, upgrades: {} }];   // 切片：1 據點（spec §12）
    return S;
  }

  // 日結流水線：收帳（貨→錢）→ Faction.push → day+1 → 存檔 → 晨報事件
  function dayEnd(S) {
    const goodsSold = S.goods;
    const income = goodsSold * GOODS_RATE;
    S.money += income;
    S.goods = 0;
    if (income > 0) Bus.emit('money', income);
    const settle = Faction.push(S);
    S.day += 1;
    save(S);
    Bus.emit('dayEnd', { day: S.day, goodsSold, income, events: settle.events, locks: settle.locks });
    return S;
  }

  function reset() {
    try { localStorage.removeItem(KEY); } catch (e) { /* 同上 */ }
  }

  return { load, save, dayEnd, newGame, reset };
})();
