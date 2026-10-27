/* KK 園區 · 派遣版 — 靜態資料表
 *
 * 數值以 Discord 端 cogs/common/work_function/work_system.py 的 LEVELS 為錨：
 * Lv0「待宰豬仔」在 Bot 端一天約賺 362 KK幣，這裡的領錢 base(8h)=120、
 * 一天額度 24h → 120 × 3 = 360，兩邊對得起來。
 * 全滿等最高 大單詐騙 1600 × 1.88 × 3 = 9,024 / 天，壓在 10,000 以內。
 */

/* 七級職位。salary / days / xp 沿用 Bot 端原值，供升職面板顯示。 */
const RANKS = [
  { lv: 0, title: '待宰豬仔',       salary: 250,   days: 0,  xp: 0     },
  { lv: 1, title: '基層狗推(車手)', salary: 1500,  days: 7,  xp: 500   },
  { lv: 2, title: '一線聊手',       salary: 2750,  days: 14, xp: 1500  },
  { lv: 3, title: '收水/車頭',      salary: 4500,  days: 28, xp: 4000  },
  { lv: 4, title: '水房會計',       salary: 7500,  days: 42, xp: 8500  },
  { lv: 5, title: '機房主任',       salary: 12500, days: 60, xp: 18000 },
  { lv: 6, title: '小區代理人',     salary: 21000, days: 90, xp: 40000 },
];

/* 業務。base = 派滿 8 小時的報酬，risk = 派遣結束時的失敗機率。
 * slot = 對應的紙娃娃部位，穿對部位會加乘這個業務。
 * prop = 派遣時紙娃娃會走到哪個場景物件前面。 */
const JOBS = [
  { id: 'lingqian',  name: '領錢',     lv: 0, base: 120,  risk: 0.10, slot: 'face',          prop: 'vault',  anim: 'alert'   },
  { id: 'zhapian',   name: '詐騙',     lv: 1, base: 480,  risk: 0.35, slot: 'hat',           prop: 'phone',  anim: 'alert'   },
  { id: 'tanpan',    name: '談判',     lv: 2, base: 400,  risk: 0.30, slot: 'hair',          prop: 'phone',  anim: 'alert'   },
  { id: 'shoushui',  name: '收水',     lv: 3, base: 600,  risk: 0.20, slot: 'top',           prop: 'vault',  anim: 'swingO1' },
  { id: 'zhuanyi',   name: '轉移陣地', lv: 3, base: 720,  risk: 0.25, slot: 'shoes',         prop: 'server', anim: 'walk1'   },
  { id: 'xiqian',    name: '洗錢',     lv: 3, base: 1150, risk: 0.40, slot: 'bottom',        prop: 'server', anim: 'swingO1' },
  { id: 'suanzhang', name: '算帳',     lv: 4, base: 950,  risk: 0.20, slot: 'top',           prop: 'desk',   anim: 'alert'   },
  { id: 'touaqian',  name: '偷A錢',    lv: 4, base: 1050, risk: 0.30, slot: 'faceAccessory', prop: 'vault',  anim: 'swingO1' },
  { id: 'zuojia',    name: '做假帳',   lv: 4, base: 1150, risk: 0.50, slot: 'bottom',        prop: 'desk',   anim: 'swingO1' },
  { id: 'nuoyong',   name: '挪用公款', lv: 4, base: 1400, risk: 0.60, slot: 'faceAccessory', prop: 'vault',  anim: 'swingO1' },
  { id: 'peixun',    name: '培訓新人', lv: 5, base: 1000, risk: 0.10, slot: 'face',          prop: 'desk',   anim: 'alert'   },
  { id: 'wajue',     name: '挖虛擬幣', lv: 5, base: 1150, risk: 0.15, slot: 'shoes',         prop: 'server', anim: 'swingO1' },
  { id: 'huashu',    name: '開發話術', lv: 5, base: 1150, risk: 0.25, slot: 'hair',          prop: 'desk',   anim: 'alert'   },
  { id: 'dadan',     name: '大單詐騙', lv: 5, base: 1600, risk: 0.70, slot: 'hat',           prop: 'phone',  anim: 'alert'   },
];

/* ================= 派遣 ================= */

/* 一天可派 24 小時，跨日（本機午夜）歸零。 */
const DAILY_HOURS = 24;

/* 可選時長（小時）。報酬按比例換算，所以派長派短每小時都一樣。 */
const DURATIONS = [0.5, 2, 8];

/* 報酬的基準時數：base 是「派滿 8 小時」的數字。 */
const BASE_HOURS = 8;

/* 派遣失敗時，只拿回這個比例。 */
const FAIL_KEEP = 0.45;

