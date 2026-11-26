'use strict';
/* data.js — 倖存者數值表：怪、波次、詞綴、技能、升級選項。全部純資料，行為在別的檔 */

const GAME_VERSION = 'v0.2.1';

// DC 群導流（跟 kkpark-map 同一條無限期邀請）
const DC_INVITE = 'https://discord.gg/BTggYYFVf8';

// VM API（紙娃娃 JSON；CORS 已放行）
const API_BASE = 'https://kkgroup2026.duckdns.org';

// ===== 怪種 =====
// hue: 疊在紙娃娃上的色相旋轉（CSS filter），0=原色。speed px/s、hp 基數、dmg 碰撞傷害、xp 經驗珠
// v0.2.0：怪物改穿「巡查員制服」後，hue-rotate 會洗掉制服原色（深藍變青）→ 全部改 0，
// 改用「配件色」區分怪種（accessory 槽位只染配件不染全身），靠外型本身辨識。
const MOB_TYPES = {
  rusher: { name: '巡查員', hue: 0, speed: 52, hp: 18,  dmg: 8,  xp: 1,  r: 14 },
  swarm:  { name: '便衣',   hue: 0, speed: 78, hp: 10,  dmg: 5,  xp: 1,  r: 12 },
  gunner: { name: '槍手',   hue: 0, speed: 34, hp: 26,  dmg: 10, xp: 3,  r: 14, ranged: true, range: 240, fireCd: 2.2, bulletSpeed: 170 },
};

// 波次：30 秒一群，強度遞增。spawn/s、hp 倍率、怪種權重
const WAVE = {
  stepSec: 30,
  spawnPerSec: t => 1.1 + t / 18,        // 每秒生成數（t=波次指數）
  hpMult: t => 1 + t * 0.22 + t * t * 0.03,
  weights: t => (t < 2 ? { rusher: 1, swarm: 0.4, gunner: 0 } :
                  t < 4 ? { rusher: 1, swarm: 0.8, gunner: 0.25 } :
                          { rusher: 1, swarm: 1.1, gunner: 0.45 }),
  eliteEvery: 5,                          // 每 5 群一隻精英（hp×10、大隻、必掉黃裝）
};

// ===== POE 詞綴池（MVP：前綴+後綴各 1）=====
// val = [min,max] 隨機 roll；fmt 顯示。前綴偏攻、後綴偏防/功能
const PREFIXES = [
  { k: 'dmg',    label: '殘暴的', stat: '傷害',    val: [8, 15],  fmt: v => `傷害 +${v}%` },
  { k: 'aspd',   label: '迅捷的', stat: '攻速',    val: [6, 12],  fmt: v => `攻速 +${v}%` },
  { k: 'bullet', label: '分裂的', stat: '彈幕',    val: [1, 1],   fmt: v => `彈幕 +${v}` },
  { k: 'pierce', label: '貫穿的', stat: '穿透',    val: [1, 2],   fmt: v => `穿透 +${v}` },
];
const SUFFIXES = [
  { k: 'mspd',  label: '之輕功', stat: '移速',      val: [5, 10], fmt: fmtPct },
  { k: 'hp',    label: '之蠻軀', stat: '最大體力',  val: [10, 25], fmt: v => `最大體力 +${v}` },
  { k: 'magnet',label: '之磁石', stat: '拾取範圍',  val: [15, 30], fmt: v => `拾取範圍 +${v}%` },
  { k: 'xp',    label: '之巧思', stat: '經驗',      val: [8, 15], fmt: fmtPct },
];
// 稀有度：普通(1詞)→魔物(2詞)→稀有(4詞)；掉落權重
const RARITY = [
  { id: 'normal', name: '普通', color: '#cfd6de', w: 62, affixes: 1 },
  { id: 'magic',  name: '魔物', color: '#7fb3ff', w: 30, affixes: 2 },
  { id: 'rare',   name: '稀有', color: '#ffd35c', w: 8,  affixes: 4 },
];
// 裝備底名（前綴+底+後綴 = 「殘暴的西裝外套之輕功」）
const BASES = ['西裝外套', '便服', '制服', '夾克', '長袍'];

function fmtPct(v) { return `+${v}%`; }

// ===== 升級三選一池 =====
// 新技能 → 強化 → 被動，權重抽 3
const LEVEL_UPS = [
  { id: 'new_ring',   name: '🔨 環身鎖鏈', desc: '新技能：繞身旋轉環，持續撞傷', w: 2, apply: s => { s.skills.ring = s.skills.ring || { lvl: 0 }; s.skills.ring.lvl++; } },
  { id: 'new_lance',  name: '🗡️ 貫穿鏢',  desc: '新技能：朝移動方向直線穿透鏢', w: 2, apply: s => { s.skills.lance = s.skills.lance || { lvl: 0 }; s.skills.lance.lvl++; } },
  { id: 'up_bullet',  name: '🔥 彈幕強化', desc: '基礎彈幕 +1（需已有彈幕 <6）', w: 3, can: s => s.stats.bullets < 6, apply: s => { s.stats.bullets++; } },
  { id: 'up_dmg',     name: '⚔️ 全體傷害', desc: '所有傷害 +15%', w: 3, apply: s => { s.stats.dmgPct += 15; } },
  { id: 'up_aspd',    name: '⚡ 攻速',     desc: '攻擊頻率 +12%', w: 3, apply: s => { s.stats.aspdPct += 12; } },
  { id: 'up_mspd',    name: '👟 移速',     desc: '移動速度 +8%', w: 2, apply: s => { s.stats.mspdPct += 8; } },
  { id: 'up_magnet',  name: '🧲 拾取範圍', desc: '撿東西半徑 +25%', w: 2, apply: s => { s.stats.magnetPct += 25; } },
  { id: 'up_hp',      name: '❤️ 最大體力', desc: '最大體力 +25 並補滿', w: 2, apply: s => { s.stats.maxHp += 25; s.stats.hp = s.stats.maxHp; } },
];

// ===== 平衡 =====
const BAL = {
  playerSpeed: 130,          // px/s
  baseHp: 100,
  baseFireCd: 0.78,          // 基礎彈幕間隔秒（v0.2.1 調校：早期火力要追上生成率，不然核心 65s 淪陷）
  baseBulletDmg: 13,
  bulletSpeed: 330,
  magnetR: 64,               // 拾取半徑 px（v0.2.1：46 撿不到環帶邊的掉落）
  xpToLevel: lvl => 5 + lvl * 7,
  invulnHit: 0.6,            // 被撞後無敵秒
  ring: { r: 62, dps: 22, speed: 2.6, perLvlR: 8, perLvlDps: 10 },
  lance: { cd: 1.9, dmg: 24, speed: 420, perLvlDmg: 10 },
  // ===== 守塔：園區核心 =====
  core: {
    hp: 420,                 // 核心血量（被怪碰到就掉）
    radius: 64,              // 核心碰撞半徑 px（塔身 68×60，視覺一致）
    playerRingMin: 90,       // 玩家不可進內圈（不能站在核心裡）
    playerRingMax: 260,      // 玩家活動範圍上限（圍著核心打）
    hitDmg: 7,               // 每次碰撞扣核心血（v0.2.1 調校：10 會讓漏怪堆疊時 65s 蒸發）
    hitCd: 1.0,              // 碰撞扣血間隔（單隻怪約 7dps）
    regen: 2,                // 每秒回血（撐住壓力，別讓一波就死）
  },
  waveToWin: 12,             // 撐過第 12 波＝守住園區（勝利）
};
