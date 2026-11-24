'use strict';
/* map.js — 街區棋王地圖：A=Voronoi 街區生成（§2.1，寫手 A）；B=街區色塊渲染（§9.1，寫手 2）
   現階段：B 渲染層照 mock 街區資料先跑（垂直切片 D1-3），A 的生成器落地後整段替換。
   視覺基準：turf.html A 模式——色塊深淺＋中心數字；色塊是「光」不是「漆」（疊磚不蓋磚）。 */

/* ===== 邏輯層（寫手 A）：Voronoi 街區生成＋seed =====
   契約（spec §2.1）：每街區 { id, polygon:[[x,y]...], ctrl:-100..100, type:'park'|'police'|'neutral', yieldRate, gear }
   生成規則：12–20 種子（Poisson disk 最小間距）→ jitter 不規則邊 → Chaikin 平滑一次。
   seed 固定存檔（同一存檔永遠同一張圖）。
   —— A 未落地，下方 MOCK_BLOCKS 佔位（形狀照契約），簽名到了直接換 BlockMap 來源。 */
const BlockMap = (() => {
  // 世界尺寸（像素；磚 32px，地圖 2.5–3 屏——spec §3）
  const W = 1440, H = 960;
  const TILE = 32;

  // mock：8 街區（切片範圍 8 街區小圖）——不規則多邊形手排，ctrl 涵蓋八階樣本
  const MOCK_BLOCKS = [
    { id: 'b1', type: 'park',    ctrl: 85,  polygon: [[30, 40], [300, 25], [360, 200], [330, 400], [120, 430], [20, 260]] },
    { id: 'b2', type: 'park',    ctrl: 40,  polygon: [[380, 30], [640, 45], [700, 240], [620, 420], [390, 400], [370, 220]] },
    { id: 'b3', type: 'neutral', ctrl: 12,  polygon: [[30, 460], [330, 440], [380, 620], [350, 900], [120, 930], [25, 700]] },
    { id: 'b4', type: 'park',    ctrl: -5,  polygon: [[400, 440], [660, 430], [710, 640], [640, 910], [400, 920], [385, 640]] },
    { id: 'b5', type: 'police',  ctrl: -30, polygon: [[740, 40], [1020, 30], [1080, 220], [1040, 430], [760, 420], [730, 230]] },
    { id: 'b6', type: 'police',  ctrl: -60, polygon: [[740, 450], [1060, 440], [1110, 650], [1050, 920], [750, 910], [725, 660]] },
    { id: 'b7', type: 'neutral', ctrl: 25,  polygon: [[1110, 30], [1400, 45], [1420, 240], [1380, 420], [1120, 430], [1095, 220]] },
    { id: 'b8', type: 'neutral', ctrl: -95, polygon: [[1130, 450], [1410, 460], [1425, 660], [1390, 920], [1140, 910], [1108, 650]] },
  ];

  let blocks = null;
  function get() {
    if (!blocks) blocks = MOCK_BLOCKS;
    return blocks;
  }
  // 多邊形質心（面積加權，頂點數不均也能取中心）
  function centroid(poly) {
    let a = 0, cx = 0, cy = 0;
    for (let i = 0; i < poly.length; i++) {
      const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length];
      const cr = x1 * y2 - x2 * y1;
      a += cr; cx += (x1 + x2) * cr; cy += (y1 + y2) * cr;
    }
    a /= 2;
    return a ? { x: cx / (6 * a), y: cy / (6 * a) } : { x: poly[0][0], y: poly[0][1] };
  }
  return { W, H, TILE, get, centroid };
})();

/* ===== 表現層（寫手 2）：街區色塊渲染（§9.1） =====
   綠 #4dff9d／藍 #5aa7ff，透明度八階 0.08→0.45（=控制度八檔）；
   色塊永遠半透明疊在磚上（磚色不變）——勢力是「光」不是「漆」；
   中心數字 Cubic 11。 */
const BlockRender = (() => {
  const C_GREEN = 0x4dff9d, C_BLUE = 0x5aa7ff;
  // 八階透明度階梯（0.08 → 0.45）
  const ALPHA = [0, 0.08, 0.1317, 0.1833, 0.235, 0.2867, 0.3383, 0.39, 0.45];

  let layer = null;
  const texts = [];

  function alphaOf(ctrl) {
    const lv = Math.min(8, Math.floor(Math.abs(ctrl) / 12.5) + 1);  // ±12.5 一階，八階封頂
    return ALPHA[lv];
  }

  function init(world) {
    layer = new PIXI.Container();
    world.addChild(layer);
  }

  // 重畫整層（ctrl 變動時呼叫——色塊流動）；磚層獨立於此（僅首鋪）
  function render() {
    if (!layer) return;
    layer.removeChildren();
    texts.length = 0;
    for (const b of BlockMap.get()) {
      const g = new PIXI.Graphics();
      const pos = b.ctrl > 0, a = alphaOf(b.ctrl);
      if (a > 0) {
        g.poly(b.polygon.map((p) => [p[0], p[1]]).flat());
        g.fill({ color: pos ? C_GREEN : C_BLUE, alpha: a });
      }
      g.poly(b.polygon.map((p) => [p[0], p[1]]).flat());
      g.stroke({ width: 1, color: 0xffffff, alpha: 0.05 });   // 邊界極淡描邊（turf 慣例）
      layer.addChild(g);
      // 中心數字：控制度（Cubic 11；字色跟陣營，0 = 暗灰）
      const c = BlockMap.centroid(b.polygon);
      const lv = Math.min(8, Math.floor(Math.abs(b.ctrl) / 12.5) + 1);
      const t = new PIXI.Text({
        text: String(Math.round(b.ctrl)),
        style: {
          fontFamily: '"Cubic 11", monospace',
          fontSize: 13, fill: a > 0 ? (pos ? 0x9dffcb : 0x9ecbff) : 0x5a6580,
          dropShadow: { blur: 2, distance: 0, color: 0x0b0e14, alpha: 0.8 },
        },
      });
      t.anchor.set(0.5);
      t.position.set(c.x, c.y);
      layer.addChild(t);
      texts.push(t);
    }
  }

  return { init, render };
})();

/* ===== 磚層（底）：tile_01 草地滿鋪（64px 原生 → scale 0.5 = 32px，NEAREST 像素） ===== */
const GroundRender = (() => {
  function init(world, tileTex) {
    const g = new PIXI.TilingSprite({ texture: tileTex, width: BlockMap.W, height: BlockMap.H });
    g.tileScale.set(BlockMap.TILE / 64);   // 64 原生 → 32 格
    world.addChildAt(g, 0);
  }
  return { init };
})();