/* 派遣失敗的隨機事件，純文字描述。 */
const EVENTS = [
  { name: '臨檢',   text: '警察上門臨檢，這趟的錢先拿去疏通。' },
  { name: '黑吃黑', text: '同業上門搶地盤，抽屜被搜走一批。' },
  { name: '內鬼',   text: '底下的人手腳不乾淨，帳對不上。' },
  { name: '跳電',   text: '機房跳電，整批業務停擺。' },
  { name: '斷線',   text: '網路被切，客人跑光了。' },
];

/* ================= 紙娃娃 ================= */

/* 七個部位。每個部位對應 JOBS 裡的 slot。 */
const SLOTS = [
  { id: 'face',          name: '臉型' },
  { id: 'hair',          name: '髮型' },
  { id: 'hat',           name: '帽子' },
  { id: 'faceAccessory', name: '臉飾' },
  { id: 'top',           name: '上衣' },
  { id: 'bottom',        name: '褲子' },
  { id: 'shoes',         name: '鞋子' },
];

/* 部位加成：三階，穿越高階加越多（只加乘對應的那個業務）。 */
const TIER_BONUS = [0.03, 0.05, 0.08];

/* 每階的售價（index 0 是第一階）。 */
const TIER_COST = [300, 1500, 7000];

/* 21 件單品，全部取自 twms_fashion_db.json 的真實道具 ID。 */
const ITEMS = {
  face: [
    { id: 20000, name: '黑色挑戰的臉型' },
    { id: 20005, name: '黑色乾淨的臉型' },
    { id: 20009, name: '黑色很不屑臉型' },
  ],
  hair: [
    { id: 30000, name: '黑色基本冒險造型' },
    { id: 30005, name: '藍色基本冒險造型' },
    { id: 30007, name: '棕色基本冒險造型' },
  ],
  hat: [
    { id: 1000000, name: '藍色毛帽' },
    { id: 1000004, name: '學生帽' },
    { id: 1000006, name: '大和男性假髮' },
  ],
  faceAccessory: [
    { id: 1010000, name: '褐色落腮鬍' },
    { id: 1010002, name: '男生忍者口罩' },
    { id: 1010003, name: '鬍渣痕跡' },
  ],
  top: [
    { id: 1040001, name: '黑西裝' },
    { id: 1040027, name: '中學生上衣' },
    { id: 1040045, name: '紅色運動服' },
  ],
  bottom: [
    { id: 1060001, name: '黑西褲' },
    { id: 1060003, name: '軍用短褲' },
    { id: 1060034, name: '藍摩托車褲' },
  ],
  shoes: [
    { id: 1070001, name: '黑聖誕鞋' },
    { id: 1070003, name: '地獄使者靴' },
    { id: 1070007, name: '唐裝鞋' },
  ],
};

/* 開局就穿在身上的「囚服」，讓新角色不是一顆空白頭。 */
const START_OWNED = [20000, 30000, 1040001, 1060001, 1070001];

/* ================= 加成 ================= */

/* 設備：逐級解鎖，每階 +6%。 */
const GEAR = [
  { name: '二手手機',     cost: 120,   bonus: 0.06 },
  { name: '中古電腦',     cost: 700,   bonus: 0.06 },
  { name: '專用機房',     cost: 2500,  bonus: 0.06 },
  { name: '雲端伺服器',   cost: 8000,  bonus: 0.06 },
  { name: '私人數據中心', cost: 22000, bonus: 0.06 },
];

/* 人手：每多一人 +2%，最多 10 人。 */
const CREW = { baseCost: 200, growth: 1.35, bonus: 0.02, max: 10 };

/* 每升一階職位 +5%。 */
const RANK_BONUS = 0.05;

/* 升職門檻，對應 RANKS[1..6]。 */
const PROMO_COST = [500, 2000, 6000, 16000, 40000, 80000];

/* ================= maplestory.io ================= */

/* 已實測可用的端點形狀：
 *   /api/TWMS/256/Character/animated/{skin}/{itemsCSV}/{anim}/0
 * skin 必須獨立成一段路徑，混進 itemsCSV 會 500。
 * animated 端點吃不到 resize，GIF 固定 39×66，放大交給 CSS。 */
const API = {
  base: 'https://maplestory.io/api/TWMS/256/Character',
  skin: 12000,
  body: 2000,
  resize: 2,
  idle: 'stand1',
  walk: 'walk1',
  done: 'jump',
  fail: 'prone',
};

/* 要預先抓下來的動作，避免派遣當下才開始下載。 */
const PRELOAD_ANIMS = ['stand1', 'walk1', 'alert', 'swingO1', 'jump', 'prone'];
