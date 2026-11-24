'use strict';
/* walk.js — 斜俯視走動（redesign-spec-final §3，寫手 2）
   相機跟隨主角（lerp 0.15）＋ WASD/方向鍵八向 ＋ 世界邊界碰撞
   ＋走路動畫（Kenney 人物 sprite 圖朝上，rotation 對準移動向；雙幀擺動以
   bob＋wobble 程式化替代——素材無走路幀，視覺等效，QA 不對再調）。
   45 度感：建築 y-offset 疊層（B10）＋陰影 135°（v0.2）；本版角色平貼。 */

const Walk = (() => {
  const SPEED = 160;          // 世界 px/s（2× zoom 下螢幕 320——穿一街區約 2 秒）
  const LERP = 0.15;          // 相機跟隨（spec §3）
  const MAN_H = 32;           // §9.1 角色 32px 高
  const SRC_H = 43;           // Kenney manBrown_stand 原生高
  const KEYMAP = {
    KeyW: 'up', ArrowUp: 'up', KeyS: 'down', ArrowDown: 'down',
    KeyA: 'left', ArrowLeft: 'left', KeyD: 'right', ArrowRight: 'right',
  };

  const keys = {};
  let app = null, world = null, hero = null, texStand = null;
  let cam = { x: 0, y: 0 };
  let t = 0;                  // 動畫時鐘
  let moving = false;
  let obstacles = null;       // BlockMap.generate 產出（簽名 §1；格寬 32px，1=牆/樹）

  function init(application, worldContainer, manTex) {
    app = application;
    world = worldContainer;
    texStand = manTex;
    hero = new PIXI.Sprite(manTex);
    hero.anchor.set(0.5, 0.62);          // 腳感：中心偏下
    const s = MAN_H / SRC_H;
    hero.scale.set(s);
    hero.position.set(BlockMap.W / 2, BlockMap.H / 2);
    world.addChild(hero);
    document.addEventListener('keydown', (e) => {
      if (KEYMAP[e.code]) { keys[KEYMAP[e.code]] = true; e.preventDefault(); }
    });
    document.addEventListener('keyup', (e) => { if (KEYMAP[e.code]) keys[KEYMAP[e.code]] = false; });
    window.addEventListener('blur', () => { for (const k in keys) keys[k] = false; });  // 切窗不粘鍵
    // 相機初始就在主角身上（免開場飄移）
    cam.x = camTargetX(); cam.y = camTargetY();
    applyCam();
  }

  function camTargetX() {
    return clamp(app.screen.width / 2 - hero.position.x * world.scale.x, app.screen.width - BlockMap.W * world.scale.x, 0);
  }
  function camTargetY() {
    return clamp(app.screen.height / 2 - hero.position.y * world.scale.y, app.screen.height - BlockMap.H * world.scale.y, 0);
  }
  function clamp(v, min, max) { return v < min ? min : v > max ? max : v; }

  function applyCam() {
    world.position.set(cam.x, cam.y);
  }

  // 障礙格碰撞（簽名 §1 obstacles）：目標格=1 → 該軸移動取消（軸分離滑牆）
  function blocked(x, y) {
    if (!obstacles) return false;
    const gx = Math.floor(x / BlockMap.TILE), gy = Math.floor(y / BlockMap.TILE);
    const gw = Math.ceil(BlockMap.W / BlockMap.TILE);
    if (gx < 0 || gy < 0 || gx >= gw || gy >= Math.ceil(BlockMap.H / BlockMap.TILE)) return true;
    return obstacles[gy * gw + gx] === 1;
  }

  function setObstacles(arr) { obstacles = arr || null; }

  function tick(dtSec) {
    if (!app) return;
    t += dtSec;
    // 八向移動（同時按＝斜走，向量和歸一）
    let dx = (keys.right ? 1 : 0) - (keys.left ? 1 : 0);
    let dy = (keys.down ? 1 : 0) - (keys.up ? 1 : 0);
    moving = !!(dx || dy);
    if (moving) {
      const d = Math.hypot(dx, dy);
      dx /= d; dy /= d;
      const nx = hero.position.x + dx * SPEED * dtSec;
      const ny = hero.position.y + dy * SPEED * dtSec;
      // 軸分離：撞格只擋該軸（可沿牆滑）
      if (!blocked(nx, hero.position.y)) hero.position.x = nx;
      if (!blocked(hero.position.x, ny)) hero.position.y = ny;
      // 世界邊界（街區多邊形內部全可走——spec §3）
      hero.position.x = clamp(hero.position.x, 12, BlockMap.W - 12);
      hero.position.y = clamp(hero.position.y, 14, BlockMap.H - 14);
      // 圖朝上 → rotation = 移動角 + 90°
      hero.rotation = Math.atan2(dy, dx) + Math.PI / 2;
    }
    // 走路動畫：bob（±1px）＋ wobble（±0.05rad）；靜止歸位
    if (moving) {
      hero.pivot.y = Math.sin(t * 14) * 1.6;
      hero.rotation += Math.sin(t * 7) * 0.05;
    } else {
      hero.pivot.y = 0;
    }
    // 相機跟隨 lerp 0.15（相機追 hero 的目標位移）
    cam.x += (camTargetX() - cam.x) * LERP;
    cam.y += (camTargetY() - cam.y) * LERP;
    applyCam();
  }

  function pos() { return hero ? { x: hero.position.x, y: hero.position.y } : { x: 0, y: 0 }; }

  return { init, tick, pos, setObstacles };
})();
