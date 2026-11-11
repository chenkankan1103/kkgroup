'use strict';
/* data.js — 數值表：時鐘、警察密度、任務、事件、裝備、價格 */

// 遊戲內時鐘：1 真實秒 = 1 遊戲分鐘（1 真實分鐘 ≈ 1 遊戲小時）
const TICK_MS = 1000;

// 各時段巡邏密度（0-23 時）——深夜安靜、白天最多
const POLICE_DENSITY = [
  0.5, 0.4, 0.35, 0.3, 0.3, 0.4,
  0.6, 0.8, 1.0, 1.1, 1.2, 1.2,
  1.1, 1.1, 1.2, 1.2, 1.1, 1.1,
  1.0, 0.9, 0.9, 0.8, 0.7, 0.6,
];

const NAMES = ['小馬', '阿虎', '阿德', '小海', '阿肯', '大丙', '阿斌', '小乖', '阿豹', '小鹿',
  '阿坤', '大黑', '小美', '阿西', '肥宅', '阿傑', '小鬼', '阿龍', '小強', '阿養樂多'];
const AVATARS = ['🧢', '🕶️', '🧣', '👒', '🎓', '🧤', '💅', '🦺'];

// ===== 任務類型 =====
// stat: 成功判定吃的能力；dur: 遊戲分鐘；pay: 金額範圍；risk: 基礎風險；trust: 成功後組織信任變動
const MISSION_TYPES = {
  scam: {
    name: '詐騙班', icon: '☎️', stat: 'gab', statName: '口才',
    desc: '坐機房打電話釣人頭，話術就是生產力',
    dur: [90, 240], pay: [3000, 9000], risk: 0.30, trust: 6,
  },
  pickup: {
    name: '車手收贓', icon: '🚗', stat: 'legs', statName: '腿力',
    desc: '跑去面交點把贓款帶回來，快進快出',
    dur: [60, 180], pay: [5000, 14000], risk: 0.45, trust: 8,
  },
  cargo: {
    name: '運貨', icon: '📦', stat: 'legs', statName: '腿力',
    desc: '搬一批貨到指定點，要快也要穩',
    dur: [120, 360], pay: [8000, 20000], risk: 0.40, trust: 10,
  },
  intel: {
    name: '情報任務', icon: '🕵️', stat: 'luck', statName: '運氣',
    desc: '跟警方線人碰面交資料——餵警察的活',
    dur: [45, 90], pay: [0, 0], risk: 0.35, trust: -9,
  },
};
const MISSION_POOL = [
  { k: 'scam', w: 30 }, { k: 'pickup', w: 30 }, { k: 'cargo', w: 30 }, { k: 'intel', w: 10 },
];

// ===== 短任務隨機事件（A/B 二選一）=====
// kind: risk = 擲能力（失敗有代價）、abandon = 丟包斷尾、continue = 穩穩過
const EVENTS = [
  {
    icon: '🚨', title: '被警察盤查',
    text: '一名巡邏警察走了過來，上下打量著你的人。這時候跑，看起來更可疑……',
    A: { label: '自然地應對', kind: 'risk', stat: 'luck' },
    B: { label: '丟包斷尾', kind: 'abandon' },
  },
  {
    icon: '🐍', title: '目標反咬',
    text: '對方察覺不對勁，揚言要報警，還開口要一筆封口費……',
    A: { label: '話術安撫', kind: 'risk', stat: 'gab' },
    B: { label: '丟包走人', kind: 'abandon' },
  },
  {
    icon: '🐟', title: '大肥羊上鉤',
    text: '有個受害者願意轉一筆特大金額，再推一把就能全部入袋……',
    A: { label: '狠狠加碼撈', kind: 'risk', stat: 'gab', bonus: 0.6 },
    B: { label: '見好就收', kind: 'continue' },
  },
  {
    icon: '🏚️', title: '據點被盯上',
    text: '對街連兩天停著一台沒熄火的陌生車，後照鏡總是轉向你這邊……',
    A: { label: '換裝硬著頭皮上', kind: 'risk', stat: 'legs' },
    B: { label: '棄單保平安', kind: 'abandon' },
  },
];

// ===== 裝備（買一次永久生效）=====
const GEAR = [
  { id: 'plate', name: '假車牌', icon: '🏷️', price: 12000, desc: '車手／運貨被逮風險降低' },
  { id: 'voice', name: '變聲器', icon: '🎙️', price: 20000, desc: '詐騙班與話術安撫成功率 +10%' },
  { id: 'vpn', name: '企業級 VPN', icon: '💻', price: 30000, desc: '所有懷疑度累積 -20%' },
  { id: 'car', name: '贓車', icon: '🏎️', price: 45000, desc: '成員移動速度將近兩倍，省趕路時間' },
];

