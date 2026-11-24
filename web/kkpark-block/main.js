'use strict';
/* main.js — boot＋主迴圈（寫手 A＝四段日迴圈骨架接縫 §11-13；寫手 2＝Pixi 初始化）
   日迴圈四段（spec §1）：①開機收帳 ②街上時光（主玩法）③處理帳面 ④睡覺結算
   —— A 的段落狀態機落地前，本檔先常駐「街上時光」段（垂直切片 D1-3）。 */

(async () => {
  // 像素 perfect：全域 NEAREST（§9.1）——texture 縮放不吃模糊
  PIXI.TextureSource.defaultOptions.scaleMode = 'nearest';

  const app = new PIXI.Application();
  await app.init({ background: 0x0b0e14, resizeTo: window, antialias: false });
  document.body.appendChild(app.canvas);

  // Cubic 11 是 web font——canvas Text 用前先等字體就緒（否則中心數字掉 fallback）
  try { await document.fonts.load('13px "Cubic 11"'); } catch (e) {}

  // 素材：Kenney Topdown Shooter（CC0，web/kkpark-map/assets/kenney-topdown/）——跨目錄引用不複製
  const A = 'web/kkpark-block/../kkpark-map/assets/kenney-topdown/PNG/';
  const ASSETS = {
    tile: A + 'Tiles/tile_01.png',
    man: A + 'Man Brown/manBrown_stand.png',
  };
  const tex = await PIXI.Assets.load(ASSETS);

  // 世界容器：相機 zoom 固定 2×（§9.1）
  const world = new PIXI.Container();
  world.scale.set(2);
  app.stage.addChild(world);

  GroundRender.init(world, tex.tile);
  BlockRender.init(world);
  BlockRender.render();
  Walk.init(app, world, tex.man);

  // HUD：進場亮出（星星三顆＝B11 掛點）
  document.getElementById('hud').classList.remove('hidden');

  // ===== 主迴圈 =====
  // A 的日迴圈接縫（①收帳／②街上／③帳面／④睡覺）在此排程；現階段常駐街上。
  let last = performance.now();
  app.ticker.add(() => {
    const now = performance.now();
    const dtSec = Math.min(0.05, (now - last) / 1000);   // 切窗回來不吃大步（防瞬移）
    last = now;
    Walk.tick(dtSec);
  });
})();
