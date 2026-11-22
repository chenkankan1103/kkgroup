# 圖示退役計畫 — emoji → SVG（Emoji Retirement v1）

> 目標：**圖示用途的 emoji 全數退役**；文案語氣用的表情符號保留（見 §5）。
> 依據：美術聖經 §4。截圖診斷：彩色 emoji 是深色 UI 上最鬧的雜訊源（櫻井 132「同一画面に色を混ぜない」）。

---

## 1. 選型決策

**主套件：game-icons.net** — CC BY 3.0、4000+ 張、單色 silhouette、`fill: currentColor` 可任意上霓虹色。

落選者與理由（一句話檔案）：

| 候選 | 結論 |
|---|---|
| Lucide / Tabler | 線性精緻但語彙偏辦公 App：警車、幫派、突襲、宮廟全缺，對照表會一半自製 |
| Phosphor | duotone 漂亮、權重多，但同樣是 App 語彙，遊戲向物件覆蓋弱於 game-icons |
| Bootstrap Icons | 數量與遊戲語彙皆不足 |
| 全自製 | 90 個圖示不現實，且品質不穩（櫻井 129：多人多筆觸必須統一） |

**供給方式（寫手 2 決定權，建議值）**：JS 常數 `ICONS = { name: '<path .../>' }`，注入 `innerHTML` 時包 `<svg viewBox="0 0 512 512" fill="currentColor" width="1em" height="1em">`。marker/panel 都是 innerHTML 注入，JS 物件最省事、零執行期 CDN 依賴。game-icons path 是 512 viewBox。

**授權**：CC BY 3.0 — 在 `design/NOTICE.md` 註明「Icons from game-icons.net (CC BY 3.0)」＋作者集合頁連結即可。自製圖示標 `self-made`。

**實作規則**：候選名以 game-icons 官方 dataset 為準（實作時查檔名）；表列名稱若查無此檔，**按聖經 §4 規格自製**（單 path、無內嵌色），不要硬湊近義圖。

---

## 2. 分期

| 期 | 範圍 | 數量約 | 理由 |
|---|---|---|---|
| **P0** | HUD chips／三條 bar／地圖 marker pill／警車 | ~25 | 每秒在畫面上的東西先換，一次換完視覺斷層最小 |
| **P1** | 名冊卡／商店 gi／dock／事件卡 ev-icon | ~40 | 面板層 |
| **P2** | 主角金冠（style.css `content:'👑'`）、收尾掃蕩 | ~5 | 金冠改 CSS 造型或 SVG |

---

## 3. 對照表（P0：HUD 與地圖）

出現位置：`index.html`（HUD 靜態）、`map.js`（marker 建構）、`style.css:139`。

