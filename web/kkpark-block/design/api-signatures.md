# 街區棋王 接縫契約 v1 — 寫手 A API 簽名（B 吃這份 mock）

> 來源：redesign-spec-final.md §11 接縫契約。A 實現、B mock 先行。
> 全域模組：`BlockMap / Faction / Dice / Star / Base / Save`（無建置工具，`<script>` 順序載入，皆掛 window）。
> 資料中心：單一存檔物件 `S`，所有模組只讀寫 `S` 不另立全域。`Bus`（事件匯流排）沿用舊 `emit/on` 模式。
> 中性代稱：園區／巡查方。版本 v0.1.0。

## 0. 存檔 S 形狀（唯一資料中心）

```js
S = {
  ver: 1,                 // 存檔版號（遷移用）
  seed: 20261124,         // 地圖種子，開新檔隨機一次，之後不變
  day: 1,                 // 遊戲日（睡覺 +1）
  phase: 'street',        // 日迴圈四段：'morning' | 'street' | 'ledger' | 'sleep'
  money: 0,               // 現金
  goods: 0,               // 貨（點擊機產出，可換錢）
  faction: 'park',        // 'park'（園區）| 'police'（跳槽後）
  stars: 0,               // 0-3
  heat: 0,                // 星星進度條（0-100，滿 100 升星）
  attrs: { talk: 1, agility: 1, brain: 1, guts: 1 },   // 口才/身手/頭腦/膽識
  attrExp: { talk: 0, agility: 0, brain: 0, guts: 0 }, // 經驗粒灌注進度
  blocks: [Block...],     // 見 §1（BlockMap.generate 產出後存入）
  bases: [Base...],       // 見 §5
  suspects: [],           // 暗件佇列（離線代價）：{kind, dayDue, payload}
  skills: { bait: 0, smoke: 0, bot: 0 },  // 自動技能冷卻剩秒
  police: 0,              // 巡查方進度（主線壓力，25 階增哨、60 開跳槽）
  switchCooldown: 0,      // 跳槽後「舊關係懷疑度」0-100
}
```

Block（街區，§2.1）：

```js
Block = {
  id: 0,                // 索引
  polygon: [[x,y],...], // 像素座標（世界系，32px 磚格）
  center: [x, y],       // 多邊形質心（放數字/哨所/據點用）
  ctrl: 0,              // 控制度 -100..100，正=園區綠 負=巡查方藍
  locked: null,         // 定色：null | 'park' | 'police'
  lockStreak: 0,        // ±100 連續天數（≥3 觸發定色）
  type: 'neutral',      // 'biz'（營運）| 'watch'（巡查哨所在）| 'neutral'
  yieldRate: 1.0,       // 定色綠 +25% 由此乘
  watch: 0,             // 該區巡查密度（巡邏班表寫入）
}
```

## 1. BlockMap — Voronoi 街區生成（A1）

> ⚠️ 命名規則：模組名不得撞 JS 內建（`Map` 會遮蔽 built-in，Pixi v8 內部 `new Map()` 直接炸）。原 `Map` 已更名 `BlockMap`。

```js
BlockMap.generate(seed) -> {blocks: Block[], obstacles: Uint8Array}
```
- seed 種子抖動＋Poisson 最小間距撒 12-20 點；Voronoi 分割；Chaikin 平滑一次。
- `obstacles`：世界網格 0/1（牆/樹格），B 的 walk.js 碰撞直接吃。格寬 32px。
- 同 seed 永遠同圖。產出後 `S.blocks = blocks`，obstacles 只存 seed（重算得）。
- B 渲染色塊只吃 `blocks[].polygon/ctrl/locked`（spec §9.1 半透明疊層）。

## 2. Faction — 控制度推拉引擎（A2/A6）

```js
Faction.push(S) -> {events: [{blk, from, to}...]}   // 每日結算（睡覺段）呼叫一次
```
- 公式照 spec §2.2：`ctrl[blk] += parkPush - policePush + neighborFlow`，clamp ±100。
- 定色：|ctrl|==100 連續 3 天 → `locked='park'|'police'`，回傳事件。
- 「易手」事件：ctrl 過 0 跨界（由正轉負或反之）→ 回傳 events，B 可做閃光/戰報文字。
- 跳槽翻轉（A6，v0.1 後段）：

```js
Faction.flip(S) -> S            // 就地翻轉：S.faction、綠藍定義、星星誰帶誰
Faction.sideOf(S, block) -> 'mine' | 'foe'   // B 上色一律問這個，不讀 ctrl 正負
```
- **B 渲染鐵律**：色塊意義永遠走 `Faction.sideOf()`，跳槽反轉後 B 零改動。

