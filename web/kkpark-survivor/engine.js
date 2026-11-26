'use strict';
/* engine.js — canvas 渲染＋零配置池＋FPS 自適應降級（97KB 海底 demo 手法） */

const Engine = (() => {
  let cv = null, ctx = null, W = 0, H = 0, dpr = 1;
  let Q = 2;                       // 2 全效 / 1 減特效 / 0 減粒子
  let fpsAcc = 0, fpsN = 0;
  const tex = {};                  // 地紋理（AI 生成，加載失敗就退回網格）

  // 通用零配置池：物件重用，永不 splice/new
  function makePool(create, reset) {
    const free = [];
    return {
      get() { const o = free.length ? free.pop() : create(); reset(o); return o; },
      put(o) { free.push(o); },
    };
  }

  // 幀率取樣（1 秒窗口）：<50 降級、>58 回升
  function fpsTick(dt) {
    fpsAcc += dt; fpsN++;
    if (fpsAcc < 1) return;
    const fps = fpsN / fpsAcc; fpsAcc = 0; fpsN = 0;
    if (fps < 50 && Q > 0) Q--;
    else if (fps > 58 && Q < 2) Q++;
  }

  function init(canvas) {
    cv = canvas;
    ctx = cv.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
  }
  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
  }

  // 每幀開頭：世界座標跟著玩家（鏡頭），transform 一次
  function begin(cam) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#101418';
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.translate(W / 2 - cam.x, H / 2 - cam.y);
  }
  function end() { ctx.restore(); }

  // 地板網格（程序化，無圖片）：只畫可視範圍
  function drawGrid(cam) {
    const g = 96;
    const x0 = Math.floor((cam.x - W / 2) / g) * g, y0 = Math.floor((cam.y - H / 2) / g) * g;
    ctx.strokeStyle = 'rgba(255,255,255,0.045)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    const x1 = cam.x + W / 2 + g, y1 = cam.y + H / 2 + g;
    for (let x = x0; x < x1; x += g) { ctx.moveTo(x, y0); ctx.lineTo(x, y1); }
    for (let y = y0; y < y1; y += g) { ctx.moveTo(x0, y); ctx.lineTo(x1, y); }
    ctx.stroke();
  }

  // ===== 地面紋理（AI 生成，加載失敗自動退回網格）=====
  function loadTexture(url, onReady) {
    const im = new Image();
    im.onload = () => { onReady(im); };
    im.onerror = () => { onReady(null); };
    im.src = url;
  }
  function loadTextures(onDone) {
    let left = 2;
    const fin = () => { if (--left <= 0) onDone(); };
    loadTexture('assets/ground.png', (im) => { tex.ground = im; fin(); });
    loadTexture('assets/core.png', (im) => { tex.core = im; fin(); });
  }

  // 畫地面：主紋理平鋪＋核心圈內疊核心區紋理；沒紋理就畫網格
  // 注意：begin() 已把 transform 設成「世界座標」（translate 到鏡頭），所以這裡直接用世界座標畫
  const TEX_SCALE = 2;               // 1 張 256px 紋理＝世界 512px（不然地面太密）
  function drawGround(cam, coreR) {
    if (!tex.ground) { drawGrid(cam); return; }
    const x0 = cam.x - W / 2 - 64, y0 = cam.y - H / 2 - 64;
    const w = W + 128, h = H + 128;
    // 主地面平鋪（pattern 跟著世界座標走，放大 TEX_SCALE 倍讓地面有尺度感）
    ctx.save();
    ctx.scale(TEX_SCALE, TEX_SCALE);
    ctx.fillStyle = ctx.createPattern(tex.ground, 'repeat');
    ctx.fillRect(x0 / TEX_SCALE, y0 / TEX_SCALE, w / TEX_SCALE, h / TEX_SCALE);
    ctx.restore();
    // 核心區：疊核心廣場紋理（圓形遮罩）
    if (tex.core && coreR) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(cam.x, cam.y, coreR, 0, Math.PI * 2);
      ctx.clip();
      ctx.scale(TEX_SCALE, TEX_SCALE);
      ctx.fillStyle = ctx.createPattern(tex.core, 'repeat');
      ctx.fillRect(x0 / TEX_SCALE, y0 / TEX_SCALE, w / TEX_SCALE, h / TEX_SCALE);
      ctx.restore();
    }
  }

  return { init, begin, end, drawGrid, drawGround, loadTextures, fpsTick, makePool,
    get ctx() { return ctx; }, get W() { return W; }, get H() { return H; }, get Q() { return Q; } };
})();