| emoji | 用途 | 位置 | 替換 | 備註 |
|---|---|---|---|---|
| 💰 | 金額 chip | index.html:17,45,131 | `money-stack` | 語義色 --warn |
| 🪙 | KK 幣 | index.html:22,133、sim.js 多處、ui.js:170,174 | `coins` | 同上 |
| 🍚 | 伙食 | index.html:18,132、ui.js:142,361 | `hot-meal`（缺則自製便當） | --ok／低量轉 --danger |
| 📕/📖 | 任務數 chip | index.html:21 | `scroll-unfurled` | |
| ⏰鈴 | 時鐘 | index.html（第1天 09:12 旁） | 自製 SVG 時鐘（兩針圓） | 數字改 Cubic 11（聖經 §3） |
| 🚨 | 警報 chip／查崗 | index.html:52,79,133、ui.js:140,437、sim.js 多處 | `siren`（缺則 `police-badge`＋紅光） | --danger，可保留閃爍 |
| 🌙 / ☀️ | 夜／日 | ui.js:140,248,307、index.html:128 | `new-moon` / `sunbeams` | 0.5.0 日夜主圖示 |
| ❓ | 幫助 | index.html:31,122、map.js:183、ui.js:7 | 自製 SVG（圓＋?） | |
| ✕ | 關閉 | index.html:39,45 | 自製 SVG（兩線） | |
| ⬆️ | 升級 | dock.js:4,62,174、index.html:153 | 自製 SVG 箭頭 | UI 箭頭類 game-icons 語弱，自製 3 行 path |
| 🔧 | 設定／維修 | dock.js:4、ui.js:365、index.html:154 | `wrench` | |
| ✅ | 完成 | dock.js:105、ui.js:356,369,516、index.html:144 | `checkmark` | |
| 🔁 | 重複 | index.html:94 | 自製 SVG（循環箭頭） | |
| 🚔 | 巡邏警車 marker | map.js:151、ui.js:492 等 | `police-badge`（缺側視車則自製警車側影） | 保留藍 glow（光源＝警燈，合法） |
| 🚓 | 攻堅警車 | map.js:722、data.js:265 | 同上 | 與 🚔 同一張圖，靠尺寸/光分級 |
| 🕴️ | HQ | ui.js:209 | `hideout`（缺則 `warehouse`） | --neon2 粉框語 |
| 🏢/🏭/🏚️/🛖 | 建築 marker | map.js:49,365,384、data.js:170,218 | `office-building`（缺則自製）/ `factory` / 自製廢屋 / `tent`（缺則自製） | 完工綠框語 |
| ⚒️ | 工地 | map.js:319、ui.js:201、sim.js:1310、data.js | `sledgehammer`（缺則 `hammer-drop`） | 灰框工地態 |
| 🔨 | 施工中 | sim.js:227、ui.js:534,548、data.js:73 | `hammer-drop` | 與 ⚒️ 分色不分支 |
| 📍 | 任務釘 | map.js:251 | `position-marker`（缺則自製 pin） | |
| 🛵 | 派遣小人座駕／任務 icon | map.js:251、ui.js:246-247,301,319、data.js:173 | `scooter` | |
| 👁️ | 監視／曝光 | index.html:28,112,141、ui.js:478,521,535,561、sim.js:724 | `eye`（或 `cctv`，缺則自製） | heat 語系 |
| 🏴 | 據點／夜襲旗 | index.html:26,110,141、ui.js:477,556、data.js:308 | `black-flag` | |
| 🟢/🔴 | turf 圖例 | index.html:135、ui.js:211、map.js:293 | 自製 SVG 圓點（CSS 即可，非圖示庫件） | 純色圓，10px |

---

## 4. 對照表（P1：面板層）

`data.js`（定義處，改定義即全遊戲生效）、`ui.js`、`dock.js`、`sim.js` 文案嵌圖。

