'use strict';
/* mocks.js — 寫手 A 側模組空殼（照 design/api-signatures.md §0–6 簽名回固定/mock 資料）
   ※ A 真實作落地後：整檔刪除＋index.html 移除本行。B 的渲染碼零改動（只吃簽名）。
   Bus＝事件匯流排（emit/on，沿用舊遊戲 Sim.on 模式——簽名 §7）。 */

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

/* ===== Map（簽名 §1）：mock 8 街區（切片範圍），obstacles 全 0 ===== */
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
};

/* ===== Faction（簽名 §2）：mock 上色語意（渲染鐵律——B 只准問 sideOf） ===== */
const Faction = {
  push(S) {
    // 真引擎（A2）：ctrl 推拉＋定色＋易手事件。mock 不動 ctrl。
    return { events: [] };
  },
  flip(S) {
    S.faction = S.faction === 'park' ? 'police' : 'park';
    Bus.emit('flip', S.faction);
    return S;
  },
  sideOf(S, block) {
    // mock 語意：街區當前控制方是否 = 我方陣營（跳槽後自動反轉）。真引擎可改演算法，簽名不變。
    const mineGreen = block.ctrl > 0;
    return (S.faction === 'park') === mineGreen ? 'mine' : 'foe';
  },
};

/* ===== Dice（簽名 §3）：mock 偏向成功（QA 體感），形狀照簽名 ===== */
const Dice = {
  roll(attrKey, dc, opts) {
    const bonus = (opts && opts.bonus) || 0;
    const d20 = 8 + ((Math.random() * 13) | 0);          // mock 偏置 8–20（真實作改 1–20）
    const attr = S.attrs[attrKey] || 0;
    const total = d20 + attr + bonus;
    return { d20, attr, bonus, total, dc, ok: total >= dc, crit: d20 === 20, fumble: d20 === 1 };
  },
  consequence(kind, roll) {
    void kind; void roll;
    return { text: '（mock：後果表等寫手 A）', effects: {} };
  },
};

/* ===== Star（簽名 §4）：mock 固定 0 星、無追擊、無怪潮 ===== */
const Star = {
  update(dt, ctx) {
    void dt; void ctx;
    return { stars: S.stars, chasers: [], wave: null };
  },
  useSkill(skill) { void skill; return false; },
};

/* ===== Base（簽名 §5）：mock 點擊機（+1 貨），雇員/升級空殼 ===== */
const Base = {
  click(base) {
    S.goods += 1;
    Bus.emit('money', 0);   // 貨不是錢——先不發 money；匯率機制等 A
    return { goods: 1 };
  },
  tick() {}, hire() {}, upgrade() {},
  offline(S, hoursAway) { return { gain: 0, backlog: [] }; },
  resolveSuspect(S, idx, choice) { void idx; void choice; return { text: '' }; },
};

/* ===== Save（簽名 §6）：mock 記憶體存檔（localStorage 留 A） ===== */
const Save = {
  load() { return null; },
  save(S) {},
  dayEnd(S) {
    Faction.push(S);
    S.day += 1;
    Bus.emit('dayEnd', { report: [] });
    return S;
  },
  newGame() {
    const gen = BlockMap.generate(S.seed);
    S.blocks = gen.blocks;
    return S;
  },
  reset() {},
};
