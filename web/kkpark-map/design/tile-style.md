# 地圖瓦片風格建議 — Tile Style v1

> 修正簡報前提：**現況已不是 OSM 標準街圖**，是 Esri World_Dark_Gray_Base（[map.js:33](../map.js)）。
> 截圖實測（kkpark-verify shot1/shot3）：路網幾乎不可讀、城市街廓紋理缺席——地圖是一塊灰色空白，紙娃娃在虛空上走。**這是「陽春感」的第一來源，比 emoji 更根本。**

---

## 1. 評估維度（依美術聖經 L0「舞台去飽和、路網可讀但低調」）

| 維度 | 為何重要 |
|---|---|
| 路網可讀性 | 遊戲沿路網滑行（v0.5.3 heroGlideTick），玩家要能預判「路上 vs 離路」 |
| 對 UI 的讓位 | marker pill、HUD 的對比必須永遠贏瓦片 |
| 街廓紋理 | 有建築塊才有「城市感」，光有輪廓線是 PDF 底圖 |
| 標籤干擾 | 地名標籤跟 UI 文字打架（櫻井 030：非判定物退後） |
| 維運成本 | 免 key、無配額限制、公開 repo 可直接內嵌 |

## 2. 候選評估

| 候選 | 路網 | 街廓 | 標籤 | 成本 | 裁決 |
|---|---|---|---|---|---|
| **CARTO dark_matter（nolabels）** | 白線清楚 | 可見 | **無** | 免 key、{r} retina 支援 | ✅ **採用** |
| CARTO dark_matter（all，帶標籤） | 同上 | 同上 | 小而多 | 免 key | 備選——標籤仍搶戲，不採 |
| Esri Dark Gray（現況） | 極淡 | 近無 | 無 | 免 key | 治標方案 B |
| Stadia Alidade Smooth Dark | 佳 | 佳 | 無變體 | **要 API key** | 淘汰 |
| OSM 標準 | 亮 | 亮 | 多 | 免 key | 淘汰（違反 L0） |

## 3. 替換（一行，寫手 2 直接改）

[map.js:33](../map.js) 現行：

```js
L.tileLayer('https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
```

改為：

```js
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', {
```

attribution（`attribution:` 選項）改：

```js
attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
```

`{r}` 是 Leaflet 內建 retina 佔位，高分屏自動抓 @2x。`{s}` 子網域 Leaflet 預設就有，不需額外設定。

## 4. 驗收條件（給截圖者）

1. z16 主場景：主幹道白線可讀、街廓塊面可辨，marker pill 對比仍明顯贏瓦片
2. 瓦片無任何地名文字（nolabels）
3. heat vignette（紅暈）疊上瓦片後不糊——紅光與灰底分離度比 Esri 更好（CARTO 更黑）
4. HUD 頂部漸層與新瓦片銜接無斷層

## 5. 追加價值：0.5.0 日夜迴圈的掛點

瓦片換成 CARTO 後，**日夜只要對 `.leaflet-tile-pane` 上 CSS filter class**：

```css
body.night .leaflet-tile-pane { filter: brightness(0.75) saturate(1.2) hue-rotate(200deg) 0.3; }  /* 數值屆時調 */
body.day   .leaflet-tile-pane { filter: brightness(1.05) saturate(0.9); }
```

一行 class 切換整個舞台的光，不用換瓦片源——這是 0.5.0 的免費地基，建議本輪一併把 class 掛點留好（不用做濾鏡本體）。

---

*依據：美術聖經 §1（L0 舞台規則）、櫻井 graphics.md 030（非判定物退後）、044（資源集中在效果高處）。*