| emoji | 用途 | 替換 | 備註 |
|---|---|---|---|
| ☎️ | 通話班任務 | `phone`（缺則 `reticule`?→ 自製話筒） | data.js:24 |
| 🚗 | 車手任務 | `car`（缺則 `steering-wheel`） | data.js:29 |
| 📦 | 運貨任務 | `wood-box`（缺則 `cube`） | data.js:34 |
| 🕵️ | 情報任務 | `spy` | data.js:39,107、ui.js:379 |
| 🧹 | 街頭幫忙 | `broom`（缺則 `push-broom`?→自製掃帚） | data.js:45 |
| 🍢 | 夜市攤 POI | **自製**（三串燒架） | data.js:53；在地物，套件無 |
| ⛩️ | 宮廟 POI | `temple-gate` | data.js:54 |
| 🏪 | 便利商店 | `shop` | data.js:55 |
| 🎫 | 入場 POI | `ticket` | data.js:56 |
| 💆 | 養生 POI | **自製**（躺姿人形）或改語意 `leaf` | data.js:57 |
| 🥥 | 飲品 POI | **自製**（帶吸管杯）或 `soda-can` | data.js:58 |
| 📰 | 報社 POI | `newspaper` | data.js:59 |
| 🐍 | 內鬼象徵 | `snake` | data.js:89、ui.js:533,566 |
| 🐟 | 漁獲系 | `fish`（缺則 `fish-cooked`） | data.js:95 |
| 🍺 | 酒類交易 | `kebab-skewer` 誤—用 `drink-me`?→**自製**酒瓶杯 | data.js:113 |
| 🏷️ / 🎙️ / 💻 / 🏎️ | 商店道具 | `label`?→自製價籤 / `megaphone` / `laptop` / 自製跑車側影 | data.js:122-125 |
| 📈 / 🧾 / 🧰 / 🛡️ / 🪪 / 🎯 / 🤝 | 升級樹 | 自製折線箭頭 / `scroll-unfurled` / `toolbox`（缺則 `toolbox` 查無→`first-aid-kit` 誤→自製）/ `checked-shield` / `id-card`?→自製卡 / `bullseye` / 自製交握 | data.js:145-176；升級樹圖示可整批自製統一筆觸 |
| ⚔️ / 🗡️ | 衝突系 | `crossed-swords` / `sword-brandish` | data.js:239,263,310 |
| 🤫 / 🌑 | 暗語系 | `silence`（缺則自製噤聲）/ `new-moon` | data.js:240,311 |
| 💸 | 支出／損失 | `burning-money` | sim.js 十餘處——**最高頻 emoji**，P1 首換 |
| 💵 | 收入 | `money-stack`（與 💰 同圖，尺寸分） | sim.js:400,408 |
| 🧯 | 壓熱 | `fire-extinguisher`（缺則自製滅火器） | sim.js:551、ui.js:371,372、dock.js:136,138 |
| ⚖️ | 法律／結算 | `scales` | sim.js:1256、ui.js:263 |
| 🚪 / 🔍 / 🗂️ / 📡 / 🏁 / 🚧 / ⚡ / 🔥 / 💥 / 💦 / 🕯️ / 🧋 / 🏨 | 事件文案嵌圖 | `exit-door` / `magnifying-glass` / 自製檔案匣 / `broadcast` / `finish-line` / `fence` / `lightning-tear` / `fire` / `bang` / `water-drop` / 自製蠟燭 / 自製 / — | 事件卡 `ev-icon` 44px 大圖，P1 末段 |
| 🌅 / 💬 / 👀 | 場景／對話 | 保留或移除：**見 §5** | |

### 人員頭像（特殊處理，不是換圖是退役）

`data.js:18` `AVATARS = ['🧢','🕶️','🧣','👒','🎓','🧤','💅','🦺']`：

- 成員頭像**已有紙娃娃系統**（`.ava.has-doll` 已存在，emoji 退居角標）。
- 計畫：頭像 emoji 直接刪除；紙娃娃載入失敗的 fallback 改「單色首字底牌」（CSS：深底圓角方塊＋成員名首字，語義色邊框）。
- 名冊卡裡的屬性小 emoji（口才/腿力/蓮氣列）一併換 12px 單色 SVG。

---

## 5. 保留清單（文案語氣，非圖示）

這些是**敘事文字**（櫻井 093：書き文字・漫符是表現），不是圖示，不退役：

`🙂 😌 😐 😅 😬 😖 😤 🤐 🫡 🎉 💬 🔥 💦 👀 👇 👉 🍱 🌅`

使用規則（聖經 §4 引申）：只准出現在 toast／事件卡敘事文案／NPC 對話欄；**不准出現在 HUD chip、按鈕、標題、marker**。若實作時分不清，問：拿掉後句子還是句子嗎？是 → 保留。

---

## 6. 驗收（給截圖者）

1. HUD 區 grep 不到 emoji（§5 保留清單除外）——`grep -P '[\x{1F300}-\x{1FAFF}]' index.html` 應為零或僅文案檔
2. marker pill 縮放 z15-z18 圖示不糊（SVG 向量，應無問題）
3. 全畫面同時可見語義色 ≤4 種（聖經 §2 規 3）
4. `design/NOTICE.md` 存在且含 CC BY 歸屬