const PRICES = { bail: 20000, bailPerMin: 2000, hire: 25000, intel: 30000 };
const INTEL_BUY_POLICE = 15; // 花錢買情報一次加的警方進度
const LONG = { durMult: 4, durAdd: 120, payMult: 2.2, riskAdd: 0.12 }; // 大活模式

// ===== V1.5：伙食與移動 =====
const MOVE_DEG = 0.0028;    // 每遊戲分鐘（=1 真實秒）移動距離 ≈ 310m，園區附近單程約 10 秒
const MOVE_CAR_MULT = 1.9;  // 有贓車時的移動速度倍率
const START_FOOD = 25;      // 開場伙食庫存
const FOOD_EAT = 2;         // 每人每天消耗（有廚房 → 1）
const FOOD_TANK = 4;        // 水塔每天產出
const FOOD_PACK = { price: 3000, amount: 10 }; // 商店買伙食
const FOOD_MAX = 99;
const MEMBER_CAP_BASE = 6;  // 基礎成員上限（工寮 +3）

// ===== V1.5：園區建設（蓋好永久生效；buildMin 為遊戲分鐘 = 真實秒）=====
const BUILDINGS = [
  { id: 'tank', icon: '🌊', name: '水塔', price: 18000, buildMin: 90, desc: '每天清晨 +4 伙食' },
  { id: 'kitchen', icon: '🍳', name: '廚房', price: 22000, buildMin: 120, desc: '伙食消耗 2 → 1／人／天' },
  { id: 'fence', icon: '🚧', name: '圍籬', price: 15000, buildMin: 120, desc: '夜間（20:00–06:00）警力密度 -25%' },
  { id: 'generator', icon: '⚡', name: '發電機', price: 30000, buildMin: 180, desc: '任務報酬 +15%' },
  { id: 'dorm', icon: '🛖', name: '工寮', price: 26000, buildMin: 150, desc: '成員上限 +3' },
];

// ===== V2：夜間警方攻堅 =====
// 節奏：20:00 擲骰出「風聲預警」→ 02:00 深夜發動 → 彈策略卡一次結算
const RAID = {
  WARN_MIN: 20 * 60,  // 20:00 風聲擲骰
  HIT_MIN: 2 * 60,    // 02:00 發動
  GRACE_DAYS: 3,      // 前三天教學期免戰
  BASE: 0.10, DAY_RAMP: 0.015, DAY_CAP: 0.30,   // 機率 = 基礎 + 天數遞增（封頂）
  SUS_MULT: 0.25, POLICE_MULT: 0.15,            // 懷疑度／警方進度再加碼
  P_MIN: 0.05, P_MAX: 0.60,
  STRENGTH_BASE: 40, STRENGTH_DAY: 2,           // 強度 = 40 + 天數×2 + 懷疑×0.25 + 進度×0.3
  STRENGTH_SUS: 0.25, STRENGTH_POLICE: 0.3,
  FENCE_CUT: 0.8,     // 圍籬讓突擊強度 -20%（加上原本夜間巡邏 -25%）
  BRIBE_PRICE: 20000, // 花錢消災
  SEIZE_PCT: 0.25, SEIZE_CAP: 30000,            // 迎戰敗北被抄現金（躲藏/棄車更輕）
};
// 策略卡選項（判定在 sim.resolveRaid）
const RAID_PLANS = [
  { id: 'fight', icon: '⚔️', name: '死守迎戰', desc: '全員硬碰硬——贏了最有面子，輸了抓最兇' },
  { id: 'hide', icon: '🤫', name: '全員躲藏', desc: '熄燈屏息——沒人被抓，但會被抄走一些錢' },
  { id: 'car', icon: '🏎️', name: '棄車誘敵', desc: '犧牲贓車引開突擊隊（需要贓車）' },
  { id: 'bribe', icon: '💸', name: '花錢消災', desc: '付 $20,000 擺平，今晚必定平安' },
];

const START = { money: 60000, trust: 60, police: 0, sus: 0, members: 2, missions: 4 };
const JAIL_MIN = [3, 8]; // 看守所真實分鐘範圍

// 地圖與園區
const HQ = { lat: 22.62, lng: 120.30 };
const TW = {
  center: [23.75, 120.9], zoom: 8,
  bounds: [[21.6, 118.0], [25.8, 122.4]],
  latR: [21.9, 25.3], lngR: [119.6, 121.9], // 任務生成範圍
};

function rollStat() { return 3 + Math.floor(Math.random() * 6); } // 3-8
function rndInt(a, b) { return a + Math.floor(Math.random() * (b - a + 1)); }
function clamp100(v) { return Math.max(0, Math.min(100, v)); }
