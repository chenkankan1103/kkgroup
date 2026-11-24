'use strict';
/* map.js — 街區色塊渲染（寫手 2；redesign-spec-final §9.1）
   資料源：S.blocks（BlockMap.generate 產出，簽名 §1）。渲染鐵律（簽名 §2）：
   上色一律問 Faction.sideOf()——渲染碼不讀 ctrl 正負，跳槽反轉零改動。
   綠 #4dff9d／藍 #5aa7ff，透明度八階 0.08→0.45；色塊永遠半透明疊在磚上
   （磚色不變）——勢力是「光」不是「漆」。中心數字 Cubic 11。 */

const BlockRender = (() => {
  const C_GREEN = 0x4dff9d, C_BLUE = 0x5aa7ff;
  const ALPHA = [0, 0.08, 0.1317, 0.1833, 0.235, 0.2867, 0.3383, 0.39, 0.45];  // 八階

  let layer = null;

  function alphaOf(ctrl) {
    const lv = Math.min(8, Math.floor(Math.abs(ctrl) / 12.5) + 1);  // ±12.5 一階，八階封頂
    return ALPHA[lv];
  }

  function init(world) {
    layer = new PIXI.Container();
    world.addChild(layer);
  }

  // 重畫整層（開機＋ctrl 變動時呼叫——色塊流動）；磚層獨立（僅首鋪）
  function render() {
    if (!layer) return;
    layer.removeChildren();
    for (const b of S.blocks) {
      const side = Faction.sideOf(S, b);              // ← 上色唯一訊號（簽名 §2 鐵律）
      const myCol = S.faction === 'park' ? C_GREEN : C_BLUE;
      const col = side === 'mine' ? myCol : (myCol === C_GREEN ? C_BLUE : C_GREEN);
      const a = alphaOf(b.ctrl);                      // 強度吃 |ctrl|（八階，訊號不碰正負）
      const g = new PIXI.Graphics();
      const pts = b.polygon.flat();
      if (a > 0) {
        g.poly(pts);
        g.fill({ color: col, alpha: a });
      }
      g.poly(pts);
      g.stroke({ width: 1, color: 0xffffff, alpha: 0.05 });   // 邊界極淡描邊（turf 慣例）
      // 定色街區：描邊轉亮（定色加成的可視訊號）
      if (b.locked) g.stroke({ width: 2, color: col, alpha: 0.35 });
      layer.addChild(g);
      // 中心數字：控制度（Cubic 11；字色跟陣營色，強度低時暗灰）
      const t = new PIXI.Text({
        text: String(Math.round(b.ctrl)),
        style: {
          fontFamily: '"Cubic 11", monospace',
          fontSize: 13, fill: a > 0 ? col : 0x5a6580,
          dropShadow: { blur: 2, distance: 0, color: 0x0b0e14, alpha: 0.8 },
        },
      });
      t.anchor.set(0.5);
      t.position.set(b.center[0], b.center[1]);
      layer.addChild(t);
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

/* ===== 據點標記（v0.2.0 切片：小屋圖示，金框——據點內部視角 B10 後替換） ===== */
const BaseRender = (() => {
  let layer = null;

  function init(world) {
    layer = new PIXI.Container();
    world.addChild(layer);
  }

  function render() {
    if (!layer) return;
    layer.removeChildren();
    for (const base of S.bases || []) {
      const c = S.blocks[base.blk].center;
      const g = new PIXI.Graphics();
      g.poly([c[0] - 14, c[1] - 26, c[0], c[1] - 38, c[0] + 14, c[1] - 26])
        .fill({ color: 0x2a3348 })
        .stroke({ width: 1, color: 0xffe14d, alpha: 0.5 });
      g.rect(c[0] - 12, c[1] - 26, 24, 18)
        .fill({ color: 0x1a2130, alpha: 0.95 })
        .stroke({ width: 2, color: 0xffe14d, alpha: 0.9 });
      layer.addChild(g);
    }
  }

  return { init, render };
})();
