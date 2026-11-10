'use strict';
/* data.js — 平衡數值表：武器、被動、敵人、波次時間軸 */

const RUN_TIME = 600; // 一場 10 分鐘

// ===== 武器（maxLv 5；滿級＋對應被動滿級 → 進化） =====
const WEAPONS = {
  dart: {
    name: 'KK幣飛鏢',
    icon: '🪙',
    desc: '自動射擊最近的敵人',
    evoName: '黃金發財鏢',
    evoIcon: '🌟',
    evoDesc: '追蹤導彈化，彈數+2、傷害翻倍',
    evoWith: 'dmg', // 需「經紀人加持」滿級
    lv: [
      { cd: 0.9, dmg: 10, count: 1, spd: 380 },
      { cd: 0.8, dmg: 12, count: 1, spd: 400 },
      { cd: 0.7, dmg: 14, count: 2, spd: 420 },
      { cd: 0.6, dmg: 16, count: 2, spd: 440 },
      { cd: 0.5, dmg: 18, count: 3, spd: 460 },
    ],
  },
  glowstick: {
    name: '應援螢光棒',
    icon: '✨',
    desc: '螢光棒繞著你旋轉，碰撞造成傷害',
    evoName: '雙生霓虹棒',
    evoIcon: '💫',
    evoDesc: '棒數翻倍、變大、範圍更廣',
    evoWith: 'speed', // 需「咖啡因汽水」滿級
    lv: [
      { dmg: 8, n: 1, r: 62, spd: 2.6, size: 1 },
      { dmg: 10, n: 1, r: 70, spd: 2.8, size: 1 },
      { dmg: 12, n: 2, r: 76, spd: 3.0, size: 1 },
      { dmg: 15, n: 2, r: 84, spd: 3.2, size: 1.15 },
      { dmg: 18, n: 3, r: 92, spd: 3.4, size: 1.25 },
    ],
  },
  sonic: {
    name: '音浪應援',
    icon: '📢',
    desc: '定期發出擴散音波，擊退敵人',
    evoName: '共鳴風暴',
    evoIcon: '🌀',
    evoDesc: '音波更大更密、擊退力翻倍',
    evoWith: 'cd', // 需「應援節奏」滿級
    lv: [
      { cd: 3.2, dmg: 14, r: 110, knock: 130 },
      { cd: 2.9, dmg: 17, r: 125, knock: 150 },
      { cd: 2.6, dmg: 20, r: 140, knock: 170 },
      { cd: 2.3, dmg: 24, r: 155, knock: 190 },
      { cd: 2.0, dmg: 28, r: 175, knock: 220 },
    ],
  },
  laser: {
    name: '追星雷射',
    icon: '🔆',
    desc: '對最近敵人射出貫穿光束',
    evoName: '銀河雷射',
    evoIcon: '🌠',
    evoDesc: '雙光束、傷害大幅提升',
    evoWith: 'xp', // 需「經紀人契約」滿級
    lv: [
      { cd: 1.6, dmg: 16, len: 340, w: 5 },
      { cd: 1.45, dmg: 19, len: 360, w: 6 },
      { cd: 1.3, dmg: 22, len: 380, w: 7 },
      { cd: 1.15, dmg: 26, len: 410, w: 8 },
      { cd: 1.0, dmg: 30, len: 440, w: 9 },
    ],
  },
};

// ===== 被動（maxLv 5） =====
const PASSIVES = {
  speed: { name: '咖啡因汽水', icon: '🥤', desc: '每級移動速度 +8%', max: 5 },
  pickup: { name: '應援手幅', icon: '🎽', desc: '每級撿寶石半徑 +25%', max: 5 },
  hp: { name: '應援制服', icon: '👕', desc: '每級最大 HP +20', max: 5 },
  dmg: { name: '經紀人加持', icon: '📣', desc: '每級傷害 +10%', max: 5 },
  cd: { name: '應援節奏', icon: '🥁', desc: '每級武器冷卻 -7%', max: 5 },
  xp: { name: '經紀人契約', icon: '📝', desc: '每級獲得經驗 +10%', max: 5 },
};

// ===== 敵人 =====
// sprite 對應 sprites.js；scale 為像素放大倍率
const ENEMIES = {
  fan: { sprite: 'fan', hp: 12, spd: 60, dmg: 8, xp: 1, scale: 3, radius: 14 },
  bot: { sprite: 'bot', hp: 8, spd: 95, dmg: 6, xp: 1, scale: 3, radius: 14 },
  troll: { sprite: 'troll', hp: 30, spd: 45, dmg: 12, xp: 2, scale: 3, radius: 16 },
  elite: { sprite: 'truck', hp: 500, spd: 34, dmg: 20, xp: 15, scale: 4, radius: 30, elite: true },
  boss1: { sprite: 'boss', hp: 1600, spd: 40, dmg: 25, xp: 60, scale: 5, radius: 52, boss: '灌水機器王' },
  boss2: { sprite: 'boss', hp: 3800, spd: 48, dmg: 30, xp: 100, scale: 6, radius: 62, boss: '輿論風暴', tint: '#a06bff' },
};

// ===== 波次時間軸（隨時間增壓；elite 3 分起、boss 6/9 分） =====
// pool: {敵人key: 權重}；interval 生成間隔(秒)；burst 每次生成隻數
const WAVES = [
  { t: 0, pool: { fan: 3, bot: 1 }, interval: 1.2, burst: 2 },
  { t: 60, pool: { fan: 3, bot: 2 }, interval: 1.0, burst: 3 },
  { t: 120, pool: { fan: 2, bot: 2, troll: 1 }, interval: 0.9, burst: 3 },
  { t: 180, pool: { fan: 2, bot: 3, troll: 1 }, elite: true, interval: 0.8, burst: 4 },
  { t: 240, pool: { bot: 3, troll: 2 }, elite: true, interval: 0.7, burst: 4 },
  { t: 300, pool: { fan: 2, bot: 3, troll: 2 }, elite: true, interval: 0.55, burst: 5 },
  { t: 360, pool: { bot: 2, troll: 3 }, elite: true, interval: 0.5, burst: 5 },
  { t: 420, pool: { troll: 3, bot: 2 }, elite: true, interval: 0.42, burst: 6 },
  { t: 480, pool: { troll: 4, bot: 2 }, elite: true, interval: 0.34, burst: 6 },
  { t: 540, pool: { troll: 4, bot: 3 }, elite: true, interval: 0.28, burst: 7 },
];
const BOSS_TIMES = [
  { t: 360, key: 'boss1' },
  { t: 540, key: 'boss2' },
];
const MAX_ENEMIES = 260;

// ===== 玩家基礎值 =====
const PLAYER_BASE = { hp: 100, speed: 170, pickup: 60, iframes: 0.8 };

// XP 曲線：升級所需經驗
function nextXP(level) {
  return Math.floor(6 + level * 4 + level * level * 0.6);
}