## 3. Dice — 檢定系統（A3）

```js
Dice.roll(attrKey, dc, opts?) -> Roll
Roll = {
  d20: 1-20,        // 骰面原值
  attr: 屬性值,      // S.attrs[attrKey]
  bonus: 總修正,     // 裝備/情境（opts.bonus，預設 0）
  total: d20+attr+bonus,
  dc,               // 10-20
  ok: total >= dc,
  crit: d20 === 20,   // 大成功：雙倍效果（呼叫方解讀）
  fumble: d20 === 1,  // 大失敗：加壞後果（呼叫方查後果表）
}
```
- 後果表在 Dice 內：`Dice.consequence(kind, Roll)` → 文字＋數值補丁（kind: 'arrest'|'deal'|'raid'|'plea'）。呼叫方給場景 kind，回 `{text, effects:{money, heat, ...}}`。
- 檢定滲透對照（呼叫時機，spec §6）：談判=deal/talk、搬家當=heist/agility、求情=plea/talk、逃跑=escape/agility、圓謊=cover/brain、跳槽攤牌=switch/guts。

## 4. Star — 星星狀態機＋追擊 AI＋怪潮（A4）

```js
Star.update(dt, ctx) -> {stars, chasers: [Unit...], wave: null | {n, units}}
```
- 每幀呼叫（main.js 的 tick 傳 dt 秒）。ctx：`{hero: {x,y}, cops: [Unit...], blocks, obstacles}`。
- 升降星條件照 spec §4 表（目擊/再犯/大失敗；脫離視線 40s/60s+400m 計時降星）。
- 追擊 AI：A* 沿可走格每 0.5s 重算路徑；`chasers` 是「正在追的單位」子集，B 只負責畫。
- 怪潮：2 星 80s 預備、3 星連續 3 波；`wave.units` 是湧入單位列表（Zombie 重著色）。
- 事件（B 掛監聽）：`Bus.on('stars', n=>)`、`Bus.on('chase', units=>)`、`Bus.on('wave', w=>)`。
- 自動技能介面（放置互餵掛點）：

```js
Star.useSkill(skill) -> bool   // 'bait'|'smoke'|'bot'；冷卻 30s，消耗 S.goods
```

## 5. Base — 據點放置數值（A5）

```js
Base.click(base) -> {goods: +n}          // 主點擊機：每點 +1 貨（升級後 ×2 鏈）
Base.tick(base, dt) -> {}                // 雇員自動產出（B 內部視角掛每秒）
Base.hire(base, kind) -> {}              // 雇小弟：kind 'runner'|'guard'|'operator'
Base.upgrade(base, key) -> {}            // 'output'|'offline'|'skillslot'
Base.offline(S, hoursAway) -> {gain, backlog}  // 離線 1/8，上限 8h；backlog=暗件
```
- 暗件代價結算走 `Base.resolveSuspect(S, idx, choice)`（回來先收拾）。
- 據點資料 `Base = {blk, level, hires: [], goodsRate, upgrades: {}}`，存 `S.bases`。
- B 內部視角只讀數值畫，機制全在 Base。

## 6. Save — 存檔＋日結（A7）

```js
Save.load()  -> S | null        // localStorage key 'kkpark_block_save'；無檔回 null
Save.save(S)                    // 睡覺段呼叫（一天一個 save 點）
Save.dayEnd(S) -> S             // 日結流水線：Faction.push → 巡邏重排 → 怪潮部署 → 疑犯到期 → day+1
Save.newGame() -> S             // 造新檔（seed 隨機、初始 2 哨所、首據點）
Save.reset()                    // 刪檔（debug 用）
```
- 中途離開（不睡覺關頁）：下次 load 自動標記「未結算」，收益減半規則由 Save.load 補算。
- 版本遷移：`Save.load` 內按 `S.ver` 逐級補欄位，B 不用管。

## 7. 事件匯流排一覽（B 掛這些）

| 事件 | payload | 時機 |
|---|---|---|
| `stars` | n (0-3) | 升降星 |
| `chase` | units[] | 追擊集合變動 |
| `wave` | {n, units} | 怪潮湧入 |
| `arrest` | {attr, dc} | 進被捕檢定畫面（B 開三選一 UI） |
| `flip` | faction | 跳槽翻轉 |
| `dayEnd` | {report} | 睡覺結算（勢力戰報，B 開機面板吃） |
| `money` | delta | 金錢變動（浮字用） |

---
*B 先 mock 的入口：載入本檔所述模組空殼（回固定資料），walk.js/main.js 即可開工。A 實現後原簽名替換，B 零改動。*
